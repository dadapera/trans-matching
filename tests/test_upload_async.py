from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from trans_matching.models import Transaction
from trans_matching.web.upload import parse_carta_and_gestionale


def test_parse_carta_and_gestionale_ok(tmp_path: Path) -> None:
    carta = tmp_path / "amex.csv"
    gestionale = tmp_path / "gest.pdf"
    carta.write_bytes(b"x")
    gestionale.write_bytes(b"y")

    card = Transaction(
        date="01/02/2026",
        description="card",
        amount=Decimal("1"),
        source="amex",
    )
    gest = Transaction(
        date="01/02/2026",
        description="gest",
        amount=Decimal("1"),
        source="gestionale",
    )

    events: list[tuple[int, int, str]] = []

    with (
        patch("trans_matching.web.upload.parse_amex_file", return_value=[card]),
        patch("trans_matching.web.upload.parse_gestionale_pdf", return_value=[gest]),
    ):
        cards, gests = parse_carta_and_gestionale(
            carta,
            gestionale,
            on_progress=lambda cur, tot, msg: events.append((cur, tot, msg)),
        )

    assert len(cards) == 1
    assert len(gests) == 1
    assert events
    assert events[-1][0] == events[-1][1]
    assert events[-1][1] == 2
