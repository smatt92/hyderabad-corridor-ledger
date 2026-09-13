import math

import numpy as np
import pandas as pd
import pytest

from metrics.confseq import before_after, normal_mixture_radius, rho_for, running_cs
from metrics.params import Params
from tests.helpers import local


def test_rho_for():
    # la = -2 ln 0.05 = 5.99146; (la + ln(la + 1)) / 28 = 0.283434
    assert rho_for(28, 0.05) == pytest.approx(0.532385, rel=1e-5)


def test_normal_mixture_radius_by_hand():
    # t = 4, sd = 2, rho = 0.5: t rho^2 = 1, 2 * 2 / (16 * 0.25) = 1
    # radius = 2 * sqrt(ln(sqrt(2) / 0.05)) = 2 * sqrt(3.342307)
    assert normal_mixture_radius(4, 2.0, 0.05, 0.5) == pytest.approx(3.656396, rel=1e-5)


def test_sequence_is_valid_at_every_day_while_daily_peeking_is_not():
    """With known sd the mixture boundary is exact (Ville's inequality): the chance
    that the sequence EVER excludes the true mean is at most alpha. A fixed 95%
    interval re-checked daily excludes it far more often."""
    rng = np.random.default_rng(20260913)
    sims, days, alpha = 2000, 100, 0.05
    t = np.arange(1, days + 1)
    cs_miss = peek_miss = 0
    for _ in range(sims):
        x = rng.standard_normal(days)
        mean, low, high = running_cs(x, alpha, t_star=28, sd=1.0)
        cs_miss += bool(((low > 0) | (high < 0)).any())
        peek_miss += bool((np.abs(mean) > 1.959964 / np.sqrt(t)).any())
    assert cs_miss / sims <= alpha + 0.015   # Monte Carlo slack
    assert peek_miss / sims > 0.25


def test_before_after_by_hand():
    days = pd.date_range("2026-09-07", "2026-09-12", freq="D")
    stl = pd.DataFrame({
        "corridor_id": "a", "basis": "tomtom", "day": days,
        "observed": [1.0, 1.2, 1.4, 9.9, 1.5, 1.7],  # 09-10 is the effective day: excluded
        "seasonal": 0.0,
    })
    interventions = pd.DataFrame({"id": ["signal-retiming"], "corridor_id": ["a"],
                                  "effective_at": [local("2026-09-10 00:30")]})
    params = Params(cs_alpha=0.10, cs_before_days=3, cs_rho_target_days=4)
    out = before_after(stl, interventions, params)

    b_mean, b_sd = 1.2, 0.2
    b_radius = 4.302652729911275 * b_sd / math.sqrt(3)  # t(0.975, df=2); alpha/2 split twice
    la = -2 * math.log(0.05)
    rho2 = (la + math.log(la + 1)) / 4

    def radius(t, sd):
        return sd * math.sqrt(2 * (t * rho2 + 1) / (t * t * rho2)
                              * math.log(math.sqrt(t * rho2 + 1) / 0.05))

    # day 1: running sd undefined -> pre-period sd 0.2
    # day 2: running sd of [1.5, 1.7] is 0.1414 -> still the larger 0.2
    expected = [(1, 1.5, radius(1, 0.2)), (2, 1.6, radius(2, 0.2))]
    assert out["as_of"].tolist() == [pd.Timestamp("2026-09-11"), pd.Timestamp("2026-09-12")]
    for row, (n_after, a_mean, a_radius) in zip(out.itertuples(), expected, strict=True):
        assert row.n_before == 3 and row.n_after == n_after
        assert row.mean_before == pytest.approx(b_mean)
        assert row.diff == pytest.approx(a_mean - b_mean)
        assert row.cs_low == pytest.approx(a_mean - a_radius - (b_mean + b_radius))
        assert row.cs_high == pytest.approx(a_mean + a_radius - (b_mean - b_radius))
