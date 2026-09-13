"""Corridor-hour cells and informative missingness.

API failures cluster during peak congestion, so missingness correlates with
the quantity being measured. Every cell carries its missingness rate and a
low-confidence flag. Nothing is imputed: a cell with no successful sample
has NaN metrics, not an estimate.

A cell holds a handful of calls, too few for a tail statistic. BTI, PTI and
p95 travel time are computed only over pooled calls (metrics.pooled).
"""

import numpy as np
import pandas as pd

from metrics import schedule
from metrics.params import LOCAL_TZ, Params

KEYS = ["corridor_id", "day", "hour"]


def local_day_hour(ts: pd.Series) -> pd.DataFrame:
    """Local calendar day (tz-naive midnight) and hour for UTC timestamps."""
    local = ts.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    return pd.DataFrame(
        {
            "day": local.dt.normalize().astype("datetime64[ns]"),
            "hour": local.dt.hour.astype("int64"),
        },
        index=ts.index,
    )


def daily_missingness(cells: pd.DataFrame, params: Params = Params()) -> pd.DataFrame:
    """Missingness per corridor and local day, from the hourly cells."""
    totals = cells.groupby(["corridor_id", "day"])[["n_expected", "n_ok"]].sum()
    totals["missing_rate"] = (totals["n_expected"] - totals["n_ok"]) / totals["n_expected"]
    totals["low_confidence"] = totals["missing_rate"] > params.low_confidence_missing_rate
    return totals[["missing_rate", "low_confidence"]].reset_index()


def expected_slots(samples: pd.DataFrame, corridors: pd.DataFrame) -> pd.Series:
    """Scheduled call slots per cell, from the slot a corridor's first call answered
    through its last call.

    The slots are the collector's schedule for the corridor's tier
    (metrics.schedule), on local wall-clock time, so a run that never started
    still counts as missing. Corridors without a tier contribute nothing; their
    denominator falls back to attempted calls in hourly_cells.
    """
    tiers = corridors.set_index("corridor_id")["tier"]
    parts = []
    for corridor_id, group in samples.groupby("corridor_id"):
        tier = tiers.get(corridor_id)
        if not isinstance(tier, str):
            continue
        first, last = group["requested_at"].min(), group["requested_at"].max()
        slots = pd.Series(schedule.slots_between(tier, first, last))
        cells = local_day_hour(slots).assign(corridor_id=corridor_id)
        parts.append(cells.groupby(KEYS).size())
    if not parts:
        empty = pd.MultiIndex.from_arrays(
            [pd.Series(dtype=str), pd.Series(dtype="datetime64[ns]"), pd.Series(dtype="int64")],
            names=KEYS,
        )
        return pd.Series(dtype="int64", name="n_slots", index=empty)
    return pd.concat(parts).rename("n_slots")


def hourly_cells(
    samples: pd.DataFrame, corridors: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    """Counts, missingness and travel-time statistics per corridor-hour."""
    s = samples.join(local_day_hour(samples["requested_at"]))
    attempted = s.groupby(KEYS).size().rename("n_attempted")
    ok = s[s["ok"]]
    stats = ok.groupby(KEYS).agg(
        n_ok=("travel_time_s", "size"),
        tt_mean_s=("travel_time_s", "mean"),
        ff_tomtom_s=("no_traffic_travel_time_s", "mean"),
    )
    slots = expected_slots(samples, corridors)

    index = attempted.index.union(slots.index)
    cells = pd.concat(
        [attempted.reindex(index), slots.reindex(index), stats.reindex(index)], axis=1
    )
    for col in ("n_attempted", "n_slots", "n_ok"):
        cells[col] = cells[col].fillna(0).astype("int64")

    cells["n_expected"] = np.maximum(cells["n_slots"], cells["n_attempted"])
    cells["missing_rate"] = (cells["n_expected"] - cells["n_ok"]) / cells["n_expected"]
    cells["low_confidence"] = cells["missing_rate"] > params.low_confidence_missing_rate
    cols = [
        "n_expected", "n_attempted", "n_ok", "missing_rate", "low_confidence",
        "tt_mean_s", "ff_tomtom_s",
    ]
    return cells[cols].reset_index().sort_values(KEYS, ignore_index=True)
