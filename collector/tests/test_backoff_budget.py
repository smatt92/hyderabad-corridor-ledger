import random
import urllib.error
from datetime import date, datetime, time

import pytest

from backoff import backoff_delays, error_class, retryable
from budget import allowance, check_fits, day_plan
from schedule import IST

DAY = date(2026, 9, 14)


def ist(h, m):
    return datetime.combine(DAY, time(h, m), IST)


def test_full_jitter_delays_are_bounded_and_reproducible():
    delays = backoff_delays(random.Random(7), attempts=3, base=2.0, cap=20.0)
    assert len(delays) == 2
    assert 0 <= delays[0] <= 2.0 and 0 <= delays[1] <= 4.0
    assert delays == backoff_delays(random.Random(7), attempts=3, base=2.0, cap=20.0)
    assert max(backoff_delays(random.Random(1), attempts=8, base=2.0, cap=20.0)) <= 20.0


def test_error_classes_and_what_is_retried():
    assert (error_class(429, None), retryable(429, None)) == ("rate_limited", True)
    assert (error_class(503, None), retryable(503, None)) == ("upstream_5xx", True)
    assert (error_class(403, None), retryable(403, None)) == ("client_403", False)
    assert (error_class(None, TimeoutError()), retryable(None, TimeoutError())) == ("timeout", True)
    refused = urllib.error.URLError(ConnectionRefusedError())
    assert (error_class(None, refused), retryable(None, refused)) == ("connection", True)
    assert error_class(None, urllib.error.URLError(TimeoutError())) == "timeout"
    assert error_class(None, ValueError("bad json")) == "ValueError"
    assert not retryable(None, ValueError("bad json"))


def test_plan_counts_one_call_per_corridor_per_slot():
    plan = dict(day_plan(["A", "A", "B"], DAY))
    assert sum(plan.values()) == 42 + 42 + 25
    assert plan[ist(0, 30)] == 3   # night slots: every tier
    assert plan[ist(6, 30)] == 3   # all tiers
    assert plan[ist(6, 45)] == 2   # Tier A only


def test_panel_that_cannot_fit_the_budget_fails_at_load():
    with pytest.raises(ValueError, match="2100 calls/day"):
        check_fits(day_plan(["A"] * 50, DAY), capacity=2400, reserve=0.15)  # limit 2040
    assert check_fits(day_plan(["A"] * 45, DAY), capacity=2400, reserve=0.15) == 1890


def test_morning_retries_cannot_starve_the_evening():
    plan = day_plan(["A"] * 10, DAY)  # 42 slots x 10 corridors = 420 planned, capacity 500
    # by 10:15, 8 night + 16 morning slots are due: 240 planned -> floor(500 * 240/420) = 285
    assert allowance(ist(10, 15), plan, used_today=285, capacity=500) == 0
    # the morning spent every token it was given; the evening's share still arrives
    # 18:00: 8 + 16 + 7 slots = 310 planned -> floor(500 * 310/420) = 369, minus 285 spent
    assert allowance(ist(18, 0), plan, used_today=285, capacity=500) == 84
    # end of day: all 500 released
    assert allowance(ist(20, 45), plan, used_today=285, capacity=500) == 215


def test_allowance_formula_by_hand():
    plan = [(ist(1, 0), 10), (ist(2, 0), 30)]
    assert allowance(ist(0, 59), plan, used_today=0, capacity=100) == 0
    assert allowance(ist(1, 0), plan, used_today=0, capacity=100) == 25    # floor(100 * 10/40)
    assert allowance(ist(1, 30), plan, used_today=20, capacity=100) == 5
    assert allowance(ist(2, 0), plan, used_today=20, capacity=100) == 80
    assert allowance(ist(2, 0), [], used_today=0) == 0
