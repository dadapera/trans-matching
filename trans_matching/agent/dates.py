from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from trans_matching.models import Transaction
from trans_matching.parsers.common import format_italian_date


def parse_transaction_date(value: str) -> datetime | None:
    normalized = format_italian_date(value)
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def dates_within_window(
    left: str,
    right: str,
    *,
    days: int,
) -> bool:
    left_dt = parse_transaction_date(left)
    right_dt = parse_transaction_date(right)
    if left_dt is None or right_dt is None:
        return False
    return abs((left_dt - right_dt).days) <= days


def date_window_bounds(center: str, *, days: int) -> tuple[datetime | None, datetime | None]:
    center_dt = parse_transaction_date(center)
    if center_dt is None:
        return None, None
    delta = timedelta(days=days)
    return center_dt - delta, center_dt + delta


def format_amount(amount: Decimal) -> str:
    return f"{amount:.2f}"
