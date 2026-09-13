"""The fixture panel's travel-time model, on the collector's schedule.

Shared by scripts/dev/build_fixtures.py (the local preview), the audit's
positive control (tests/test_audit_power.py) and its power analysis
(scripts/dev/audit_power.py). Never imported by metrics/ or by the frontend.

A corridor's TTI follows the fixture generator's shape: a morning and evening
peak, a weekly cycle, per-call volatility that grows at the peaks, and an
occasional long tail. Calls fail more often at peaks and on whole dark days.
scheduled_panel adds two sources of slow variation an audit has to see
through, both applied to the excess over free flow:
  shared_day_sd      a city-wide daily shock shared by every corridor
  corridor_week_sd   each corridor's own week-to-week drift
Their sizes are assumptions, not estimates from Hyderabad data. `first` overrides
c00's base, volatility and spread after they are drawn, so the other corridors
stay identical: the audit's stress test uses it to make the treated corridor
unlike its donors on purpose.

inject_bti_effect adds an intervention of known size: it stretches one
corridor's peak-hour travel times about their mean, which keeps the mean and
moves the empirical p95 affinely, so the pooled BTI rises by exactly delta.
"""

import numpy as np
import pandas as pd

from metrics import pooled, schedule
from metrics.cells import hourly_cells, local_day_hour
from metrics.params import LOCAL_TZ, Params

DOW_FACTOR = np.array([0.86, 1.00, 1.05, 1.05, 1.03, 1.13, 0.72])  # Monday first


def hour_factor(h: np.ndarray) -> np.ndarray:
    def bump(mean, sd, amp):
        return amp * np.exp(-((h - mean) ** 2) / (2 * sd * sd))

    f = 1 + bump(9.4, 1.35, 0.62) + bump(18.9, 1.8, 0.86) + bump(13, 2.4, 0.14)
    return np.where(h < 6, f * (0.9 - 0.02 * (6 - h)), f)


def scheduled_panel(n_corridors: int, first_day: pd.Timestamp, days: int, tier: str,
                    rng: np.random.Generator, shared_day_sd: float = 0.10,
                    corridor_week_sd: float = 0.08, first: dict | None = None) -> pd.DataFrame:
    """Samples for corridors c00, c01, ... at every slot of their tier's schedule."""
    first_day = pd.Timestamp(first_day).normalize()
    by_day = [schedule.day_slots(tier, first_day + pd.Timedelta(days=d)) for d in range(days)]
    slots = by_day[0].append(by_day[1:])
    local = slots.tz_convert(LOCAL_TZ)
    hour = np.asarray(local.hour + local.minute / 60, dtype=float)
    day_index = np.asarray((local.tz_localize(None).normalize() - first_day).days)
    shape = hour_factor(hour) * DOW_FACTOR[np.asarray(local.dayofweek)]
    peakiness = (hour_factor(hour) - 1) / 0.9
    shared = rng.normal(0, shared_day_sd, days)
    parts = []
    for i in range(n_corridors):
        base = 1.12 + rng.random() * 1.25
        volatility = 0.05 + rng.random() * 0.16
        spread = 1.22 + rng.random() * 0.62
        miss = 0.16 + rng.random() * 0.22 if rng.random() < 0.18 else rng.random() * 0.12
        free = 300 + rng.random() * 1300
        if i == 0 and first:
            base = first.get("base", base)
            volatility = first.get("volatility", volatility)
            spread = first.get("spread", spread)
        weekly = rng.normal(0, corridor_week_sd, days // 7 + 1)
        jitter = rng.normal(0, volatility, len(slots)) * (0.4 + (hour_factor(hour) - 1))
        tti = base * shape * (1 + jitter)
        tti = np.where(rng.random(len(slots)) < 0.08, tti * spread, tti)
        scale = np.clip((1 + shared[day_index]) * (1 + weekly[day_index // 7]), 0, None)
        tti = np.clip(1 + (tti - 1) * scale, 1.0, None)
        fail = rng.random(len(slots)) < miss * (0.5 + peakiness)
        fail |= (rng.random(days) < miss / 6)[day_index]
        parts.append(pd.DataFrame({
            "corridor_id": f"c{i:02d}", "requested_at": slots, "ok": ~fail,
            "http_status": np.where(fail, 429, 200),
            "travel_time_s": np.where(fail, np.nan, free * tti),
            "no_traffic_travel_time_s": np.where(fail, np.nan, free),
        }))
    return pd.concat(parts, ignore_index=True)


def audit_inputs(samples: pd.DataFrame, tier: str,
                 params: Params = Params()) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(successful calls, hourly cells, corridors) as metrics.audit takes them."""
    ids = sorted(samples["corridor_id"].unique())
    corridors = pd.DataFrame({"corridor_id": ids, "tier": tier, "pair_id": None})
    cells = hourly_cells(samples, corridors, params)
    ok = samples[samples["ok"]]
    calls = ok[["corridor_id", "requested_at", "travel_time_s"]].join(
        local_day_hour(ok["requested_at"]))
    return calls.reset_index(drop=True), cells, corridors


def _bti(values: np.ndarray) -> float:
    mean = values.mean()
    return float((np.quantile(values, 0.95) - mean) / mean)


def inject_bti_effect(frame: pd.DataFrame, corridor_id: str, start: pd.Timestamp,
                      end: pd.Timestamp, delta: float,
                      params: Params = Params()) -> tuple[pd.DataFrame, float, float]:
    """(frame with the effect, pooled BTI before, after) for one corridor's successful
    peak-hour calls between two local days, inclusive."""
    ok = frame["ok"] if "ok" in frame else pd.Series(True, index=frame.index)
    day = local_day_hour(frame["requested_at"])["day"]
    mask = ((frame["corridor_id"] == corridor_id) & ok & day.between(start, end)
            & pooled.is_peak(frame["requested_at"], params))
    values = frame.loc[mask, "travel_time_s"].to_numpy(dtype=float)
    before, mean = _bti(values), values.mean()
    out = frame.copy()
    out.loc[mask, "travel_time_s"] = mean + (1 + delta / before) * (values - mean)
    return out, before, _bti(out.loc[mask, "travel_time_s"].to_numpy(dtype=float))
