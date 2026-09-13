"""Always-valid confidence sequences for before/after comparisons.

Intervention data is looked at every day. A fixed-horizon p-value checked
daily until it looks significant has a far higher error rate than it claims.
A confidence sequence holds simultaneously at every day, so it can be read
daily without inflating error.

The after-period mean uses Robbins' normal-mixture boundary, as in the
asymptotic confidence sequences of Waudby-Smith et al. (2021):

    mean_t +/- sd * sqrt(2 (t rho^2 + 1) / (t^2 rho^2) * log(sqrt(t rho^2 + 1) / alpha))

with rho tuned to be tightest near t_star. sd is the larger of the pre-period
standard deviation and the running after-period one: a running estimate from
the first one or two days can be near zero, which would make the sequence
narrowest exactly when it is least trustworthy.

The pre-intervention window is fixed, so it gets an ordinary t interval. Each
side gets alpha / 2, and a union bound makes the difference interval valid at
level alpha for all days at once. Inputs are STL-adjusted daily TTI
(observed - seasonal), so the weekly cycle is not read as an effect. The
sequence assumes daily values are not strongly autocorrelated.
"""

import numpy as np
import pandas as pd
from scipy import stats

from metrics.cells import local_day_hour
from metrics.params import BASES, Params

COLUMNS = [
    "intervention_id", "basis", "as_of", "n_before", "n_after", "mean_before", "mean_after",
    "diff", "cs_low", "cs_high", "alpha",
]


def rho_for(t_star: float, alpha: float) -> float:
    """Mixture scale that makes the boundary tightest at t_star observations."""
    log_term = -2 * np.log(alpha)
    return float(np.sqrt((log_term + np.log(log_term + 1)) / t_star))


def normal_mixture_radius(t, sd, alpha: float, rho: float):
    t = np.asarray(t, dtype=float)
    return sd * np.sqrt(
        2 * (t * rho**2 + 1) / (t**2 * rho**2) * np.log(np.sqrt(t * rho**2 + 1) / alpha)
    )


def running_mean_sd(x) -> tuple[np.ndarray, np.ndarray]:
    """Running mean and sample standard deviation (NaN after one observation)."""
    x = np.asarray(x, dtype=float)
    t = np.arange(1, len(x) + 1)
    mean = np.cumsum(x) / t
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (np.cumsum(x**2) - t * mean**2) / (t - 1)
    return mean, np.sqrt(np.clip(var, 0, None))


def running_cs(x, alpha: float, t_star: float, sd=None):
    """Running mean and its confidence sequence. sd defaults to the running sd."""
    mean, running_sd = running_mean_sd(x)
    t = np.arange(1, len(mean) + 1)
    radius = normal_mixture_radius(
        t, running_sd if sd is None else sd, alpha, rho_for(t_star, alpha)
    )
    return mean, mean - radius, mean + radius


def before_after(
    stl: pd.DataFrame, interventions: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    """One row per intervention, basis and post-intervention day with data."""
    if stl.empty or interventions.empty:
        return pd.DataFrame(columns=COLUMNS)
    adjusted = stl.assign(adjusted=stl["observed"] - stl["seasonal"])
    half = params.cs_alpha / 2
    rows = []
    for iv in interventions.itertuples(index=False):
        effective_at = pd.to_datetime(pd.Series([iv.effective_at]), utc=True)
        effective_day = local_day_hour(effective_at)["day"].iloc[0]
        for basis in BASES:
            series = (
                adjusted[(adjusted["corridor_id"] == iv.corridor_id) & (adjusted["basis"] == basis)]
                .set_index("day")["adjusted"]
                .sort_index()
            )
            start = effective_day - pd.Timedelta(days=params.cs_before_days)
            before = series[(series.index >= start) & (series.index < effective_day)]
            after = series[series.index > effective_day].to_numpy()
            if len(before) < 2 or len(after) == 0:
                continue
            b_mean, b_sd = before.mean(), before.std(ddof=1)
            b_radius = stats.t.ppf(1 - half / 2, len(before) - 1) * b_sd / np.sqrt(len(before))
            _, after_sd = running_mean_sd(after)
            a_mean, a_low, a_high = running_cs(
                after, half, params.cs_rho_target_days, sd=np.fmax(after_sd, b_sd)
            )
            after_days = series[series.index > effective_day].index
            for i, day in enumerate(after_days):
                rows.append((
                    iv.id, basis, day, len(before), i + 1, b_mean, a_mean[i], a_mean[i] - b_mean,
                    a_low[i] - (b_mean + b_radius), a_high[i] - (b_mean - b_radius),
                    params.cs_alpha,
                ))
    return pd.DataFrame(rows, columns=COLUMNS)
