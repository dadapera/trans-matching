from __future__ import annotations

import gc
import statistics
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader

ProgressCallback = Callable[[int, int, str], None]

# Keep OCR lean on Render starter (512MB). Higher DPI blows memory with ONNX + pixmap.
_DEFAULT_OCR_DPI = 110


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
    from rapidocr_onnxruntime import RapidOCR

    # Angle classifier adds another ONNX model; skip to reduce peak RAM.
    try:
        ocr = RapidOCR(params={"Global.use_angle_cls": False})
    except TypeError:
        ocr = RapidOCR()
    doc = fitz.open(str(path))
    lines: list[str] = []
    total = len(doc)

    try:
        for index in range(total):
            page_num = index + 1
            if on_progress is not None:
                on_progress(index, total, f"OCR carta: pagina {page_num}/{total}")

            page = doc.load_page(index)
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            try:
                image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width, pixmap.n
                )
                # Copy so RapidOCR does not keep a view into the pixmap buffer.
                try:
                    result, _elapsed = ocr(image.copy(), use_cls=False)
                except TypeError:
                    result, _elapsed = ocr(image.copy())
            finally:
                del pixmap

            if result:
                lines.extend(_group_ocr_rows(result))

            if on_progress is not None:
                on_progress(page_num, total, f"OCR carta: pagina {page_num}/{total}")

            # Peak RAM is model + one page; force reclaim between pages.
            gc.collect()
    finally:
        doc.close()
        del ocr
        gc.collect()

    return lines


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
