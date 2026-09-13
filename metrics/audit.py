"""Intervention audit: pooled BTI before and after, against untreated corridors.

BTI is a property of a distribution, so each value in the comparison is ONE
BTI computed over every successful peak-hour call in a fixed period, never an
average of daily values. Averaging daily BTIs is wrong twice over: the mean of
ratios is not the ratio of means, and a day's empirical p95 is biased low by
an amount that depends on how many calls the day had. A change in sample
density between periods would then manufacture an effect out of an estimator
artifact. tests/test_audit.py draws both periods from one distribution with
different densities and requires no effect.

Periods are fixed by the intervention date:
  pre     audit_pre_days days before the change
  settle  audit_settle_days days from the change, excluded
  post    audit_post_days days after settling
The audit publishes an effect only once the post period has closed, so its
numbers do not change as it is re-read. It is a fixed-horizon estimate.

Controls are corridors no intervention touches, with at least p95_min_samples
peak-hour calls in both periods. The control value for a period is the
equal-weight mean of the controls' pooled BTIs, and

    effect = (treated_post - treated_pre) - (control_post - control_pre)

Its interval is a percentile bootstrap: calls are resampled within each
corridor and period, bootstrap_resamples times.
"""

import numpy as np
import pandas as pd

from metrics import pooled
from metrics.cells import local_day_hour
from metrics.params import Params

COLUMNS = [
    "intervention_id", "corridor_id", "status", "effective_day", "settle_days", "pre_start",
    "pre_end", "post_start", "post_end", "n_pre", "n_post", "n_controls", "treated_pre",
    "treated_post", "control_pre", "control_post", "effect", "ci_low", "ci_high", "alpha",
    "resamples", "weights", "missing_rate", "low_confidence",
]


def periods(effective_day: pd.Timestamp, params: Params = Params()) -> dict:
    """The fixed pre and post periods around a change, as inclusive local days."""
    post_start = effective_day + pd.Timedelta(days=params.audit_settle_days)
    return {
        "pre_start": effective_day - pd.Timedelta(days=params.audit_pre_days),
        "pre_end": effective_day - pd.Timedelta(days=1),
        "post_start": post_start,
        "post_end": post_start + pd.Timedelta(days=params.audit_post_days - 1),
    }


def audit_one(peak: dict[str, pd.DataFrame], cells: pd.DataFrame, treated: str,
              controls: list[str], effective_day: pd.Timestamp, last_day: pd.Timestamp,
              params: Params) -> dict:
    """peak: each corridor's successful peak-hour calls (day, travel_time_s)."""
    span = periods(effective_day, params)
    floor = params.p95_min_samples

    def values(corridor_id: str, period: str) -> np.ndarray:
        rows = peak.get(corridor_id)
        if rows is None:
            return np.empty(0)
        inside = rows["day"].between(span[f"{period}_start"], span[f"{period}_end"])
        return pooled.clean(rows.loc[inside, "travel_time_s"])

    def bti(corridor_id: str, period: str) -> tuple[float, np.ndarray]:
        """A corridor's pooled BTI for a period, and its bootstrap draws."""
        v = values(corridor_id, period)
        key = ("audit", treated, effective_day.date(), corridor_id, period)
        (sample,) = pooled.draws(v, [pooled.bti_rows], params, key)
        return float(pooled.bti_rows(v[np.newaxis, :])[0]), sample

    n_pre, n_post = len(values(treated, "pre")), len(values(treated, "post"))
    out = {
        "corridor_id": treated, "effective_day": effective_day,
        "settle_days": params.audit_settle_days, **span, "n_pre": n_pre, "n_post": n_post,
        "n_controls": 0, "alpha": params.bootstrap_alpha, "resamples": params.bootstrap_resamples,
        "weights": {},
    }
    if n_pre < floor:
        return out | {"status": "insufficient_pre"}
    treated_pre, pre_draws = bti(treated, "pre")
    out["treated_pre"] = treated_pre
    if last_day < span["post_end"]:
        return out | {"status": "post_pending"}
    if n_post < floor:
        return out | {"status": "insufficient_post"}
    usable = [c for c in controls
              if min(len(values(c, "pre")), len(values(c, "post"))) >= floor]
    if not usable:
        return out | {"status": "no_controls"}

    treated_post, post_draws = bti(treated, "post")
    control_pre, control_pre_draws = zip(*(bti(c, "pre") for c in usable), strict=True)
    control_post, control_post_draws = zip(*(bti(c, "post") for c in usable), strict=True)
    control_pre_value = float(np.mean(control_pre))
    control_post_value = float(np.mean(control_post))
    effect_draws = (post_draws - pre_draws) - (
        np.mean(control_post_draws, axis=0) - np.mean(control_pre_draws, axis=0)
    )
    low, high = pooled.interval(effect_draws, params)

    days = cells["day"]
    involved = cells[(cells["corridor_id"] == treated) & (
        days.between(span["pre_start"], span["pre_end"])
        | days.between(span["post_start"], span["post_end"])
    )]
    n_expected, n_ok = involved["n_expected"].sum(), involved["n_ok"].sum()
    rate = float((n_expected - n_ok) / n_expected) if n_expected else np.nan
    return out | {
        "status": "ok", "n_controls": len(usable),
        "weights": {c: round(1 / len(usable), 6) for c in usable},
        "treated_post": treated_post, "control_pre": control_pre_value,
        "control_post": control_post_value,
        "effect": (treated_post - treated_pre) - (control_post_value - control_pre_value),
        "ci_low": low, "ci_high": high, "missing_rate": rate,
        "low_confidence": bool(np.isnan(rate) or rate > params.low_confidence_missing_rate),
    }


def intervention_audits(
    tti: pd.DataFrame, cells: pd.DataFrame, interventions: pd.DataFrame,
    params: Params = Params(),
) -> pd.DataFrame:
    """One row per intervention. tti: successful calls (corridor_id, requested_at, day,
    travel_time_s). cells: hourly cells, for missingness and the last day with data."""
    if interventions.empty or tti.empty:
        return pd.DataFrame(columns=COLUMNS)
    calls = tti[pooled.is_peak(tti["requested_at"], params)]
    peak = {cid: group[["day", "travel_time_s"]] for cid, group in calls.groupby("corridor_id")}
    last_day = cells.loc[cells["n_ok"] > 0, "day"].max()
    treated_all = set(interventions["corridor_id"])
    controls = sorted(c for c in cells["corridor_id"].unique() if c not in treated_all)
    rows = []
    for iv in interventions.itertuples(index=False):
        effective = local_day_hour(pd.to_datetime(pd.Series([iv.effective_at]), utc=True))
        row = audit_one(peak, cells, iv.corridor_id, controls, effective["day"].iloc[0],
                        last_day, params)
        rows.append({"intervention_id": iv.id, "missing_rate": np.nan,
                     "low_confidence": True} | row)
    return pd.DataFrame(rows).reindex(columns=COLUMNS)
