from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    date: str
    description: str
    amount: Decimal
    source: str
    raw: str = ""
    identificativo: str = ""
