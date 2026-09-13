"""Read model for the P-04 API.

The API selects rows; it never computes. Everything a view shows is
precomputed here, pure like the rest of metrics/.

Pooling windows end on the last local day with a successful call:
  read window, read_window_days (90): dataset and corridor stats, the ledger's
      pooled peak-hour statistics, the rhythm matrix and network state.
  profile window, profile_window_days (120): the 24-hour profile and the pair
      comparison, which pool every call at each local hour across the window.

BTI, PTI and every p95 exist only as statistics of pooled calls
(metrics.pooled): never computed from one day or one hour cell, published only
at or above their floor, as point values with no interval. Pooled counts
are published beside them, so a withheld value says why.

TTI appears against both free-flow bases wherever it appears. Quantities that
need no free-flow reference (travel time, BTI, travel time against a
corridor's own normal) carry no basis.
"""

import numpy as np
import pandas as pd

from metrics import pooled
from metrics.cells import local_day_hour
from metrics.params import BASES, Params

MISSING = ["n_expected", "n_ok", "missing_rate", "low_confidence"]
CENTRAL_QUANTILES = {"p25": 0.25, "p50": 0.5, "p75": 0.75}

LEDGER_TRAVEL = ["n_peak", "tt_mean_peak_s", "tt_p95_peak_s", "bti_peak"]
LEDGER_PTI = [f"pti_{b}_peak" for b in BASES]
STATS_COLUMNS = [
    "corridor_id", "window_start", "window_end", *MISSING, "length_meters", "ff_tomtom_s",
    "ff_p5_s", *LEDGER_TRAVEL, *LEDGER_PTI,
]
DATASET_COLUMNS = [
    "id", "window_start", "window_end", "n_corridors", "n_expected", "n_ok", "missing_rate",
    "low_confidence", "p95_min_samples", "central_min_samples",
]
DAY_COLUMNS = ["corridor_id", "day", *MISSING, "tt_mean_s", "tti_tomtom", "tti_p5"]
PROFILE_STATS = [
    "n_tti_p5", "tt_mean_s", "tt_p50_s", "tt_p95_s", "bti",
    *[f"tti_{b}_{s}" for b in BASES for s in ("p25", "p50", "p75", "p95")],
]
PROFILE_COLUMNS = ["corridor_id", "hour", "window_start", "window_end", *MISSING, *PROFILE_STATS]
HEATMAP_COLUMNS = [
    "scope", "corridor_id", "dow", "hour", "window_start", "window_end", "n_days",
    "tti_tomtom_p50", "tti_p5_p50", *MISSING,
]
NETWORK_COLUMNS = [
    "day", "hour", "n_corridors", "tt_ratio_p50", "pct_vs_normal", "state", "tti_tomtom_p50",
    "tti_p5_p50", *MISSING,
]
PAIR_COLUMNS = [
    "pair_id", "hour", "window_start", "window_end", "primary_id", "alternate_id", "primary_n",
    "alternate_n", "primary_tt_p95_s", "alternate_tt_p95_s", "advantage_p95_s", "low_confidence",
]


def read_window(
    cells: pd.DataFrame, params: Params = Params()
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last local day of the read window, inclusive."""
    days = cells.loc[cells["n_ok"] > 0, "day"]
    if days.empty:
        raise ValueError("no successful calls to build a read window from")
    end = days.max()
    return end - pd.Timedelta(days=params.read_window_days - 1), end


def profile_window(window, params: Params = Params()) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The profile's pooling window: profile_window_days ending with the read window."""
    end = window[1]
    return end - pd.Timedelta(days=params.profile_window_days - 1), end


def in_window(frame: pd.DataFrame, window) -> pd.DataFrame:
    start, end = window
    return frame[(frame["day"] >= start) & (frame["day"] <= end)]


def missingness(cells: pd.DataFrame, keys: list[str], params: Params = Params()) -> pd.DataFrame:
    """Scheduled and successful calls, missing rate and low-confidence flag by keys."""
    totals = cells.groupby(keys)[["n_expected", "n_ok"]].sum()
    rate = (totals["n_expected"] - totals["n_ok"]) / totals["n_expected"]
    totals["missing_rate"] = rate
    totals["low_confidence"] = rate.isna() | (rate > params.low_confidence_missing_rate)
    return totals


def sunday_first(day: pd.Series) -> pd.Series:
    """Weekday with Sunday = 0, the order the rhythm matrix is drawn in."""
    return (day.dt.dayofweek + 1) % 7


def add_hourly_context(indexed: pd.DataFrame, window) -> pd.DataFrame:
    """Adds to each corridor-hour row:

    tti_tomtom_delta_wk, tti_p5_delta_wk: change against the same hour seven
        days earlier. NaN when either reading is missing.
    tt_ratio_own_median: tt_mean_s over this corridor's median tt_mean_s at the
        same hour across the read window. Travel time only, so no basis.
    """
    keys = ["corridor_id", "day", "hour"]
    week_before = indexed[keys + ["tti_tomtom", "tti_p5"]].assign(
        day=lambda f: f["day"] + pd.Timedelta(days=7)
    )
    out = indexed.merge(week_before, on=keys, how="left", suffixes=("", "_wk"))
    for basis in BASES:
        out[f"tti_{basis}_delta_wk"] = out[f"tti_{basis}"] - out[f"tti_{basis}_wk"]
    own = in_window(indexed, window).groupby(["corridor_id", "hour"])["tt_mean_s"].median()
    own = own.rename("own_median_s").reset_index()
    out = out.merge(own, on=["corridor_id", "hour"], how="left")
    out["tt_ratio_own_median"] = out["tt_mean_s"] / out["own_median_s"]
    return out.drop(columns=["tti_tomtom_wk", "tti_p5_wk", "own_median_s"])


def ledger_stats(calls: pd.DataFrame, params: Params = Params()) -> pd.DataFrame:
    """The ledger's pooled statistics: every successful peak-hour call in calls, one
    distribution per corridor."""
    peak = calls[pooled.is_peak(calls["requested_at"], params)]
    rows = []
    for corridor_id, group in peak.groupby("corridor_id"):
        s = pooled.travel(group["travel_time_s"], params)
        rows.append({
            "corridor_id": corridor_id, "n_peak": s["n"], "tt_mean_peak_s": s["mean"],
            "tt_p95_peak_s": s["p95"], "bti_peak": s["bti"],
        })
    return pd.DataFrame(rows, columns=["corridor_id", *LEDGER_TRAVEL]).set_index("corridor_id")


def corridor_stats(
    samples: pd.DataFrame,
    indexed: pd.DataFrame,
    ff_p5: pd.DataFrame,
    window,
    params: Params = Params(),
) -> pd.DataFrame:
    """Per corridor over the read window.

    length_meters is the median lengthInMeters that TomTom measured on successful
    calls: measured, never derived from coordinates. The ledger's BTI and PTI pool
    every successful peak-hour call in the window; PTI divides that pooled p95 by
    each free-flow reference. Point values beside n_peak: no interval is published.
    """
    start, end = window
    ok = samples[samples["ok"]]
    ok = in_window(ok.join(local_day_hour(ok["requested_at"])), window)
    measured = ok.groupby("corridor_id").agg(
        length_meters=("length_m", "median"),
        ff_tomtom_s=("no_traffic_travel_time_s", "median"),
    )
    latest_p5 = (
        ff_p5[(ff_p5["day"] <= end) & ff_p5["ff_p5_s"].notna()]
        .sort_values("day")
        .groupby("corridor_id")["ff_p5_s"]
        .last()
    )
    out = missingness(in_window(indexed, window), ["corridor_id"], params)
    out = out.join(measured, how="left").join(latest_p5, how="left")
    out = out.join(ledger_stats(ok, params), how="left")
    out["length_meters"] = out["length_meters"].round().astype("Int64")
    out["n_peak"] = out["n_peak"].fillna(0).astype("int64")  # a count, not a measurement
    for col in LEDGER_TRAVEL[1:]:
        out[col] = out[col].astype(float)
    for basis, reference in (("tomtom", "ff_tomtom_s"), ("p5", "ff_p5_s")):
        out[f"pti_{basis}_peak"] = out["tt_p95_peak_s"] / out[reference].astype(float)
    return out.reset_index().assign(window_start=start, window_end=end)[STATS_COLUMNS]


def dataset_stats(indexed: pd.DataFrame, window, params: Params = Params()) -> pd.DataFrame:
    """The read window's coverage, and the floors every published number was held to."""
    start, end = window
    cells = in_window(indexed, window)
    n_expected, n_ok = int(cells["n_expected"].sum()), int(cells["n_ok"].sum())
    rate = (n_expected - n_ok) / n_expected if n_expected else np.nan
    return pd.DataFrame([{
        "id": "window", "window_start": start, "window_end": end,
        "n_corridors": int(cells["corridor_id"].nunique()), "n_expected": n_expected,
        "n_ok": n_ok, "missing_rate": rate,
        "low_confidence": bool(np.isnan(rate) or rate > params.low_confidence_missing_rate),
        "p95_min_samples": params.p95_min_samples,
        "central_min_samples": params.central_min_samples,
    }])[DATASET_COLUMNS]


def metrics_day(indexed: pd.DataFrame, params: Params = Params()) -> pd.DataFrame:
    """Daily means over the hours that have a value, as the STL series uses."""
    keys = ["corridor_id", "day"]
    means = indexed.groupby(keys)[["tt_mean_s", "tti_tomtom", "tti_p5"]].mean()
    out = missingness(indexed, keys, params).join(means, how="left")
    return out.reset_index()[DAY_COLUMNS]


def hour_stats(corridor_id: str, hour: int, calls: pd.DataFrame, params: Params) -> dict:
    """One corridor-hour of the profile, pooled over its calls."""
    travel = pooled.travel(calls["travel_time_s"], params)
    row = {
        "corridor_id": corridor_id, "hour": hour, "n_tti_p5": int(calls["tti_p5"].notna().sum()),
        "tt_mean_s": travel["mean"], "tt_p50_s": travel["p50"], "tt_p95_s": travel["p95"],
        "bti": travel["bti"],
    }
    for basis in BASES:
        values = calls[f"tti_{basis}"]
        for name, q in CENTRAL_QUANTILES.items():
            row[f"tti_{basis}_{name}"] = pooled.quantile(values, q, params)
        row[f"tti_{basis}_p95"] = pooled.quantile(values, 0.95, params)
    return row


def profile_hourly(
    tti: pd.DataFrame, indexed: pd.DataFrame, window, params: Params = Params()
) -> pd.DataFrame:
    """24-hour profile over the profile window: every successful call at each local
    hour, pooled. Mean, median and TTI quartiles at the central floor; p95 travel time,
    BTI and TTI p95 at the p95 floor, each a point value beside its count."""
    start, end = window
    keys = ["corridor_id", "hour"]
    rows = [hour_stats(corridor_id, hour, calls, params)
            for (corridor_id, hour), calls in in_window(tti, window).groupby(keys)]
    stats = pd.DataFrame(rows, columns=keys + PROFILE_STATS).set_index(keys)
    out = missingness(in_window(indexed, window), keys, params).join(stats, how="left")
    out["n_tti_p5"] = out["n_tti_p5"].fillna(0).astype("int64")  # a count
    for col in PROFILE_STATS[1:]:
        out[col] = out[col].astype(float)
    return out.reset_index().assign(window_start=start, window_end=end)[PROFILE_COLUMNS]


def heatmap_weekly(
    tti: pd.DataFrame, indexed: pd.DataFrame, window, params: Params = Params()
) -> pd.DataFrame:
    """Median TTI per weekday and hour over the read window, for each corridor and for
    all corridors pooled: the median of every successful call in the cell, published
    only at the central floor. NULL below it, never estimated."""
    start, end = window
    cells = in_window(indexed, window).assign(dow=lambda f: sunday_first(f["day"]))
    calls = in_window(tti, window).assign(dow=lambda f: sunday_first(f["day"]))

    def matrix(keys: list[str]) -> pd.DataFrame:
        stats = cells[cells["n_ok"] > 0].groupby(keys).agg(n_days=("day", "nunique"))
        for basis in BASES:
            col = f"tti_{basis}"
            if calls.empty:
                stats[f"{col}_p50"] = np.nan
                continue
            medians = calls.groupby(keys)[col].agg(lambda v: pooled.quantile(v, 0.5, params))
            stats = stats.join(medians.rename(f"{col}_p50"), how="left")
        out = missingness(cells, keys, params).join(stats, how="left")
        out["n_days"] = out["n_days"].fillna(0).astype("int64")  # a count, not a measurement
        return out.reset_index()

    corridor = matrix(["corridor_id", "dow", "hour"]).assign(scope="corridor")
    network = matrix(["dow", "hour"]).assign(scope="network", corridor_id=None)
    out = pd.concat([corridor, network], ignore_index=True)
    return out.assign(window_start=start, window_end=end)[HEATMAP_COLUMNS]


def network_hourly(indexed: pd.DataFrame, window, params: Params = Params()) -> pd.DataFrame:
    """Citywide state per local day and hour, against normal.

    Each corridor's travel time is divided by its own median at the same hour
    and weekday over the previous network_baseline_weeks weeks (at least
    network_baseline_min of them). The citywide figure is the median of those
    ratios. It uses travel time only, so it is one number without collapsing
    the two free-flow bases.
    """
    keys = ["corridor_id", "day", "hour"]
    base = indexed[keys + ["tt_mean_s"]]
    values = ["tt_mean_s", "tti_tomtom", "tti_p5", "n_expected", "n_ok"]
    frame = in_window(indexed, window)[keys + values]
    weeks = [f"wk{k}" for k in range(1, params.network_baseline_weeks + 1)]
    for k, col in enumerate(weeks, start=1):
        shifted = base.assign(day=base["day"] + pd.Timedelta(days=7 * k))
        frame = frame.merge(shifted.rename(columns={"tt_mean_s": col}), on=keys, how="left")
    prior = frame[weeks]
    enough = prior.notna().sum(axis=1) >= params.network_baseline_min
    frame["ratio"] = (frame["tt_mean_s"] / prior.median(axis=1)).where(enough)

    grouped = frame.groupby(["day", "hour"])
    out = grouped.agg(
        n_corridors=("ratio", "count"),
        tt_ratio_p50=("ratio", "median"),
        tti_tomtom_p50=("tti_tomtom", "median"),
        tti_p5_p50=("tti_p5", "median"),
    )
    out = missingness(frame, ["day", "hour"], params).join(out)
    out["pct_vs_normal"] = (out["tt_ratio_p50"] - 1) * 100
    band = params.network_state_band_pct
    state = np.select(
        [out["pct_vs_normal"] > band, out["pct_vs_normal"] < -band], ["worse", "better"], "normal"
    )
    out["state"] = pd.Series(state, index=out.index).where(out["pct_vs_normal"].notna())
    return out.reset_index()[NETWORK_COLUMNS]


def pair_advantage_hourly(
    tti: pd.DataFrame, profile: pd.DataFrame, corridors: pd.DataFrame, window,
    params: Params = Params(),
) -> pd.DataFrame:
    """p95 travel time of the primary minus the declared alternate, per local hour.
    Each side pools its calls at that hour over the profile window. The difference is
    a point value, published only when both sides reach the p95 floor, beside both
    counts; no interval is published (docs/ledger_intervals.md).

    Only pairs that declare an alternate appear. A pair with one corridor has
    nothing to compare against, and no second route is ever derived for it.
    """
    start, end = window
    declared = corridors.dropna(subset=["pair_id", "role"])
    primary = declared.loc[declared["role"] == "primary", ["pair_id", "corridor_id"]]
    alternate = declared.loc[declared["role"] == "alternate", ["pair_id", "corridor_id"]]
    pairs = primary.merge(alternate, on="pair_id", suffixes=("_p", "_a")).rename(
        columns={"corridor_id_p": "primary_id", "corridor_id_a": "alternate_id"}
    )
    if pairs.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    calls = {key: group["travel_time_s"].to_numpy()
             for key, group in in_window(tti, window).groupby(["corridor_id", "hour"])}
    confident = profile.set_index(["corridor_id", "hour"])["low_confidence"].eq(False)
    rows = []
    for pair in pairs.itertuples(index=False):
        for hour in range(24):
            p = pooled.clean(calls.get((pair.primary_id, hour), []))
            a = pooled.clean(calls.get((pair.alternate_id, hour), []))
            advantage = (pooled.quantile(p, 0.95, params)
                         - pooled.quantile(a, 0.95, params))
            # no profile row for an hour means nothing measured: low confidence
            both = (bool(confident.get((pair.primary_id, hour), False))
                    and bool(confident.get((pair.alternate_id, hour), False)))
            rows.append({
                "pair_id": pair.pair_id, "hour": hour, "primary_id": pair.primary_id,
                "alternate_id": pair.alternate_id, "primary_n": len(p), "alternate_n": len(a),
                "primary_tt_p95_s": pooled.quantile(p, 0.95, params),
                "alternate_tt_p95_s": pooled.quantile(a, 0.95, params),
                "advantage_p95_s": advantage,
                "low_confidence": not both,
            })
    return pd.DataFrame(rows).assign(window_start=start, window_end=end)[PAIR_COLUMNS]
