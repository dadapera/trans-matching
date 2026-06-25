from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_RETRY_HINT_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def is_rate_limit_error(exc: BaseException) -> bool:
    if exc.__class__.__name__ == "RateLimitError":
        return True
    message = str(exc).lower()
    return "rate_limit" in message or "rate limit" in message or "error code: 429" in message


def rate_limit_wait_seconds(exc: BaseException, attempt: int) -> float:
    match = _RETRY_HINT_RE.search(str(exc))
    if match:
        return float(match.group(1)) + 0.5
    return min(60.0, 1.5**attempt)


def invoke_with_rate_limit_retry(
    func: Callable[[], T],
    *,
    max_retries: int,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except BaseException as exc:
            if not is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            last_exc = exc
            wait = rate_limit_wait_seconds(exc, attempt)
            if on_retry is not None:
                on_retry(attempt + 1, wait, exc)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc
