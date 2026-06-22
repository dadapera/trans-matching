from __future__ import annotations

import re
from pathlib import Path

from trans_matching.models import Transaction
from trans_matching.parsers.common import format_italian_date, parse_italian_amount


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
                date=format_italian_date(rest[:comma]),
                description=rest[comma + 1 :],
                amount=amount,
                source=str(path),
                raw=line,
            )
        )

    return transactions
