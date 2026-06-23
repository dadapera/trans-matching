from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trans_matching.config import get_openai_config
from trans_matching.llm_usage import get_llm_usage
from trans_matching.matchers.agent_models import AgentMatchResult, MatchAlternative
from trans_matching.models import Transaction
from trans_matching.paths import DB_PATH

_AGENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    openai_model TEXT,
    total_transactions INTEGER NOT NULL,
    matched_count INTEGER NOT NULL,
    elapsed_seconds REAL,
    log_path TEXT,
    llm_cost_usd REAL,
    llm_prompt_tokens INTEGER,
    llm_completion_tokens INTEGER,
    llm_requests INTEGER
);

CREATE TABLE IF NOT EXISTS agent_match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    matched INTEGER NOT NULL,
    trace_id TEXT,
    card_date TEXT NOT NULL,
    card_description TEXT NOT NULL,
    card_amount TEXT NOT NULL,
    agent_confidence TEXT,
    agent_reason TEXT,
    agent_strategy TEXT,
    gestionale_entries_json TEXT,
    alternatives_json TEXT
);

CREATE TABLE IF NOT EXISTS agent_trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    trace_id TEXT,
    row_number INTEGER,
    event TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_match_results_run_id ON agent_match_results(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_trace_events_run_id ON agent_trace_events(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_trace_events_trace_id ON agent_trace_events(trace_id);
"""


@dataclass(frozen=True)
class AgentRunRecord:
    id: int
    created_at: str
    openai_model: str | None
    total_transactions: int
    matched_count: int
    elapsed_seconds: float | None
    log_path: str | None
    llm_cost_usd: float | None
    llm_prompt_tokens: int | None
    llm_completion_tokens: int | None
    llm_requests: int | None


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_AGENT_SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _serialize_gestionale(entries: list[Transaction]) -> str:
    payload = [
        {
            "identificativo": txn.identificativo,
            "date": txn.date,
            "description": txn.description,
            "amount": str(txn.amount),
        }
        for txn in entries
    ]
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_gestionale(raw: str | None) -> list[Transaction]:
    if not raw:
        return []
    data = json.loads(raw)
    return [
        Transaction(
            date=item["date"],
            description=item.get("description", ""),
            amount=Decimal(item["amount"]),
            source="gestionale",
            identificativo=item.get("identificativo", ""),
        )
        for item in data
    ]


def _serialize_alternatives(items: list[MatchAlternative]) -> str:
    payload = [
        {
            "identificativi": item.identificativi,
            "confidence": item.confidence,
            "reason": item.reason,
            "gestionale_preview": item.gestionale_preview,
        }
        for item in items
    ]
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_alternatives(raw: str | None) -> list[MatchAlternative]:
    if not raw:
        return []
    return [
        MatchAlternative(
            identificativi=item.get("identificativi", []),
            confidence=item.get("confidence", "basso"),
            reason=item.get("reason", ""),
            gestionale_preview=item.get("gestionale_preview", ""),
        )
        for item in json.loads(raw)
    ]


def save_agent_run(
    results: list[AgentMatchResult],
    *,
    elapsed_seconds: float | None = None,
    log_path: Path | None = None,
    run_id: int | None = None,
    trace_events: list[dict] | None = None,
    db_path: Path = DB_PATH,
) -> int:
    usage = get_llm_usage()
    matched_count = sum(1 for result in results if result.matched)
    created_at = datetime.now(timezone.utc).isoformat()
    model = get_openai_config().model

    with _connect(db_path) as conn:
        if run_id is None:
            cursor = conn.execute(
                """
                INSERT INTO agent_runs (
                    created_at, openai_model, total_transactions, matched_count,
                    elapsed_seconds, log_path, llm_cost_usd, llm_prompt_tokens,
                    llm_completion_tokens, llm_requests
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    model,
                    len(results),
                    matched_count,
                    elapsed_seconds,
                    str(log_path) if log_path else None,
                    usage.estimated_cost_usd(),
                    usage.prompt_tokens or None,
                    usage.completion_tokens or None,
                    usage.requests or None,
                ),
            )
            saved_run_id = int(cursor.lastrowid)
        else:
            saved_run_id = run_id

        conn.executemany(
            """
            INSERT INTO agent_match_results (
                run_id, row_number, matched, trace_id,
                card_date, card_description, card_amount,
                agent_confidence, agent_reason, agent_strategy,
                gestionale_entries_json, alternatives_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    saved_run_id,
                    result.row_number,
                    int(result.matched),
                    result.trace_id,
                    result.card.date,
                    result.card.description,
                    str(result.card.amount),
                    result.confidence,
                    result.reason,
                    result.strategy,
                    _serialize_gestionale(result.gestionale),
                    _serialize_alternatives(result.alternatives),
                )
                for result in results
            ],
        )
        if trace_events:
            conn.executemany(
                """
                INSERT INTO agent_trace_events (
                    run_id, trace_id, row_number, event, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        saved_run_id,
                        event.get("trace_id"),
                        _trace_row_number(event.get("trace_id")),
                        event.get("event", "unknown"),
                        json.dumps(event, ensure_ascii=False, default=str),
                        event.get("ts") or created_at,
                    )
                    for event in trace_events
                ],
            )
        conn.commit()
        return saved_run_id


def _trace_row_number(trace_id: str | None) -> int | None:
    if not trace_id:
        return None
    try:
        return int(trace_id.rsplit("-", 1)[-1])
    except ValueError:
        return None


def load_agent_run_for_report(
    run_id: int | None = None,
    *,
    db_path: Path = DB_PATH,
) -> tuple[AgentRunRecord, list[AgentMatchResult]]:
    with _connect(db_path) as conn:
        resolved_run_id = _resolve_run_id(conn, run_id)
        run_row = conn.execute(
            "SELECT * FROM agent_runs WHERE id = ?",
            (resolved_run_id,),
        ).fetchone()
        if run_row is None:
            raise ValueError(f"Agent run {resolved_run_id} non trovata")

        rows = conn.execute(
            """
            SELECT * FROM agent_match_results
            WHERE run_id = ?
            ORDER BY row_number
            """,
            (resolved_run_id,),
        ).fetchall()

    run = _row_to_run_record(run_row)
    results = [_row_to_agent_result(row) for row in rows]
    return run, results


def _resolve_run_id(conn: sqlite3.Connection, run_id: int | None) -> int:
    if run_id is not None:
        row = conn.execute("SELECT id FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Agent run {run_id} non trovata")
        return run_id

    row = conn.execute("SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise ValueError("Nessuna agent run salvata")
    return int(row["id"])


def _row_to_run_record(row: sqlite3.Row) -> AgentRunRecord:
    return AgentRunRecord(
        id=row["id"],
        created_at=row["created_at"],
        openai_model=row["openai_model"],
        total_transactions=row["total_transactions"],
        matched_count=row["matched_count"],
        elapsed_seconds=row["elapsed_seconds"],
        log_path=row["log_path"],
        llm_cost_usd=row["llm_cost_usd"],
        llm_prompt_tokens=row["llm_prompt_tokens"],
        llm_completion_tokens=row["llm_completion_tokens"],
        llm_requests=row["llm_requests"],
    )


def _row_to_agent_result(row: sqlite3.Row) -> AgentMatchResult:
    card = Transaction(
        date=row["card_date"],
        description=row["card_description"],
        amount=Decimal(row["card_amount"]),
        source="carta",
    )
    return AgentMatchResult(
        card=card,
        matched=bool(row["matched"]),
        gestionale=_deserialize_gestionale(row["gestionale_entries_json"]),
        confidence=row["agent_confidence"] or "basso",
        reason=row["agent_reason"] or "",
        alternatives=_deserialize_alternatives(row["alternatives_json"]),
        strategy=row["agent_strategy"] or "generic",
        trace_id=row["trace_id"] or "",
        row_number=row["row_number"],
    )
