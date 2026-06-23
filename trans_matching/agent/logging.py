from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trans_matching.config import get_agent_log_config

_EVENT_LEVELS = {
    "run_start": logging.INFO,
    "run_end": logging.INFO,
    "data_loaded": logging.INFO,
    "router_classify": logging.DEBUG,
    "txn_start": logging.INFO,
    "txn_end": logging.INFO,
    "tool_call": logging.INFO,
    "agent_step": logging.DEBUG,
    "llm_call": logging.DEBUG,
    "email_search": logging.INFO,
    "confidence_gate": logging.INFO,
    "pool_update": logging.DEBUG,
    "error": logging.ERROR,
}


class AgentRunLogger:
    """Logger strutturato: console + JSONL per run."""

    def __init__(
        self,
        *,
        run_id: int,
        log_path: Path,
        console_level: str = "INFO",
    ) -> None:
        self.run_id = run_id
        self.log_path = log_path
        self._events: list[dict[str, Any]] = []
        self._console = logging.getLogger(f"trans_matching.agent.run-{run_id}")
        self._console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
        if not self._console.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._console.addHandler(handler)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event: str,
        *,
        trace_id: str | None = None,
        step: int | None = None,
        duration_ms: int | None = None,
        **payload: Any,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
        }
        if trace_id:
            record["trace_id"] = trace_id
        if step is not None:
            record["step"] = step
        if duration_ms is not None:
            record["duration_ms"] = duration_ms
        record.update(_sanitize_payload(payload))

        self._events.append(record)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        level = _EVENT_LEVELS.get(event, logging.INFO)
        summary = _format_console(record)
        self._console.log(level, summary)

    def log_error(
        self,
        event: str,
        exc: BaseException,
        *,
        trace_id: str | None = None,
        **payload: Any,
    ) -> None:
        self.log(
            event,
            trace_id=trace_id,
            error=str(exc),
            traceback=traceback.format_exc(),
            **payload,
        )

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"api_key", "app_password", "password", "token"}:
            cleaned[key] = "***"
            continue
        cleaned[key] = _truncate_value(value)
    return cleaned


def _truncate_value(value: Any, max_len: int = 2000) -> Any:
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "…"
    if isinstance(value, list) and len(value) > 20:
        return value[:20] + [f"…(+{len(value) - 20} altri)"]
    if isinstance(value, dict):
        return {key: _truncate_value(item, max_len) for key, item in value.items()}
    return value


def _format_console(record: dict[str, Any]) -> str:
    parts = [record["event"]]
    if trace_id := record.get("trace_id"):
        parts.append(f"trace={trace_id}")
    if tool := record.get("tool"):
        parts.append(f"tool={tool}")
    if record.get("matched") is not None:
        parts.append(f"matched={record['matched']}")
    if confidence := record.get("confidence"):
        parts.append(f"confidence={confidence}")
    if error := record.get("error"):
        parts.append(f"error={error}")
    return " | ".join(parts)


def create_run_logger(run_id: int) -> AgentRunLogger:
    config = get_agent_log_config()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = config.log_dir / f"run-{stamp}-id{run_id}.jsonl"
    return AgentRunLogger(run_id=run_id, log_path=log_path, console_level=config.level)
