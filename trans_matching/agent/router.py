from __future__ import annotations

import re
from typing import Literal

CardCategory = Literal["expedia", "msc", "auto_europe", "generic"]

_EXPEDIA = re.compile(r"EG\*TRVL", re.IGNORECASE)
_MSC = re.compile(r"mscbook\.it|MSC Cruises", re.IGNORECASE)
_AUTO_EUROPE = re.compile(r"AUTOEUROPE", re.IGNORECASE)


def classify_card_transaction(description: str) -> CardCategory:
    if _EXPEDIA.search(description):
        return "expedia"
    if _MSC.search(description):
        return "msc"
    if _AUTO_EUROPE.search(description):
        return "auto_europe"
    return "generic"
