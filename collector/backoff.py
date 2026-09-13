"""Retries: exponential backoff with full jitter.

Each wait is drawn uniformly from [0, min(cap, base * 2^attempt)], so many
corridors retrying after the same upstream failure spread out instead of
retrying in lockstep (Brooker, "Exponential Backoff and Jitter", 2015).
Every attempt, retries included, spends a budget token.
"""

import email.utils
import random
import urllib.error
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

ATTEMPTS = 3
BASE_SECONDS = 2.0
CAP_SECONDS = 20.0
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
QPS_WAIT_SECONDS = 1.0
SHORT_RETRY_AFTER_SECONDS = 60.0

LimitKind = Literal["qps", "quota"]


def retry_after_seconds(headers: Mapping[str, str], now: datetime) -> float | None:
    """Seconds a Retry-After header asks for, as delta-seconds or an HTTP date. None when
    absent or unreadable."""
    value = (headers.get("retry-after") or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


def limit_kind(status: int | None, headers: Mapping[str, str], now: datetime) -> LimitKind | None:
    """What a 429 means. None for any other status.

    TomTom returns 429 both for "too many requests in a given amount of time" and
    "when limits are exceeded", and documents no body or header that tells the two
    apart, Retry-After included (docs.tomtom.com, read 2026-09-14). They need opposite
    handling: a QPS refusal clears in about a second, a quota refusal lasts until the
    allowance resets, and retrying it only spends calls. A Retry-After of a minute or
    less is read as QPS. Anything else, including no Retry-After, is read as quota:
    the conservative error costs the rest of the UTC day's slots, the other one
    burns calls against an exhausted allowance."""
    if status != 429:
        return None
    wait = retry_after_seconds(headers, now)
    return "qps" if wait is not None and wait <= SHORT_RETRY_AFTER_SECONDS else "quota"


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
