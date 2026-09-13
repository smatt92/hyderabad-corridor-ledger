"""Daily gap alarm: python collector/gaps.py [YYYY-MM-DD]

For one IST day (yesterday by default), compares each active corridor's
scheduled slots with what the ledger holds. A slot with neither a sample nor
a failed_samples row is missing: the dispatcher never ran for it, which is how
GitHub Actions' delayed and dropped schedules show up. Writes gap_reports and
exits non-zero when anything is missing.

Nothing is ever backfilled. A missing slot stays missing and renders as a gap.
"""

import os
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from schedule import IST, slots_for_day
from store import Database, iso

SHOW_SLOTS = 12
STREAK_LOOKBACK_DAYS = 30


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


def main(argv: list[str]) -> int:
    day = date.fromisoformat(argv[1]) if len(argv) > 1 else datetime.now(IST).date() - timedelta(1)
    db = Database.from_env()
    _, corridors = db.request("GET", "corridors", [("select", "id,tier,status,activated_at")])
    owed = [c["id"] for c in corridors or [] if expected_slots(c, day)]
    if not owed:
        print(f"{day}: no active corridor owed a slot")
        return 0
    start = datetime.combine(day, time.min, IST)
    window = [("corridor_id", f"in.({','.join(owed)})"),
              ("scheduled_slot", f"gte.{iso(start)}"),
              ("scheduled_slot", f"lt.{iso(start + timedelta(days=1))}")]
    outcomes = {}
    for table, kind in (("samples", "sample"), ("failed_samples", "failed")):
        for row in db.select_all(table, [("select", "corridor_id,scheduled_slot"), *window]):
            outcomes[(row["corridor_id"], datetime.fromisoformat(row["scheduled_slot"]))] = kind

    rows = gap_rows(corridors or [], outcomes, day)
    checked_at = iso(datetime.now(UTC))
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

    lines = [f"## Gaps for {day} (IST)", "", "| corridor | tier | expected | recorded | failed "
             "| missing |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['corridor_id']} | {r['tier']} | {r['expected']} | {r['recorded']} | "
              f"{r['failed']} | {len(r['missing_slots'])} |" for r in rows]
    lines += ["", f"Unbroken days through {day}: {streak}"]
    print("\n".join(lines))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

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
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
