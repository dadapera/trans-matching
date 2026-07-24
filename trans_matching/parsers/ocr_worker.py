"""OCR Amex in processo dedicato: esce e libera RSS nativa (ONNX/OpenCV)."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 4:
        print(
            "usage: python -m trans_matching.parsers.ocr_worker "
            "<pdf> <dpi> <out.json> <progress.json>",
            file=sys.stderr,
        )
        return 2

    pdf_path = Path(args[0])
    dpi = int(args[1])
    out_path = Path(args[2])
    progress_path = Path(args[3])

    # Ensure the worker never spawns another OCR subprocess.
    import os

    os.environ["OCR_IN_SUBPROCESS"] = "0"

    try:
        from trans_matching.parsers.pdf_text import _extract_pdf_lines_ocr_inprocess

        def on_progress(current: int, total: int, message: str) -> None:
            _write_json(
                progress_path,
                {"current": current, "total": total, "message": message},
            )

        lines = _extract_pdf_lines_ocr_inprocess(
            pdf_path,
            dpi=dpi,
            on_progress=on_progress,
        )
        _write_json(out_path, {"ok": True, "lines": lines})
        return 0
    except Exception as exc:
        _write_json(
            out_path,
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        )
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
