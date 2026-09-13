"""Daily gap and usage alarm: python collector/gaps.py [YYYY-MM-DD]

For one IST day (yesterday by default), compares each active corridor's
scheduled slots with what the ledger holds. A slot with neither a sample nor
a failed_samples row is missing: the dispatcher never ran for it, which is how
GitHub Actions' delayed and dropped schedules show up. Writes gap_reports and
exits non-zero when anything is missing.

It also counts routing calls against TomTom's published monthly allowance, so
the allowance running out is seen days before it shows up as gaps: see
usage_report.

Nothing is ever backfilled. A missing slot stays missing and renders as a gap.
"""

import math
import os
import re
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from budget import CAPACITY_PER_DAY, TOMTOM_FREE_MONTHLY, USAGE_ALARM_SHARE
from schedule import IST, slots_for_day
from store import Database, Ledger, iso

SHOW_SLOTS = 12
STREAK_LOOKBACK_DAYS = 30
QUOTA_HEADER = re.compile(r"rate|limit|quota|remain|retry|usage|credit", re.IGNORECASE)


def expected_slots(corridor: dict, day: date) -> list[datetime]:
    """Slots a corridor owed on `day`: active corridors, from their activation on.
    Status is today's, so a corridor paused today is not owed yesterday's slots."""
    if corridor["status"] != "active" or not corridor.get("activated_at"):
        return []
    activated = datetime.fromisoformat(corridor["activated_at"])
    return [slot for slot in slots_for_day(corridor["tier"], day) if slot >= activated]


def gap_rows(corridors: list[dict], outcomes: dict, day: date) -> list[dict]:
    """outcomes maps (corridor_id, slot) to 'sample' or 'failed'."""
    rows = []
    for corridor in sorted(corridors, key=lambda c: c["id"]):
        slots = expected_slots(corridor, day)
        if not slots:
            continue
        kinds = [outcomes.get((corridor["id"], slot)) for slot in slots]
        missing = [slot for slot, kind in zip(slots, kinds, strict=True) if kind is None]
        rows.append({
            "day": day.isoformat(), "corridor_id": corridor["id"], "tier": corridor["tier"],
            "expected": len(slots), "recorded": kinds.count("sample"),
            "failed": kinds.count("failed"), "missing_slots": missing,
        })
    return rows


def unbroken_days(reports: list[dict], through: date) -> int:
    """Consecutive days ending at `through` on which slots were owed and none is missing."""
    owed: dict[str, int] = defaultdict(int)
    missing: dict[str, int] = defaultdict(int)
    for r in reports:
        owed[r["day"]] += r["expected"]
        missing[r["day"]] += r["missing"]
    streak, day = 0, through
    while owed.get(day.isoformat(), 0) > 0 and missing[day.isoformat()] == 0:
        streak += 1
        day -= timedelta(days=1)
    return streak


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """The UTC calendar month holding `now`. TomTom does not document when its monthly
    allowance resets, so UTC is an assumption."""
    now = now.astimezone(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    end = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def quota_headers(headers: dict | None) -> dict:
    """Headers whose names suggest TomTom reporting its own count or limit."""
    return {k: v for k, v in (headers or {}).items() if QUOTA_HEADER.search(k)}


def usage_report(now: datetime, month_attempts: int, day: date, day_attempts: int,
                 refusals: int, latest: dict | None, allowance: int = TOMTOM_FREE_MONTHLY,
                 capacity: int = CAPACITY_PER_DAY,
                 share: float = USAGE_ALARM_SHARE) -> tuple[list[str], list[str], list[str]]:
    """(summary lines, warnings, errors) for routing calls against TomTom's allowance.

    Errors, which fail the job:
      - month to date at `share` of the published allowance or more
      - any quota refusal from TomTom this month: its count ran out before ours did
      - the IST day over the collector's own ceiling: the governor and the meter disagree
    Warning: this month's rate, carried to month end, reaches the allowance.

    Our count is every HTTP attempt the collector recorded. TomTom documents no header
    carrying its own count; any header that looks like one is printed beside ours."""
    start, end = month_bounds(now)
    elapsed = (now - start) / (end - start)
    projected = math.ceil(month_attempts / elapsed) if elapsed > 0 else month_attempts
    alarm = math.floor(allowance * share)
    lines = [
        f"## Routing calls, {start:%B %Y} (UTC) to {now:%Y-%m-%d %H:%M} UTC", "",
        "| measure | calls |", "|---|---|",
        f"| attempts this month, as the collector recorded them | {month_attempts} |",
        f"| carried to month end at this month's rate | {projected} |",
        f"| TomTom's published free allowance (reset time undocumented) | {allowance} |",
        f"| alarm at {share:.0%} | {alarm} |",
        f"| attempts on {day} (IST), against the collector's own ceiling of {capacity} "
        f"| {day_attempts} |",
        f"| quota refusals from TomTom this month | {refusals} |", "",
    ]
    reported = quota_headers(latest and latest.get("headers"))
    if latest is None:
        lines.append("TomTom's own count: no response headers kept yet.")
    elif reported:
        shown = ", ".join(f"{k}: {v}" for k, v in sorted(reported.items()))
        lines.append(f"TomTom's own count, latest response ({latest['observed_at']}): {shown}")
    else:
        lines.append(f"TomTom's own count: not reported. The latest kept response "
                     f"({latest['observed_at']}) carries no quota or rate-limit header.")

    warnings, errors = [], []
    if month_attempts >= alarm:
        errors.append(f"{month_attempts} routing calls this UTC month: "
                      f"{month_attempts / allowance:.0%} of TomTom's published free allowance "
                      f"of {allowance}")
    elif projected >= allowance:
        warnings.append(f"at this month's rate the collector makes about {projected} routing "
                        f"calls by month end, over TomTom's published free allowance of "
                        f"{allowance}")
    if refusals:
        errors.append(f"TomTom refused {refusals} calls for quota this UTC month")
    if day_attempts > capacity:
        errors.append(f"{day_attempts} attempts on {day} (IST), over the collector's own "
                      f"ceiling of {capacity}: the budget governor and the meter disagree")
    return lines, warnings, errors


def check_usage(db: Database, day: date, now: datetime) -> tuple[list[str], list[str], list[str]]:
    ledger = Ledger(db)
    month_start, _ = month_bounds(now)
    day_start = datetime.combine(day, time.min, IST)
    _, refusals = db.request("GET", "failed_samples", [
        ("select", "seq"), ("error_class", "eq.quota_exhausted"),
        ("requested_at", f"gte.{iso(month_start)}"),
    ])
    _, latest = db.request("GET", "tomtom_responses", [
        ("select", "observed_at,headers"), ("order", "observed_at.desc"), ("limit", "1"),
    ])
    return usage_report(now, ledger.attempts_between(month_start, now), day,
                        ledger.attempts_between(day_start, day_start + timedelta(days=1)),
                        len(refusals or []), (latest or [None])[0])


def emit(lines: list[str]) -> None:
    print("\n".join(lines))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main(argv: list[str]) -> int:
    now = datetime.now(UTC)
    yesterday = now.astimezone(IST).date() - timedelta(1)
    day = date.fromisoformat(argv[1]) if len(argv) > 1 else yesterday
    db = Database.from_env()

    usage_lines, usage_warnings, usage_errors = check_usage(db, day, now)
    emit(usage_lines)
    for warning in usage_warnings:
        print(f"::warning::{warning}")
    for error in usage_errors:
        print(f"::error::{error}")

    _, corridors = db.request("GET", "corridors", [("select", "id,tier,status,activated_at")])
    owed = [c["id"] for c in corridors or [] if expected_slots(c, day)]
    if not owed:
        print(f"{day}: no active corridor owed a slot")
        return 1 if usage_errors else 0
    start = datetime.combine(day, time.min, IST)
    window = [("corridor_id", f"in.({','.join(owed)})"),
              ("scheduled_slot", f"gte.{iso(start)}"),
              ("scheduled_slot", f"lt.{iso(start + timedelta(days=1))}")]
    outcomes = {}
    for table, kind in (("samples", "sample"), ("failed_samples", "failed")):
        for row in db.select_all(table, [("select", "corridor_id,scheduled_slot"), *window]):
            outcomes[(row["corridor_id"], datetime.fromisoformat(row["scheduled_slot"]))] = kind

    rows = gap_rows(corridors or [], outcomes, day)
    checked_at = iso(now)
    db.request("POST", "gap_reports", [("on_conflict", "day,corridor_id")], body=[
        {**{k: v for k, v in r.items() if k != "missing_slots"},
         "missing": len(r["missing_slots"]), "checked_at": checked_at}
        for r in rows
    ], prefer="resolution=merge-duplicates,return=minimal")

    _, history = db.request("GET", "gap_reports", [
        ("select", "day,expected,missing"),
        ("day", f"gte.{(day - timedelta(days=STREAK_LOOKBACK_DAYS)).isoformat()}"),
        ("day", f"lte.{day.isoformat()}"),
    ])
    streak = unbroken_days(history or [], day)

    lines = ["", f"## Gaps for {day} (IST)", "", "| corridor | tier | expected | recorded | failed "
             "| missing |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['corridor_id']} | {r['tier']} | {r['expected']} | {r['recorded']} | "
              f"{r['failed']} | {len(r['missing_slots'])} |" for r in rows]
    lines += ["", f"Unbroken days through {day}: {streak}"]
    emit(lines)

    gaps = [r for r in rows if r["missing_slots"]]
    for r in gaps:
        first = r["missing_slots"][:SHOW_SLOTS]
        shown = ", ".join(s.astimezone(IST).strftime("%H:%M") for s in first)
        more = len(r["missing_slots"]) - SHOW_SLOTS
        print(f"::error::{r['corridor_id']} missed {len(r['missing_slots'])} of {r['expected']} "
              f"slots on {day}: {shown}{f' and {more} more' if more > 0 else ''} IST")
    for r in rows:
        if r["failed"]:
            print(f"::warning::{r['corridor_id']}: {r['failed']} slots failed on {day}")
    return 1 if gaps or usage_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
