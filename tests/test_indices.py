import numpy as np
import pandas as pd
import pytest

from metrics.indices import cell_indices, free_flow_p5, sample_tti
from metrics.params import Params
from tests.helpers import parsed


def test_free_flow_p5_trailing_window():
    samples = parsed([
        ("a", "2026-09-01 00:00", 200, 100, 90),
        ("a", "2026-09-01 00:30", 200, 200, 90),
        ("a", "2026-09-01 01:00", 200, 300, 90),
        ("a", "2026-09-01 01:30", 429, None, None),  # failures never enter p5
        ("a", "2026-09-02 02:00", 200, 400, 90),
        ("a", "2026-09-03 03:00", 200, 500, 90),
        ("a", "2026-09-03 03:30", 200, 600, 90),
        ("a", "2026-09-03 03:59", 200, 700, 90),
    ])
    params = Params(ff_p5_window_days=2, ff_p5_min_samples=3)
    ff = free_flow_p5(samples, params).set_index("day")["ff_p5_s"]

    # linear interpolation: position (n - 1) * 0.05
    assert ff[pd.Timestamp("2026-09-01")] == pytest.approx(110.0)  # [100,200,300]: 100 + 0.1*100
    assert ff[pd.Timestamp("2026-09-02")] == pytest.approx(115.0)  # [100..400]: 100 + 0.15*100
    assert ff[pd.Timestamp("2026-09-03")] == pytest.approx(415.0)  # [400..700]: 400 + 0.15*100


def test_free_flow_p5_uses_night_slots_only():
    # Daytime calls are congested by definition; only 00:00-04:00 local is free flow.
    samples = parsed([
        ("a", "2026-09-01 00:30", 200, 300, 90),
        ("a", "2026-09-01 03:30", 200, 400, 90),
        ("a", "2026-09-01 04:00", 200, 10, 90),    # 04:00 is outside [00:00, 04:00)
        ("a", "2026-09-01 08:15", 200, 20, 90),
        ("a", "2026-09-01 23:59", 200, 30, 90),
    ])
    ff = free_flow_p5(samples, Params(ff_p5_window_days=1, ff_p5_min_samples=2))
    assert ff["ff_p5_s"].tolist() == [pytest.approx(305.0)]  # [300, 400]: 300 + 0.05*100


def test_free_flow_p5_is_nan_below_minimum_samples():
    samples = parsed([("a", "2026-09-01 01:00", 200, 100, 90)])
    ff = free_flow_p5(samples, Params(ff_p5_min_samples=2))
    assert np.isnan(ff["ff_p5_s"].iloc[0])


def test_cell_indices_keep_both_free_flow_bases():
    cells = pd.DataFrame({
        "corridor_id": ["a", "a"],
        "day": [pd.Timestamp("2026-09-01")] * 2,
        "hour": [8, 9],
        "tt_mean_s": [900.0, np.nan],
        "tt_p95_s": [1170.0, np.nan],
        "ff_tomtom_s": [500.0, np.nan],
    })
    ff = pd.DataFrame({"corridor_id": ["a"], "day": [pd.Timestamp("2026-09-01")],
                       "ff_p5_s": [450.0]})
    out = cell_indices(cells, ff).set_index("hour")

    assert out.loc[8, "tti_tomtom"] == pytest.approx(1.8)    # 900 / 500
    assert out.loc[8, "tti_p5"] == pytest.approx(2.0)        # 900 / 450
    assert out.loc[8, "bti"] == pytest.approx(0.3)           # (1170 - 900) / 900
    assert out.loc[8, "pti_tomtom"] == pytest.approx(2.34)   # 1170 / 500
    assert out.loc[8, "pti_p5"] == pytest.approx(2.6)        # 1170 / 450
    # a cell with no successful call stays NaN on every index
    assert out.loc[9, ["tti_tomtom", "tti_p5", "bti", "pti_tomtom", "pti_p5"]].isna().all()


def test_sample_tti_per_call():
    samples = parsed([("a", "2026-09-01 08:00", 200, 600, 500),
                      ("a", "2026-09-01 08:15", 429, None, None)])
    ff = pd.DataFrame({"corridor_id": ["a"], "day": [pd.Timestamp("2026-09-01")],
                       "ff_p5_s": [400.0]})
    out = sample_tti(samples, ff)
    assert len(out) == 1
    assert out["tti_tomtom"].iloc[0] == pytest.approx(1.2)  # 600 / 500
    assert out["tti_p5"].iloc[0] == pytest.approx(1.5)      # 600 / 400
    assert out["hour"].iloc[0] == 8
