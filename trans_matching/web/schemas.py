from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from trans_matching.matchers.agent_models import AgentMatchResult, MatchAlternative
from trans_matching.models import Transaction

RunStatusLiteral = Literal["idle", "running", "completed", "stopped", "error"]


class TransactionDTO(BaseModel):
    date: str
    description: str
    amount: str
    identificativo: str = ""
    source: str = ""


class MatchAlternativeDTO(BaseModel):
    identificativi: list[str]
    confidence: str
    reason: str
    gestionale_preview: str = ""


class MatchResultDTO(BaseModel):
    row_number: int
    trace_id: str
    matched: bool
    confidence: str
    reason: str
    strategy: str
    card: TransactionDTO
    gestionale: list[TransactionDTO]
    alternatives: list[MatchAlternativeDTO]
    ambiguous: bool = False


class AgentEventDTO(BaseModel):
    event: str
    ts: str | None = None
    run_id: int | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    carta_count: int
    gestionale_count: int
    carta_filename: str
    gestionale_filename: str


class RunStartResponse(BaseModel):
    run_id: int


class RunStartRequest(BaseModel):
    row_start: int = Field(ge=1)
    row_end: int = Field(ge=1)


class RunStatusDTO(BaseModel):
    run_id: int
    status: str
    processed: int
    expected: int
    matched_count: int
    elapsed_seconds: float | None
    log_path: str | None
    openai_model: str | None
    created_at: str | None = None


class RunListItemDTO(BaseModel):
    id: int
    status: str
    created_at: str
    total_transactions: int
    matched_count: int
    expected_transactions: int | None


def _txn_to_dto(txn: Transaction) -> TransactionDTO:
    return TransactionDTO(
        date=txn.date,
        description=txn.description,
        amount=str(txn.amount),
        identificativo=txn.identificativo or "",
        source=txn.source or "",
    )


def _alt_to_dto(alt: MatchAlternative) -> MatchAlternativeDTO:
    return MatchAlternativeDTO(
        identificativi=alt.identificativi,
        confidence=alt.confidence,
        reason=alt.reason,
        gestionale_preview=alt.gestionale_preview,
    )


def match_result_to_dto(result: AgentMatchResult) -> MatchResultDTO:
    ambiguous = not result.matched and bool(result.alternatives)
    return MatchResultDTO(
        row_number=result.row_number,
        trace_id=result.trace_id,
        matched=result.matched,
        confidence=result.confidence,
        reason=result.reason,
        strategy=result.strategy,
        card=_txn_to_dto(result.card),
        gestionale=[_txn_to_dto(txn) for txn in result.gestionale],
        alternatives=[_alt_to_dto(alt) for alt in result.alternatives],
        ambiguous=ambiguous,
    )


def event_record_to_dto(record: dict[str, Any]) -> AgentEventDTO:
    payload = {k: v for k, v in record.items() if k not in {"event", "ts", "run_id", "trace_id"}}
    return AgentEventDTO(
        event=record.get("event", "unknown"),
        ts=record.get("ts"),
        run_id=record.get("run_id"),
        trace_id=record.get("trace_id"),
        payload=payload,
    )
