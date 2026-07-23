from __future__ import annotations

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
