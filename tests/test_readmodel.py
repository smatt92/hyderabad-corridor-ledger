import numpy as np
import pandas as pd
import pytest

from metrics.params import Params
from metrics.readmodel import (
    add_hourly_context,
    corridor_stats,
    dataset_stats,
    heatmap_weekly,
    metrics_day,
    network_hourly,
    pair_advantage_hourly,
    profile_hourly,
    read_window,
    sunday_first,
)
from tests.helpers import parsed

CELL_COLUMNS = ["corridor_id", "day", "hour", "tt_mean_s", "tti_tomtom", "tti_p5", "bti",
                "n_expected", "n_ok"]
NAN = np.nan


def cells(rows):
    frame = pd.DataFrame(rows, columns=CELL_COLUMNS)
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


def window(start, end):
    return pd.Timestamp(start), pd.Timestamp(end)


def test_read_window_ends_on_last_day_with_a_successful_call():
    frame = cells([
        ("a", "2026-09-01", 8, 600, 1.2, 1.3, 0.1, 1, 1),
        ("a", "2026-09-10", 8, 600, 1.2, 1.3, 0.1, 1, 1),
        ("a", "2026-09-11", 8, NAN, NAN, NAN, NAN, 1, 0),  # failures only
    ])
    assert read_window(frame, Params(read_window_days=5)) == window("2026-09-06", "2026-09-10")


def test_sunday_first():
    days = pd.Series(pd.to_datetime(["2026-09-13", "2026-09-14", "2026-09-19"]))
    assert sunday_first(days).tolist() == [0, 1, 6]  # Sun, Mon, Sat


def test_add_hourly_context_week_delta_and_own_median():
    frame = cells([
        ("a", "2026-09-01", 8, 600, 1.2, 1.5, 0.1, 1, 1),
        ("a", "2026-09-02", 8, 700, 1.4, 1.6, 0.1, 1, 1),
        ("a", "2026-09-08", 8, 900, 1.8, NAN, 0.1, 1, 1),
    ])
    out = add_hourly_context(frame, window("2026-09-01", "2026-09-08")).set_index("day")
    week_later = out.loc[pd.Timestamp("2026-09-08")]
    assert week_later.tti_tomtom_delta_wk == pytest.approx(0.6)   # 1.8 - 1.2
    assert np.isnan(week_later.tti_p5_delta_wk)                   # p5 missing that day
    assert np.isnan(out.loc[pd.Timestamp("2026-09-01"), "tti_tomtom_delta_wk"])
    # own median at hour 8 = median(600, 700, 900) = 700
    assert out["tt_ratio_own_median"].tolist() == pytest.approx([600 / 700, 1.0, 900 / 700])


def test_corridor_stats_uses_measured_length_and_keeps_unmeasured_corridors():
    samples = parsed([
        ("a", "2026-09-01 08:00", 200, 600, 500),
        ("a", "2026-09-02 08:00", 200, 620, 520),
        ("a", "2026-09-03 08:00", 200, 640, 480),
        ("b", "2026-09-03 08:00", 429, None, None),
    ])
    samples.loc[:2, "length_m"] = [5000.0, 5200.0, 5100.0]
    indexed = cells([
        ("a", "2026-09-01", 8, 600, NAN, NAN, NAN, 4, 3),
        ("a", "2026-09-03", 8, 640, NAN, NAN, NAN, 2, 2),
        ("b", "2026-09-03", 8, NAN, NAN, NAN, NAN, 2, 0),
    ])
    ff_p5 = pd.DataFrame({"corridor_id": "a",
                          "day": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
                          "ff_p5_s": [300.0, NAN, 310.0]})
    out = corridor_stats(samples, indexed, ff_p5, window("2026-09-01", "2026-09-03"))
    out = out.set_index("corridor_id")

    assert out.loc["a", "length_meters"] == 5100            # median of measured lengths
    assert out.loc["a", "ff_tomtom_s"] == pytest.approx(500.0)
    assert out.loc["a", "ff_p5_s"] == pytest.approx(310.0)
    assert out.loc["a", "missing_rate"] == pytest.approx(1 / 6)
    assert bool(out.loc["a", "low_confidence"])
    assert pd.isna(out.loc["b", "length_meters"])          # absent, never estimated
    assert out.loc["b", "missing_rate"] == 1.0


def test_dataset_stats():
    indexed = cells([("a", "2026-09-01", 8, 600, NAN, NAN, NAN, 10, 9),
                     ("b", "2026-09-01", 8, 600, NAN, NAN, NAN, 10, 8)])
    (row,) = dataset_stats(indexed, window("2026-09-01", "2026-09-01")).to_dict("records")
    assert (row["n_corridors"], row["n_expected"], row["n_ok"]) == (2, 20, 17)
    assert row["missing_rate"] == pytest.approx(0.15)
    assert row["low_confidence"] is False  # exactly 15% is not above 15%


def test_metrics_day_means_over_hours_with_a_value():
    indexed = cells([("a", "2026-09-01", 8, 600, 1.2, 1.5, 0.2, 4, 3),
                     ("a", "2026-09-01", 9, NAN, NAN, NAN, NAN, 2, 0)])
    (row,) = metrics_day(indexed).to_dict("records")
    assert (row["tt_mean_s"], row["tti_tomtom"], row["bti"]) == (600, 1.2, 0.2)
    assert (row["n_expected"], row["n_ok"], row["missing_rate"]) == (6, 3, 0.5)


def test_profile_hourly_quantiles_from_calls():
    days = pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"])
    tti = pd.DataFrame({
        "corridor_id": "a", "day": days, "hour": 8,
        "travel_time_s": [600.0, 700.0, 800.0, 900.0, 1000.0],
        "tti_tomtom": [1.0, 1.2, 1.4, 1.6, 1.8],
        "tti_p5": [2.0, 2.2, 2.4, 2.6, 2.8],
    })
    indexed = cells(
        [("a", d, 8, NAN, NAN, NAN, NAN, 1, 1) for d in days.strftime("%Y-%m-%d")]
        + [("a", "2026-09-06", 8, NAN, NAN, NAN, NAN, 1, 0),
           ("a", "2026-09-06", 9, NAN, NAN, NAN, NAN, 2, 0)]
    )
    out = profile_hourly(tti, indexed, window("2026-09-01", "2026-09-06")).set_index("hour")
    h8 = out.loc[8]
    # n = 5, linear interpolation at position (n - 1) * q: 1, 2, 3, 3.8
    assert (h8.tt_p50_s, h8.tt_p95_s, h8.tt_mean_s) == pytest.approx((800, 980, 800))
    assert h8.bti == pytest.approx(0.225)                     # (980 - 800) / 800
    assert [h8.tti_tomtom_p25, h8.tti_tomtom_p50, h8.tti_tomtom_p75, h8.tti_tomtom_p95] == \
        pytest.approx([1.2, 1.4, 1.6, 1.76])
    assert h8.tti_p5_p95 == pytest.approx(2.76)
    assert (h8.n_expected, h8.n_ok) == (6, 5) and h8.missing_rate == pytest.approx(1 / 6)
    # an hour with only failures still gets a row: missing, not dropped
    assert out.loc[9, "missing_rate"] == 1.0 and np.isnan(out.loc[9, "tt_p50_s"])


def test_heatmap_weekly_suppresses_thin_cells_per_basis():
    indexed = cells([
        ("a", "2026-09-13", 8, 900, 2.0, 2.2, NAN, 1, 1),   # Sunday
        ("a", "2026-09-06", 8, 500, 1.0, NAN, NAN, 1, 1),   # Sunday
        ("a", "2026-09-07", 8, 700, 1.5, 1.7, NAN, 1, 1),   # Monday, one day only
        ("b", "2026-09-13", 8, 800, 3.0, NAN, NAN, 1, 1),   # Sunday
    ])
    out = heatmap_weekly(indexed, window("2026-09-01", "2026-09-13"), Params(heatmap_min_days=2))

    def cell(scope, corridor, dow):
        mask = (out.scope == scope) & (out.dow == dow) & (out.hour == 8)
        mask &= out.corridor_id.isna() if corridor is None else out.corridor_id == corridor
        (row,) = out[mask].to_dict("records")
        return row

    a_sun = cell("corridor", "a", 0)
    assert a_sun["n_days"] == 2 and a_sun["tti_tomtom_p50"] == pytest.approx(1.5)
    assert np.isnan(a_sun["tti_p5_p50"])  # one p5 value: too few to publish
    a_mon = cell("corridor", "a", 1)
    assert a_mon["n_days"] == 1 and np.isnan(a_mon["tti_tomtom_p50"])
    network_sun = cell("network", None, 0)
    assert network_sun["n_days"] == 2 and network_sun["tti_tomtom_p50"] == pytest.approx(2.0)


def test_network_hourly_against_same_hour_same_weekday_baseline():
    rows = [
        # a: baseline median(1000, 1200) = 1100; 09-01 absent; today 1320 -> ratio 1.2
        ("a", "2026-09-15", 8, 1000, NAN, NAN, NAN, 4, 4),
        ("a", "2026-09-08", 8, 1200, NAN, NAN, NAN, 4, 4),
        ("a", "2026-09-22", 8, 1320, 1.5, NAN, NAN, 4, 4),
        # b: baseline 1000; today 900 -> ratio 0.9
        ("b", "2026-09-15", 8, 1000, NAN, NAN, NAN, 4, 4),
        ("b", "2026-09-08", 8, 1000, NAN, NAN, NAN, 4, 4),
        ("b", "2026-09-01", 8, 1000, NAN, NAN, NAN, 4, 4),
        ("b", "2026-09-22", 8, 900, 1.2, NAN, NAN, 4, 3),
        # c: one prior week only, below the minimum of 2 -> no ratio
        ("c", "2026-09-15", 8, 500, NAN, NAN, NAN, 4, 4),
        ("c", "2026-09-22", 8, 500, 1.1, NAN, NAN, 4, 2),
    ]
    params = Params(network_baseline_weeks=3, network_baseline_min=2, network_state_band_pct=7.0)
    out = network_hourly(cells(rows), window("2026-09-22", "2026-09-22"), params)

    (row,) = out.to_dict("records")  # baseline days outside the window emit no rows
    assert row["n_corridors"] == 2
    assert row["tt_ratio_p50"] == pytest.approx(1.05)   # median(1.2, 0.9)
    assert row["pct_vs_normal"] == pytest.approx(5.0)
    assert row["state"] == "normal"                     # within +/- 7%
    assert row["tti_tomtom_p50"] == pytest.approx(1.2)  # median(1.5, 1.2, 1.1)
    assert row["missing_rate"] == pytest.approx(0.25)   # 12 expected, 9 ok
    assert row["low_confidence"]

    worse = network_hourly(cells(rows[:3]), window("2026-09-22", "2026-09-22"), params)
    assert worse["state"].iloc[0] == "worse"            # +20%


def test_pair_advantage_only_for_declared_alternates():
    corridors = pd.DataFrame({
        "corridor_id": ["a", "b", "c"], "pair_id": ["PR-01", "PR-01", "PR-02"],
        "role": ["primary", "alternate", "primary"],
    })
    profile = pd.DataFrame({
        "corridor_id": ["a", "b", "a"], "hour": [8, 8, 9],
        "tt_p95_s": [1200.0, 1000.0, 900.0], "low_confidence": [False, False, False],
    })
    out = pair_advantage_hourly(profile, corridors).set_index("hour")

    assert set(out["pair_id"]) == {"PR-01"}  # PR-02 declares one corridor: nothing derived
    assert len(out) == 24
    assert out.loc[8, "advantage_p95_s"] == pytest.approx(200.0)
    assert not out.loc[8, "low_confidence"]
    assert np.isnan(out.loc[9, "advantage_p95_s"]) and out.loc[9, "low_confidence"]


def test_pair_advantage_with_no_alternates_is_empty():
    corridors = pd.DataFrame({"corridor_id": ["c"], "pair_id": ["PR-02"], "role": ["primary"]})
    assert pair_advantage_hourly(pd.DataFrame(columns=["corridor_id", "hour", "tt_p95_s",
                                                       "low_confidence"]), corridors).empty
