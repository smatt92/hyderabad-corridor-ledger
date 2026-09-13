from datetime import date, datetime, time, timedelta

from gaps import expected_slots, gap_rows, unbroken_days
from schedule import IST, slots_for_day

DAY = date(2026, 9, 14)


def corridor(cid="c", tier="A", status="active", activated=datetime(2026, 9, 1, tzinfo=IST)):
    return {"id": cid, "tier": tier, "status": status,
            "activated_at": activated.isoformat() if activated else None}


def test_only_active_corridors_owe_slots_and_only_after_activation():
    assert len(expected_slots(corridor(), DAY)) == 42
    assert len(expected_slots(corridor(tier="B"), DAY)) == 25
    assert expected_slots(corridor(status="paused"), DAY) == []
    assert expected_slots(corridor(activated=None), DAY) == []
    mid_morning = datetime.combine(DAY, time(8, 7), IST)
    owed = expected_slots(corridor(activated=mid_morning), DAY)
    assert owed[0] == datetime.combine(DAY, time(8, 15), IST)
    assert len(owed) == 42 - 8 - 7     # night slots and 06:30..08:00 were before activation


def test_gap_rows_count_samples_failures_and_missing_slots():
    slots = slots_for_day("B", DAY)
    outcomes = {("c", s): "sample" for s in slots[:20]}
    outcomes.update({("c", s): "failed" for s in slots[20:23]})
    outcomes[("c", slots[0] + timedelta(minutes=5))] = "sample"  # not a scheduled slot
    (row,) = gap_rows([corridor(tier="B"), corridor("d", status="draft")], outcomes, DAY)
    assert (row["expected"], row["recorded"], row["failed"]) == (25, 20, 3)
    assert row["missing_slots"] == slots[23:]


def test_unbroken_days_stop_at_a_gap_or_a_day_with_nothing_owed():
    def report(d, expected=42, missing=0):
        return {"day": d.isoformat(), "expected": expected, "missing": missing}

    days = [DAY - timedelta(days=i) for i in range(10)]
    reports = [report(d) for d in days[:8]] + [report(days[8], missing=1)]
    assert unbroken_days(reports, DAY) == 8
    assert unbroken_days(reports + [report(DAY, missing=2)], DAY) == 0
    assert unbroken_days([report(d) for d in days[1:]], DAY) == 0
