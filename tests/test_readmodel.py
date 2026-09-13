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
    profile_window,
    read_window,
    sunday_first,
)
from tests.helpers import parsed

CELL_COLUMNS = ["corridor_id", "day", "hour", "tt_mean_s", "tti_tomtom", "tti_p5", "n_expected",
                "n_ok"]
CALL_COLUMNS = ["corridor_id", "day", "hour", "travel_time_s", "tti_tomtom", "tti_p5"]
NAN = np.nan
# Floors low enough to work examples by hand. Production floors are 30 and 200.
SMALL = Params(central_min_samples=3, p95_min_samples=5, bootstrap_resamples=200)


def cells(rows):
    frame = pd.DataFrame(rows, columns=CELL_COLUMNS)
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


def calls(rows):
    frame = pd.DataFrame(rows, columns=CALL_COLUMNS)
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


def window(start, end):
    return pd.Timestamp(start), pd.Timestamp(end)


def test_read_window_ends_on_last_day_with_a_successful_call():
    frame = cells([
        ("a", "2026-09-01", 8, 600, 1.2, 1.3, 1, 1),
        ("a", "2026-09-10", 8, 600, 1.2, 1.3, 1, 1),
        ("a", "2026-09-11", 8, NAN, NAN, NAN, 1, 0),  # failures only
    ])
    assert read_window(frame, Params(read_window_days=5)) == window("2026-09-06", "2026-09-10")


def test_profile_window_is_longer_and_ends_with_the_read_window():
    assert profile_window(window("2026-06-15", "2026-09-12")) == window("2026-05-16", "2026-09-12")


def test_sunday_first():
    days = pd.Series(pd.to_datetime(["2026-09-13", "2026-09-14", "2026-09-19"]))
    assert sunday_first(days).tolist() == [0, 1, 6]  # Sun, Mon, Sat


def test_add_hourly_context_week_delta_and_own_median():
    frame = cells([
        ("a", "2026-09-01", 8, 600, 1.2, 1.5, 1, 1),
        ("a", "2026-09-02", 8, 700, 1.4, 1.6, 1, 1),
        ("a", "2026-09-08", 8, 900, 1.8, NAN, 1, 1),
    ])
    out = add_hourly_context(frame, window("2026-09-01", "2026-09-08")).set_index("day")
    week_later = out.loc[pd.Timestamp("2026-09-08")]
    assert week_later.tti_tomtom_delta_wk == pytest.approx(0.6)   # 1.8 - 1.2
    assert np.isnan(week_later.tti_p5_delta_wk)                   # p5 missing that day
    assert np.isnan(out.loc[pd.Timestamp("2026-09-01"), "tti_tomtom_delta_wk"])
    # own median at hour 8 = median(600, 700, 900) = 700
    assert out["tt_ratio_own_median"].tolist() == pytest.approx([600 / 700, 1.0, 900 / 700])


def corridor_inputs():
    samples = parsed([
        ("a", "2026-09-01 08:00", 200, 600, 500),
        ("a", "2026-09-02 08:00", 200, 620, 520),
        ("a", "2026-09-03 08:00", 200, 640, 480),
        ("a", "2026-09-03 02:00", 200, 300, 500),   # a night call: never pooled as peak
        ("b", "2026-09-03 08:00", 429, None, None),
    ])
    samples.loc[:3, "length_m"] = [5000.0, 5200.0, 5100.0, 5100.0]
    indexed = cells([
        ("a", "2026-09-01", 8, 600, NAN, NAN, 4, 3),
        ("a", "2026-09-03", 8, 640, NAN, NAN, 2, 2),
        ("b", "2026-09-03", 8, NAN, NAN, NAN, 2, 0),
    ])
    ff_p5 = pd.DataFrame({"corridor_id": "a",
                          "day": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
                          "ff_p5_s": [300.0, NAN, 310.0]})
    return samples, indexed, ff_p5


def test_corridor_stats_uses_measured_length_and_keeps_unmeasured_corridors():
    out = corridor_stats(*corridor_inputs(), window("2026-09-01", "2026-09-03")).set_index(
        "corridor_id")
    assert out.loc["a", "length_meters"] == 5100            # median of measured lengths
    assert out.loc["a", "ff_tomtom_s"] == pytest.approx(500.0)
    assert out.loc["a", "ff_p5_s"] == pytest.approx(310.0)
    assert out.loc["a", "missing_rate"] == pytest.approx(1 / 6)
    assert bool(out.loc["a", "low_confidence"])
    assert pd.isna(out.loc["b", "length_meters"])          # absent, never estimated
    assert out.loc["b", "missing_rate"] == 1.0
    # three peak calls are far below the floors: counted, not published
    assert out.loc["a", "n_peak"] == 3 and out.loc["b", "n_peak"] == 0
    assert out.loc["a", ["tt_mean_peak_s", "tt_p95_peak_s", "bti_peak", "pti_p5_peak"]].isna().all()


def test_ledger_pools_peak_hour_calls_into_one_distribution():
    tiny = Params(central_min_samples=3, p95_min_samples=3, bootstrap_resamples=200)
    out = corridor_stats(*corridor_inputs(), window("2026-09-01", "2026-09-03"), tiny).set_index(
        "corridor_id")
    a = out.loc["a"]
    assert a.n_peak == 3                                   # 02:00 is not a peak hour
    assert a.tt_mean_peak_s == pytest.approx(620.0)
    assert a.tt_p95_peak_s == pytest.approx(638.0)         # position 1.9: 620 + 0.9 * 20
    assert a.bti_peak == pytest.approx(18 / 620)
    assert a.pti_tomtom_peak == pytest.approx(638 / 500)
    assert a.pti_p5_peak == pytest.approx(638 / 310)
    assert not [c for c in out.columns if "_ci_" in c]  # point values beside n_peak
    assert out.loc["b", ["tt_p95_peak_s", "bti_peak"]].isna().all()


def test_dataset_stats_records_the_floors():
    indexed = cells([("a", "2026-09-01", 8, 600, NAN, NAN, 10, 9),
                     ("b", "2026-09-01", 8, 600, NAN, NAN, 10, 8)])
    (row,) = dataset_stats(indexed, window("2026-09-01", "2026-09-01")).to_dict("records")
    assert (row["n_corridors"], row["n_expected"], row["n_ok"]) == (2, 20, 17)
    assert row["missing_rate"] == pytest.approx(0.15)
    assert row["low_confidence"] is False  # exactly 15% is not above 15%
    assert (row["p95_min_samples"], row["central_min_samples"]) == (200, 30)
    assert "bootstrap_resamples" not in row


def test_metrics_day_means_over_hours_with_a_value():
    indexed = cells([("a", "2026-09-01", 8, 600, 1.2, 1.5, 4, 3),
                     ("a", "2026-09-01", 9, NAN, NAN, NAN, 2, 0)])
    (row,) = metrics_day(indexed).to_dict("records")
    assert (row["tt_mean_s"], row["tti_tomtom"], row["tti_p5"]) == (600, 1.2, 1.5)
    assert (row["n_expected"], row["n_ok"], row["missing_rate"]) == (6, 3, 0.5)
    assert "bti" not in row


def profile_inputs():
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
    tti = calls([("a", d, 8, t, tt, p) for d, t, tt, p in zip(
        days, [600.0, 700.0, 800.0, 900.0, 1000.0], [1.0, 1.2, 1.4, 1.6, 1.8],
        [2.0, 2.2, 2.4, 2.6, 2.8], strict=True)])
    indexed = cells(
        [("a", d, 8, NAN, NAN, NAN, 1, 1) for d in days]
        + [("a", "2026-09-06", 8, NAN, NAN, NAN, 1, 0),
           ("a", "2026-09-06", 9, NAN, NAN, NAN, 2, 0)]
    )
    return tti, indexed


def test_profile_hourly_pools_every_call_at_the_hour():
    tti, indexed = profile_inputs()
    out = profile_hourly(tti, indexed, window("2026-09-01", "2026-09-06"), SMALL).set_index("hour")
    h8 = out.loc[8]
    # n = 5, linear interpolation at position (n - 1) * q: 1, 2, 3, 3.8
    assert (h8.tt_p50_s, h8.tt_p95_s, h8.tt_mean_s) == pytest.approx((800, 980, 800))
    assert h8.bti == pytest.approx(0.225)                     # (980 - 800) / 800
    assert not [c for c in out.columns if "_ci_" in c]
    assert [h8.tti_tomtom_p25, h8.tti_tomtom_p50, h8.tti_tomtom_p75, h8.tti_tomtom_p95] == \
        pytest.approx([1.2, 1.4, 1.6, 1.76])
    assert h8.tti_p5_p95 == pytest.approx(2.76)
    assert (h8.n_expected, h8.n_ok, h8.n_tti_p5) == (6, 5, 5)
    assert h8.missing_rate == pytest.approx(1 / 6)
    assert (h8.window_start, h8.window_end) == window("2026-09-01", "2026-09-06")
    # an hour with only failures still gets a row: missing, not dropped
    assert out.loc[9, "missing_rate"] == 1.0 and np.isnan(out.loc[9, "tt_p50_s"])
    assert out.loc[9, "n_tti_p5"] == 0


def test_profile_below_the_floors_publishes_counts_not_numbers():
    tti, indexed = profile_inputs()
    h8 = profile_hourly(tti, indexed, window("2026-09-01", "2026-09-06")).set_index("hour").loc[8]
    assert h8.n_ok == 5
    assert np.isnan([h8.tt_mean_s, h8.tt_p50_s, h8.tt_p95_s, h8.bti, h8.tti_tomtom_p50,
                     h8.tti_p5_p95]).all()


def test_heatmap_weekly_publishes_medians_of_pooled_calls_at_the_floor():
    indexed = cells([
        ("a", "2026-09-13", 8, 900, NAN, NAN, 1, 1),   # Sunday
        ("a", "2026-09-06", 8, 500, NAN, NAN, 1, 1),   # Sunday
        ("a", "2026-09-07", 8, 700, NAN, NAN, 1, 1),   # Monday, one call only
        ("b", "2026-09-13", 8, 800, NAN, NAN, 1, 1),   # Sunday
    ])
    tti = calls([
        ("a", "2026-09-13", 8, 900, 2.0, 2.2),
        ("a", "2026-09-06", 8, 500, 1.0, NAN),
        ("a", "2026-09-07", 8, 700, 1.5, 1.7),
        ("b", "2026-09-13", 8, 800, 3.0, NAN),
    ])
    out = heatmap_weekly(tti, indexed, window("2026-09-01", "2026-09-13"),
                         Params(central_min_samples=2))

    def cell(scope, corridor, dow):
        mask = (out.scope == scope) & (out.dow == dow) & (out.hour == 8)
        mask &= out.corridor_id.isna() if corridor is None else out.corridor_id == corridor
        (row,) = out[mask].to_dict("records")
        return row

    a_sun = cell("corridor", "a", 0)
    assert (a_sun["n_days"], a_sun["n_ok"]) == (2, 2)
    assert a_sun["tti_tomtom_p50"] == pytest.approx(1.5)
    assert np.isnan(a_sun["tti_p5_p50"])  # one p5 value: below the floor
    a_mon = cell("corridor", "a", 1)
    assert a_mon["n_days"] == 1 and np.isnan(a_mon["tti_tomtom_p50"])
    network_sun = cell("network", None, 0)
    assert network_sun["n_ok"] == 3 and network_sun["tti_tomtom_p50"] == pytest.approx(2.0)


def test_network_hourly_against_same_hour_same_weekday_baseline():
    rows = [
        # a: baseline median(1000, 1200) = 1100; 09-01 absent; today 1320 -> ratio 1.2
        ("a", "2026-09-15", 8, 1000, NAN, NAN, 4, 4),
        ("a", "2026-09-08", 8, 1200, NAN, NAN, 4, 4),
        ("a", "2026-09-22", 8, 1320, 1.5, NAN, 4, 4),
        # b: baseline 1000; today 900 -> ratio 0.9
        ("b", "2026-09-15", 8, 1000, NAN, NAN, 4, 4),
        ("b", "2026-09-08", 8, 1000, NAN, NAN, 4, 4),
        ("b", "2026-09-01", 8, 1000, NAN, NAN, 4, 4),
        ("b", "2026-09-22", 8, 900, 1.2, NAN, 4, 3),
        # c: one prior week only, below the minimum of 2 -> no ratio
        ("c", "2026-09-15", 8, 500, NAN, NAN, 4, 4),
        ("c", "2026-09-22", 8, 500, 1.1, NAN, 4, 2),
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


def test_pair_advantage_is_a_point_difference_beside_both_counts():
    corridors = pd.DataFrame({
        "corridor_id": ["a", "b", "c"], "pair_id": ["PR-01", "PR-01", "PR-02"],
        "role": ["primary", "alternate", "primary"],
    })
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]

    def at_eight(corridor, travel):
        return [(corridor, d, 8, t, NAN, NAN) for d, t in zip(days, travel, strict=True)]

    tti = calls(
        at_eight("a", [1000, 1100, 1200, 1300, 1400]) + at_eight("b", [800, 900, 1000, 1100, 1200])
        + [("a", "2026-09-01", 9, 900, NAN, NAN), ("a", "2026-09-02", 9, 950, NAN, NAN)]
    )
    profile = pd.DataFrame({"corridor_id": ["a", "b", "a"], "hour": [8, 8, 9],
                            "low_confidence": [False, False, False]})
    out = pair_advantage_hourly(tti, profile, corridors, window("2026-09-01", "2026-09-05"),
                                SMALL).set_index("hour")

    assert set(out["pair_id"]) == {"PR-01"}  # PR-02 declares one corridor: nothing derived
    assert len(out) == 24
    h8 = out.loc[8]
    # five evenly spaced values, p95 at position 3.8: 1300 + 80 and 1100 + 80
    assert (h8.primary_tt_p95_s, h8.alternate_tt_p95_s, h8.advantage_p95_s) == pytest.approx(
        (1380, 1180, 200))
    assert (h8.primary_n, h8.alternate_n) == (5, 5)
    assert not [c for c in out.columns if "_ci_" in c]
    assert not h8.low_confidence
    h9 = out.loc[9]
    assert (h9.primary_n, h9.alternate_n) == (2, 0)
    assert np.isnan(h9.primary_tt_p95_s) and np.isnan(h9.advantage_p95_s) and h9.low_confidence


def test_pair_advantage_with_no_alternates_is_empty():
    corridors = pd.DataFrame({"corridor_id": ["c"], "pair_id": ["PR-02"], "role": ["primary"]})
    empty = calls([])
    assert pair_advantage_hourly(empty, pd.DataFrame(columns=["corridor_id", "hour",
                                                              "low_confidence"]),
                                 corridors, window("2026-09-01", "2026-09-05")).empty
