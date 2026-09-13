"""Worst-15: the 15-minute window with the highest mean TTI, per corridor per day.

It pinpoints when a corridor breaks, not merely that it does. The window is
(window_start, window_end], ending at a successful call. At a cadence of 15
minutes or more a window holds one call, so this is the worst single reading.
"""

import numpy as np
import pandas as pd

from metrics.params import BASES, Params

COLUMNS = [
    "corridor_id", "day", "basis", "window_start", "window_end", "tti", "n_samples",
    "missing_rate", "low_confidence",
]


def worst_15(
    tti: pd.DataFrame, daily_missing: pd.DataFrame, params: Params = Params()
) -> pd.DataFrame:
    width = pd.Timedelta(params.worst_window)
    rows = []
    for (corridor_id, day), group in tti.groupby(["corridor_id", "day"], sort=True):
        series = group.set_index("requested_at").sort_index()
        for basis in BASES:
            rolled = series[f"tti_{basis}"].rolling(params.worst_window)
            means = rolled.mean().to_numpy()
            counts = rolled.count().to_numpy()
            if np.isnan(means).all():
                rows.append((corridor_id, day, basis, pd.NaT, pd.NaT, np.nan, 0))
                continue
            pos = int(np.nanargmax(means))
            end = series.index[pos]
            rows.append((corridor_id, day, basis, end - width, end, means[pos], int(counts[pos])))
    out = pd.DataFrame(rows, columns=COLUMNS[:7])
    out = out.merge(daily_missing, on=["corridor_id", "day"], how="left")
    return out[COLUMNS]
