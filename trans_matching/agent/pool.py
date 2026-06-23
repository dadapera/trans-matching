from __future__ import annotations

from decimal import Decimal

from trans_matching.agent.dates import dates_within_window
from trans_matching.matchers.gestionale_text import (
    guest_matches,
    hotel_matches,
    normalize_text,
)
from trans_matching.models import Transaction


class GestionalePool:
    """Pool righe gestionale con tracking righe già abbinate."""

    def __init__(self, transactions: list[Transaction]) -> None:
        self._all = list(transactions)
        self._used_keys: set[str] = set()

    @staticmethod
    def _key(txn: Transaction) -> str:
        return txn.identificativo or f"{txn.date}|{txn.description}|{txn.amount}"

    @property
    def total(self) -> int:
        return len(self._all)

    @property
    def available_count(self) -> int:
        return sum(1 for txn in self._all if self._key(txn) not in self._used_keys)

    def available(self) -> list[Transaction]:
        return [txn for txn in self._all if self._key(txn) not in self._used_keys]

    def mark_used(self, transactions: list[Transaction]) -> list[str]:
        marked: list[str] = []
        for txn in transactions:
            key = self._key(txn)
            if key in self._used_keys:
                continue
            self._used_keys.add(key)
            marked.append(txn.identificativo or key)
        return marked

    def find_by_identificativi(self, identificativi: list[str]) -> list[Transaction]:
        targets = {value.strip().upper() for value in identificativi if value.strip()}
        found: list[Transaction] = []
        for txn in self.available():
            ident = txn.identificativo.strip().upper()
            if ident in targets:
                found.append(txn)
        return found

    def search(
        self,
        *,
        text: str | None = None,
        amount: Decimal | None = None,
        amount_tolerance_pct: float = 15.0,
        card_date: str | None = None,
        date_window_days: int = 7,
        limit: int = 30,
    ) -> list[Transaction]:
        results: list[tuple[int, Transaction]] = []
        text_norm = normalize_text(text or "") if text else ""

        for txn in self.available():
            score = 0
            if text_norm:
                haystack = normalize_text(txn.description)
                if text_norm in haystack:
                    score += 3
                else:
                    tokens = [token for token in text_norm.split() if len(token) > 2]
                    hits = sum(1 for token in tokens if token in haystack)
                    if hits == 0:
                        continue
                    score += hits

            if amount is not None:
                if txn.amount == amount:
                    score += 4
                elif txn.amount != 0:
                    delta_pct = abs(float((txn.amount - amount) / amount * 100))
                    if delta_pct <= amount_tolerance_pct:
                        score += 2
                    elif text_norm:
                        pass
                    else:
                        continue

            if card_date and not dates_within_window(card_date, txn.date, days=date_window_days):
                if score == 0:
                    continue
                score -= 1

            if score > 0 or (not text_norm and amount is None):
                results.append((score, txn))

        results.sort(key=lambda item: (-item[0], item[1].date, item[1].identificativo))
        return [txn for _, txn in results[:limit]]

    def search_by_guest_hotel(
        self,
        *,
        guest: str | None,
        hotel: str | None,
        amount: Decimal | None = None,
        card_date: str | None = None,
        date_window_days: int = 7,
    ) -> list[Transaction]:
        scored: list[tuple[int, Transaction]] = []
        for txn in self.available():
            if guest and not guest_matches(txn.description, guest):
                continue
            if hotel and not hotel_matches(txn.description, hotel):
                continue
            if card_date and not dates_within_window(card_date, txn.date, days=date_window_days):
                continue

            score = 2
            if guest:
                score += 2
            if hotel:
                score += 2
            if amount is not None and txn.amount == amount:
                score += 3
            scored.append((score, txn))

        scored.sort(key=lambda item: (-item[0], item[1].date))
        return [txn for _, txn in scored]

    def format_rows(self, transactions: list[Transaction] | None = None) -> str:
        rows = transactions or self.available()
        return "\n".join(
            f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}"
            for txn in rows
        )
