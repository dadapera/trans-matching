from __future__ import annotations

from datetime import datetime
from decimal import Decimal

_ITALIAN_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d.%m.%Y",
    "%d.%m.%y",
)


def format_italian_date(value: str) -> str:
    """Normalizza una data in formato gg/mm/aaaa (es. 08/06/2026)."""
    cleaned = value.strip()
    if not cleaned:
        return cleaned

    for fmt in _ITALIAN_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    return cleaned


def parse_italian_amount(value: str) -> Decimal:
    """Converte importi in formato italiano (es. 1.234,56 o 25,98-) in Decimal."""
    cleaned = value.strip().strip('"')
    negative = cleaned.endswith("-") or cleaned.startswith("-")
    cleaned = cleaned.replace("-", "").replace(".", "").replace(",", ".")
    amount = Decimal(cleaned)
    return -amount if negative else amount
