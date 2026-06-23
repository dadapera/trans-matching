from __future__ import annotations

import re
from typing import Literal

CardCategory = Literal["expedia", "msc", "generic"]

_EXPEDIA = re.compile(r"EG\*TRVL", re.IGNORECASE)
_MSC = re.compile(r"mscbook\.it|MSC Cruises", re.IGNORECASE)


def classify_card_transaction(description: str) -> CardCategory:
    if _EXPEDIA.search(description):
        return "expedia"
    if _MSC.search(description):
        return "msc"
    return "generic"
