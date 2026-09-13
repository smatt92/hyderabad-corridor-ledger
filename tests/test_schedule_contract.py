"""metrics.schedule must count against exactly the slots the collector measures."""

import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd

from metrics import schedule

COLLECTOR_SCHEDULE = Path(__file__).parent.parent / "collector" / "schedule.py"


def collector_schedule():
    spec = importlib.util.spec_from_file_location("collector_schedule", COLLECTOR_SCHEDULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metrics_and_collector_share_one_schedule():
    collector = collector_schedule()
    for tier in ("A", "B", "C"):
        for day in (date(2026, 9, 14), date(2026, 12, 31), date(2027, 3, 1)):
            theirs = [pd.Timestamp(slot) for slot in collector.slots_for_day(tier, day)]
            assert list(schedule.day_slots(tier, day)) == theirs, (tier, day)


def test_slots_between_starts_at_the_slot_the_first_call_answered():
    first = pd.Timestamp("2026-09-14 08:04", tz="Asia/Kolkata").tz_convert("UTC")
    last = pd.Timestamp("2026-09-14 17:00", tz="Asia/Kolkata").tz_convert("UTC")
    local = schedule.slots_between("B", first, last).tz_convert("Asia/Kolkata")
    assert local[0] == pd.Timestamp("2026-09-14 08:00", tz="Asia/Kolkata")
    assert [t.strftime("%H:%M") for t in local] == [
        "08:00", "08:30", "09:00", "09:30", "10:00", "16:30", "17:00"]
