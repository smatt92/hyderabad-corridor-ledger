"""Intervention audit: treated corridor against a synthetic control.

Controls are corridors that no intervention touches. Weights are
non-negative, sum to one, and minimise squared error against the treated
corridor's demeaned pre-period daily BTI (Abadie et al.). The weighted
control is shifted by the pre-period gap, so treated and synthetic share a
pre-period mean by construction (demeaned synthetic control). The effect is
the post-period gap, treated minus synthetic. Days from the change until
audit_settle_days after it are excluded as settling time.

A control with a missing pre-period day is dropped rather than filled, and
post-period days with any missing input are skipped. The post-period gap is
read daily, so its interval is an always-valid confidence sequence
(metrics.confseq), never a fixed-horizon p-value.
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import nnls

from metrics.cells import local_day_hour
from metrics.confseq import running_cs, running_mean_sd
from metrics.params import Params

COLUMNS = [
    "intervention_id", "corridor_id", "status", "effective_day", "settle_days", "pre_start",
    "pre_end", "post_start", "post_end", "n_pre", "n_post", "n_controls", "treated_pre",
    "treated_post", "synthetic_pre", "synthetic_post", "effect", "cs_low", "cs_high", "alpha",
    "pre_rmse", "weights", "missing_rate", "low_confidence",
]


def simplex_weights(y: np.ndarray, x: np.ndarray, penalty: float = 1e4) -> np.ndarray:
    """argmin ||y - X w||^2 subject to w >= 0 and sum(w) = 1.

    NNLS with the sum constraint appended as a heavily weighted row, then
    renormalised to remove the residual violation.
    """
    a = np.vstack([x, np.full(x.shape[1], penalty)])
    b = np.append(y, penalty)
    w, _ = nnls(a, b)
    total = w.sum()
    return w / total if total > 0 else np.full(x.shape[1], 1 / x.shape[1])


def audit_one(series: pd.DataFrame, day_missing: pd.DataFrame, treated: str, controls: list[str],
              effective_day: pd.Timestamp, params: Params) -> dict:
    """series: BTI by day (index) and corridor (columns)."""
    settle_end = effective_day + pd.Timedelta(days=params.audit_settle_days)
    out = {
        "corridor_id": treated, "effective_day": effective_day,
        "settle_days": params.audit_settle_days, "alpha": params.cs_alpha, "weights": {},
        "n_pre": 0, "n_post": 0, "n_controls": 0,
    }
    y = series[treated] if treated in series else pd.Series(dtype=float)
    pre_days = y[(y.index < effective_day) & y.notna()].index
    if len(pre_days) < params.audit_min_pre_days:
        return out | {"status": "insufficient_pre", "n_pre": len(pre_days)}

    usable = [c for c in controls if c in series and series.loc[pre_days, c].notna().all()]
    if not usable:
        return out | {"status": "no_controls", "n_pre": len(pre_days)}

    y_pre = y.loc[pre_days].to_numpy()
    x_pre = series.loc[pre_days, usable].to_numpy()
    w = simplex_weights(y_pre - y_pre.mean(), x_pre - x_pre.mean(axis=0))
    keep = w > 1e-6
    usable = [c for c, k in zip(usable, keep, strict=True) if k]
    w = w[keep] / w[keep].sum()
    shift = y_pre.mean() - series.loc[pre_days, usable].to_numpy().mean(axis=0) @ w

    def synthetic(days):
        return series.loc[days, usable].to_numpy() @ w + shift

    pre_gap = y_pre - synthetic(pre_days)
    post_candidates = y[(y.index >= settle_end)].index
    post_ok = series.loc[post_candidates, [treated, *usable]].notna().all(axis=1)
    post_days = post_candidates[post_ok.to_numpy()]
    base = out | {
        "n_pre": len(pre_days), "n_controls": len(usable),
        "weights": {c: round(float(v), 6) for c, v in zip(usable, w, strict=True)},
        "pre_start": pre_days.min(), "pre_end": pre_days.max(),
        "treated_pre": float(y_pre.mean()), "synthetic_pre": float(synthetic(pre_days).mean()),
        "pre_rmse": float(np.sqrt(np.mean(pre_gap**2))),
    }
    if len(post_days) == 0:
        return base | {"status": "no_post"}

    y_post = y.loc[post_days].to_numpy()
    s_post = synthetic(post_days)
    gap = y_post - s_post
    half = params.cs_alpha / 2
    pre_sd = float(np.std(pre_gap, ddof=1)) if len(pre_gap) > 1 else 0.0
    intercept_radius = stats.t.ppf(1 - half / 2, len(pre_gap) - 1) * pre_sd / np.sqrt(len(pre_gap))
    _, running_sd = running_mean_sd(gap)
    sd = np.fmax(running_sd, pre_sd)
    mean, low, high = running_cs(gap, half, params.cs_rho_target_days, sd=sd)

    involved = day_missing[
        (day_missing["corridor_id"] == treated)
        & day_missing["day"].isin(pre_days.union(post_days))
    ]
    n_expected, n_ok = involved["n_expected"].sum(), involved["n_ok"].sum()
    rate = float((n_expected - n_ok) / n_expected) if n_expected else np.nan
    return base | {
        "status": "ok", "n_post": len(post_days), "post_start": post_days.min(),
        "post_end": post_days.max(), "treated_post": float(y_post.mean()),
        "synthetic_post": float(s_post.mean()), "effect": float(mean[-1]),
        "cs_low": float(low[-1] - intercept_radius), "cs_high": float(high[-1] + intercept_radius),
        "missing_rate": rate,
        "low_confidence": bool(np.isnan(rate) or rate > params.low_confidence_missing_rate),
    }


def intervention_audits(
    day: pd.DataFrame, interventions: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    """One row per intervention. day: metrics_day rows (corridor_id, day, bti, counts)."""
    if interventions.empty or day.empty:
        return pd.DataFrame(columns=COLUMNS)
    series = day.pivot(index="day", columns="corridor_id", values="bti").sort_index()
    treated_all = set(interventions["corridor_id"])
    controls = sorted(c for c in series.columns if c not in treated_all)
    rows = []
    for iv in interventions.itertuples(index=False):
        effective = local_day_hour(pd.to_datetime(pd.Series([iv.effective_at]), utc=True))
        row = audit_one(series, day, iv.corridor_id, controls, effective["day"].iloc[0], params)
        rows.append({"intervention_id": iv.id, "missing_rate": np.nan,
                     "low_confidence": True} | row)
    return pd.DataFrame(rows).reindex(columns=COLUMNS)
