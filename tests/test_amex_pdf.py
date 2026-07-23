from decimal import Decimal
from pathlib import Path

from trans_matching.parsers.amex import (
    _extract_amex_statement_line,
    parse_amex_csv,
    parse_amex_file,
    parse_amex_pdf_lines,
    write_amex_csv,
)

FIXTURES = Path(__file__).parent / "fixtures"
OCR_LINES = FIXTURES / "amex_feb_ocr_lines.txt"
AMEX_CSV = FIXTURES / "amex_feb.csv"


def test_amex_statement_line_parses_dotted_dates() -> None:
    txn = _extract_amex_statement_line("09.02.26 09.02.26 EASYJET LUTON 118,97")

    assert txn is not None
    assert txn.date == "09/02/2026"
    assert txn.description == "EASYJET LUTON"
    assert txn.amount == Decimal("118.97")


def test_amex_statement_line_parses_concatenated_ocr_dates() -> None:
    txn = _extract_amex_statement_line("09.02.2610.02.26 TIMRINNOVOOFFERTAROMA 16,48")

    assert txn is not None
    assert txn.date == "09/02/2026"
    assert txn.amount == Decimal("16.48")


def test_amex_statement_line_skips_summary_rows() -> None:
    assert _extract_amex_statement_line(
        "26.02.26 26.02.26 ADDEBITO IN C/C SALVO BUON FINE 77.810,44 CR"
    ) is None
    assert _extract_amex_statement_line(
        "26.02.26 26.02.26 ADDEBITOINC/CSALVOBUONFINE 77.810,44"
    ) is None


def test_amex_statement_line_parses_lenient_ocr_layout() -> None:
    txn = _extract_amex_statement_line(
        "10.02.26 11.02.26 OMANAIR(S.A.O.C)WWW.ITALY 357,23"
    )

    assert txn is not None
    assert txn.date == "10/02/2026"
    assert txn.amount == Decimal("357.23")


def test_amex_statement_line_uses_euro_amount_when_fx_present() -> None:
    txn = _extract_amex_statement_line(
        "10.02.26 10.02.26 EASYJET LUTON 84.47 99,61"
    )

    assert txn is not None
    assert txn.amount == Decimal("99.61")


def test_amex_statement_line_fixes_corrupted_ocr_posting_date() -> None:
    txn = _extract_amex_statement_line(
        "04.03.26 505.03.26 RYANAIR LTD AIRLINE DUBLIN 8.287,00"
    )

    assert txn is not None
    assert txn.date == "04/03/2026"
    assert txn.amount == Decimal("8287.00")


def test_parse_amex_pdf_lines_puts_details_in_description() -> None:
    txns = parse_amex_pdf_lines(
        [
            "09.02.26 09.02.26 EASYJET LUTON 118,97",
            "ITINERARIO:DA:NAPLES CAPODICHINO",
            "A: MILAN MALPENSA APT VETTORE:U2 CLASSE: Y",
            "NUM.BIGLIETTO KC38J4N NOME PASSEGGERO VALERIO RUSSO",
            "09.02.26 09.02.26 EG*TRVL733696860362040269430760 398,70",
        ]
    )

    assert len(txns) == 2
    easyjet, expedia = txns
    assert easyjet.amount == Decimal("118.97")
    assert easyjet.description.startswith("EASYJET LUTON")
    assert "ITINERARIO" in easyjet.description
    assert "VALERIORUSSO" in easyjet.description.replace(" ", "")
    assert expedia.description == "EG*TRVL73369686036204 0269430760"


def test_parse_amex_pdf_lines_merges_cr_and_amount_on_following_lines() -> None:
    txns = parse_amex_pdf_lines(
        [
            "06.03.26 06.03.26 EG*TRVL733778234420640269430760 901,47",
            "CR",
            "13.02.26 13.02.26 EG*TRVL733731584782840269430760",
            "85,89",
        ]
    )

    assert [txn.amount for txn in txns] == [Decimal("-901.47"), Decimal("85.89")]


def test_write_amex_csv_uses_data_descrizione_importo(tmp_path: Path) -> None:
    txns = parse_amex_pdf_lines(
        [
            "09.02.26 09.02.26 EASYJET LUTON 118,97",
            "ITINERARIO:DA:NAPLES CAPODICHINO",
            "NUM.BIGLIETTO KC38J4N NOME PASSEGGERO VALERIO RUSSO",
        ]
    )
    path = tmp_path / "amex.csv"
    write_amex_csv(path, txns)

    text = path.read_text(encoding="utf-8")
    assert text.startswith("Data,Descrizione,Importo\n")
    [parsed] = parse_amex_csv(path)
    assert parsed.date == "09/02/2026"
    assert parsed.amount == Decimal("118.97")
    assert "ITINERARIO" in parsed.description
    assert "VALERIORUSSO" in parsed.description.replace(" ", "")


def test_parse_amex_file_dispatches_csv(tmp_path: Path) -> None:
    path = tmp_path / "carta.csv"
    path.write_text(
        'Data,Descrizione,Importo\n'
        '06/08/2026,EG*TRVL73443592561624   0269430760,""938,09""\n',
        encoding="utf-8",
    )

    [txn] = parse_amex_file(path)

    assert txn.date == "08/06/2026"
    assert txn.amount == Decimal("938.09")


def _csv_comparable(txns: list) -> list:
    return [
        txn
        for txn in txns
        if "ADDEBITO IN C/C" not in txn.description.upper()
    ]


def test_amex_pdf_ocr_fixture_matches_csv_by_date_and_amount() -> None:
    """PDF OCR extraction must cover every non-summary CSV row (date + amount)."""
    assert OCR_LINES.exists(), "missing OCR fixture"
    assert AMEX_CSV.exists(), "missing CSV fixture"

    csv_txns = _csv_comparable(parse_amex_csv(AMEX_CSV))
    pdf_txns = parse_amex_pdf_lines(OCR_LINES.read_text(encoding="utf-8").splitlines())

    from collections import Counter

    csv_keys = Counter((txn.date, txn.amount) for txn in csv_txns)
    pdf_keys = Counter((txn.date, txn.amount) for txn in pdf_txns)

    missing = []
    for key, count in csv_keys.items():
        if pdf_keys.get(key, 0) < count:
            sample = next(txn for txn in csv_txns if (txn.date, txn.amount) == key)
            missing.append((key, count - pdf_keys.get(key, 0), sample.description))

    assert not missing, f"CSV rows missing from PDF parse: {missing}"
    assert len(pdf_txns) >= len(csv_txns)


def test_amex_pdf_ocr_fixture_extracts_rich_airline_details() -> None:
    pdf_txns = parse_amex_pdf_lines(OCR_LINES.read_text(encoding="utf-8").splitlines())
    detailed = [
        txn
        for txn in pdf_txns
        if "ITINERARIO" in txn.description.upper()
        and "PASSEGGERO" in txn.description.upper()
    ]

    assert len(detailed) >= 20
    sample = next(txn for txn in detailed if txn.amount == Decimal("118.97"))
    assert sample.description.startswith("EASYJET LUTON")
    assert "NAPLES" in sample.description.upper() or "NAPOLI" in sample.description.upper()
