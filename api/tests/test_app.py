import pytest
from fastapi.testclient import TestClient

import app as api
from store import READABLE, MemoryStore, StoreError, postgrest_params, store_from_env

COMPUTED = "2026-09-13T21:45:00+00:00"


def corridor(cid, code, pair, cls, lat=17.497, lon=78.360):
    return {"id": cid, "code": code, "name": f"Demo — {cid}", "pair_id": pair, "class": cls,
            "origin_name": "Miyapur", "destination_name": "Hitec City", "origin_lat": lat,
            "origin_lon": lon, "dest_lat": 17.447, "dest_lon": 78.377, "active": True}


TAIL_STATS = ["tt_p95_peak_s", "bti_peak", "pti_tomtom_peak", "pti_p5_peak"]


def stats(cid, length, n_peak=620):
    row = {"corridor_id": cid, "window_start": "2026-06-15", "window_end": "2026-09-12",
           "n_expected": 100, "n_ok": 90, "missing_rate": 0.1, "low_confidence": False,
           "length_meters": length, "ff_tomtom_s": 1100.0, "ff_p5_s": 1050.0,
           "n_peak": n_peak, "tt_mean_peak_s": 1500.0,
           "tt_p95_peak_s": 2130.0, "tt_p95_peak_ci_low": 2010.0, "tt_p95_peak_ci_high": 2290.0,
           "bti_peak": 0.42, "bti_peak_ci_low": 0.31, "bti_peak_ci_high": 0.58,
           "pti_tomtom_peak": 1.94, "pti_tomtom_peak_ci_low": 1.83, "pti_tomtom_peak_ci_high": 2.08,
           "pti_p5_peak": 2.03, "pti_p5_peak_ci_low": 1.91, "pti_p5_peak_ci_high": 2.18,
           "computed_at": COMPUTED}
    if n_peak < 200:  # below the p95 floor the pipeline publishes nulls
        row |= {f"{k}{s}": None for k in TAIL_STATS for s in ("", "_ci_low", "_ci_high")}
    return row


def profile_rows(cid):
    return [{"corridor_id": cid, "hour": h, "window_start": "2026-05-16",
             "window_end": "2026-09-12", "n_expected": 400, "n_ok": 360, "n_tti_p5": 350,
             "missing_rate": 0.1, "low_confidence": False, "tt_mean_s": 1300.0 + h,
             "tt_p50_s": 1250.0 + h, "tt_p95_s": 1800.0 + h, "tt_p95_ci_low": 1750.0 + h,
             "tt_p95_ci_high": 1850.0 + h, "bti": 0.38, "bti_ci_low": 0.3, "bti_ci_high": 0.46,
             "computed_at": COMPUTED} for h in range(24)]


def walk(wid, table, at, rows, broken_at=None):
    return {"id": wid, "table_name": table, "verified_at": at, "ok": broken_at is None,
            "rows_checked": rows, "first_seq": 1, "head_seq": rows, "head_row_hash": "b" * 64,
            "breaks": 0 if broken_at is None else 1, "first_break_seq": broken_at,
            "first_break_problem": broken_at and "row_hash does not match row contents"}


def tables():
    return {
        "corridors": [corridor("miyapur-hitec", "HC-01", "PR-01", "core"),
                      corridor("miyapur-hitec-alt", "HC-02", "PR-01", "alternate"),
                      corridor("kukatpally-madhapur", "HC-03", "PR-02", "core")],
        "dataset_stats": [{"id": "window", "window_start": "2026-06-15",
                           "window_end": "2026-09-12", "n_corridors": 3, "n_expected": 300,
                           "n_ok": 270, "missing_rate": 0.1, "low_confidence": False,
                           "p95_min_samples": 200, "central_min_samples": 30,
                           "bootstrap_resamples": 2000, "method_version": "p02.4",
                           "computed_at": COMPUTED}],
        "corridor_stats": [stats("miyapur-hitec", 9800), stats("miyapur-hitec-alt", None, 180),
                           stats("kukatpally-madhapur", 11200)],
        "corridor_rankings": [{"corridor_id": "miyapur-hitec", "index_name": "tti_tomtom",
                               "n": 90, "raw": 1.9, "shrunk": 1.8, "city_mean": 1.5, "rank": 1}],
        "metrics_daily": [{"corridor_id": "miyapur-hitec", "day": d, "hour": 8, "n_expected": 4,
                           "n_ok": 3, "missing_rate": 0.25, "low_confidence": True,
                           "tti_tomtom": 1.9, "tti_p5": 2.0, "computed_at": COMPUTED}
                          for d in ("2026-09-11", "2026-09-12")],
        "profile_hourly": profile_rows("miyapur-hitec") + profile_rows("miyapur-hitec-alt"),
        "heatmap_weekly": [{"scope": "corridor", "corridor_id": "miyapur-hitec", "dow": 0,
                            "hour": 8, "window_start": "2026-06-15", "window_end": "2026-09-12",
                            "n_days": 12, "tti_tomtom_p50": 1.4, "tti_p5_p50": None,
                            "missing_rate": 0.05, "low_confidence": False}],
        "network_hourly": [
            {"day": "2026-09-12", "hour": 23, "pct_vs_normal": None, "missing_rate": 0.4},
            {"day": "2026-09-12", "hour": 22, "pct_vs_normal": 12.0, "state": "worse",
             "n_corridors": 3, "tti_tomtom_p50": 1.6, "tti_p5_p50": 1.7, "missing_rate": 0.08,
             "low_confidence": False, "computed_at": COMPUTED},
        ],
        "pair_advantage_hourly": [{"pair_id": "PR-01", "hour": h, "primary_n": 360,
                                   "alternate_n": 360, "advantage_p95_s": 60.0,
                                   "advantage_ci_low": 20.0, "advantage_ci_high": 100.0,
                                   "low_confidence": False} for h in range(24)],
        "interventions": [{"id": "signal-retiming", "corridor_id": "miyapur-hitec",
                           "effective_at": "2026-08-01T00:00:00+05:30",
                           "description": "Signal retiming, 6 junctions"}],
        "intervention_audit": [{
            "intervention_id": "signal-retiming", "corridor_id": "miyapur-hitec", "status": "ok",
            "effective_day": "2026-08-01", "settle_days": 9, "pre_start": "2026-05-09",
            "pre_end": "2026-07-31", "settle_start": "2026-08-01", "settle_end": "2026-08-09",
            "post_start": "2026-08-10", "post_end": "2026-09-06", "effect": -0.04,
            "ci_low": -0.09, "ci_high": 0.01, "equal_effect": -0.02, "equal_ci_low": -0.07,
            "equal_ci_high": 0.03, "estimator_gap": -0.02, "estimators_disagree": False,
            "n_placebos": 1, "placebo_rank": 2, "placebo_p_value": 1.0, "pre_rmspe": 0.02,
            "cv_pre_rmspe": 0.05, "overfit_ratio": 0.4, "pre_fit_overfit": True,
            "n_active_donors": 1, "std_effect": 2.5,
            "placebo_p_floor": 0.5, "placebo_extreme": False, "n_excluded_incomplete_pre": 1,
            "included_pre_missing_rate": 0.05, "excluded_pre_missing_rate": 0.22,
            "sensitivity_min_effect": -0.05, "sensitivity_max_effect": -0.03,
            "sensitivity_material": False,
            "placebo_verdict": "Not extreme: 1 of 1 placebo runs on untreated donors show a "
                               "post/pre fit ratio at least as large as the treated corridor's",
            "resamples": 2000, "missing_rate": 0.06, "computed_at": COMPUTED}],
        "audit_donors": [
            {"intervention_id": "signal-retiming", "corridor_id": "kukatpally-madhapur",
             "included": True, "weight": 1.0, "exclusion": None, "n_pre": 2400, "n_post": 800,
             "pre_missing_rate": 0.05, "short_pre_blocks": 0, "min_pre_block_n": 390},
            {"intervention_id": "signal-retiming", "corridor_id": "miyapur-hitec-alt",
             "included": False, "weight": None, "exclusion": "same_pair", "n_pre": 2300,
             "n_post": 790},
        ],
        "audit_placebos": [{"intervention_id": "signal-retiming",
                            "corridor_id": "kukatpally-madhapur", "effect": 0.01,
                            "pre_rmspe": 0.02, "cv_pre_rmspe": 0.04, "std_effect": 0.25,
                            "post_rmspe": 0.03,
                            "rmspe_ratio": 1.5,
                            "poor_pre_fit": False, "weights": {}}],
        "audit_sensitivity": [
            {"intervention_id": "signal-retiming", "variant": "relaxed_one_block",
             "block_floor": 200, "max_short_blocks": 1, "status": "ok", "n_donors": 2,
             "n_fit_blocks": 5, "effect": -0.05},
            {"intervention_id": "signal-retiming", "variant": "base", "block_floor": 200,
             "max_short_blocks": 0, "status": "ok", "n_donors": 1, "n_fit_blocks": 6,
             "effect": -0.04},
        ],
        "audit_blocks": [
            {"intervention_id": "signal-retiming", "period": "post", "block": 0,
             "block_start": "2026-08-10", "block_end": "2026-08-23", "complete": True,
             "n_treated": 400, "treated_bti": 0.38, "synthetic_bti": 0.41, "gap": -0.03,
             "running_mean": -0.03, "cs_low": -0.2, "cs_high": 0.14},
            {"intervention_id": "signal-retiming", "period": "pre", "block": 1,
             "block_start": "2026-05-23", "block_end": "2026-06-05", "complete": True,
             "n_treated": 400, "treated_bti": 0.42, "synthetic_bti": 0.41, "gap": 0.01},
            {"intervention_id": "signal-retiming", "period": "pre", "block": 0,
             "block_start": "2026-05-09", "block_end": "2026-05-22", "complete": True,
             "n_treated": 400, "treated_bti": 0.40, "synthetic_bti": 0.41, "gap": -0.01},
        ],
        "chain_verifications": [
            walk(1, "samples", "2026-09-12T22:00:00+00:00", 9),
            walk(2, "failed_samples", "2026-09-12T22:00:00+00:00", 1),
            walk(3, "samples", "2026-09-13T22:00:00+00:00", 10),
            walk(4, "failed_samples", "2026-09-13T22:00:00+00:00", 2),
        ],
        "export_manifest": [{"format": "csv", "object_path": "ledger/metrics_daily.csv",
                             "window_start": "2026-06-15", "window_end": "2026-09-12",
                             "n_rows": 6480, "n_bytes": 900000, "sha256": "c" * 64,
                             "missing_rate": 0.1, "computed_at": COMPUTED}],
    }


@pytest.fixture
def store():
    return MemoryStore(tables())


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    api.app.dependency_overrides[api.get_store] = lambda: store
    yield TestClient(api.app, follow_redirects=False)
    api.app.dependency_overrides.clear()


PATHS = [
    "/api/corridors", "/api/corridors/miyapur-hitec/series",
    "/api/corridors/miyapur-hitec/series?granularity=day", "/api/corridors/miyapur-hitec/profile",
    "/api/corridors/miyapur-hitec/heatmap", "/api/network/heatmap",
    "/api/pairs/PR-01/compare?hour=8", "/api/pairs/PR-02/compare", "/api/network/state",
    "/api/interventions", "/api/interventions/signal-retiming/audit", "/api/verify",
    "/api/export.csv", "/api/export.parquet", "/api/health",
    "/api/corridors/nope/profile", "/api/corridors/miyapur-hitec/series?granularity=week",
]


@pytest.mark.parametrize("path", PATHS)
def test_every_response_carries_as_of_and_missingness_rate(client, path):
    body = client.get(path).json()
    assert {"as_of", "missingness_rate", "missingness_note", "collection"} <= body.keys()


def test_read_path_never_touches_samples(client, store):
    assert "samples" not in READABLE
    for path in PATHS:
        client.get(path)
    assert "samples" not in store.queried
    with pytest.raises(ValueError):
        store.select("samples")


def test_cache_headers(client):
    cached = client.get("/api/corridors").headers["cache-control"]
    assert "s-maxage=3600" in cached and "stale-while-revalidate" in cached
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    assert client.get("/api/corridors/nope/profile").headers["cache-control"] == "no-store"


def test_corridors_pass_measured_length_through_or_null(client):
    body = client.get("/api/corridors").json()
    by_id = {c["id"]: c for c in body["corridors"]}
    assert body["as_of"] == COMPUTED and body["missingness_rate"] == 0.1
    assert by_id["miyapur-hitec"]["length_meters"] == 9800
    assert by_id["miyapur-hitec-alt"]["length_meters"] is None  # absent, not estimated
    assert by_id["miyapur-hitec"]["rankings"]["tti_tomtom"]["rank"] == 1
    assert "sample" not in body


def test_pair_declaring_one_corridor_is_a_valid_response(client):
    response = client.get("/api/pairs/PR-02/compare")
    assert response.status_code == 200
    body = response.json()
    assert body["primary"]["id"] == "kukatpally-madhapur"
    assert body["alternate"] is None and body["advantage"] is None


def test_pair_with_declared_alternate(client):
    body = client.get("/api/pairs/PR-01/compare?hour=8").json()
    assert body["hour"] == 8
    assert body["alternate"]["id"] == "miyapur-hitec-alt"
    assert len(body["primary"]["profile"]["tt_p95_s"]) == 24
    assert body["advantage"]["advantage_p95_s"][8] == 60.0
    # interval columns still in a stored row are never served
    assert not {"advantage_ci_low", "advantage_ci_high"} & set(body["advantage"])
    assert body["window"] == {"start": "2026-05-16", "end": "2026-09-12"}
    assert not [k for k in body["primary"]["profile"] if "_ci_" in k]
    assert body["primary"]["origin"] == {"name": "Miyapur", "lat": 17.497, "lon": 78.36}


def test_ledger_serves_pooled_peak_hours_as_point_values_with_counts(client):
    body = client.get("/api/corridors").json()
    assert body["floors"] == {"p95_min_samples": 200, "central_min_samples": 30}
    by_id = {c["id"]: c for c in body["corridors"]}
    ledger = by_id["miyapur-hitec"]["ledger"]
    assert ledger["window"] == {"start": "2026-06-15", "end": "2026-09-12"}
    assert ledger["n"] == 620 and ledger["hours"].startswith("06:30-10:30")
    assert (ledger["bti"], ledger["tt_p95_s"], ledger["pti_p5"]) == (0.42, 2130.0, 2.03)
    thin = by_id["miyapur-hitec-alt"]["ledger"]
    assert thin["n"] == 180  # the count that fell short of the floor
    assert thin["bti"] is None


def test_series_never_carry_cell_level_tail_statistics(client):
    hourly = client.get("/api/corridors/miyapur-hitec/series").json()["series"]
    assert not {"tt_p95_s", "bti", "pti_tomtom", "pti_p5"} & set(hourly)
    daily = client.get("/api/corridors/miyapur-hitec/series?granularity=day").json()["series"]
    assert "bti" not in daily


def test_profile_states_its_own_pooling_window(client):
    body = client.get("/api/corridors/miyapur-hitec/profile").json()
    assert body["window"] == {"start": "2026-05-16", "end": "2026-09-12"}
    assert "each local hour" in body["pooling"]
    assert body["profile"]["bti"][8] == 0.38
    assert not [k for k in body["profile"] if "_ci_" in k]
    assert body["floors"]["p95_min_samples"] == 200


def test_audit_publishes_donors_placebos_blocks_and_the_cross_check(client):
    body = client.get("/api/interventions/signal-retiming/audit").json()
    audit = body["audit"]
    assert audit["effect"] == -0.04
    # stored interval columns from before 0008 are never served
    assert not {"ci_low", "ci_high", "equal_ci_low", "equal_ci_high", "resamples"} & set(audit)
    assert (audit["equal_effect"], audit["estimators_disagree"]) == (-0.02, False)
    assert audit["placebo_verdict"].startswith("Not extreme")
    assert (audit["settle_start"], audit["settle_end"]) == ("2026-08-01", "2026-08-09")
    assert not {"control_pre", "weights", "n_controls"} & set(audit)
    donors = {d["corridor_id"]: d for d in body["donors"]}
    assert (donors["kukatpally-madhapur"]["weight"], donors["kukatpally-madhapur"]["code"]) == (
        1.0, "HC-03")
    assert donors["miyapur-hitec-alt"]["exclusion"] == "same_pair"
    assert donors["miyapur-hitec-alt"]["weight"] is None
    assert body["placebos"][0]["rmspe_ratio"] == 1.5
    assert body["placebos"][0]["cv_pre_rmspe"] == 0.04
    assert (audit["std_effect"], body["placebos"][0]["std_effect"]) == (2.5, 0.25)
    assert (audit["cv_pre_rmspe"], audit["overfit_ratio"], audit["pre_fit_overfit"],
            audit["n_active_donors"]) == (0.05, 0.4, True, 1)
    assert body["blocks"]["pre"]["block"] == [0, 1]
    # a legacy confidence-sequence column in a stored row is never served
    assert not {"running_mean", "cs_low", "cs_high"} & set(body["blocks"]["post"])
    assert (audit["placebo_rank"], audit["placebo_p_floor"]) == (2, 0.5)
    assert (audit["n_excluded_incomplete_pre"], audit["excluded_pre_missing_rate"]) == (1, 0.22)
    assert donors["kukatpally-madhapur"]["short_pre_blocks"] == 0
    assert [v["variant"] for v in body["sensitivity"]] == ["base", "relaxed_one_block"]
    assert body["sensitivity"][1]["n_fit_blocks"] == 5
    assert "bootstrap_resamples" not in body["floors"]


def test_unknown_pair_and_bad_hour(client):
    assert client.get("/api/pairs/PR-99/compare").status_code == 404
    assert client.get("/api/pairs/PR-01/compare?hour=24").status_code == 422


def test_series_defaults_to_window_and_limits_span(client):
    body = client.get("/api/corridors/miyapur-hitec/series").json()
    assert (body["from"], body["to"]) == ("2026-06-15", "2026-09-12")
    assert body["series"]["day"] == ["2026-09-11", "2026-09-12"]
    assert body["series"]["low_confidence"] == [True, True]
    too_long = "/api/corridors/miyapur-hitec/series?from=2026-01-01&to=2026-06-01"
    assert client.get(too_long).status_code == 422
    assert client.get("/api/corridors/nope/series").status_code == 404


def test_heatmap_is_sunday_first_and_keeps_unpublished_cells_null(client):
    body = client.get("/api/corridors/miyapur-hitec/heatmap").json()
    assert body["days"][0] == "Sun"
    assert len(body["tti_tomtom_p50"]) == 7 and len(body["tti_tomtom_p50"][0]) == 24
    assert body["tti_tomtom_p50"][0][8] == 1.4
    assert body["tti_p5_p50"][0][8] is None
    assert body["tti_tomtom_p50"][1][8] is None


def test_network_state_is_latest_hour_with_a_value(client):
    body = client.get("/api/network/state").json()
    assert (body["day"], body["hour"], body["value"], body["state"]) == ("2026-09-12", 22, 12.0,
                                                                          "worse")
    assert client.get("/api/network/state?hour=3").status_code == 422


def test_verify_reports_latest_walk(client):
    body = client.get("/api/verify").json()
    assert body["status"] == "ok"
    assert body["verification"]["head_seq"] == 10
    assert body["chains"]["failed_samples"]["head_seq"] == 2
    assert body["as_of"] == "2026-09-13T22:00:00+00:00"


def test_a_break_in_either_chain_is_reported():
    t = tables()
    t["chain_verifications"].append(
        walk(5, "failed_samples", "2026-09-14T22:00:00+00:00", 3, broken_at=2))
    api.app.dependency_overrides[api.get_store] = lambda: MemoryStore(t)
    try:
        body = TestClient(api.app).get("/api/verify").json()
    finally:
        api.app.dependency_overrides.clear()
    assert body["status"] == "broken"
    assert body["chains"]["failed_samples"]["first_break_seq"] == 2
    assert body["verification"]["ok"] is True


def test_pair_roles_come_from_declared_class(client):
    by_id = {c["id"]: c for c in client.get("/api/corridors").json()["corridors"]}
    assert by_id["miyapur-hitec"]["role"] == "primary"
    assert by_id["miyapur-hitec-alt"]["role"] == "alternate"
    assert api.pair_role({"class": "donor", "pair_id": None}) is None
    assert api.pair_role({"class": "core", "pair_id": None}) is None


def test_export_redirects_to_published_file(client):
    response = client.get("/api/export.csv")
    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://example.supabase.co/storage/v1/object/public/exports/ledger/metrics_daily.csv")
    assert response.headers["x-ledger-sha256"] == "c" * 64
    missing = client.get("/api/export.parquet")
    assert missing.status_code == 503 and missing.json()["as_of"] is None


def test_health_degrades_when_database_is_unreachable(client, store, monkeypatch):
    assert client.get("/api/health").json()["status"] == "ok"

    def fail(*_args, **_kwargs):
        raise StoreError("could not read dataset_stats")

    monkeypatch.setattr(store, "select", fail)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.headers["cache-control"] == "no-store"


def test_sample_flag_only_on_fixture_store(client, store):
    store.sample = True
    assert client.get("/api/corridors").json()["sample"] is True


def test_store_refuses_service_key_and_fixtures_on_vercel(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "anything")
    with pytest.raises(RuntimeError, match="service key"):
        store_from_env()
    monkeypatch.delenv("SUPABASE_SERVICE_KEY")
    monkeypatch.setenv("LEDGER_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="deployment"):
        store_from_env()


def test_postgrest_params():
    params = postgrest_params(
        [("corridor_id", "eq", "a"), ("day", "gte", "2026-09-01"), ("day", "lte", "2026-09-12"),
         ("pct_vs_normal", "notnull", None)],
        [("day", "desc"), ("hour", "asc")], limit=1000, offset=2000,
    )
    assert params == [
        ("select", "*"), ("corridor_id", "eq.a"), ("day", "gte.2026-09-01"),
        ("day", "lte.2026-09-12"), ("pct_vs_normal", "not.is.null"),
        ("order", "day.desc,hour.asc"), ("limit", "1000"), ("offset", "2000"),
    ]


def test_runtime_dependencies_exclude_numpy_and_pandas():
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    deps = " ".join(project["project"]["dependencies"]).lower()
    assert "numpy" not in deps and "pandas" not in deps


def test_a_stored_road_is_served_simplified_and_the_full_polyline_is_never_read():
    t = tables()
    full = [[17.497, 78.36], [17.48, 78.358], [17.464, 78.357], [17.447, 78.377]]
    simple = [full[0], full[2], full[3]]
    t["corridors"][0] |= {"route_polyline": full, "route_polyline_simplified": simple,
                          "route_polyline_fetched_at": "2026-09-14T02:00:00+00:00"}
    api.app.dependency_overrides[api.get_store] = lambda: MemoryStore(t)
    try:
        client = TestClient(api.app)
        corridors = client.get("/api/corridors").json()["corridors"]
        pair = client.get("/api/pairs/PR-01/compare").json()
    finally:
        api.app.dependency_overrides.clear()
    by_id = {c["id"]: c for c in corridors}
    assert by_id["miyapur-hitec"]["path"] == {
        "points": simple, "fetched_at": "2026-09-14T02:00:00+00:00",
        "source": "TomTom calculateRoute, fetched once at verification, simplified to 5 m"}
    assert by_id["kukatpally-madhapur"]["path"] is None       # no stored road: nothing drawn as one
    assert pair["primary"]["path"]["points"] == simple and pair["alternate"]["path"] is None
    assert full[1] not in by_id["miyapur-hitec"]["path"]["points"]


def test_postgrest_selects_only_the_columns_asked_for():
    assert postgrest_params([], [], 1, columns=("id", "code"))[0] == ("select", "id,code")
    assert postgrest_params([], [], 1)[0] == ("select", "*")


# The three states a view must tell apart: nothing collected, collected, unreachable.
WALKED_AT = "2026-09-14T23:58:29+00:00"
DATA_PATHS = ["/api/corridors", "/api/network/state", "/api/network/heatmap",
              "/api/interventions", "/api/verify", "/api/health"]


def empty_walk(wid, table):
    """A walk of an empty chain, as the database records it: no head at all."""
    return {"id": wid, "table_name": table, "verified_at": WALKED_AT, "ok": True,
            "rows_checked": 0, "first_seq": None, "head_seq": None, "head_row_hash": None,
            "breaks": 0, "first_break_seq": None, "first_break_problem": None}


def nothing_collected(walks):
    draft = corridor("placeholder-01", "HC-01", None, "donor") | {"active": False}
    return {"corridors": [draft], "chain_verifications": walks}


@pytest.fixture
def serve():
    def use(t):
        api.app.dependency_overrides[api.get_store] = lambda: MemoryStore(t)
        return TestClient(api.app, follow_redirects=False)
    yield use
    api.app.dependency_overrides.clear()


@pytest.mark.parametrize("path", DATA_PATHS)
def test_zero_samples_reads_as_not_started_on_every_endpoint(serve, path):
    walks = [empty_walk(9, "samples"), empty_walk(10, "failed_samples")]
    client = serve(nothing_collected(walks))
    response = client.get(path)
    body = response.json()
    assert response.status_code == 200
    assert body["collection"] == {"status": "not_started",
                                  "basis": "latest walk of the samples chain", "as_of": WALKED_AT}
    assert body["missingness_rate"] is None
    assert body["missingness_note"] == "collection_not_started"


def test_samples_without_published_metrics_are_collecting_and_not_yet_computed(serve):
    client = serve(nothing_collected([walk(3, "samples", WALKED_AT, 12)]))
    body = client.get("/api/corridors").json()
    assert body["collection"]["status"] == "collecting"
    assert body["missingness_note"] == "not_yet_computed"


def test_no_walk_and_no_metrics_is_unknown_rather_than_not_started(serve):
    body = serve(nothing_collected([])).get("/api/verify").json()
    assert body["status"] == "never_verified"
    assert body["collection"] == {"status": "unknown",
                                  "basis": "no chain walk and no published metrics", "as_of": None}
    assert body["missingness_note"] == "collection_unknown"


def test_published_metrics_carry_their_rate_and_no_note(client):
    body = client.get("/api/corridors").json()
    assert body["collection"] == {"status": "collecting", "basis": "published metrics",
                                  "as_of": COMPUTED}
    assert body["missingness_rate"] == 0.1 and body["missingness_note"] is None
    assert all(c["missingness_note"] is None for c in body["corridors"])


def test_an_unreachable_database_never_reads_as_not_started(client, store, monkeypatch):
    def fail(*_args, **_kwargs):
        raise StoreError("connection refused")

    monkeypatch.setattr(store, "select", fail)
    for path in ("/api/corridors", "/api/verify", "/api/network/state"):
        response = client.get(path)
        body = response.json()
        assert response.status_code == 502, path
        assert body["collection"] is None and body["missingness_note"] == "not_applicable"
    health = client.get("/api/health")
    assert health.status_code == 503
    assert health.json()["collection"] is None and health.json()["database"] == "unreachable"
