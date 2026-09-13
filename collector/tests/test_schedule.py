from datetime import UTC, date, datetime, time

import pytest

from schedule import IST, due_slot, slots_for_day

DAY = date(2026, 9, 14)


def ist(h, m, day=DAY):
    return datetime.combine(day, time(h, m), IST)


def local(slots):
    return [s.astimezone(IST).strftime("%H:%M") for s in slots]


def test_tier_a_slots():
    slots = slots_for_day("A", DAY)
    # night 00:00..03:30 = 8, morning 06:30..10:15 = 16, evening 16:30..20:45 = 18
    assert len(slots) == 42
    names = local(slots)
    assert names[:9] == ["00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
                         "06:30"]
    assert "04:00" not in names and "10:30" not in names and "21:00" not in names  # half-open
    assert names[-1] == "20:45"


def test_tiers_b_and_c_slots():
    # night 8, morning 06:30..10:00 = 8, evening 16:30..20:30 = 9
    assert len(slots_for_day("B", DAY)) == 25
    assert slots_for_day("B", DAY) == slots_for_day("C", DAY)


def test_slots_are_utc_instants():
    assert slots_for_day("A", DAY)[0] == datetime(2026, 9, 13, 18, 30, tzinfo=UTC)  # 00:00 IST
    assert slots_for_day("A", DAY)[8] == datetime(2026, 9, 14, 1, 0, tzinfo=UTC)   # 06:30 IST


def test_late_run_collects_the_latest_slot_within_its_spacing():
    assert due_slot("A", ist(8, 0)) == ist(8, 0)
    assert due_slot("A", ist(8, 14)) == ist(8, 0)      # 14 min late, Tier A spacing 15
    assert due_slot("B", ist(8, 29)) == ist(8, 0)      # 29 min late, Tier B spacing 30
    assert due_slot("A", ist(3, 45)) == ist(3, 30)     # night slots are 30 min apart for every tier


def test_stale_slot_is_a_gap_never_collected_late():
    assert due_slot("A", ist(10, 31)) is None          # last morning slot 10:15, 16 min ago
    assert due_slot("C", ist(4, 5)) is None            # last night slot 03:30, 35 min ago
    assert due_slot("A", ist(12, 0)) is None


def test_just_after_midnight():
    assert due_slot("C", ist(0, 5)) == ist(0, 0)
    assert due_slot("B", ist(23, 59)) is None          # yesterday's 20:30 is long stale


def test_due_slot_requires_timezone():
    with pytest.raises(ValueError):
        due_slot("A", datetime(2026, 9, 14, 8, 0))
