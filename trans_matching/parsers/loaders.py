from __future__ import annotations

from pathlib import Path

from trans_matching.parsers.amex import parse_amex_csv
from trans_matching.parsers.gestionale import ensure_gestionale_csv_files, parse_gestionale_csv


def load_card_transactions(carta_dir: Path) -> list:
    from trans_matching.models import Transaction

    transactions: list[Transaction] = []
    for csv_file in sorted(carta_dir.glob("*.csv")):
        transactions.extend(parse_amex_csv(csv_file))
    return transactions


def load_gestionale_transactions(gestionale_dir: Path) -> list:
    from trans_matching.models import Transaction

    transactions: list[Transaction] = []
    for csv_file in ensure_gestionale_csv_files(gestionale_dir):
        transactions.extend(parse_gestionale_csv(csv_file))
    return transactions
