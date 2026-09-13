"""STL decomposition of each corridor's daily TTI series.

Traffic is violently weekly-seasonal. A trend read off the raw series mistakes
festival weeks and monsoon fortnights for real change, so every trend
statement is made on the STL trend component only.

STL cannot run across gaps, and gaps are never imputed. The series is split
at every day with no successful call, and each contiguous segment of at
least stl_min_segment_days is decomposed on its own.
"""

import pandas as pd
from statsmodels.tsa.seasonal import STL

from metrics.params import BASES, Params

COLUMNS = [
    "corridor_id", "basis", "day", "segment_start", "observed", "trend", "seasonal",
    "resid", "missing_rate", "low_confidence",
]


def daily_series(cells: pd.DataFrame, basis: str) -> pd.DataFrame:
    """Mean of the hourly cell TTIs per corridor and day, over hours with a value."""
    col = f"tti_{basis}"
    valid = cells[cells[col].notna()]
    return valid.groupby(["corridor_id", "day"])[col].mean().rename("observed").reset_index()


def contiguous_segments(days: pd.Series) -> pd.Series:
    """Segment number for each of a sorted run of days; a gap starts a new segment."""
    return (days.diff() != pd.Timedelta(days=1)).cumsum()


def stl_decompose(
    cells: pd.DataFrame, daily_missing: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    parts = []
    for basis in BASES:
        series = daily_series(cells, basis)
        for corridor_id, group in series.groupby("corridor_id"):
            group = group.sort_values("day", ignore_index=True)
            for _, seg in group.groupby(contiguous_segments(group["day"])):
                if len(seg) < params.stl_min_segment_days:
                    continue
                y = pd.Series(seg["observed"].to_numpy(), index=pd.DatetimeIndex(seg["day"]))
                fit = STL(y, period=params.stl_period, robust=True).fit()
                parts.append(
                    pd.DataFrame(
                        {
                            "corridor_id": corridor_id,
                            "basis": basis,
                            "day": seg["day"].to_numpy(),
                            "segment_start": seg["day"].iloc[0],
                            "observed": y.to_numpy(),
                            "trend": fit.trend.to_numpy(),
                            "seasonal": fit.seasonal.to_numpy(),
                            "resid": fit.resid.to_numpy(),
                        }
                    )
                )
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out = out.merge(daily_missing, on=["corridor_id", "day"], how="left")
    return out[COLUMNS]
