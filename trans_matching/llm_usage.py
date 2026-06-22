from __future__ import annotations

from dataclasses import dataclass, field

from trans_matching.config import estimate_openai_cost_usd

_DEFAULT_TOTALS = None


@dataclass
class LlmUsageTotals:
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def estimated_cost_usd(self) -> float | None:
        if self.requests == 0:
            return None

        total = 0.0
        has_pricing = False
        for model, (prompt_tokens, completion_tokens) in self.by_model.items():
            pricing = estimate_openai_cost_usd(model, prompt_tokens, completion_tokens)
            if pricing is None:
                continue
            has_pricing = True
            total += pricing

        return total if has_pricing else None


def reset_llm_usage() -> None:
    global _DEFAULT_TOTALS
    _DEFAULT_TOTALS = LlmUsageTotals()


def get_llm_usage() -> LlmUsageTotals:
    global _DEFAULT_TOTALS
    if _DEFAULT_TOTALS is None:
        _DEFAULT_TOTALS = LlmUsageTotals()
    return _DEFAULT_TOTALS


def record_chat_completion(response: object, model: str) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        return

    totals = get_llm_usage()
    totals.requests += 1
    totals.prompt_tokens += prompt_tokens
    totals.completion_tokens += completion_tokens

    model_prompt, model_completion = totals.by_model.get(model, (0, 0))
    totals.by_model[model] = (
        model_prompt + prompt_tokens,
        model_completion + completion_tokens,
    )


def format_llm_cost_line() -> str | None:
    usage = get_llm_usage()
    if usage.requests == 0:
        return None

    cost = usage.estimated_cost_usd()
    tokens = (
        f"{usage.prompt_tokens:,} in + {usage.completion_tokens:,} out, "
        f"{usage.requests} chiamate"
    )
    if cost is None:
        return f"n/d ({tokens})"
    return f"${cost:.4f} USD ({tokens})"
