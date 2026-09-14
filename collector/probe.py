"""Probe mode: how often TomTom calls fail, measured without storing a Result.

    python collector/probe.py          one probe run (GitHub Actions, after fetch.py)
    python collector/probe.py check    validate config/probe.yaml (CI)
    python collector/probe.py report   failure rates so far, from probe_calls

Every sizing table in docs/free_tier.md turns on how often a peak-hour call fails, and
nobody has measured it. A probe run makes the collector's own calls, at a tier's real
cadence, for the corridors config/probe.yaml names, and keeps only what each attempt
was: corridor_id, requested_at, http_status, attempt and the latency to the response
headers (probe_calls, migration 0013).

The response body is never read. The connection is closed as soon as the status line
and headers arrive, so no travel time, distance or geometry reaches this code and
nothing TomTom computed is stored. Sahil's reading, not legal advice and put to TomTom
as a question: clause 11.4 prohibits storing Results, the travel-time data, and a status
code is metadata about our own request.

Probing is off until config/probe.yaml names corridors and dates. It never runs while
any corridor is active, it stops at a quota refusal until 00:00 UTC, and it spends the
same Routing allowance as collection: every attempt counts in the daily meter.
"""

import datetime as dt
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backoff import (
    ATTEMPTS,
    QPS_WAIT_SECONDS,
    backoff_delays,
    limit_kind,
    retry_after_seconds,
    retryable,
)
from budget import RETRY_RESERVE, TOMTOM_FREE_MONTHLY, allowance, day_plan
from config import Corridor, Panel, load_panel
from fetch import Pacer, _headers, utc_midnight
from schedule import IST, WINDOWS, due_slot, scheduled_slots
from store import Database, Ledger, iso
from tomtom import route_url

PROBE_PATH = Path(__file__).resolve().parent.parent / "config" / "probe.yaml"
LONGEST_MONTH_DAYS = 31
MAX_WINDOW_DAYS = 31
# A probe spends real calls, so it is held to the most a free month allows a day, not to
# collector/budget.py's daily ceiling, which was set against the wrong allowance.
CAPACITY_PER_DAY = TOMTOM_FREE_MONTHLY // LONGEST_MONTH_DAYS
QUOTA_FOLLOW_UP = timedelta(minutes=2)

# (status or None for no response, response headers, seconds to the headers)
Transport = Callable[[str], tuple[int | None, dict[str, str], float]]
Clock = Callable[[], datetime]
Sleep = Callable[[float], None]


class ProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["A", "B", "C"] = "B"
    first_day: dt.date | None = None
    last_day: dt.date | None = None
    corridors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _window(self) -> "ProbeConfig":
        if not self.corridors:
            return self
        if self.first_day is None or self.last_day is None:
            raise ValueError("a probe that names corridors needs first_day and last_day")
        if self.last_day < self.first_day:
            raise ValueError("last_day is before first_day")
        if (self.last_day - self.first_day).days + 1 > MAX_WINDOW_DAYS:
            raise ValueError(f"a probe runs at most {MAX_WINDOW_DAYS} days")
        if len(set(self.corridors)) != len(self.corridors):
            raise ValueError("a corridor is listed twice")
        return self

    def on(self, day: dt.date) -> bool:
        return bool(self.corridors) and self.first_day <= day <= self.last_day


def load_probe(path: Path = PROBE_PATH) -> ProbeConfig:
    return ProbeConfig.model_validate(yaml.safe_load(path.read_text()) or {})


def check_probe(config: ProbeConfig, panel: Panel) -> list[str]:
    """Why this probe must not run, or nothing."""
    if not config.corridors:
        return []
    problems = []
    declared = {c.id for c in panel.corridors}
    unknown = [c for c in config.corridors if c not in declared]
    if unknown:
        problems.append(f"not declared in config/corridors.yaml: {', '.join(unknown)}")
    active = sorted(c.id for c in panel.active())
    if active:
        problems.append(f"corridors are active ({', '.join(active)}): a probe never runs "
                        "while collection does")
    planned = len(config.corridors) * len(scheduled_slots(config.tier, config.first_day))
    limit = math.floor(CAPACITY_PER_DAY * (1 - RETRY_RESERVE))
    if planned > limit:
        problems.append(f"{planned} first attempts a day; {limit} fit {TOMTOM_FREE_MONTHLY:,} "
                        f"calls in a {LONGEST_MONTH_DAYS}-day month with a {RETRY_RESERVE:.0%} "
                        "retry reserve")
    return problems


def headers_only(url: str, timeout: float = 20.0) -> tuple[int | None, dict[str, str], float]:
    """One GET, closed as soon as its status line and headers arrive: the body is never
    read. (status, headers, seconds to the headers); status None when no response came,
    timed until the failure."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    started = time.monotonic()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status, headers = exc.code, _headers(exc.headers)
        exc.close()
        return status, headers, time.monotonic() - started
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, {}, time.monotonic() - started
    try:
        return response.status, _headers(response.headers), time.monotonic() - started
    finally:
        response.close()


def probe_slot(corridor: Corridor, key: str, transport: Transport, clock: Clock,
               rng: random.Random, sleep: Sleep, pace: Callable[[], None],
               attempts: int = ATTEMPTS) -> tuple[list[dict], bool]:
    """(the rows for one slot's attempts, whether TomTom refused for quota). The retry
    rules are the collector's."""
    delays = backoff_delays(rng, attempts)
    url = route_url(corridor, key)
    rows = []
    for attempt in range(1, attempts + 1):
        pace()
        requested_at = clock()
        status, headers, latency = transport(url)
        rows.append({"corridor_id": corridor.id, "requested_at": iso(requested_at),
                     "attempt": attempt, "http_status": status,
                     "latency_ms": max(0, round(latency * 1000))})
        if status == 200:
            return rows, False
        limit = limit_kind(status, headers, clock())
        if limit == "quota":
            return rows, True
        error = TimeoutError() if status is None else None
        if attempt == attempts or not retryable(status, error):
            return rows, False
        wait = delays[attempt - 1]
        if limit == "qps":
            wait = max(wait, QPS_WAIT_SECONDS, retry_after_seconds(headers, clock()) or 0.0)
        sleep(wait)
    raise AssertionError("unreachable")


def final_quota_refusal(rows: list[dict]) -> bool:
    """Whether a stored 429 ended its slot: no next attempt followed within two minutes.
    probe_calls keeps no reason, so every 429 that was not retried counts as quota, the
    conservative reading."""
    followed = defaultdict(list)
    for r in rows:
        followed[(r["corridor_id"], r["attempt"])].append(datetime.fromisoformat(r["requested_at"]))
    for r in rows:
        if r["http_status"] != 429:
            continue
        at = datetime.fromisoformat(r["requested_at"])
        nexts = followed.get((r["corridor_id"], r["attempt"] + 1), [])
        if not any(timedelta(0) < n - at <= QUOTA_FOLLOW_UP for n in nexts):
            return True
    return False


@dataclass
class ProbeReport:
    slots_due: int = 0
    probed: int = 0
    skipped_existing: int = 0
    skipped_budget: int = 0
    skipped_quota: int = 0
    attempts: int = 0
    quota_refused: bool = False


def run_probe(config: ProbeConfig, panel: Panel, ledger, transport: Transport, key: str,
              clock: Clock, rng: random.Random, sleep: Sleep,
              capacity: int = CAPACITY_PER_DAY) -> ProbeReport:
    report = ProbeReport()
    now = clock()
    day = now.astimezone(IST).date()
    if not config.on(day):
        return report
    problems = check_probe(config, panel)
    if problems:
        raise RuntimeError("; ".join(problems))
    slot = due_slot(config.tier, now)
    if slot is None:
        return report
    report.slots_due = len(config.corridors)
    probed = ledger.probed_since(slot, config.corridors)
    by_id = {c.id: c for c in panel.corridors}
    pending = [by_id[c] for c in config.corridors if c not in probed]
    report.skipped_existing = report.slots_due - len(pending)
    if not pending:
        return report
    if final_quota_refusal(ledger.probe_retries_and_refusals(utc_midnight(now))):
        report.skipped_quota = len(pending)
        return report

    plan = day_plan([config.tier] * len(config.corridors), day)
    day_start = datetime.combine(day, datetime.min.time(), IST)
    used = ledger.attempts_between(day_start, day_start + timedelta(days=1))
    pace = Pacer(clock, sleep)
    for corridor in pending:
        if report.quota_refused:
            report.skipped_quota += 1
            continue
        tokens = allowance(clock(), plan, used, capacity)
        if tokens <= 0:
            report.skipped_budget += 1
            continue
        rows, refused = probe_slot(corridor, key, transport, clock, rng, sleep, pace,
                                   min(ATTEMPTS, tokens))
        ledger.insert_probe_calls(rows)
        used += len(rows)
        report.attempts += len(rows)
        report.probed += 1
        report.quota_refused = report.quota_refused or refused
    return report


def _slot_of(tier: str, moment: datetime) -> tuple[datetime, bool] | None:
    """(the scheduled slot an attempt at `moment` belongs to, whether it is a peak slot)."""
    local_day = moment.astimezone(IST).date()
    candidates = [(slot, spacing) for d in (local_day - timedelta(days=1), local_day)
                  for slot, spacing in scheduled_slots(tier, d) if slot <= moment]
    if not candidates:
        return None
    slot, spacing = max(candidates)
    return (slot, _is_peak(slot)) if moment - slot < spacing else None


def _is_peak(slot: datetime) -> bool:
    local = slot.astimezone(IST).time()
    return any(start <= local < end for start, end in WINDOWS)


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "—"


def _percentile(values: list[int], q: float) -> str:
    if not values:
        return "—"
    ordered = sorted(values)
    return f"{ordered[min(len(ordered) - 1, math.floor(q * len(ordered)))]} ms"


def summarize(rows: list[dict], config: ProbeConfig, through: dt.date) -> list[str]:
    """What the probe has measured over the whole days from first_day through `through`.

    A scheduled slot ends three ways: a 200 on some attempt, a failure after its last
    attempt, or no attempt at all (a collector run GitHub delayed or dropped). The audit
    cannot tell the last two apart, so the rate docs/free_tier.md's breaking points are
    in is slots without a 200 over slots scheduled, both reasons together."""
    last = min(config.last_day, through)
    days = [config.first_day + timedelta(days=i) for i in range((last - config.first_day).days + 1)]
    attempts: dict[tuple[str, datetime], list[dict]] = defaultdict(list)
    for r in rows:
        found = _slot_of(config.tier, datetime.fromisoformat(r["requested_at"]))
        if found:
            attempts[(r["corridor_id"], found[0])].append(r)
    tally = {kind: defaultdict(int) for kind in ("peak", "night")}
    reasons: dict[str, int] = defaultdict(int)
    by_hour: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    latencies = [r["latency_ms"] for r in rows if r["http_status"] == 200]
    for corridor in config.corridors:
        for day in days:
            for slot, _ in scheduled_slots(config.tier, day):
                kind = "peak" if _is_peak(slot) else "night"
                t = tally[kind]
                t["scheduled"] += 1
                tries = attempts.get((corridor, slot), [])
                final = max(tries, key=lambda r: r["attempt"]) if tries else None
                if final is None:
                    t["missed"] += 1
                elif final["http_status"] == 200:
                    t["ok"] += 1
                else:
                    t["failed"] += 1
                    status = final["http_status"]
                    if kind == "peak":
                        reasons["no response" if status is None else
                                "429" if status == 429 else f"{status // 100}xx"] += 1
                t["attempts"] += len(tries)
                if kind == "peak":
                    hour = slot.astimezone(IST).hour
                    by_hour[hour][0] += 1
                    by_hour[hour][1] += final is None or final["http_status"] != 200
    lines = [f"## Probe: {config.first_day} to {last} (IST), tier {config.tier}, "
             f"{len(config.corridors)} corridors", "",
             "| slots | scheduled | no attempt (run missed) | failed after retries | "
             "without a 200 | attempts per slot tried |", "|---|---|---|---|---|---|"]
    for kind in ("peak", "night"):
        t = tally[kind]
        tried = t["scheduled"] - t["missed"]
        lines.append(f"| {kind} | {t['scheduled']} | {_share(t['missed'], t['scheduled'])} | "
                     f"{_share(t['failed'], t['scheduled'])} | "
                     f"{_share(t['missed'] + t['failed'], t['scheduled'])} | "
                     f"{t['attempts'] / tried:.2f} |" if tried else
                     f"| {kind} | {t['scheduled']} | — | — | — | — |")
    hours = ", ".join(f"{h:02d}:00 {_share(bad, n)}" for h, (n, bad) in sorted(by_hour.items()))
    lines += ["", f"Peak slots without a 200, by local hour: {hours}",
              "Why peak slots failed after retries: "
              + (", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "none"),
              f"Latency to the response headers, 200s: median {_percentile(latencies, 0.5)}, "
              f"p95 {_percentile(latencies, 0.95)}",
              "",
              "Compare the peak `without a 200` share with the breaking points in "
              "docs/free_tier.md, which are in the same unit."]
    return lines


def main(argv: list[str]) -> int:
    config = load_probe()
    command = argv[1] if len(argv) > 1 else "run"
    if command == "check":
        problems = check_probe(config, load_panel())
        for problem in problems:
            print(f"::error file=config/probe.yaml::{problem}")
        state = (f"{len(config.corridors)} corridors, {config.first_day} to {config.last_day}"
                 if config.corridors else "off")
        print(f"probe: {state}, {len(problems)} problem(s)")
        return 1 if problems else 0
    if not config.corridors:
        print("probe mode is off: config/probe.yaml names no corridors")
        return 0
    if command == "report":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            print("SUPABASE_URL and SUPABASE_KEY must be set", file=sys.stderr)
            return 2
        start = datetime.combine(config.first_day, datetime.min.time(), IST)
        end = datetime.combine(config.last_day + timedelta(days=1), datetime.min.time(), IST)
        rows = Ledger(Database(url, key)).probe_rows(start, end)
        yesterday = datetime.now(IST).date() - timedelta(days=1)
        if yesterday < config.first_day:
            print("probe has not completed a day yet")
            return 0
        lines = summarize(rows, config, yesterday)
        print("\n".join(lines))
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return 0
    if command != "run":
        print(__doc__, file=sys.stderr)
        return 2
    if not config.on(datetime.now(IST).date()):
        print(f"probe mode is outside its window, {config.first_day} to {config.last_day}")
        return 0
    key = os.environ.get("TOMTOM_API_KEY")
    if not key:
        print("::error::TOMTOM_API_KEY is not set", file=sys.stderr)
        return 1
    report = run_probe(config, load_panel(), Ledger(Database.from_env()), headers_only, key,
                       lambda: datetime.now(UTC), random.Random(), time.sleep)
    print(f"probe: due {report.slots_due}, probed {report.probed}, skipped "
          f"{report.skipped_existing} existing / {report.skipped_budget} budget / "
          f"{report.skipped_quota} quota, attempts {report.attempts}")
    if report.quota_refused:
        print("::error::TomTom refused a probe call for quota; no further probe call until "
              "00:00 UTC", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
