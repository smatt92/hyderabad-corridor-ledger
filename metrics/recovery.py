"""Recovery time: from the day's peak TTI until TTI first drops below threshold.

This is a duration with censoring. A corridor that has not cleared by the end
of the day's sampling window is right-censored at its last reading, and so is
one whose readings stop (a gap longer than recovery_max_gap_min; failures
cluster in the worst congestion). Censored durations are never dropped:
dropping them removes exactly the corridors that stay broken longest.

Days whose peak never reaches the threshold never enter the risk set.
Kaplan-Meier estimates the recovery curve; a Cox model estimates what
drives the hazard of clearing.
"""

import numpy as np
import pandas as pd
from statsmodels.duration.hazard_regression import PHReg

from metrics.cells import local_day_hour
from metrics.params import BASES, Params

EVENT_COLUMNS = [
    "corridor_id", "basis", "day", "peak_at", "peak_tti", "duration_min", "cleared",
    "censor_reason", "is_weekend", "missing_rate", "low_confidence",
]
KM_COLUMNS = [
    "corridor_id", "basis", "t_min", "n_at_risk", "n_events", "n_censored", "survival", "se",
]
COX_COLUMNS = [
    "basis", "covariate", "n_obs", "n_events", "coef", "hazard_ratio", "se", "p_value",
    "ci_low", "ci_high",
]
COVARIATES = ["peak_tti", "is_weekend", "pm_peak", "missing_rate"]


def recovery_duration(times: list, values: np.ndarray, threshold: float, max_gap: pd.Timedelta):
    """For one day's ordered readings: (peak index, duration, cleared, censor_reason),
    or None when the peak stays below threshold."""
    peak = int(np.argmax(values))
    if values[peak] < threshold:
        return None
    last = times[peak]
    for j in range(peak + 1, len(values)):
        if times[j] - last > max_gap:
            return peak, last - times[peak], False, "data_gap"
        last = times[j]
        if values[j] < threshold:
            return peak, last - times[peak], True, None
    return peak, last - times[peak], False, "window_end"


def recovery_events(
    tti: pd.DataFrame, daily_missing: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    max_gap = pd.Timedelta(minutes=params.recovery_max_gap_min)
    rows = []
    for (corridor_id, day), group in tti.groupby(["corridor_id", "day"], sort=True):
        group = group.sort_values("requested_at")
        for basis in BASES:
            readings = group[group[f"tti_{basis}"].notna()]
            if readings.empty:
                continue
            times = list(readings["requested_at"])
            values = readings[f"tti_{basis}"].to_numpy(dtype=float)
            result = recovery_duration(times, values, params.recovery_threshold, max_gap)
            if result is None:
                continue
            peak, duration, cleared, reason = result
            rows.append((
                corridor_id, basis, day, times[peak], values[peak],
                duration.total_seconds() / 60, cleared, reason, pd.Timestamp(day).dayofweek >= 5,
            ))
    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    out = pd.DataFrame(rows, columns=EVENT_COLUMNS[:9])
    return out.merge(daily_missing, on=["corridor_id", "day"], how="left")[EVENT_COLUMNS]


def kaplan_meier(duration, cleared) -> pd.DataFrame:
    """Product-limit estimate with Greenwood standard errors, one row per distinct
    time. Censorings at time t are counted at risk at t."""
    duration = np.asarray(duration, dtype=float)
    event = np.asarray(cleared, dtype=bool)
    rows = []
    survival, greenwood = 1.0, 0.0
    for t in np.unique(duration):
        at_risk = int((duration >= t).sum())
        events = int((event & (duration == t)).sum())
        censored = int((~event & (duration == t)).sum())
        if events:
            survival *= 1 - events / at_risk
            greenwood = (
                greenwood + events / (at_risk * (at_risk - events)) if at_risk > events else np.inf
            )
        se = survival * np.sqrt(greenwood) if np.isfinite(greenwood) else np.nan
        rows.append((t, at_risk, events, censored, survival, se))
    return pd.DataFrame(rows, columns=KM_COLUMNS[2:])


def km_by_corridor(events: pd.DataFrame) -> pd.DataFrame:
    parts = [
        kaplan_meier(g["duration_min"], g["cleared"]).assign(corridor_id=c, basis=b)
        for (c, b), g in events.groupby(["corridor_id", "basis"])
    ]
    if not parts:
        return pd.DataFrame(columns=KM_COLUMNS)
    return pd.concat(parts, ignore_index=True)[KM_COLUMNS]


def cox_model(events: pd.DataFrame, min_events_per_covariate: int = 10) -> pd.DataFrame:
    """Cox proportional hazards for clearing, per basis (Efron ties).

    hazard_ratio, ci_low and ci_high are on the hazard-ratio scale; a ratio
    above 1 means faster recovery. Constant covariates are dropped, and a
    basis with fewer than min_events_per_covariate events per covariate is
    not fitted.
    """
    parts = []
    for basis, g in events.groupby("basis"):
        x = pd.DataFrame(
            {
                "peak_tti": g["peak_tti"].astype(float),
                "is_weekend": g["is_weekend"].astype(float),
                "pm_peak": local_day_hour(g["peak_at"])["hour"].between(16, 21).astype(float),
                "missing_rate": g["missing_rate"].astype(float),
            }
        )
        keep = x.notna().all(axis=1)
        x, g = x[keep], g[keep]
        x = x.loc[:, x.nunique() > 1]
        n_events = int(g["cleared"].sum())
        if x.shape[1] == 0 or n_events < min_events_per_covariate * x.shape[1]:
            continue
        try:
            fit = PHReg(
                g["duration_min"].to_numpy(dtype=float),
                x.to_numpy(),
                status=g["cleared"].to_numpy(dtype=int),
                ties="efron",
            ).fit()
        except (np.linalg.LinAlgError, ValueError):
            continue
        ci = np.exp(np.asarray(fit.conf_int()))
        parts.append(
            pd.DataFrame(
                {
                    "basis": basis,
                    "covariate": list(x.columns),
                    "n_obs": len(g),
                    "n_events": n_events,
                    "coef": fit.params,
                    "hazard_ratio": np.exp(fit.params),
                    "se": fit.bse,
                    "p_value": fit.pvalues,
                    "ci_low": ci[:, 0],
                    "ci_high": ci[:, 1],
                }
            )
        )
    if not parts:
        return pd.DataFrame(columns=COX_COLUMNS)
    return pd.concat(parts, ignore_index=True)[COX_COLUMNS]
