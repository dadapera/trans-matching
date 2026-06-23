from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from trans_matching.models import Transaction

Confidence = Literal["alto", "medio", "basso"]


@dataclass
class MatchAlternative:
    identificativi: list[str]
    confidence: Confidence
    reason: str
    gestionale_preview: str = ""


@dataclass
class AgentMatchResult:
    card: Transaction
    matched: bool
    gestionale: list[Transaction] = field(default_factory=list)
    confidence: Confidence = "basso"
    reason: str = ""
    alternatives: list[MatchAlternative] = field(default_factory=list)
    strategy: str = "generic"
    trace_id: str = ""
    row_number: int = 0

    @property
    def is_matched(self) -> bool:
        return self.matched
