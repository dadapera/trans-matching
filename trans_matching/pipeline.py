"""Pipeline completa: matching importo + verifica Expedia."""

from __future__ import annotations

from trans_matching.config import get_expedia_matcher_mode
from trans_matching.email import GmailReader
from trans_matching.matchers.amount import MatchResult, match_by_amount
from trans_matching.models import Transaction
from trans_matching.parsers.loaders import load_card_transactions, load_gestionale_transactions
from trans_matching.paths import CARTA_DIR, GESTIONALE_DIR
from trans_matching.verifiers.expedia_trvl import (
    enrich_with_expedia_verification,
    filter_expedia_transactions,
)


def run_matching(
    card_transactions: list[Transaction] | None = None,
    gestionale_transactions: list[Transaction] | None = None,
) -> list[MatchResult]:
    card_txns = card_transactions or load_card_transactions(CARTA_DIR)
    gestionale_txns = gestionale_transactions or load_gestionale_transactions(GESTIONALE_DIR)

    if not card_txns:
        raise ValueError(f"Nessuna transazione trovata in {CARTA_DIR}")
    if not gestionale_txns:
        raise ValueError(f"Nessuna transazione trovata in {GESTIONALE_DIR}")

    results = match_by_amount(card_txns, gestionale_txns)
    expedia_txns = filter_expedia_transactions(card_txns)

    if not expedia_txns:
        return results

    mode = get_expedia_matcher_mode()
    print(
        f"Verifica email Expedia ({mode.value}) per {len(expedia_txns)} transazioni EG*TRVL..."
    )
    with GmailReader() as reader:
        return enrich_with_expedia_verification(results, reader, gestionale_txns)
