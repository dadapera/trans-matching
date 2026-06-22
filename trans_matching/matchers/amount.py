from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from trans_matching.models import Transaction

if TYPE_CHECKING:
    from trans_matching.verifiers.expedia_trvl import ExpediaVerificationResult


@dataclass
class MatchResult:
    card: Transaction
    matched: bool
    gestionale: Transaction | None = None
    expedia: ExpediaVerificationResult | None = None

    @property
    def is_matched(self) -> bool:
        return self.matched


def match_by_amount(
    card_transactions: list[Transaction],
    gestionale_transactions: list[Transaction],
) -> list[MatchResult]:
    pool: dict = defaultdict(list)
    for txn in gestionale_transactions:
        pool[txn.amount].append(txn)

    results: list[MatchResult] = []
    for card in card_transactions:
        candidates = pool.get(card.amount)
        if candidates:
            results.append(MatchResult(card=card, matched=True, gestionale=candidates.pop(0)))
        else:
            results.append(MatchResult(card=card, matched=False))
    return results
