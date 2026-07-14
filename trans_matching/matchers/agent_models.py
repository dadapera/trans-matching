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
    metadata: dict = field(default_factory=dict)

    @property
    def is_matched(self) -> bool:
        return self.matched

    @property
    def is_ambiguous(self) -> bool:
        return not self.matched and any(
            alternative.confidence in ("alto", "medio")
            for alternative in self.alternatives
        )
