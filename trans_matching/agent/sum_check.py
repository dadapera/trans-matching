from __future__ import annotations

import itertools
from decimal import Decimal

from trans_matching.agent.dates import dates_within_window
from trans_matching.agent.pool import GestionalePool
from trans_matching.matchers.gestionale_text import (
    normalize_guest_parts,
    normalize_text,
    split_gestionale_description,
)
from trans_matching.models import Transaction


def find_amount_combinations(
    pool: GestionalePool,
    *,
    target_amount: Decimal,
    card_date: str,
    card_description: str = "",
    date_window_days: int = 7,
    tolerance_pct: float = 15.0,
    max_group_size: int = 5,
    limit: int = 10,
) -> list[dict]:
    """Trova gruppi di righe gestionale la cui somma approssima l'importo carta."""
    candidates = [
        txn
        for txn in pool.available()
        if dates_within_window(card_date, txn.date, days=date_window_days)
        and txn.amount > 0
        and _is_candidate_compatible(card_description, txn)
    ]
    if not candidates:
        return []

    grouped: dict[str, list[Transaction]] = {}
    for txn in candidates:
        guest_key = _guest_key(txn)
        ident_key = _ident_prefix(txn.identificativo)
        provider_key = _provider_key(txn.description)
        for key in {guest_key, ident_key, provider_key}:
            grouped.setdefault(key, []).append(txn)

    seen: set[tuple[str, ...]] = set()
    results: list[dict] = []

    for group_key, group in grouped.items():
        subset = group[:20]
        for size in range(2, min(max_group_size, len(subset)) + 1):
            for combo in itertools.combinations(subset, size):
                keys = tuple(sorted(txn.identificativo or txn.description for txn in combo))
                if keys in seen:
                    continue
                total = sum((txn.amount for txn in combo), Decimal("0"))
                if total <= 0:
                    continue
                delta_pct = abs(float((total - target_amount) / target_amount * 100))
                if delta_pct > tolerance_pct:
                    continue
                seen.add(keys)
                results.append(
                    {
                        "identificativi": [
                            GestionalePool.row_reference(txn) for txn in combo
                        ],
                        "total": str(total),
                        "delta_eur": str(total - target_amount),
                        "delta_pct": round(delta_pct, 2),
                        "group_key": group_key,
                        "rows": [
                            f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}"
                            for txn in combo
                        ],
                    }
                )

    results.sort(key=lambda item: (item["delta_pct"], len(item["identificativi"])))
    return results[:limit]


def find_document_amount_groups(
    pool: GestionalePool,
    *,
    target_amount: Decimal,
    card_date: str,
    card_description: str = "",
    date_window_days: int = 7,
    tolerance_pct: float = 15.0,
    limit: int = 10,
) -> list[dict]:
    """Trova gruppi per Documento+Codice Cliente la cui somma approssima la carta."""
    if target_amount <= 0:
        return []

    grouped: dict[str, list[Transaction]] = {}
    for txn in pool.available():
        if not txn.identificativo.strip():
            continue
        if not dates_within_window(card_date, txn.date, days=date_window_days):
            continue
        if txn.amount <= 0:
            continue
        if not _is_candidate_compatible(card_description, txn):
            continue
        grouped.setdefault(txn.identificativo, []).append(txn)

    results: list[dict] = []
    for group_key, rows in grouped.items():
        if len(rows) < 2:
            continue
        total = sum((txn.amount for txn in rows), Decimal("0"))
        if total <= 0:
            continue
        delta_pct = abs(float((total - target_amount) / target_amount * 100))
        if delta_pct > tolerance_pct:
            continue
        results.append(
            {
                "identificativo": group_key,
                "identificativi": [
                    GestionalePool.row_reference(txn) for txn in rows
                ],
                "total": str(total),
                "delta_eur": str(total - target_amount),
                "delta_pct": round(delta_pct, 2),
                "row_count": len(rows),
                "rows": [
                    f"{txn.identificativo}|{txn.date}|{txn.amount}|{txn.description}"
                    for txn in rows
                ],
            }
        )

    results.sort(key=lambda item: (item["delta_pct"], item["row_count"]))
    return results[:limit]


def _guest_key(txn: Transaction) -> str:
    _, guest = split_gestionale_description(txn.description)
    if not guest:
        return "NOGUEST"
    parts = sorted(normalize_guest_parts(guest))
    return "GUEST:" + "|".join(parts)


def _ident_prefix(identificativo: str) -> str:
    tokens = identificativo.split()
    if len(tokens) >= 2:
        return "IDENT:" + " ".join(tokens[:2])
    return "IDENT:" + identificativo


def _provider_key(description: str) -> str:
    tokens = normalize_text(description).split()
    if not tokens:
        return "PROVIDER:UNKNOWN"
    return "PROVIDER:" + tokens[0]


_EXPEDIA_INCOMPATIBLE_TOKENS = {
    "TRE",
    "TRENITALIA",
    "RYA",
    "RYANAIR",
    "WIZ",
    "WIZZ",
    "FB",
    "FLIXBUS",
    "PC",
    "PEGASUS",
    "WY",
    "OMAN",
    "EST",
    "ESTA",
}


def _is_candidate_compatible(card_description: str, txn: Transaction) -> bool:
    card_text = normalize_text(card_description)
    if "EG TRVL" not in card_text and "EG*TRVL" not in card_text:
        return True

    tokens = normalize_text(txn.description).split()
    if not tokens:
        return True
    return not (
        tokens[0] in _EXPEDIA_INCOMPATIBLE_TOKENS
        or any(token in _EXPEDIA_INCOMPATIBLE_TOKENS for token in tokens[:3])
    )
