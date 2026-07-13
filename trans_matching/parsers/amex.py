from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from trans_matching.models import Transaction
from trans_matching.parsers.common import format_italian_date, parse_italian_amount
from trans_matching.parsers.pdf_text import (
    extract_pdf_lines_ocr,
    extract_pdf_text,
    pdf_has_text_layer,
)

_AMEX_SKIP = re.compile(
    r"^(Saldo|Accrediti|Addebiti|Importo|TOTALE|Pagina|Data Chiusura|"
    r"Data Prossimo|Data operazione|Estratto Conto|AMERICAN|EXPRESS|"
    r"Titolare|Numero di Carta|Servizio Clienti|Totale nuove|"
    r"L'Importo|Contabilizzata|Descrizione dell'operazione|"
    r"ELISABETTA|LE MONDE|VIA DELLA|ITALY|americanexpress)",
    re.IGNORECASE,
)
_AMEX_DATE = r"\d{2}\.\d{2}\.\d{2,4}"
_AMEX_STATEMENT_LINE = re.compile(
    rf"^({_AMEX_DATE})\s+({_AMEX_DATE})\s+(.+?)\s+([\d.]+,\d{{2}})(?:\s+CR)?$"
)


def parse_amex_file(path: Path) -> list[Transaction]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_amex_csv(path)
    if suffix == ".pdf":
        return parse_amex_pdf(path)
    raise ValueError(f"Formato carta non supportato: {path.name}")


def parse_amex_pdf(path: Path) -> list[Transaction]:
    if pdf_has_text_layer(path):
        lines = extract_pdf_text(path).splitlines()
    else:
        lines = extract_pdf_lines_ocr(path)

    transactions: list[Transaction] = []
    for line in lines:
        txn = _extract_amex_statement_line(line)
        if txn:
            transactions.append(
                Transaction(
                    date=txn.date,
                    description=txn.description,
                    amount=txn.amount,
                    source=str(path),
                    raw=line.strip(),
                )
            )
    return transactions


def _extract_amex_statement_line(line: str) -> Transaction | None:
    line = re.sub(r"\s+", " ", line.strip())
    if not line or _AMEX_SKIP.search(line):
        return None

    parsed = _parse_amex_statement_fields(line)
    if not parsed:
        return None

    operation_date, description, amount_str, credit = parsed
    if _is_summary_description(description):
        return None

    amount = parse_italian_amount(amount_str)
    if credit:
        amount = -abs(amount)

    return Transaction(
        date=format_italian_date(operation_date),
        description=description.strip(),
        amount=amount,
        source="amex-pdf",
        raw=line,
    )


def _parse_amex_statement_fields(
    line: str,
) -> tuple[str, str, str, bool] | None:
    credit = bool(re.search(r"\sCR$", line))
    amount_match = re.search(r"([\d.]+,\d{2})(?:\s+CR)?$", line)
    if not amount_match:
        return None

    head = line[: amount_match.start()].strip()
    amount_str = amount_match.group(1)

    match = _AMEX_STATEMENT_LINE.match(line)
    if not match:
        match = _match_concatenated_amex_dates(line)
    if match:
        return match.group(1), match.group(3), amount_str, credit

    dates = re.findall(_AMEX_DATE, head)
    if len(dates) < 2:
        return None

    after_dates = head
    for date in dates[:2]:
        pos = after_dates.find(date)
        if pos == -1:
            return None
        after_dates = after_dates[pos + len(date) :].lstrip()

    description = after_dates.strip()
    if not description:
        return None

    return dates[0], description, amount_str, credit


def _match_concatenated_amex_dates(line: str) -> re.Match[str] | None:
    """Gestisce righe OCR con date fuse, es. 09.02.2610.02.26 DESCR 118,97."""
    compact = line.replace(" ", "")
    prefix_match = re.match(rf"^({_AMEX_DATE})({_AMEX_DATE})(.*)$", compact)
    if not prefix_match:
        return None

    remainder = prefix_match.group(3)
    amount_match = re.search(r"([\d.]+,\d{2})(?:CR)?$", remainder)
    if not amount_match:
        return None

    description = remainder[: amount_match.start()].strip()
    if not description:
        return None

    normalized = (
        f"{prefix_match.group(1)} {prefix_match.group(2)} "
        f"{description} {amount_match.group(1)}"
    )
    if compact.endswith("CR"):
        normalized += " CR"
    return _AMEX_STATEMENT_LINE.match(normalized)


def _normalize_ocr_description(description: str) -> str:
    return re.sub(r"[^a-z0-9]", "", description.lower())


def _is_summary_description(description: str) -> bool:
    normalized = _normalize_ocr_description(description)
    return any(
        token in normalized
        for token in (
            "saldo",
            "addebitoincc",
            "addebitoinc/c",
            "accreditiregistrati",
            "addebitiregistrati",
            "importodovuto",
            "totalenuoveoperazioni",
            "salvobuonfine",
        )
    )


def parse_amex_csv(path: Path) -> list[Transaction]:
    transactions: list[Transaction] = []
    content = path.read_text(encoding="utf-8")

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("Data,"):
            continue

        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]

        match = re.search(r',""([^"]+)""$', line)
        if not match:
            continue

        amount = parse_italian_amount(match.group(1))
        rest = line[: match.start()]
        comma = rest.find(",")
        if comma == -1:
            continue

        transactions.append(
            Transaction(
                date=_format_amex_date(rest[:comma]),
                description=rest[comma + 1 :],
                amount=amount,
                source=str(path),
                raw=line,
            )
        )

    return transactions


def _format_amex_date(value: str) -> str:
    """Amex exports card dates as month/day/year."""
    cleaned = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return format_italian_date(cleaned)
