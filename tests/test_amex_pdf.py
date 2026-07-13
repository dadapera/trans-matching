from decimal import Decimal
from pathlib import Path

from trans_matching.parsers.amex import _extract_amex_statement_line, parse_amex_file


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
