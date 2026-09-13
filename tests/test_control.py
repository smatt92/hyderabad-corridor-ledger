import numpy as np
import pandas as pd
import pytest

from metrics.control import change_points, cusum, ewma, robust_sigma
from metrics.params import Params


def test_robust_sigma():
    # median 3; absolute deviations [2, 1, 0, 1, 97] -> MAD 1
    assert robust_sigma(np.array([1, 2, 3, 4, 100])) == pytest.approx(1.4826)


def test_cusum_detects_slow_upward_drift_and_estimates_the_shift():
    # upper sum after the drift starts: 1.5, 3.0, 4.5, 6.0 > 5 at index 6
    # shift = k + S/N = 0.5 + 6.0/4 = 2.0 (the true shift)
    signals = cusum(np.array([0, 0, 0, 2, 2, 2, 2, 2]), k=0.5, h=5)
    assert signals == [(6, "up", pytest.approx(6.0), pytest.approx(2.0))]  # reset: index 7 is 1.5


def test_cusum_downward():
    # lower sum: 2.5, 5.0 (not > 5), 7.5 -> signal at 2; shift = 0.5 + 7.5/3 = 3.0
    assert cusum(np.array([-3, -3, -3]), k=0.5, h=5) == [
        (2, "down", pytest.approx(7.5), pytest.approx(3.0))
    ]


def test_ewma_signals_once_per_excursion():
    # limit_t = 3 sqrt(0.2/1.8 (1 - 0.8^(2t))): t1 0.6, t2 0.7684, t3 0.8590
    # stat: 0, 0, 1.0 (> 0.859, signal), 1.8 (still out, no new signal),
    #       -0.56 (back in), -2.448 (out below, signal)
    signals = ewma(np.array([0, 0, 5, 5, -10, -10]), lam=0.2, limit_l=3)
    assert signals == [
        (2, "up", pytest.approx(1.0), pytest.approx(1.0)),
        (5, "down", pytest.approx(-2.448), pytest.approx(2.448)),
    ]


def test_change_points_rows_in_tti_units():
    # resid: five -1, five +1 alternating, then five 3.
    # median 1, MAD 2 -> sigma 2.9652; z(3) = 3 / 2.9652
    # CUSUM with h = 2: upper sum 0.5117, 1.0235, 1.5352, 2.0469 > 2 at index 13
    # shift = 0.5 + 2.0469/4 = z(3); in TTI units z(3) * sigma = 3.0
    resid = [-1.0, 1.0] * 5 + [3.0] * 5
    days = pd.date_range("2026-09-01", periods=15, freq="D")
    stl = pd.DataFrame({"corridor_id": "a", "basis": "tomtom", "segment_start": days[0],
                        "day": days, "resid": resid})
    out = change_points(stl, Params(cusum_h=2.0))
    cusum_rows = out[out["chart"] == "cusum"]

    assert len(cusum_rows) == 1
    row = cusum_rows.iloc[0]
    assert row.detected_at == pd.Timestamp("2026-09-14")
    assert row.direction == "up"
    assert row.magnitude == pytest.approx(3.0)
