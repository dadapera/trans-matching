from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trans_matching.config import (
    ExpediaMatcherMode,
    get_expedia_llm_batch_size,
    get_expedia_matcher_mode,
    get_openai_config,
)
from trans_matching.llm_usage import get_llm_usage
from trans_matching.matchers.amount import MatchResult
from trans_matching.models import Transaction
from trans_matching.paths import DB_PATH
from trans_matching.verifiers.expedia_trvl import (
    ExpediaTransaction,
    ExpediaVerificationResult,
    LlmConfidence,
    extract_booking_code,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    expedia_matcher TEXT NOT NULL,
    openai_model TEXT,
    llm_batch_size INTEGER,
    total_transactions INTEGER NOT NULL,
    matched_count INTEGER NOT NULL,
    elapsed_seconds REAL,
    llm_cost_usd REAL,
    llm_prompt_tokens INTEGER,
    llm_completion_tokens INTEGER,
    llm_requests INTEGER
);

CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    matched INTEGER NOT NULL,
    card_date TEXT NOT NULL,
    card_description TEXT NOT NULL,
    card_amount TEXT NOT NULL,
    gestionale_identificativo TEXT,
    gestionale_date TEXT,
    gestionale_description TEXT,
    gestionale_amount TEXT,
    expedia_booking_code TEXT,
    expedia_email_found INTEGER,
    expedia_hotel TEXT,
    expedia_guest TEXT,
    expedia_note TEXT,
    expedia_llm_reason TEXT,
    expedia_llm_confidence TEXT
);

CREATE INDEX IF NOT EXISTS idx_match_results_run_id ON match_results(run_id);
"""


@dataclass(frozen=True)
class RunRecord:
    id: int
    created_at: str
    expedia_matcher: str
    openai_model: str | None
    llm_batch_size: int | None
    total_transactions: int
    matched_count: int
    elapsed_seconds: float | None
    llm_cost_usd: float | None
    llm_prompt_tokens: int | None
    llm_completion_tokens: int | None
    llm_requests: int | None


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _confidence_value(value: str | None) -> LlmConfidence | None:
    if value in ("basso", "medio", "alto"):
        return value
    return None


def _serialize_result(run_id: int, row_number: int, result: MatchResult) -> dict:
    card = result.card
    gestionale = result.gestionale
    expedia = result.expedia

    data = {
        "run_id": run_id,
        "row_number": row_number,
        "matched": int(result.matched),
        "card_date": card.date,
        "card_description": card.description,
        "card_amount": str(card.amount),
        "gestionale_identificativo": None,
        "gestionale_date": None,
        "gestionale_description": None,
        "gestionale_amount": None,
        "expedia_booking_code": None,
        "expedia_email_found": None,
        "expedia_hotel": None,
        "expedia_guest": None,
        "expedia_note": None,
        "expedia_llm_reason": None,
        "expedia_llm_confidence": None,
    }

    if gestionale:
        data.update(
            {
                "gestionale_identificativo": gestionale.identificativo or None,
                "gestionale_date": gestionale.date,
                "gestionale_description": gestionale.description,
                "gestionale_amount": str(gestionale.amount),
            }
        )

    if expedia:
        data.update(
            {
                "expedia_booking_code": expedia.expedia.booking_code,
                "expedia_email_found": int(expedia.email_found),
                "expedia_hotel": expedia.hotel_name,
                "expedia_guest": expedia.guest_name,
                "expedia_note": expedia.note or None,
                "expedia_llm_reason": expedia.llm_reason,
                "expedia_llm_confidence": expedia.llm_confidence,
            }
        )

    return data


def _row_to_match_result(row: sqlite3.Row) -> MatchResult:
    card = Transaction(
        date=row["card_date"],
        description=row["card_description"],
        amount=Decimal(row["card_amount"]),
        source="carta",
    )

    gestionale: Transaction | None = None
    if row["gestionale_date"]:
        gestionale = Transaction(
            date=row["gestionale_date"],
            description=row["gestionale_description"] or "",
            amount=Decimal(row["gestionale_amount"] or "0"),
            source="gestionale",
            identificativo=row["gestionale_identificativo"] or "",
        )

    expedia: ExpediaVerificationResult | None = None
    booking_code = row["expedia_booking_code"] or extract_booking_code(card.description)
    if booking_code and row["expedia_email_found"] is not None:
        expedia = ExpediaVerificationResult(
            expedia=ExpediaTransaction(transaction=card, booking_code=booking_code),
            email_found=bool(row["expedia_email_found"]),
            emails=[],
            hotel_name=row["expedia_hotel"],
            guest_name=row["expedia_guest"],
            gestionale=gestionale,
            note=row["expedia_note"] or "",
            llm_reason=row["expedia_llm_reason"],
            llm_confidence=_confidence_value(row["expedia_llm_confidence"]),
        )

    return MatchResult(
        card=card,
        matched=bool(row["matched"]),
        gestionale=gestionale,
        expedia=expedia,
    )


def _row_to_run_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        created_at=row["created_at"],
        expedia_matcher=row["expedia_matcher"],
        openai_model=row["openai_model"],
        llm_batch_size=row["llm_batch_size"],
        total_transactions=row["total_transactions"],
        matched_count=row["matched_count"],
        elapsed_seconds=row["elapsed_seconds"],
        llm_cost_usd=row["llm_cost_usd"],
        llm_prompt_tokens=row["llm_prompt_tokens"],
        llm_completion_tokens=row["llm_completion_tokens"],
        llm_requests=row["llm_requests"],
    )


def save_run(
    results: list[MatchResult],
    *,
    elapsed_seconds: float | None = None,
    db_path: Path = DB_PATH,
) -> int:
    """Salva i risultati di una run e restituisce l'id."""
    matcher_mode = get_expedia_matcher_mode()
    openai_model: str | None = None
    llm_batch_size: int | None = None
    if matcher_mode == ExpediaMatcherMode.LLM:
        openai_model = get_openai_config().model
        llm_batch_size = get_expedia_llm_batch_size()

    usage = get_llm_usage()
    matched_count = sum(1 for result in results if result.is_matched)
    created_at = datetime.now(timezone.utc).isoformat()

    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (
                created_at, expedia_matcher, openai_model, llm_batch_size,
                total_transactions, matched_count, elapsed_seconds,
                llm_cost_usd, llm_prompt_tokens, llm_completion_tokens, llm_requests
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                matcher_mode.value,
                openai_model,
                llm_batch_size,
                len(results),
                matched_count,
                elapsed_seconds,
                usage.estimated_cost_usd(),
                usage.prompt_tokens or None,
                usage.completion_tokens or None,
                usage.requests or None,
            ),
        )
        run_id = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO match_results (
                run_id, row_number, matched,
                card_date, card_description, card_amount,
                gestionale_identificativo, gestionale_date, gestionale_description, gestionale_amount,
                expedia_booking_code, expedia_email_found, expedia_hotel, expedia_guest,
                expedia_note, expedia_llm_reason, expedia_llm_confidence
            ) VALUES (
                :run_id, :row_number, :matched,
                :card_date, :card_description, :card_amount,
                :gestionale_identificativo, :gestionale_date, :gestionale_description, :gestionale_amount,
                :expedia_booking_code, :expedia_email_found, :expedia_hotel, :expedia_guest,
                :expedia_note, :expedia_llm_reason, :expedia_llm_confidence
            )
            """,
            [_serialize_result(run_id, index, result) for index, result in enumerate(results, start=1)],
        )
        conn.commit()
        return run_id


def _resolve_run_id(conn: sqlite3.Connection, run_id: int | None) -> int:
    if run_id is not None:
        row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Run {run_id} non trovata nel database")
        return run_id

    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise ValueError("Nessuna run salvata nel database")
    return int(row["id"])


def load_run_for_report(
    run_id: int | None = None,
    *,
    db_path: Path = DB_PATH,
) -> tuple[RunRecord, list[MatchResult]]:
    """Carica metadati run e risultati per il report HTML."""
    with _connect(db_path) as conn:
        resolved_run_id = _resolve_run_id(conn, run_id)

        run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (resolved_run_id,)).fetchone()
        if run_row is None:
            raise ValueError(f"Run {resolved_run_id} non trovata nel database")

        result_rows = conn.execute(
            """
            SELECT * FROM match_results
            WHERE run_id = ?
            ORDER BY row_number
            """,
            (resolved_run_id,),
        ).fetchall()

    return _row_to_run_record(run_row), [_row_to_match_result(row) for row in result_rows]


def list_runs(*, db_path: Path = DB_PATH) -> list[RunRecord]:
    """Elenca le run salvate, dalla più recente."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    return [_row_to_run_record(row) for row in rows]
