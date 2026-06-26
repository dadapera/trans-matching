from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

from trans_matching.paths import AGENT_LOG_DIR, ROOT

load_dotenv(ROOT / ".env")


class ExpediaMatcherMode(str, Enum):
    REGEX = "regex"
    LLM = "llm"


class MatcherMode(str, Enum):
    LEGACY = "legacy"
    AGENT = "agent"


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str
    base_url: str | None = None


@dataclass(frozen=True)
class AgentConfig:
    max_iterations: int
    date_window_days: int
    rate_limit_max_retries: int
    txn_delay_seconds: float


@dataclass(frozen=True)
class AgentLogConfig:
    level: str
    log_dir: Path
    log_llm_body: bool
    log_email_body: bool


@dataclass(frozen=True)
class MscEmailConfig:
    from_addresses: tuple[str, ...]


def get_expedia_matcher_mode() -> ExpediaMatcherMode:
    raw = os.getenv("EXPEDIA_MATCHER", "regex").strip().lower()
    if raw in ("llm", "openai"):
        return ExpediaMatcherMode.LLM
    return ExpediaMatcherMode.REGEX


def get_openai_config() -> OpenAIConfig:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY richiesta")
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAIConfig(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17").strip(),
        base_url=base_url,
    )


def get_matcher_mode() -> MatcherMode:
    raw = os.getenv("MATCHER_MODE", "legacy").strip().lower()
    if raw == "agent":
        return MatcherMode.AGENT
    return MatcherMode.LEGACY


def get_agent_config() -> AgentConfig:
    try:
        max_iterations = int(os.getenv("AGENT_MAX_ITERATIONS", "12"))
    except ValueError:
        max_iterations = 12
    try:
        date_window_days = int(os.getenv("AGENT_DATE_WINDOW_DAYS", "7"))
    except ValueError:
        date_window_days = 7
    try:
        rate_limit_max_retries = int(os.getenv("AGENT_RATE_LIMIT_MAX_RETRIES", "8"))
    except ValueError:
        rate_limit_max_retries = 8
    try:
        txn_delay_seconds = float(os.getenv("AGENT_TXN_DELAY_SECONDS", "0"))
    except ValueError:
        txn_delay_seconds = 0.0
    return AgentConfig(
        max_iterations=max(1, max_iterations),
        date_window_days=max(1, date_window_days),
        rate_limit_max_retries=max(0, rate_limit_max_retries),
        txn_delay_seconds=max(0.0, txn_delay_seconds),
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_agent_log_config() -> AgentLogConfig:
    return AgentLogConfig(
        level=os.getenv("AGENT_LOG_LEVEL", "INFO").strip().upper(),
        log_dir=Path(os.getenv("AGENT_LOG_DIR", str(AGENT_LOG_DIR))),
        log_llm_body=_env_bool("AGENT_LOG_LLM_BODY"),
        log_email_body=_env_bool("AGENT_LOG_EMAIL_BODY"),
    )


def get_msc_email_config() -> MscEmailConfig:
    raw_from = os.getenv("MSC_EMAIL_FROM", "").strip()
    addresses = tuple(
        part.strip() for part in raw_from.split(",") if part.strip()
    ) or ("msc-booking.no-reply@msccrociere.it",)
    return MscEmailConfig(
        from_addresses=addresses,
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
    "gpt-5.4-mini": (0.75, 4.50),
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
