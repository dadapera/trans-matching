from __future__ import annotations

import gc
import statistics
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader

ProgressCallback = Callable[[int, int, str], None]

# Keep OCR lean on Render starter (512MB). Det tensors and pixmaps dominate peak RAM.
_DEFAULT_OCR_DPI = 96
_OCR_MAX_SIDE_LEN = 960
_OCR_DET_LIMIT_SIDE_LEN = 640


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
) -> list[str]:
    """OCR per PDF senza text layer (es. estratti Amex stampati in PDF)."""
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
