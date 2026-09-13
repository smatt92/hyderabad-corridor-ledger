import numpy as np
import pandas as pd
import pytest

from metrics import pooled
from metrics.params import Params
from tests.helpers import local

ONE_TO_200 = np.arange(1, 201, dtype=float)
TAIL = ("p95", "p95_ci_low", "p95_ci_high", "bti", "bti_ci_low", "bti_ci_high")


def test_floors_are_by_quantile():
    p = Params()
    assert np.isnan(pooled.quantile(ONE_TO_200[:199], 0.95, p))
    # empirical, linear between order statistics: position 199 * 0.95 = 189.05
    assert pooled.quantile(ONE_TO_200, 0.95, p) == pytest.approx(190.05)
    assert np.isnan(pooled.quantile(ONE_TO_200[:29], 0.5, p))
    assert pooled.quantile(ONE_TO_200[:30], 0.5, p) == pytest.approx(15.5)
    assert np.isnan(pooled.mean(ONE_TO_200[:29], p))
    assert pooled.mean(ONE_TO_200[:30], p) == pytest.approx(15.5)


def test_missing_values_never_count_toward_a_floor():
    assert np.isnan(pooled.quantile(np.append(ONE_TO_200[:199], np.nan), 0.95, Params()))


def test_travel_statistics_by_hand():
    s = pooled.travel(ONE_TO_200, Params(), ("hand",))
    assert s["n"] == 200
    assert (s["mean"], s["p50"], s["p95"]) == pytest.approx((100.5, 100.5, 190.05))
    assert s["bti"] == pytest.approx((190.05 - 100.5) / 100.5)
    assert s["p95_ci_low"] <= s["p95"] <= s["p95_ci_high"]
    assert s["bti_ci_low"] <= s["bti"] <= s["bti_ci_high"]


def test_below_the_p95_floor_only_central_statistics_are_published():
    s = pooled.travel(ONE_TO_200[:199], Params(), ("thin",))
    assert s["n"] == 199 and s["mean"] == pytest.approx(100.0)
    assert all(np.isnan(s[k]) for k in TAIL)


def test_bootstrap_is_reproducible_keyed_and_full_size():
    values = np.random.default_rng(1).lognormal(6.8, 0.3, 400)
    first = pooled.tail(values, pooled.bti_rows, Params(), ("x", 1))
    assert first == pooled.tail(values, pooled.bti_rows, Params(), ("x", 1))
    assert first[1:] != pooled.tail(values, pooled.bti_rows, Params(), ("x", 2))[1:]
    (sample,) = pooled.draws(values, [pooled.p95_rows], Params(), ("x",))
    assert len(sample) == 2000


def test_pooled_bti_does_not_depend_on_sample_count():
    # One distribution, sampled at 8 and at 64 calls a day for 28 days, in 40
    # replicate panels. The mean of daily BTIs reports the sparse days as far more
    # reliable; one BTI over the pooled calls does not.
    rng = np.random.default_rng(20260913)
    sparse = rng.lognormal(6.8, 0.35, (40, 28, 8))
    dense = rng.lognormal(6.8, 0.35, (40, 28, 64))

    def pooled_bti(panels):
        return pooled.bti_rows(panels.reshape(len(panels), -1))

    def mean_daily_bti(panels):
        means = panels.mean(axis=2)
        return ((np.quantile(panels, 0.95, axis=2) - means) / means).mean(axis=1)

    assert abs((pooled_bti(sparse) - pooled_bti(dense)).mean()) < 0.04
    assert (mean_daily_bti(sparse) - mean_daily_bti(dense)).mean() < -0.15


def test_difference_needs_both_sides_at_the_floor():
    p = Params()
    assert all(np.isnan(v) for v in pooled.difference(ONE_TO_200, ONE_TO_200[:199],
                                                        pooled.p95_rows, p, ("d",)))
    point, low, high = pooled.difference(ONE_TO_200 * 2, ONE_TO_200, pooled.p95_rows, p, ("d",))
    assert point == pytest.approx(190.05)
    assert low <= point <= high


def test_peak_windows_are_half_open():
    times = ["06:29", "06:30", "10:29", "10:30", "16:29", "16:30", "20:59", "21:00", "02:00"]
    at = pd.Series([local(f"2026-09-14 {t}") for t in times])
    assert pooled.is_peak(at).tolist() == [False, True, True, False, False, True, True, False,
                                           False]


def test_the_tail_floor_cannot_sit_below_the_central_floor():
    with pytest.raises(ValueError):
        Params(p95_min_samples=10, central_min_samples=30)
