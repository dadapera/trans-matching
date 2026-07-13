from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader


def extract_pdf_text(path: Path) -> str:
    """Estrae testo da PDF con text layer (pypdf)."""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def pdf_has_text_layer(path: Path) -> bool:
    return bool(extract_pdf_text(path).strip())


def extract_pdf_lines_ocr(path: Path, *, dpi: int = 180) -> list[str]:
    """OCR per PDF senza text layer (es. estratti Amex stampati in PDF)."""
    import fitz
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    doc = fitz.open(str(path))
    lines: list[str] = []

    for page in doc:
        pixmap = page.get_pixmap(dpi=dpi)
        result, _elapsed = ocr(pixmap.tobytes("png"))
        if not result:
            continue
        lines.extend(_group_ocr_rows(result))

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
