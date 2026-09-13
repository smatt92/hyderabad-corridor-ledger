"""Travel Time, Buffer Time and Planning Time indices.

Two free-flow references are computed and both are published:
  tomtom: TomTom's noTrafficTravelTimeInSeconds for the same call
  p5:     the 5th percentile of observed night-slot travel times (00:00-04:00
          local, when the roads are emptiest) over a trailing window
They answer different questions and disagree in informative ways, so they are
never averaged, reconciled or collapsed into one column.
"""

import numpy as np
import pandas as pd

from metrics.cells import local_day_hour
from metrics.params import Params


def free_flow_p5(samples: pd.DataFrame, params: Params = Params()) -> pd.DataFrame:
    """Per corridor and local day: p5 of successful night-slot travel times, local
    hours in ff_p5_night_hours, over the trailing ff_p5_window_days (inclusive).
    NaN below ff_p5_min_samples."""
    ok = samples[samples["ok"]]
    local = local_day_hour(ok["requested_at"])
    start, end = params.ff_p5_night_hours
    night = (local["hour"] >= start) & (local["hour"] < end)
    ok = ok[night].assign(day=local.loc[night, "day"])
    window = np.timedelta64(params.ff_p5_window_days - 1, "D")
    parts = []
    for corridor_id, group in ok.groupby("corridor_id"):
        group = group.sort_values("day")
        sample_days = group["day"].to_numpy()
        travel = group["travel_time_s"].to_numpy()
        days = pd.date_range(sample_days.min(), sample_days.max(), freq="D").to_numpy()
        lo = np.searchsorted(sample_days, days - window, side="left")
        hi = np.searchsorted(sample_days, days, side="right")
        p5 = [
            np.quantile(travel[a:b], 0.05) if b - a >= params.ff_p5_min_samples else np.nan
            for a, b in zip(lo, hi, strict=True)
        ]
        parts.append(
            pd.DataFrame({"corridor_id": corridor_id, "day": days, "ff_p5_s": p5})
        )
    if not parts:
        return pd.DataFrame(
            {"corridor_id": pd.Series(dtype=str), "day": pd.Series(dtype="datetime64[ns]"),
             "ff_p5_s": pd.Series(dtype="float64")}
        )
    out = pd.concat(parts, ignore_index=True)
    out["day"] = out["day"].astype("datetime64[ns]")
    return out


def cell_indices(cells: pd.DataFrame, ff_p5: pd.DataFrame) -> pd.DataFrame:
    """TTI against both references. A cell has too few calls for BTI or PTI, which
    exist only as pooled statistics (metrics.readmodel, metrics.audit)."""
    out = cells.merge(ff_p5, on=["corridor_id", "day"], how="left")
    out["tti_tomtom"] = out["tt_mean_s"] / out["ff_tomtom_s"]
    out["tti_p5"] = out["tt_mean_s"] / out["ff_p5_s"]
    return out


def sample_tti(samples: pd.DataFrame, ff_p5: pd.DataFrame) -> pd.DataFrame:
    """Per successful call: local day and hour, and TTI against both references."""
    ok = samples[samples["ok"]]
    ok = ok.join(local_day_hour(ok["requested_at"]))
    ok = ok.merge(ff_p5, on=["corridor_id", "day"], how="left")
    ok["tti_tomtom"] = ok["travel_time_s"] / ok["no_traffic_travel_time_s"]
    ok["tti_p5"] = ok["travel_time_s"] / ok["ff_p5_s"]
    return ok.sort_values(["corridor_id", "requested_at"], ignore_index=True)
