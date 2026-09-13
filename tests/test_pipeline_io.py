import numpy as np
import pandas as pd
import pytest

from metrics.io import _bytea, to_records
from metrics.params import METHOD_VERSION, Params
from metrics.pipeline import compute_all
from tests.helpers import parsed


def synthetic_panel(days=35):
    """Two corridors, hourly calls. Evening peak 18:00-20:00. Corridor b loses its
    18:00 and 19:00 calls to HTTP 429 every Friday: missingness at the peak."""
    rows = []
    for d in pd.date_range("2026-08-01", periods=days, freq="D"):
        for hour in range(24):
            wall = f"{d:%Y-%m-%d} {hour:02d}:00"
            peak = 1.0 + (0.9 if 18 <= hour <= 20 else 0.0) + (0.2 if d.dayofweek == 4 else 0.0)
            rows.append(("a", wall, 200, 600 * peak, 600))
            if d.dayofweek == 4 and hour in (18, 19):
                rows.append(("b", wall, 429, None, None))
            else:
                rows.append(("b", wall, 200, 900 * peak * 1.1, 900))
    return parsed(rows)


# 35 days of hourly calls is a small panel: floors and audit periods scaled to it.
SMALL = Params(p95_min_samples=50, central_min_samples=10, bootstrap_resamples=200,
               audit_pre_days=14, audit_settle_days=3, audit_post_days=7)


def test_compute_all_end_to_end_invariants():
    samples = synthetic_panel()
    corridors = pd.DataFrame({"corridor_id": ["a", "b"], "tier": ["B", "B"],
                              "pair_id": ["PR-01", "PR-01"], "role": ["primary", "alternate"]})
    interventions = pd.DataFrame({"id": ["a-retiming"], "corridor_id": ["a"],
                                  "effective_at": ["2026-08-22T00:00:00+05:30"]})
    tables = compute_all(samples, corridors, interventions, SMALL)

    assert set(tables) == {
        "metrics_daily", "worst15_daily", "corridor_rankings", "stl_daily", "change_points",
        "recovery_events", "recovery_km", "recovery_cox", "before_after", "dataset_stats",
        "corridor_stats", "metrics_day", "profile_hourly", "heatmap_weekly", "network_hourly",
        "pair_advantage_hourly", "intervention_audit",
    }
    assert len(tables["pair_advantage_hourly"]) == 24
    assert tables["intervention_audit"]["status"].tolist() == ["ok"]
    assert all((t["method_version"] == METHOD_VERSION).all() for t in tables.values())

    md = tables["metrics_daily"]
    assert {"tti_tomtom", "tti_p5"} <= set(md.columns)
    assert not {"tt_p95_s", "bti", "pti_tomtom", "pti_p5"} & set(md.columns)  # never per cell
    lost = md[(md.corridor_id == "b") & (md.n_ok == 0)]
    assert len(lost) == 10  # 5 Fridays x 2 peak hours
    assert lost[["tt_mean_s", "tti_tomtom", "tti_p5"]].isna().all().all()  # not imputed
    assert lost["low_confidence"].all()

    stl = tables["stl_daily"]
    assert set(stl["corridor_id"]) == {"a", "b"} and set(stl["basis"]) == {"tomtom", "p5"}

    ranks = tables["corridor_rankings"]
    for _, group in ranks.groupby("index_name"):
        assert group.sort_values("rank")["shrunk"].is_monotonic_decreasing

    assert not tables["before_after"].empty

    ledger = tables["corridor_stats"].set_index("corridor_id")
    assert ledger.loc["a", "n_peak"] == 35 * 8  # 07:00-10:00 and 17:00-20:00, every day
    assert ledger.loc["a", "bti_peak_ci_low"] <= ledger.loc["a", "bti_peak"] \
        <= ledger.loc["a", "bti_peak_ci_high"]


def test_compute_all_refuses_empty_input():
    empty = parsed([]).reindex(columns=["seq", "corridor_id", "requested_at", "http_status",
                                        "ok", "travel_time_s", "no_traffic_travel_time_s"])
    with pytest.raises(ValueError, match="no samples"):
        compute_all(empty, pd.DataFrame(), pd.DataFrame())


def test_to_records_formats_dates_and_nulls():
    frame = pd.DataFrame({
        "day": [pd.Timestamp("2026-09-01")],
        "peak_at": [pd.Timestamp("2026-09-01T02:30:00Z")],
        "tti": [np.nan],
        "rank": pd.array([pd.NA], dtype="Int64"),
        "cleared": [False],
    })
    (record,) = to_records(frame)
    assert record["day"] == "2026-09-01"
    assert record["peak_at"].startswith("2026-09-01T02:30:00")
    assert record["tti"] is None and record["rank"] is None
    assert record["cleared"] is False


def test_bytea_decoding():
    assert _bytea("\\x1f8b00") == b"\x1f\x8b\x00"
    with pytest.raises(ValueError):
        _bytea("H4sI")
