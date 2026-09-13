"""Corridor rankings over a trailing window, on shrunk estimates."""

import pandas as pd

from metrics.params import Params
from metrics.shrinkage import beta_binomial_eb, normal_eb

# BTI and PTI are not ranked here: they exist only as pooled statistics with
# floors and intervals (corridor_stats), never as a mean of hourly cells.
CONTINUOUS = ["tti_tomtom", "tti_p5"]
PROPORTIONS = {"congested_share_tomtom": "tti_tomtom", "congested_share_p5": "tti_p5"}
COLUMNS = [
    "window_end", "window_days", "index_name", "corridor_id", "n", "raw", "shrunk",
    "city_mean", "rank", "missing_rate", "low_confidence",
]


def rank_corridors(
    cells: pd.DataFrame,
    tti: pd.DataFrame,
    window_end: pd.Timestamp,
    params: Params = Params(),
) -> pd.DataFrame:
    """Rank 1 is the worst corridor (highest shrunk value) for each index.

    cells: hourly cells with indices; tti: per-call TTI. Continuous indices use
    one value per corridor-hour cell; congested shares use per-call TTI.
    """
    end = pd.Timestamp(window_end).normalize()
    start = end - pd.Timedelta(days=params.ranking_window_days - 1)
    cells = cells[(cells["day"] >= start) & (cells["day"] <= end)]
    tti = tti[(tti["day"] >= start) & (tti["day"] <= end)]

    parts = []
    for name in CONTINUOUS:
        stats = cells.groupby("corridor_id")[name].agg(n="count", mean="mean", var="var")
        stats = stats[stats["n"] > 0]
        if stats.empty:
            continue
        eb = normal_eb(stats["n"], stats["mean"], stats["var"])
        parts.append(eb.assign(index_name=name, n=stats["n"]))
    for name, col in PROPORTIONS.items():
        valid = tti[tti[col].notna()]
        if valid.empty:
            continue
        grouped = valid.assign(congested=valid[col] >= params.congested_tti).groupby("corridor_id")
        n = grouped.size()
        eb = beta_binomial_eb(grouped["congested"].sum(), n)
        parts.append(eb.assign(index_name=name, n=n))
    if not parts:
        return pd.DataFrame(columns=COLUMNS)

    out = pd.concat(parts).rename_axis("corridor_id").reset_index()
    out["rank"] = (
        out.groupby("index_name")["shrunk"].rank(ascending=False, method="min").astype("Int64")
    )
    totals = cells.groupby("corridor_id")[["n_expected", "n_ok"]].sum()
    missing = (totals["n_expected"] - totals["n_ok"]) / totals["n_expected"]
    out["missing_rate"] = out["corridor_id"].map(missing)
    out["low_confidence"] = out["missing_rate"] > params.low_confidence_missing_rate
    out["window_end"] = end
    out["window_days"] = params.ranking_window_days
    out["n"] = out["n"].astype("int64")
    return out[COLUMNS].sort_values(["index_name", "rank"], ignore_index=True)
