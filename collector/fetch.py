"""One collector run: python collector/fetch.py

Runs every five minutes from GitHub Actions, never on Vercel. For each active
corridor with a slot due, it measures that slot once:

  1. Skip the slot if it already has an outcome (idempotency by slot).
  2. Spend a budget token per HTTP attempt; stop when the bucket is empty.
  3. Space HTTP attempts at least MIN_SPACING_SECONDS apart.
  4. Retry timeouts, connection errors, a short-wait 429 and 5xx, three
     attempts, with full-jitter backoff.
  5. Stop on a quota refusal: no retry, and no further call until 00:00 UTC.
  6. Record exactly one outcome: a sample, or a failed_samples row with its
     error class. A failure is never silently dropped.

Every header TomTom sends on the run's first response, and on every 403 and
429, goes to tomtom_responses. The bucket counts our calls; those headers are
the only place TomTom's own count could show up.

A response carrying route geometry is recorded as a failure and then fails
the run loudly. So does refusing to start on tables that already hold rows
before any collector run exists: the chain must begin at the genuine first row.
A run with nothing left to measure writes nothing, not even a run row.
"""

import contextlib
import gzip
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from backoff import (
    ATTEMPTS,
    QPS_WAIT_SECONDS,
    LimitKind,
    backoff_delays,
    error_class,
    limit_kind,
    retry_after_seconds,
    retryable,
)
from budget import CAPACITY_PER_DAY, allowance, check_fits, day_plan
from config import Corridor, Panel, load_panel
from schedule import IST, due_slot
from store import Database, Ledger, iso
from tomtom import GeometryLeak, compress, parse_summary, redact, route_url

MAX_BODY_BYTES = 1_000_000
DETAIL_BYTES = 2000
# At most one call a second. TomTom's default Routing limit is 5 QPS (docs.tomtom.com
# QPS limits, read 2026-09-14). One collector run at a time (collector.yml's
# concurrency group) makes this a ceiling for the whole project.
MIN_SPACING_SECONDS = 1.0
KEEP_HEADERS_FOR = frozenset({403, 429})
HEADERS_NOT_KEPT = frozenset({"set-cookie"})
HEADER_VALUE_CHARS = 256

Transport = Callable[[str], tuple[int, dict[str, str], bytes]]
Clock = Callable[[], datetime]
Sleep = Callable[[float], None]


def _headers(message) -> dict[str, str]:
    """Lowercased names; a repeated header's values joined as HTTP allows."""
    headers: dict[str, str] = {}
    for name, value in message.items() if message is not None else ():
        name = name.lower()
        headers[name] = f"{headers[name]}, {value}" if name in headers else value
    return headers


def http_get(url: str, timeout: float = 20.0) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _headers(response.headers), response.read(MAX_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        return exc.code, _headers(exc.headers), exc.read(MAX_BODY_BYTES)


class Pacer:
    """Holds each HTTP attempt until `spacing` seconds after the previous one."""

    def __init__(self, clock: Clock, sleep: Sleep, spacing: float = MIN_SPACING_SECONDS):
        self.clock, self.sleep, self.spacing = clock, sleep, spacing
        self.last: datetime | None = None

    def __call__(self) -> None:
        if self.last is not None:
            wait = self.spacing - (self.clock() - self.last).total_seconds()
            if wait > 0:
                self.sleep(wait)
        self.last = self.clock()


@dataclass
class Response:
    attempt: int
    observed_at: datetime
    status: int
    headers: dict[str, str]
    limit: LimitKind | None


@dataclass
class Outcome:
    attempts: int
    requested_at: datetime
    sample: dict | None = None
    failure: dict | None = None
    geometry_leak: bool = False
    quota_refused: bool = False
    responses: list[Response] = field(default_factory=list)


def _detail(body: bytes, error: BaseException | None) -> bytes | None:
    """Gzipped evidence for a failure, with any API key redacted."""
    if body:
        text = redact(body[:DETAIL_BYTES].decode(errors="replace"))
    elif error is not None:
        text = redact(f"{type(error).__name__}: {error}")
    else:
        return None
    return gzip.compress(text.encode()[:DETAIL_BYTES], mtime=0)


def measure(corridor: Corridor, key: str, transport: Transport, clock: Clock,
            rng: random.Random, sleep: Sleep, attempts: int = ATTEMPTS,
            pace: Callable[[], None] | None = None) -> Outcome:
    pace = pace or Pacer(clock, sleep)
    delays = backoff_delays(rng, attempts)
    url = route_url(corridor, key)
    first_request = None
    responses: list[Response] = []
    for attempt in range(1, attempts + 1):
        pace()
        requested_at = clock()
        first_request = first_request or requested_at
        status, headers, body, error, limit = None, {}, b"", None, None
        try:
            status, headers, body = transport(url)
        except Exception as exc:  # noqa: BLE001 - every failure is classified and recorded
            error = exc
        if status is not None:
            limit = limit_kind(status, headers, clock())
            responses.append(Response(attempt, requested_at, status, headers, limit))
        if status == 200:
            try:
                summary = parse_summary(body)
                raw_gz = compress(body)
            except GeometryLeak as exc:
                return Outcome(attempt, first_request, failure={
                    "error_class": "geometry_leak", "http_status": 200,
                    "detail_gz": _detail(str(exc).encode(), None)}, geometry_leak=True,
                    responses=responses)
            except ValueError as exc:
                error = exc
            else:
                return Outcome(attempt, requested_at, sample={
                    "http_status": 200, "length_m": summary.length_m,
                    "travel_time_s": summary.travel_time_s,
                    "traffic_delay_s": summary.traffic_delay_s,
                    "no_traffic_travel_time_s": summary.no_traffic_travel_time_s,
                    "historic_travel_time_s": summary.historic_travel_time_s,
                    "raw_gz": raw_gz}, responses=responses)
        if limit == "quota":
            return Outcome(attempt, first_request, failure={
                "error_class": "quota_exhausted", "http_status": status,
                "detail_gz": _detail(body, None)}, quota_refused=True, responses=responses)
        if attempt == attempts or not retryable(None if status == 200 else status, error):
            return Outcome(attempt, first_request, failure={
                "error_class": "parse_error" if status == 200 else error_class(status, error),
                "http_status": status, "detail_gz": _detail(body, error)},
                responses=responses)
        wait = delays[attempt - 1]
        if limit == "qps":
            wait = max(wait, QPS_WAIT_SECONDS, retry_after_seconds(headers, clock()) or 0.0)
        sleep(wait)
    raise AssertionError("unreachable")


def response_row(response: Response, corridor_id: str, run_id: str) -> dict:
    """A tomtom_responses row. Values are redacted and capped; cookies are not kept."""
    headers = {
        name: "not kept" if name in HEADERS_NOT_KEPT else redact(value)[:HEADER_VALUE_CHARS]
        for name, value in sorted(response.headers.items())
    }
    kept_for_status = response.status in KEEP_HEADERS_FOR
    return {
        "collector_run": run_id, "corridor_id": corridor_id,
        "observed_at": iso(response.observed_at), "attempt": response.attempt,
        "http_status": response.status,
        "reason": f"status_{response.status}" if kept_for_status else "first_response",
        "limit_kind": response.limit, "headers": headers,
    }


def _bytea(value: bytes | None) -> str | None:
    return None if value is None else "\\x" + value.hex()


def utc_midnight(moment: datetime) -> datetime:
    return datetime.combine(moment.astimezone(UTC).date(), datetime.min.time(), UTC)


@dataclass
class Report:
    slots_due: int = 0
    recorded: int = 0
    failed: int = 0
    skipped_existing: int = 0
    skipped_budget: int = 0
    skipped_quota: int = 0
    attempts: int = 0
    quota_refused: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        if self.problems:
            return "failed"
        if self.quota_refused or self.skipped_quota:
            return "quota_exhausted"
        return "budget_exhausted" if self.skipped_budget else "ok"

    def as_row(self) -> dict:
        return {
            "outcome": self.outcome, "slots_due": self.slots_due, "recorded": self.recorded,
            "failed": self.failed, "skipped_existing": self.skipped_existing,
            "skipped_budget": self.skipped_budget, "skipped_quota": self.skipped_quota,
            "attempts": self.attempts, "detail": "; ".join(self.problems)[:2000] or None,
        }


def run(panel: Panel, ledger, transport: Transport, key: str, clock: Clock,
        rng: random.Random, sleep: Sleep, run_id: str, sha: str | None,
        capacity: int = CAPACITY_PER_DAY) -> Report:
    now = clock()
    active = panel.active()
    report = Report()
    due = sorted(((c, slot) for c in active if (slot := due_slot(c.tier, now)) is not None),
                 key=lambda item: (item[1], item[0].id))
    report.slots_due = len(due)
    if not due:
        return report

    if ledger.count("collector_runs") == 0 and (
        ledger.count("samples") or ledger.count("failed_samples")
    ):
        raise RuntimeError("samples or failed_samples hold rows but no collector run was ever "
                           "recorded: this is not the genuine first row of the chain")

    ids_by_slot: dict[datetime, list[str]] = {}
    for corridor, slot in due:
        ids_by_slot.setdefault(slot, []).append(corridor.id)
    recorded = {slot: ledger.recorded_corridors(slot, ids) for slot, ids in ids_by_slot.items()}
    pending = []
    for corridor, slot in due:
        if corridor.id in recorded[slot]:
            report.skipped_existing += 1
        else:
            pending.append((corridor, slot))
    if not pending:
        return report

    day = now.astimezone(IST).date()
    plan = day_plan([c.tier for c in active], day)
    check_fits(plan, capacity)
    day_start = datetime.combine(day, datetime.min.time(), IST)
    used = ledger.attempts_between(day_start, day_start + timedelta(days=1))
    # TomTom's allowance reset time is undocumented; a refusal holds until 00:00 UTC,
    # when the first run makes one call to find out whether it has cleared.
    refused = ledger.quota_refused_since(utc_midnight(now))

    ledger.start_run(run_id, sha)
    pace = Pacer(clock, sleep)
    first_kept = False
    try:
        for corridor, slot in pending:
            if refused:
                report.skipped_quota += 1
                continue
            tokens = allowance(clock(), plan, used, capacity)
            if tokens <= 0:
                report.skipped_budget += 1
                continue
            outcome = measure(corridor, key, transport, clock, rng, sleep,
                              min(ATTEMPTS, tokens), pace)
            used += outcome.attempts
            report.attempts += outcome.attempts
            common = {"corridor_id": corridor.id, "scheduled_slot": iso(slot),
                      "requested_at": iso(outcome.requested_at), "attempts": outcome.attempts,
                      "collector_run": run_id, "collector_sha": sha}
            if outcome.sample is not None:
                row = {**common, **outcome.sample, "raw_gz": _bytea(outcome.sample["raw_gz"])}
                if ledger.insert_sample(row):
                    report.recorded += 1
                else:
                    report.skipped_existing += 1
            else:
                failure = outcome.failure or {}
                row = {**common, **failure, "detail_gz": _bytea(failure.get("detail_gz"))}
                if ledger.insert_failure(row):
                    report.failed += 1
                else:
                    report.skipped_existing += 1
                if outcome.geometry_leak:
                    report.problems.append(f"{corridor.id}: route geometry in the response")
            ledger.insert_responses([
                response_row(r, corridor.id, run_id)
                for i, r in enumerate(outcome.responses)
                if r.status in KEEP_HEADERS_FOR or (i == 0 and not first_kept)
            ])
            first_kept = first_kept or bool(outcome.responses)
            if outcome.quota_refused:
                refused = report.quota_refused = True
    except BaseException as exc:
        report.problems.append(f"run aborted: {type(exc).__name__}: {redact(str(exc))[:300]}")
        with contextlib.suppress(Exception):
            ledger.finish_run(run_id, report.as_row())
        raise
    ledger.finish_run(run_id, report.as_row())
    return report


def main() -> int:
    panel = load_panel()
    if not panel.active():
        print("no active corridors: nothing to measure")
        return 0
    key = os.environ.get("TOMTOM_API_KEY")
    if not key:
        print("::error::TOMTOM_API_KEY is not set", file=sys.stderr)
        return 1
    github_run = os.environ.get("GITHUB_RUN_ID", "local")
    run_id = f"{github_run}.{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    report = run(panel, Ledger(Database.from_env()), http_get, key,
                 lambda: datetime.now(UTC), random.Random(), time.sleep, run_id,
                 os.environ.get("GITHUB_SHA"))
    print(f"run {run_id}: due {report.slots_due}, recorded {report.recorded}, "
          f"failed {report.failed}, skipped {report.skipped_existing} existing / "
          f"{report.skipped_budget} budget / {report.skipped_quota} quota, "
          f"attempts {report.attempts}")
    if report.quota_refused:
        print("::error::TomTom refused a call for quota (429 without a short Retry-After). "
              "No further calls until 00:00 UTC; its headers are in tomtom_responses",
              file=sys.stderr)
    elif report.skipped_quota:
        print(f"::warning::{report.skipped_quota} due slots skipped: TomTom refused a call "
              "for quota earlier this UTC day")
    if report.skipped_budget:
        print(f"::warning::{report.skipped_budget} due slots skipped: daily budget exhausted")
    for problem in report.problems:
        print(f"::error::{problem}", file=sys.stderr)
    return 1 if report.problems or report.quota_refused else 0


if __name__ == "__main__":
    sys.exit(main())
