"""Compose the pure metric functions into the published tables.

compute_all is pure as well: parsed samples, corridors and interventions in,
one dataframe per table out. metrics.io does the reading and writing.
"""

import pandas as pd

from metrics.audit import intervention_audits
from metrics.cells import daily_missingness, hourly_cells
from metrics.confseq import before_after
from metrics.control import change_points
from metrics.indices import cell_indices, free_flow_p5, sample_tti
from metrics.params import METHOD_VERSION, Params
from metrics.rankings import rank_corridors
from metrics.readmodel import (
    add_hourly_context,
    corridor_stats,
    dataset_stats,
    heatmap_weekly,
    metrics_day,
    network_hourly,
    pair_advantage_hourly,
    profile_hourly,
    profile_window,
    read_window,
)
from metrics.recovery import cox_model, km_by_corridor, recovery_events
from metrics.seasonal import stl_decompose
from metrics.worst15 import worst_15

CORRIDOR_COLUMNS = ["corridor_id", "tier", "pair_id", "role", "treatment_status"]
METRICS_DAILY_COLUMNS = [
    "corridor_id", "day", "hour", "n_expected", "n_attempted", "n_ok", "missing_rate",
    "low_confidence", "tt_mean_s", "ff_tomtom_s", "ff_p5_s", "tti_tomtom", "tti_p5",
    "tti_tomtom_delta_wk", "tti_p5_delta_wk", "tt_ratio_own_median",
]


def compute_all(
    samples: pd.DataFrame,
    corridors: pd.DataFrame,
    interventions: pd.DataFrame,
    params: Params = Params(),
    window_end: pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    """Every derived table, keyed by table name, each tagged with METHOD_VERSION."""
    if samples.empty:
        raise ValueError("no samples to compute metrics from")

    corridors = corridors.reindex(columns=CORRIDOR_COLUMNS)
    cells = hourly_cells(samples, corridors, params)
    ff_p5 = free_flow_p5(samples, params)
    indexed = cell_indices(cells, ff_p5)
    tti = sample_tti(samples, ff_p5)
    daily_missing = daily_missingness(cells, params)
    window = read_window(cells, params)
    hours_window = profile_window(window, params)
    stl = stl_decompose(indexed, daily_missing, params)
    events = recovery_events(tti, daily_missing, params)
    day = metrics_day(indexed, params)
    profile = profile_hourly(tti, indexed, hours_window, params)
    audits = intervention_audits(tti, cells, corridors, interventions, params)

    tables = {
        "metrics_daily": add_hourly_context(indexed, window)[METRICS_DAILY_COLUMNS],
        "worst15_daily": worst_15(tti, daily_missing, params),
        "corridor_rankings": rank_corridors(
            indexed, tti, window_end if window_end is not None else cells["day"].max(), params
        ),
        "stl_daily": stl,
        "change_points": change_points(stl, params),
        "recovery_events": events,
        "recovery_km": km_by_corridor(events),
        "recovery_cox": cox_model(events),
        "before_after": before_after(stl, interventions, params),
        "dataset_stats": dataset_stats(indexed, window, params),
        "corridor_stats": corridor_stats(samples, indexed, ff_p5, window, params),
        "metrics_day": day,
        "profile_hourly": profile,
        "heatmap_weekly": heatmap_weekly(tti, indexed, window, params),
        "network_hourly": network_hourly(indexed, window, params),
        "pair_advantage_hourly": pair_advantage_hourly(
            tti, profile, corridors, hours_window, params
        ),
        **audits,
    }
    return {name: frame.assign(method_version=METHOD_VERSION) for name, frame in tables.items()}
