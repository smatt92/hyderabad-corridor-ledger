import numpy as np
import pandas as pd
import pytest

from metrics.cells import daily_missingness, hourly_cells
from tests.helpers import parsed

DAY = pd.Timestamp("2026-09-01")

# Corridor a polls every 15 minutes. Local times on 2026-09-01:
#   08:00 ok 600/500   08:15 ok 900/500   08:30 HTTP 429   08:45 ok 1200/520
#   09:00 and 09:15 never attempted (collector run skipped)
#   09:30 ok 700/500
# Corridor b has no cadence: one call at 08:10.
SAMPLES = parsed([
    ("a", "2026-09-01 08:00", 200, 600, 500),
    ("a", "2026-09-01 08:15", 200, 900, 500),
    ("a", "2026-09-01 08:30", 429, None, None),
    ("a", "2026-09-01 08:45", 200, 1200, 520),
    ("a", "2026-09-01 09:30", 200, 700, 500),
    ("b", "2026-09-01 08:10", 200, 300, 300),
])
CORRIDORS = pd.DataFrame({"corridor_id": ["a", "b"], "cadence_s": [900, np.nan]})


def cell(cells, corridor, hour):
    row = cells[(cells.corridor_id == corridor) & (cells.day == DAY) & (cells.hour == hour)]
    assert len(row) == 1
    return row.iloc[0]


def test_hour_with_a_failed_call():
    c = cell(hourly_cells(SAMPLES, CORRIDORS), "a", 8)
    # slots 08:00, 08:15, 08:30, 08:45; 3 of 4 succeeded
    assert (c.n_expected, c.n_attempted, c.n_ok) == (4, 4, 3)
    assert c.missing_rate == pytest.approx(0.25)
    assert c.low_confidence  # 25% > 15%
    assert c.tt_mean_s == pytest.approx(900.0)            # (600 + 900 + 1200) / 3
    assert c.tt_p95_s == pytest.approx(1170.0)            # 900 + 0.9 * (1200 - 900)
    assert c.ff_tomtom_s == pytest.approx(1520 / 3)       # (500 + 500 + 520) / 3


def test_skipped_collector_runs_count_as_missing():
    c = cell(hourly_cells(SAMPLES, CORRIDORS), "a", 9)
    # slots 09:00, 09:15, 09:30 expected; only 09:30 was attempted
    assert (c.n_expected, c.n_attempted, c.n_ok) == (3, 1, 1)
    assert c.missing_rate == pytest.approx(2 / 3)
    assert c.low_confidence
    assert c.tt_mean_s == pytest.approx(700.0)


def test_corridor_without_cadence_falls_back_to_attempted_calls():
    c = cell(hourly_cells(SAMPLES, CORRIDORS), "b", 8)
    assert (c.n_expected, c.n_attempted, c.n_ok) == (1, 1, 1)
    assert c.missing_rate == 0
    assert not c.low_confidence


def test_hourly_schedule_on_local_hours_invents_no_slot_before_first_call():
    # 00:00 IST is 18:30 UTC. Flooring to UTC hours would add a slot at
    # 23:30 IST the previous day and report it as missed.
    samples = parsed([("c", "2026-09-01 00:00", 200, 600, 500),
                      ("c", "2026-09-01 01:00", 200, 600, 500)])
    corridors = pd.DataFrame({"corridor_id": ["c"], "cadence_s": [3600]})
    cells = hourly_cells(samples, corridors)
    assert cells[["hour", "n_expected", "n_ok"]].values.tolist() == [[0, 1, 1], [1, 1, 1]]
    assert (cells["day"] == DAY).all()
    assert (cells["missing_rate"] == 0).all()


def test_hour_with_no_success_has_nan_metrics_not_estimates():
    samples = parsed([("a", "2026-09-01 08:00", 429, None, None),
                      ("a", "2026-09-01 08:15", 503, None, None)])
    corridors = pd.DataFrame({"corridor_id": ["a"], "cadence_s": [np.nan]})
    c = cell(hourly_cells(samples, corridors), "a", 8)
    assert (c.n_expected, c.n_ok, c.missing_rate) == (2, 0, 1.0)
    assert np.isnan(c.tt_mean_s) and np.isnan(c.tt_p95_s)


def test_daily_missingness():
    daily = daily_missingness(hourly_cells(SAMPLES, CORRIDORS)).set_index("corridor_id")
    assert daily.loc["a", "missing_rate"] == pytest.approx(3 / 7)  # 7 expected, 4 ok
    assert bool(daily.loc["a", "low_confidence"])
    assert daily.loc["b", "missing_rate"] == 0
