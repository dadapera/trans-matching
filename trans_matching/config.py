from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

from trans_matching.paths import ROOT

load_dotenv(ROOT / ".env")


class ExpediaMatcherMode(str, Enum):
    REGEX = "regex"
    LLM = "llm"


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str


def get_expedia_matcher_mode() -> ExpediaMatcherMode:
    raw = os.getenv("EXPEDIA_MATCHER", "regex").strip().lower()
    if raw in ("llm", "openai"):
        return ExpediaMatcherMode.LLM
    return ExpediaMatcherMode.REGEX


def get_openai_config() -> OpenAIConfig:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY richiesta quando EXPEDIA_MATCHER=llm")
    return OpenAIConfig(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
    )


def get_expedia_llm_batch_size() -> int:
    raw = os.getenv("EXPEDIA_LLM_BATCH_SIZE", "8").strip()
    try:
        size = int(raw)
    except ValueError:
        size = 8
    return max(1, min(size, 20))


# USD per 1M token (input, output)
_DEFAULT_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
}


def _pricing_for_model(model: str) -> tuple[float, float] | None:
    input_price = os.getenv("OPENAI_PRICE_INPUT_PER_1M", "").strip()
    output_price = os.getenv("OPENAI_PRICE_OUTPUT_PER_1M", "").strip()
    if input_price and output_price:
        try:
            return float(input_price), float(output_price)
        except ValueError:
            pass

    for prefix, prices in sorted(
        _DEFAULT_OPENAI_PRICING.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if model.startswith(prefix):
            return prices
    return None


def estimate_openai_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    pricing = _pricing_for_model(model)
    if pricing is None:
        return None
    input_per_m, output_per_m = pricing
    return (prompt_tokens * input_per_m + completion_tokens * output_per_m) / 1_000_000
