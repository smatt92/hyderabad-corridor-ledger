"""Retries: exponential backoff with full jitter.

Each wait is drawn uniformly from [0, min(cap, base * 2^attempt)], so many
corridors retrying after the same upstream failure spread out instead of
retrying in lockstep (Brooker, "Exponential Backoff and Jitter", 2015).
Every attempt, retries included, spends a budget token.
"""

import random
import urllib.error

ATTEMPTS = 3
BASE_SECONDS = 2.0
CAP_SECONDS = 20.0
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def backoff_delays(
    rng: random.Random, attempts: int = ATTEMPTS, base: float = BASE_SECONDS,
    cap: float = CAP_SECONDS,
) -> list[float]:
    """Waits before attempts 2..attempts."""
    return [rng.uniform(0.0, min(cap, base * 2**i)) for i in range(attempts - 1)]


def error_class(status: int | None, error: BaseException | None) -> str:
    """A stable, coarse label for a failed attempt, recorded with the failure."""
    if isinstance(error, TimeoutError):  # socket.timeout is an alias of TimeoutError
        return "timeout"
    if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
        return "timeout" if isinstance(error.reason, TimeoutError) else "connection"
    if status is None:
        return type(error).__name__ if error else "unknown"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "upstream_5xx"
    if 400 <= status < 500:
        return f"client_{status}"
    return f"http_{status}"


def retryable(status: int | None, error: BaseException | None) -> bool:
    """Retry timeouts, connection failures, 429 and 5xx. A 4xx other than those
    means the request itself is wrong, and repeating it only spends budget."""
    if status is not None:
        return status in RETRYABLE_STATUS
    return error is not None and error_class(None, error) in {"timeout", "connection"}
