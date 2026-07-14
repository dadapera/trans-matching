from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from trans_matching.agent.dates import dates_within_window
from trans_matching.matchers.gestionale_text import (
    guest_matches,
    hotel_matches,
    normalize_text,
)
from trans_matching.models import Transaction

_DATE_IN_TEXT = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")


@dataclass(frozen=True)
class RowAssignment:
    card_row_number: int
    confidence: str


class GestionalePool:
    """Pool righe gestionale con tracking assegnazioni e visibilità completa."""

    def __init__(self, transactions: list[Transaction]) -> None:
        self._all = list(transactions)
        self._assignments: dict[str, RowAssignment] = {}
        self._identifier_counts = Counter(
            self._normalize_identifier(txn.identificativo)
            for txn in self._all
            if txn.identificativo
        )

    def _key(self, txn: Transaction) -> str:
        return self._normalize_identifier(
            f"{txn.identificativo}|{self._row_signature(txn)}|{txn.raw}"
        )

    @staticmethod
    def _row_signature(txn: Transaction) -> str:
        return f"{txn.date}|{txn.amount}|{txn.description}"

    @staticmethod
    def row_reference(txn: Transaction) -> str:
        if txn.identificativo.strip():
            return f"{txn.identificativo}|{GestionalePool._row_signature(txn)}"
        return GestionalePool._row_signature(txn)

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        compact_pipes = re.sub(r"\s*\|\s*", "|", value.strip())
        return " ".join(compact_pipes.upper().split())

    def _identifier_aliases(self, txn: Transaction) -> set[str]:
        aliases = {
            GestionalePool._row_signature(txn),
            f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}",
            f"{txn.date}|{txn.description}|{txn.amount}",
        }
        if txn.identificativo:
            normalized_identifier = self._normalize_identifier(txn.identificativo)
            if self._identifier_counts[normalized_identifier] == 1:
                aliases.add(txn.identificativo)
        else:
            aliases.add(f"|{GestionalePool._row_signature(txn)}")
        return {
            normalized
            for alias in aliases
            if (normalized := GestionalePool._normalize_identifier(alias))
        }

    @property
    def total(self) -> int:
        return len(self._all)

    @property
    def available_count(self) -> int:
        return len(self._all)

    @property
    def assigned_count(self) -> int:
        return len(self._assignments)

    def is_available(self, txn: Transaction) -> bool:
        return True

    def available(self) -> list[Transaction]:
        return list(self._all)

    def get_assignment(self, txn: Transaction) -> RowAssignment | None:
        return self._assignments.get(self._key(txn))

    def assign(
        self,
        transactions: list[Transaction],
        *,
        card_row_number: int,
        confidence: str,
    ) -> list[str]:
        assigned: list[str] = []
        for txn in transactions:
            key = self._key(txn)
            self._assignments[key] = RowAssignment(
                card_row_number=card_row_number,
                confidence=confidence,
            )
            assigned.append(txn.identificativo or key)
        return assigned

    def has_assignment_conflict(
        self,
        identificativi: list[str],
        card_row_number: int,
    ) -> bool:
        return False

    def find_by_identificativi(self, identificativi: list[str]) -> list[Transaction]:
        targets = {
            normalized
            for value in identificativi
            if (normalized := self._normalize_identifier(value))
        }
        found: list[Transaction] = []
        for txn in self._all:
            if self._identifier_aliases(txn) & targets:
                found.append(txn)
        return found

    def format_row(self, txn: Transaction) -> str:
        base = f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}"
        return f"{base}  [available]"

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

        for txn in self._all:
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
        for txn in self._all:
            if guest and not guest_matches(txn.description, guest):
                continue
            if hotel and not hotel_matches(txn.description, hotel):
                continue
            if card_date and not _dates_within_any_siap_date(
                card_date,
                txn,
                days=date_window_days,
            ):
                continue

            score = 2
            if guest:
                score += 2
            if hotel:
                score += 2
            if amount is not None and txn.amount == amount:
                score += 3
            if score > 0:
                scored.append((score, txn))

        scored.sort(key=lambda item: (-item[0], item[1].date))
        return [txn for _, txn in scored]

    def format_rows(self, transactions: list[Transaction] | None = None) -> str:
        rows = transactions if transactions is not None else self._all
        return "\n".join(self.format_row(txn) for txn in rows)


def _dates_within_any_siap_date(card_date: str, txn: Transaction, *, days: int) -> bool:
    """SIAP rows can contain accounting date plus service/payment dates in raw text."""
    dates = [txn.date]
    if txn.raw:
        dates.extend(_DATE_IN_TEXT.findall(txn.raw))
    return any(dates_within_window(card_date, date, days=days) for date in dates)
