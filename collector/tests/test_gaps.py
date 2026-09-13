from datetime import UTC, date, datetime, time, timedelta

from gaps import (
    expected_slots,
    gap_rows,
    length_drift,
    month_bounds,
    quota_headers,
    reroute_errors,
    unbroken_days,
    usage_report,
)
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


NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)        # exactly half of September gone


def usage(month=2000, day=100, refusals=0, latest=None, now=NOW):
    return usage_report(now, month, DAY, day, refusals, latest)


def test_a_quiet_month_raises_nothing_and_says_tomtom_reports_no_count():
    lines, warnings, errors = usage(latest={"observed_at": "2026-09-15T02:30:00Z",
                                            "headers": {"tracking-id": "t", "content-type": "x"}})
    assert (warnings, errors) == ([], [])
    assert "| attempts this month, as the collector recorded them | 2000 |" in lines
    assert "| carried to month end at this month's rate | 4000 |" in lines
    assert any("not reported" in line for line in lines)


def test_warns_when_this_months_rate_reaches_the_allowance():
    assert usage(month=9998)[1:] == ([], [])
    _, warnings, errors = usage(month=10_000)            # 10,000 at half the month
    assert errors == [] and "about 20000 routing calls by month end" in warnings[0]


def test_fails_at_eighty_percent_of_the_allowance():
    assert usage(month=15_999)[2] == []
    _, warnings, errors = usage(month=16_000)
    assert warnings == [] and errors == [
        "16000 routing calls this UTC month: 80% of TomTom's published free allowance of 20000"]


def test_fails_on_any_quota_refusal_and_when_the_governor_lets_too_much_through():
    assert usage(refusals=1)[2] == ["TomTom refused 1 calls for quota this UTC month"]
    assert usage(day=2400)[2] == []
    assert "governor and the meter disagree" in usage(day=2401)[2][0]


def test_headers_that_look_like_tomtoms_own_count_are_shown_beside_ours():
    latest = {"observed_at": "2026-09-15T02:30:00Z",
              "headers": {"x-ratelimit-remaining": "12", "retry-after": "1", "tracking-id": "t"}}
    lines, _, _ = usage(latest=latest)
    assert any(line.endswith("retry-after: 1, x-ratelimit-remaining: 12") for line in lines)
    assert quota_headers(None) == {}


def test_months_are_utc_calendar_months():
    assert month_bounds(datetime(2026, 12, 31, 23, 0, tzinfo=IST)) == (
        datetime(2026, 12, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    early_october_ist = datetime(2026, 10, 1, 3, 0, tzinfo=IST)     # still September in UTC
    assert month_bounds(early_october_ist)[0] == datetime(2026, 9, 1, tzinfo=UTC)


def test_the_latest_compared_refetch_decides_and_retired_corridors_are_left_alone():
    def refetch(cid, at, matched, deviation=4.0, change=0.0):
        return {"corridor_id": cid, "checked_at": at, "matched": matched,
                "max_deviation_m": deviation, "length_change": change}

    checks = [refetch("a", "2026-09-14T01:00:00+00:00", False, 212.0, 0.034),
              refetch("a", "2026-09-07T01:00:00+00:00", True),
              refetch("b", "2026-09-13T01:00:00+00:00", True),
              refetch("b", "2026-09-06T01:00:00+00:00", False),     # older than b's latest
              refetch("c", "2026-09-12T01:00:00+00:00", False)]
    corridors = [{"id": "a", "status": "active"}, {"id": "b", "status": "active"},
                 {"id": "c", "status": "retired"}]
    (error,) = reroute_errors(checks, corridors)
    assert error.startswith("a: TomTom's road for this corridor changed at 2026-09-14T01:00:00")
    assert "max deviation 212 m, length +3.4%" in error


def test_samples_whose_length_strays_from_the_stored_road_are_warned_about():
    samples = [{"corridor_id": "a", "length_m": n} for n in (6100, 6120, 6400, 6100)]
    samples += [{"corridor_id": "b", "length_m": 5000}, {"corridor_id": "z", "length_m": 1}]
    (warning,) = length_drift(samples, {"a": 6100, "b": 5000}, DAY)
    assert warning.startswith(
        "a: 1 of 4 samples on 2026-09-14 (IST) measured a length more than 2%")
