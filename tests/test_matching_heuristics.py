from decimal import Decimal

from trans_matching.agent.pool import GestionalePool
from trans_matching.agent.sum_check import find_amount_combinations
from trans_matching.agent.tools import apply_confidence_gate
from trans_matching.models import Transaction
from trans_matching.parsers.amex import parse_amex_csv


def _txn(
    *,
    identificativo: str = "",
    date: str = "08/06/2026",
    amount: str = "100.00",
    description: str = "RYA RYANAIR ROSSI/MARIO",
) -> Transaction:
    return Transaction(
        identificativo=identificativo,
        date=date,
        amount=Decimal(amount),
        description=description,
        source="test",
    )


def test_amex_dates_are_parsed_as_month_day_year(tmp_path) -> None:
    path = tmp_path / "Amex.csv"
    path.write_text(
        'Data,Descrizione,Importo\n'
        '06/08/2026,EG*TRVL73443592561624   0269430760,""938,09""\n',
        encoding="utf-8",
    )

    [txn] = parse_amex_csv(path)

    assert txn.date == "08/06/2026"


def test_duplicate_gestionale_identifier_alone_is_ambiguous() -> None:
    first = _txn(identificativo="PRT 26 483", amount="842.00")
    second = _txn(identificativo="PRT 26 483", amount="1034.00")
    pool = GestionalePool([first, second])

    assert pool.find_by_identificativi(["PRT 26 483"]) == []
    assert pool.find_by_identificativi(
        ["PRT 26 483|08/06/2026|842.00|RYA RYANAIR ROSSI/MARIO"]
    ) == [first]


def test_confidence_gate_rejects_large_amount_delta() -> None:
    card = _txn(amount="354.72")
    gestionale = _txn(identificativo="BAW 2507 20", amount="200.42")
    pool = GestionalePool([gestionale])

    matched, resolved, confidence, reason = apply_confidence_gate(
        card=card,
        confidence="medio",
        identificativi=["BAW 2507 20"],
        alternatives=[],
        pool=pool,
        card_row_number=1,
    )

    assert matched is False
    assert resolved == []
    assert confidence == "basso"
    assert reason is not None and "scostamento importo" in reason


def test_check_sum_does_not_mix_unrelated_providers() -> None:
    pool = GestionalePool(
        [
            _txn(identificativo="AUT 1", amount="45.97", description="FB FLIXBUS A/B"),
            _txn(identificativo="BAW 1", amount="84.99", description="RYA RYANAIR C/D"),
            _txn(identificativo="WIZ 1", amount="48.04", description="WIZ WIZZ AIR E/F"),
        ]
    )

    combos = find_amount_combinations(
        pool,
        target_amount=Decimal("179.00"),
        card_date="08/06/2026",
        date_window_days=7,
        tolerance_pct=15,
    )

    assert combos == []


def test_expedia_gate_rejects_transport_rows() -> None:
    card = _txn(
        amount="78.61",
        description="EG*TRVL73466616161069   0269430760",
    )
    transport = _txn(
        identificativo="BF 2605270003 20",
        amount="78.60",
        description="TRE TRENITALIA ROSSI/MARIO",
    )
    pool = GestionalePool([transport])

    matched, resolved, confidence, reason = apply_confidence_gate(
        card=card,
        confidence="medio",
        identificativi=["BF 2605270003 20"],
        alternatives=[],
        pool=pool,
        card_row_number=1,
    )

    assert matched is False
    assert resolved == []
    assert confidence == "basso"
    assert reason is not None and "incoerente con Expedia" in reason
