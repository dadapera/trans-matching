from __future__ import annotations

import csv
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from trans_matching.models import Transaction
from trans_matching.parsers.common import format_italian_date, parse_italian_amount

_GESTIONALE_SKIP = re.compile(
    r"^(MAE'|--+|Controllo|Da Data|Documento|Carta di credito|TOTALE|-- \d|Pagina)",
    re.IGNORECASE,
)

_GESTIONALE_AMOUNT = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?:EUR\s+)?"
    r"([\d.]+,\d{2})"
    r"(-)?"
    r"\s+"
)

GESTIONALE_CSV_FIELDS = [
    "identificativo",
    "data",
    "descrizione",
    "importo",
    "riga_originale",
]


def _extract_gestionale_line(line: str) -> Transaction | None:
    line = line.strip()
    if not line or _GESTIONALE_SKIP.match(line):
        return None

    match = _GESTIONALE_AMOUNT.search(line)
    if not match:
        return None

    date = match.group(1)
    amount_str = match.group(2)
    negative_suffix = match.group(3) == "-"
    amount = parse_italian_amount(amount_str + ("-" if negative_suffix else ""))

    after_amount = line[match.end() :]
    desc_match = re.match(r"(\S+(?:\s+\S+)*?)(?:\s+0,00|\s+\d+,\d{2}\s|$)", after_amount)
    description = desc_match.group(1).strip() if desc_match else after_amount.strip()

    return Transaction(
        date=format_italian_date(date),
        description=description,
        amount=amount,
        source="gestionale",
        raw=line,
        identificativo=_extract_gestionale_identificativo(line),
    )


def parse_gestionale_pdf(path: Path) -> list[Transaction]:
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    transactions: list[Transaction] = []
    for line in text.splitlines():
        txn = _extract_gestionale_line(line)
        if txn:
            transactions.append(
                Transaction(
                    date=txn.date,
                    description=txn.description,
                    amount=txn.amount,
                    source=str(path),
                    raw=txn.raw,
                )
            )
    return transactions


def _extract_gestionale_identificativo(raw: str) -> str:
    return " ".join(raw.split()[:3])


def convert_gestionale_pdf_to_csv(pdf_path: Path) -> Path:
    csv_path = pdf_path.with_suffix(".csv")
    transactions = parse_gestionale_pdf(pdf_path)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GESTIONALE_CSV_FIELDS)
        writer.writeheader()
        for txn in transactions:
            writer.writerow(
                {
                    "identificativo": _extract_gestionale_identificativo(txn.raw),
                    "data": txn.date,
                    "descrizione": txn.description,
                    "importo": str(txn.amount),
                    "riga_originale": txn.raw,
                }
            )
    return csv_path


def parse_gestionale_csv(path: Path) -> list[Transaction]:
    transactions: list[Transaction] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("riga_originale", "")
            transactions.append(
                Transaction(
                    date=row["data"],
                    description=row["descrizione"],
                    amount=Decimal(row["importo"]),
                    source=str(path),
                    raw=raw,
                    identificativo=row.get("identificativo")
                    or _extract_gestionale_identificativo(raw),
                )
            )
    return transactions


def _csv_needs_regeneration(pdf_path: Path, csv_path: Path) -> bool:
    if not csv_path.exists() or pdf_path.stat().st_mtime > csv_path.stat().st_mtime:
        return True
    with csv_path.open(encoding="utf-8") as f:
        header = next(csv.reader(f), None)
    return header != GESTIONALE_CSV_FIELDS


def ensure_gestionale_csv_files(gestionale_dir: Path) -> list[Path]:
    csv_files: list[Path] = []
    for pdf_file in sorted(gestionale_dir.glob("*.pdf")):
        csv_path = pdf_file.with_suffix(".csv")
        if _csv_needs_regeneration(pdf_file, csv_path):
            convert_gestionale_pdf_to_csv(pdf_file)
            print(f"Convertito: {pdf_file.name} -> {csv_path.name}")
        csv_files.append(csv_path)
    return csv_files
