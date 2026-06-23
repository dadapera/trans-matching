from __future__ import annotations

import time
from decimal import Decimal

from tqdm import tqdm

from trans_matching.agent.context import MatchSession
from trans_matching.agent.logging import AgentRunLogger, create_run_logger
from trans_matching.agent.matcher import match_one
from trans_matching.agent.pool import GestionalePool
from trans_matching.config import get_agent_config
from trans_matching.email import GmailReader
from trans_matching.matchers.agent_models import AgentMatchResult
from trans_matching.models import Transaction
from trans_matching.parsers.loaders import load_card_transactions, load_gestionale_transactions
from trans_matching.paths import CARTA_DIR, GESTIONALE_DIR
from trans_matching.storage.agent_repository import save_agent_run


def run_agent_matching(
    card_transactions: list[Transaction] | None = None,
    gestionale_transactions: list[Transaction] | None = None,
    *,
    run_id: int | None = None,
    logger: AgentRunLogger | None = None,
) -> tuple[list[AgentMatchResult], int, AgentRunLogger]:
    started = time.perf_counter()
    card_txns = card_transactions or load_card_transactions(CARTA_DIR)
    gestionale_txns = gestionale_transactions or load_gestionale_transactions(GESTIONALE_DIR)

    if not card_txns:
        raise ValueError(f"Nessuna transazione trovata in {CARTA_DIR}")
    if not gestionale_txns:
        raise ValueError(f"Nessuna transazione trovata in {GESTIONALE_DIR}")

    provisional_run_id = run_id or 0
    run_logger = logger or create_run_logger(provisional_run_id)
    agent_config = get_agent_config()
    pool = GestionalePool(gestionale_txns)

    run_logger.log(
        "run_start",
        card_count=len(card_txns),
        gestionale_count=len(gestionale_txns),
        gestionale_available=pool.available_count,
        date_window_days=agent_config.date_window_days,
        log_path=str(run_logger.log_path),
    )
    run_logger.log(
        "data_loaded",
        card_total=str(sum((txn.amount for txn in card_txns), Decimal("0"))),
        gestionale_total=str(sum((txn.amount for txn in gestionale_txns), Decimal("0"))),
    )

    results: list[AgentMatchResult] = []
    with GmailReader() as reader:
        progress = tqdm(card_txns, desc="Agent matching", unit="txn")
        for index, card in enumerate(progress, start=1):
            trace_id = f"run-{provisional_run_id}-txn-{index:03d}"
            progress.set_postfix_str(card.description[:40])
            session = MatchSession(
                pool=pool,
                reader=reader,
                logger=run_logger,
                run_id=provisional_run_id,
                row_number=index,
                card=card,
                trace_id=trace_id,
                date_window_days=agent_config.date_window_days,
            )
            result = match_one(session)
            result.row_number = index
            result.trace_id = trace_id
            if result.matched:
                marked = pool.mark_used(result.gestionale)
                run_logger.log(
                    "pool_update",
                    trace_id=trace_id,
                    marked=marked,
                    remaining=pool.available_count,
                )
            results.append(result)

    elapsed = time.perf_counter() - started
    matched = sum(1 for item in results if item.matched)
    saved_run_id = save_agent_run(
        results,
        elapsed_seconds=elapsed,
        log_path=run_logger.log_path,
        run_id=run_id,
        trace_events=run_logger.events,
    )
    if saved_run_id != provisional_run_id:
        run_logger.log("run_end", run_id=saved_run_id, note="run_id aggiornato post-save")

    run_logger.log(
        "run_end",
        run_id=saved_run_id,
        matched=matched,
        total=len(results),
        elapsed_seconds=round(elapsed, 2),
        log_path=str(run_logger.log_path),
    )
    return results, saved_run_id, run_logger
