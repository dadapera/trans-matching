from decimal import Decimal

from trans_matching.agent.pool import GestionalePool
from trans_matching.agent.router import classify_card_transaction
from trans_matching.agent.sum_check import find_amount_combinations, find_document_amount_groups
from trans_matching.agent.tools import AGENT_TOOLS, apply_confidence_gate
from trans_matching.matchers.gestionale_text import hotel_matches
from trans_matching.models import Transaction
from trans_matching.parsers.amex import parse_amex_csv
from trans_matching.verifiers.msc_parser import parse_msc_subject
from trans_matching.verifiers.expedia_trvl import search_expedia_emails


def _txn(
    *,
    identificativo: str = "",
    date: str = "08/06/2026",
    amount: str = "100.00",
    description: str = "RYA RYANAIR ROSSI/MARIO",
    raw: str = "",
) -> Transaction:
    return Transaction(
        identificativo=identificativo,
        date=date,
        amount=Decimal(amount),
        description=description,
        source="test",
        raw=raw,
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


def test_check_sum_uses_row_signature_when_identifier_missing() -> None:
    rows = [
        _txn(
            identificativo="",
            date="05/03/2026",
            amount="250.59",
            description="RYA RYANAIR ROSSI/MARIO",
        ),
        _txn(
            identificativo="",
            date="05/03/2026",
            amount="250.59",
            description="RYA RYANAIR BIANCHI/LUCA",
        ),
    ]
    pool = GestionalePool(rows + [_txn(identificativo="OTHER 1", amount="1.00")])

    combos = find_amount_combinations(
        pool,
        target_amount=Decimal("501.18"),
        card_date="05/03/2026",
        card_description="RYANAIR LTD AIRLINE DUBLIN",
        date_window_days=7,
        tolerance_pct=1,
        max_group_size=2,
    )

    assert combos
    assert all(ref.strip() for combo in combos for ref in combo["identificativi"])


def test_document_group_sum_matches_same_siap_document() -> None:
    pool = GestionalePool(
        [
            _txn(
                identificativo="PRT 26 147",
                date="05/03/2026",
                amount="584.00",
                description="EXPEDIA INC. ROSSI/MARIO",
            ),
            _txn(
                identificativo="PRT 26 147",
                date="05/03/2026",
                amount="245.00",
                description="EXPEDIA INC. ROSSI/MARIO",
            ),
            _txn(
                identificativo="PRT 26 148",
                date="05/03/2026",
                amount="829.00",
                description="EXPEDIA INC. BIANCHI/LUCA",
            ),
        ]
    )

    groups = find_document_amount_groups(
        pool,
        target_amount=Decimal("829.00"),
        card_date="05/03/2026",
        card_description="EG*TRVL123",
        date_window_days=7,
        tolerance_pct=1,
    )

    assert groups
    assert groups[0]["identificativo"] == "PRT 26 147"
    assert groups[0]["total"] == "829.00"
    assert all("|05/03/2026|" in ref for ref in groups[0]["identificativi"])


def test_siap_identificativo_uses_documento_and_codice_cliente() -> None:
    from trans_matching.parsers.gestionale import (
        _extract_gestionale_identificativo,
        extract_siap_low_cost,
        format_siap_match_label,
    )

    assert _extract_gestionale_identificativo(
        "BAW            2424 20 1 1   4361   2/07/26            712,90  RYA RYANAIR"
    ) == "BAW 2424"
    assert _extract_gestionale_identificativo(
        "PRT   26        171 20 1 1   4273  29/06/26            190,00  AUTO EUROPE"
    ) == "PRT 26 171"
    assert _extract_gestionale_identificativo(
        "998   26         85 20 1 2    113   9/02/26 EUR        440,00  612 HOTEL REMILIA"
    ) == "998 26 85"
    assert _extract_gestionale_identificativo(
        "BF       2602090001 20 1 2    113  10/02/26             76,00  TRE TRENITALIA"
    ) == "BF 2602090001"
    assert format_siap_match_label("LOW 8574") == "[LOW 8574]"
    assert (
        extract_siap_low_cost(
            "LOW            8569 20 1 2    113  16/02/26            118,97  "
            "EAS EASY JET        RUSSO/VALERIO                      0,00   9/02/26 N   KC38J4N"
        )
        == "KC38J4N"
    )
    assert (
        extract_siap_low_cost(
            "AUT            1485 20 1 2     83  11/05/26             25,98  "
            "FB  FLIXBUS ITALIA  DEMARCO/MAURO                      0,00   7/05/26 N   335 260 16"
        )
        == "33526016"
    )
    assert (
        extract_siap_low_cost(
            "BF       2602090001 20 1 2    113  10/02/26             76,00  TRE TRENITALIA"
        )
        == ""
    )


def test_amex_ticket_matches_siap_low_cost_in_pool() -> None:
    from trans_matching.parsers.amex import extract_amex_ticket_number

    card_desc = (
        "EASYJET LUTON ITINERARIO:DA: NAPLES CAPODICHINO "
        "NUM.BIGLIETTO KC38J4N NOME PASSEGGERO VALERIO RUSSO"
    )
    assert extract_amex_ticket_number(card_desc) == "KC38J4N"

    txn = _txn(
        identificativo="LOW 8569",
        amount="118.97",
        description="EAS EASY JET        RUSSO/VALERIO",
        raw=(
            "LOW            8569 20 1 2    113  16/02/26            118,97  "
            "EAS EASY JET        RUSSO/VALERIO                      0,00   9/02/26 N   KC38J4N"
        ),
    )
    pool = GestionalePool([txn])
    assert "LowCost:KC38J4N" in pool.format_row(txn)
    assert pool.find_by_low_cost("KC38J4N") == [txn]


def test_auto_europe_router_and_supplier_search() -> None:
    assert classify_card_transaction("WWW.AUTOEUROPE.DE MUNICH") == "auto_europe"
    assert classify_card_transaction("WWW.AUTOEUROPE.DEMUNICH UBICAZIONE") == "auto_europe"
    assert classify_card_transaction("RYANAIR LTD AIRLINE DUBLIN") == "generic"

    auto_row = _txn(
        identificativo="PRT 26 142",
        date="22/06/2026",
        amount="590.00",
        description="AUTO EUROPE DEU DI PAOLO SIMONE",
    )
    other_row = _txn(
        identificativo="LOW 8570",
        amount="217.66",
        description="RYA RYANAIR BECCHI/GABRIELE",
    )
    pool = GestionalePool([auto_row, other_row])
    hits = pool.search(
        text="AUTO EUROPE",
        amount=Decimal("587.95"),
        card_date="23/02/2026",
        date_window_days=30,
    )
    assert hits == [auto_row]


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


def test_expedia_hotel_match_accepts_siap_truncated_suffix() -> None:
    assert hotel_matches(
        "322 THE ORCHID JAMN DEANGELIS GIACINTO",
        "The Orchid Jamnagar",
    )


def test_expedia_guest_hotel_search_uses_extended_window() -> None:
    pool = GestionalePool(
        [
            _txn(
                identificativo="998 26 115",
                date="19/02/2026",
                amount="1344.00",
                description="322 THE ORCHID JAMN DEANGELIS GIACINTO",
            ),
            _txn(
                identificativo="998 26 135",
                date="06/03/2026",
                amount="-1344.00",
                description="322 THE ORCHID JAMN DEANGELIS GIACINTO",
            ),
        ]
    )

    strict = pool.search_by_guest_hotel(
        guest="GIACINTO DEANGELIS",
        hotel="The Orchid Jamnagar",
        amount=Decimal("-901.47"),
        card_date="06/03/2026",
        date_window_days=7,
    )
    extended = pool.search_by_guest_hotel(
        guest="GIACINTO DEANGELIS",
        hotel="The Orchid Jamnagar",
        amount=Decimal("-901.47"),
        card_date="06/03/2026",
        date_window_days=30,
    )

    assert [txn.identificativo for txn in strict] == ["998 26 135"]
    assert [txn.identificativo for txn in extended] == ["998 26 135", "998 26 115"]


def test_expedia_guest_hotel_search_uses_secondary_siap_date_from_raw() -> None:
    row = _txn(
        identificativo="998 26 156",
        date="08/04/2026",
        amount="180.00",
        description="094 IBIS STYLES BRI AZZI/STEFANO",
    )
    row = Transaction(
        date=row.date,
        description=row.description,
        amount=row.amount,
        source=row.source,
        raw=(
            "998 26 156 20 1 2 94 8/04/26 EUR 180,00 "
            "094 IBIS STYLES BRI AZZI/STEFANO 0,00 6/03/26"
        ),
        identificativo=row.identificativo,
    )
    pool = GestionalePool([row])

    matches = pool.search_by_guest_hotel(
        guest="STEFANO AZZI",
        hotel="ibis Styles Brindisi",
        amount=Decimal("180.00"),
        card_date="06/03/2026",
        date_window_days=30,
    )

    assert [txn.identificativo for txn in matches] == ["998 26 156"]


def test_expedia_email_search_falls_back_without_sender() -> None:
    class Reader:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def search_by_text(self, text, *, from_address=None, include_body=True):
            self.calls.append((text, from_address))
            if text == "733123" and from_address is None:
                return ["mail"]
            return []

    reader = Reader()

    result = search_expedia_emails(reader, "733123")

    assert result.emails == ["mail"]
    assert result.strategy == "any_sender_code"
    assert reader.calls == [
        ("733123", "noreply@expediataap.it"),
        ("EG*TRVL733123", "noreply@expediataap.it"),
        ("733123", None),
    ]


def test_expedia_context_is_not_exposed_as_agent_tool() -> None:
    tool_names = {tool.name for tool in AGENT_TOOLS}

    assert "search_expedia" not in tool_names
    assert "search_msc" not in tool_names
    assert {"compare_amount", "check_document_group_sum", "check_sum"} <= tool_names


def test_msc_subject_extracts_booking_code() -> None:
    parsed = parse_msc_subject("Numero di prenotazione per AIA150 70527640")

    assert parsed == {
        "booking_prefix": "AIA150",
        "booking_number": "70527640",
        "booking_code": "AIA150 70527640",
    }
