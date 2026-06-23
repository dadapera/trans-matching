from __future__ import annotations

import itertools
import time
from decimal import Decimal
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from trans_matching.agent.context import get_session
from trans_matching.llm_usage import record_chat_completion


class AgentTraceCallback(BaseCallbackHandler):
    """Callback LangChain → AgentRunLogger JSONL."""

    def __init__(self) -> None:
        self._llm_start: float | None = None
        self._tool_start: dict[str, float] = {}
        self._agent_step = 0

    def _logger(self):
        return get_session().logger

    def _trace_id(self) -> str:
        return get_session().trace_id

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name", "unknown")
        self._tool_start[str(run_id)] = time.perf_counter()
        session = get_session()
        self._logger().log(
            "tool_call",
            trace_id=self._trace_id(),
            step=session.next_tool_step(),
            phase="start",
            tool=name,
            input=inputs or input_str,
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        started = self._tool_start.pop(str(run_id), None)
        duration_ms = int((time.perf_counter() - started) * 1000) if started else None
        self._logger().log(
            "tool_call",
            trace_id=self._trace_id(),
            phase="end",
            output_summary=_truncate(output),
            duration_ms=duration_ms,
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._logger().log_error(
            "error",
            error,
            trace_id=self._trace_id(),
            phase="tool",
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._llm_start = time.perf_counter()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        duration_ms = int((time.perf_counter() - self._llm_start) * 1000) if self._llm_start else None
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage") or {}
        model = llm_output.get("model_name") or llm_output.get("model") or "unknown"

        session = get_session()
        payload: dict[str, Any] = {
            "model": model,
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "completion_tokens": token_usage.get("completion_tokens"),
            "duration_ms": duration_ms,
        }
        if session.logger and getattr(session.logger, "_events", None) is not None:
            from trans_matching.config import get_agent_log_config

            if get_agent_log_config().log_llm_body:
                generations = response.generations
                if generations and generations[0]:
                    payload["response_preview"] = _truncate(generations[0][0].text)

        session.logger.log("llm_call", trace_id=self._trace_id(), **payload)

        for generation_list in response.generations:
            for generation in generation_list:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if usage:
                    class _Usage:
                        prompt_tokens = usage.get("input_tokens", 0)
                        completion_tokens = usage.get("output_tokens", 0)

                    class _Resp:
                        usage = _Usage()

                    record_chat_completion(_Resp(), model)

    def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        self._agent_step += 1
        self._logger().log(
            "agent_step",
            trace_id=self._trace_id(),
            step=self._agent_step,
            action=getattr(action, "tool", str(action)),
            log=getattr(action, "log", None),
        )

    def on_agent_finish(self, finish: Any, **kwargs: Any) -> None:
        self._logger().log(
            "agent_step",
            trace_id=self._trace_id(),
            step=self._agent_step + 1,
            action="finish",
            log=getattr(finish, "log", None),
        )


def _truncate(value: Any, max_len: int = 500) -> str:
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text
