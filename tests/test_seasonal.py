import numpy as np
import pandas as pd
import pytest

from metrics.seasonal import contiguous_segments, daily_series, stl_decompose

WEEKLY = [0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3]


def daily_cells(values, start="2026-09-01"):
    days = pd.date_range(start, periods=len(values), freq="D")
    cells = pd.DataFrame({"corridor_id": "a", "day": days, "hour": 8,
                          "tti_tomtom": values, "tti_p5": np.nan})
    cells = cells[cells["tti_tomtom"].notna()]
    missing = pd.DataFrame({"corridor_id": "a", "day": days, "missing_rate": 0.0,
                            "low_confidence": False})
    return cells, missing


def test_contiguous_segments():
    days = pd.Series(pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03",
                                     "2026-09-05", "2026-09-06"]))
    assert contiguous_segments(days).tolist() == [1, 1, 1, 2, 2]


def test_daily_series_mean_over_hours_with_a_value():
    cells = pd.DataFrame({"corridor_id": "a",
                          "day": pd.to_datetime(["2026-09-01"] * 3 + ["2026-09-02"]),
                          "tti_tomtom": [1.2, 1.4, np.nan, 2.0]})
    out = daily_series(cells, "tomtom")
    assert out["observed"].tolist() == pytest.approx([1.3, 2.0])


def test_stl_separates_weekly_cycle_from_trend():
    t = np.arange(35)
    values = 1.5 + 0.01 * t + np.array([WEEKLY[i % 7] for i in t])
    cells, missing = daily_cells(values)
    out = stl_decompose(cells, missing)

    assert set(out["basis"]) == {"tomtom"}  # no p5 reference: no p5 series
    assert np.allclose(out["observed"], out["trend"] + out["seasonal"] + out["resid"])
    middle = out.iloc[7:28]
    assert np.diff(middle["trend"]).mean() == pytest.approx(0.01, abs=0.002)
    assert np.allclose(middle["seasonal"], [WEEKLY[i % 7] for i in range(7, 28)], atol=0.03)


def test_stl_never_bridges_a_gap():
    values = [1.5 + WEEKLY[i % 7] for i in range(40)]
    values[21] = np.nan  # day 22 has no successful call
    cells, missing = daily_cells(values)
    out = stl_decompose(cells, missing)

    # segment 1 is 21 days (decomposed); segment 2 is 18 days (< 21, skipped)
    assert len(out) == 21
    assert out["segment_start"].unique().tolist() == [pd.Timestamp("2026-09-01")]
    assert out["day"].max() == pd.Timestamp("2026-09-21")
