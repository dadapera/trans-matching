from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from trans_matching.parsers import pdf_text


def test_build_lean_ocr_passes_memory_safe_kwargs_and_unloads_cls() -> None:
    fake = MagicMock()
    fake.text_cls = MagicMock()
    fake.text_cls.infer = MagicMock()
    fake.text_cls.infer.session = object()

    with patch("rapidocr_onnxruntime.RapidOCR", return_value=fake) as ctor:
        ocr = pdf_text._build_lean_ocr()

    ctor.assert_called_once()
    kwargs = ctor.call_args.kwargs
    assert kwargs["use_cls"] is False
    assert kwargs["intra_op_num_threads"] == 1
    assert kwargs["inter_op_num_threads"] == 1
    assert kwargs["max_side_len"] == pdf_text._OCR_MAX_SIDE_LEN
    assert kwargs["det_limit_side_len"] == pdf_text._OCR_DET_LIMIT_SIDE_LEN
    assert kwargs["det_limit_type"] == "max"
    assert kwargs["rec_batch_num"] == 1
    assert ocr.text_cls is None


def test_extract_pdf_lines_ocr_defaults_to_subprocess(tmp_path: Path) -> None:
    pdf = tmp_path / "amex.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    progress_events: list[tuple[int, int, str]] = []

    def fake_popen(cmd, **kwargs):
        out_path = Path(cmd[5])
        progress_path = Path(cmd[6])
        progress_path.write_text(
            json.dumps({"current": 1, "total": 2, "message": "OCR carta: pagina 1/2"}),
            encoding="utf-8",
        )
        out_path.write_text(
            json.dumps({"ok": True, "lines": ["10.02.26 EG*TRVL 100,00"]}),
            encoding="utf-8",
        )

        class Proc:
            returncode = 0

            def poll(self):
                return 0

            def communicate(self, timeout=None):
                return ("", "")

            def kill(self):
                return None

            def wait(self, timeout=None):
                return 0

        return Proc()

    with patch("trans_matching.parsers.pdf_text.subprocess.Popen", side_effect=fake_popen):
        lines = pdf_text.extract_pdf_lines_ocr(
            pdf,
            on_progress=lambda c, t, m: progress_events.append((c, t, m)),
        )

    assert lines == ["10.02.26 EG*TRVL 100,00"]
    assert progress_events
    assert progress_events[0][0] == 1


def test_extract_pdf_lines_ocr_can_force_inprocess() -> None:
    with patch(
        "trans_matching.parsers.pdf_text._extract_pdf_lines_ocr_inprocess",
        return_value=["line-a"],
    ) as inprocess:
        with patch("trans_matching.parsers.pdf_text._extract_pdf_lines_ocr_subprocess") as sub:
            lines = pdf_text.extract_pdf_lines_ocr(Path("x.pdf"), in_subprocess=False)

    assert lines == ["line-a"]
    inprocess.assert_called_once()
    sub.assert_not_called()
