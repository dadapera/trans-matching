from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from trans_matching.agent.logging import AgentRunLogger
from trans_matching.agent.pool import GestionalePool
from trans_matching.email import GmailReader
from trans_matching.models import Transaction

_session: contextvars.ContextVar[MatchSession | None] = contextvars.ContextVar(
    "match_session",
    default=None,
)


@dataclass
class MatchSession:
    pool: GestionalePool
    reader: GmailReader
    logger: AgentRunLogger
    run_id: int
    row_number: int
    card: Transaction
    trace_id: str
    date_window_days: int = 7
    _tool_step: int = field(default=0, repr=False)

    def next_tool_step(self) -> int:
        self._tool_step += 1
        return self._tool_step


def get_session() -> MatchSession:
    session = _session.get()
    if session is None:
        raise RuntimeError("MatchSession non impostata")
    return session


def set_session(session: MatchSession) -> contextvars.Token:
    return _session.set(session)


def reset_session(token: contextvars.Token) -> None:
    _session.reset(token)
