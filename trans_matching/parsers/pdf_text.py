from __future__ import annotations

import gc
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader

ProgressCallback = Callable[[int, int, str], None]

# Keep OCR lean on Render starter (512MB). Det tensors and pixmaps dominate peak RAM.
_DEFAULT_OCR_DPI = 96
_OCR_MAX_SIDE_LEN = 960
_OCR_DET_LIMIT_SIDE_LEN = 640
_OCR_PROGRESS_POLL_SECONDS = 0.25


def extract_pdf_text(path: Path) -> str:
    """Estrae testo da PDF con text layer (pypdf)."""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def pdf_has_text_layer(path: Path) -> bool:
    return bool(extract_pdf_text(path).strip())


def pdf_page_count(path: Path) -> int:
    import fitz

    doc = fitz.open(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def extract_pdf_lines_ocr(
    path: Path,
    *,
    dpi: int = _DEFAULT_OCR_DPI,
    on_progress: ProgressCallback | None = None,
    in_subprocess: bool | None = None,
) -> list[str]:
    """OCR per PDF senza text layer (es. estratti Amex stampati in PDF).

    Di default gira in un processo figlio: quando termina, onnxruntime/OpenCV
    liberano davvero la RSS del parent (necessario su Render 512MB).
    """
    use_subprocess = (
        _env_bool("OCR_IN_SUBPROCESS", True) if in_subprocess is None else in_subprocess
    )
    if use_subprocess:
        return _extract_pdf_lines_ocr_subprocess(path, dpi=dpi, on_progress=on_progress)
    return _extract_pdf_lines_ocr_inprocess(path, dpi=dpi, on_progress=on_progress)


def _extract_pdf_lines_ocr_subprocess(
    path: Path,
    *,
    dpi: int,
    on_progress: ProgressCallback | None,
) -> list[str]:
    path = path.resolve()
    with tempfile.TemporaryDirectory(prefix="amex-ocr-") as tmp:
        tmp_dir = Path(tmp)
        out_path = tmp_dir / "result.json"
        progress_path = tmp_dir / "progress.json"
        cmd = [
            sys.executable,
            "-m",
            "trans_matching.parsers.ocr_worker",
            str(path),
            str(dpi),
            str(out_path),
            str(progress_path),
        ]
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
        # Avoid re-entering subprocess from the worker.
        env["OCR_IN_SUBPROCESS"] = "0"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        last_key: tuple[int, int, str] | None = None
        try:
            while proc.poll() is None:
                last_key = _relay_progress(progress_path, on_progress, last_key)
                time.sleep(_OCR_PROGRESS_POLL_SECONDS)
            # Final progress flush after exit.
            _relay_progress(progress_path, on_progress, last_key)
            stdout, stderr = proc.communicate(timeout=30)
        except Exception:
            proc.kill()
            proc.wait(timeout=10)
            raise

        if proc.returncode != 0:
            detail = (stderr or stdout or "").strip() or f"exit {proc.returncode}"
            raise RuntimeError(f"OCR subprocess fallito: {detail}")

        if not out_path.exists():
            raise RuntimeError("OCR subprocess terminato senza file risultato")

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "OCR subprocess errore sconosciuto")
        lines = payload.get("lines")
        if not isinstance(lines, list):
            raise RuntimeError("OCR subprocess: risultato lines non valido")
        return [str(line) for line in lines]


def _relay_progress(
    progress_path: Path,
    on_progress: ProgressCallback | None,
    last_key: tuple[int, int, str] | None,
) -> tuple[int, int, str] | None:
    if on_progress is None or not progress_path.exists():
        return last_key
    try:
        data = json.loads(progress_path.read_text(encoding="utf-8"))
        current = int(data["current"])
        total = int(data["total"])
        message = str(data.get("message") or "")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return last_key
    key = (current, total, message)
    if key != last_key:
        on_progress(current, total, message)
    return key


def _extract_pdf_lines_ocr_inprocess(
    path: Path,
    *,
    dpi: int = _DEFAULT_OCR_DPI,
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    """OCR nel processo corrente (usato dal worker subprocess)."""
    import fitz
    import numpy as np

    try:
        import cv2

        cv2.setNumThreads(1)
    except Exception:
        pass

    ocr = _build_lean_ocr()
    doc = fitz.open(str(path))
    lines: list[str] = []
    total = len(doc)

    try:
        for index in range(total):
            page_num = index + 1
            if on_progress is not None:
                on_progress(index, total, f"OCR carta: pagina {page_num}/{total}")

            page = doc.load_page(index)
            # Grayscale pixmap is 1/3 the RAM of RGB before LoadImage expands to BGR.
            pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
            try:
                image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width
                ).copy()
            finally:
                del pixmap

            try:
                result, _elapsed = ocr(image, use_cls=False)
            except TypeError:
                result, _elapsed = ocr(image)
            finally:
                del image

            if result:
                lines.extend(_group_ocr_rows(result))

            if on_progress is not None:
                on_progress(page_num, total, f"OCR carta: pagina {page_num}/{total}")

            gc.collect()
    finally:
        doc.close()
        _release_ocr(ocr)
        gc.collect()

    return lines


def _build_lean_ocr():
    """Build RapidOCR with settings that keep peak RAM low on 512MB instances."""
    from rapidocr_onnxruntime import RapidOCR

    # RapidOCR takes flat kwargs (not nested YAML paths). The previous
    # params={"Global.use_angle_cls": False} was ignored.
    ocr = RapidOCR(
        use_cls=False,
        print_verbose=False,
        intra_op_num_threads=1,
        inter_op_num_threads=1,
        max_side_len=_OCR_MAX_SIDE_LEN,
        det_limit_side_len=_OCR_DET_LIMIT_SIDE_LEN,
        det_limit_type="max",
        rec_batch_num=1,
        cls_batch_num=1,
    )
    _unload_text_classifier(ocr)
    return ocr


def _unload_text_classifier(ocr) -> None:
    """RapidOCR always constructs TextClassifier; drop its ORT session when unused."""
    cls = getattr(ocr, "text_cls", None)
    if cls is None:
        return
    infer = getattr(cls, "infer", None)
    if infer is not None:
        session = getattr(infer, "session", None)
        if session is not None:
            del session
        cls.infer = None
        del infer
    ocr.text_cls = None
    del cls
    gc.collect()


def _release_ocr(ocr) -> None:
    det = getattr(ocr, "text_det", None)
    if det is not None:
        infer = getattr(det, "infer", None)
        if infer is not None:
            if getattr(infer, "session", None) is not None:
                del infer.session
            det.infer = None
        ocr.text_det = None

    _unload_text_classifier(ocr)

    rec = getattr(ocr, "text_rec", None)
    if rec is not None:
        # TextRecognizer stores OrtInferSession on .session
        ort = getattr(rec, "session", None)
        if ort is not None:
            if getattr(ort, "session", None) is not None:
                del ort.session
            rec.session = None
        ocr.text_rec = None

    del ocr


def _ocr_row_height(result: list) -> int:
    heights = [abs(box[2][1] - box[0][1]) for box, _text, _score in result]
    heights = [height for height in heights if height > 0]
    if not heights:
        return 12
    return max(8, int(statistics.median(heights) * 0.85))


def _group_ocr_rows(result: list, *, row_height: int | None = None) -> list[str]:
    bucket = row_height or _ocr_row_height(result)
    rows: dict[int, list[tuple[float, str]]] = defaultdict(list)
    for box, text, _score in result:
        cleaned = text.strip()
        if not cleaned:
            continue
        y_center = (box[0][1] + box[2][1]) / 2
        row_key = round(y_center / bucket) * bucket
        rows[row_key].append((box[0][0], cleaned))

    grouped: list[str] = []
    for _y in sorted(rows):
        parts = [text for _x, text in sorted(rows[_y])]
        grouped.append(" ".join(parts))
    return grouped


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
