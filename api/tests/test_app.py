import pytest
from fastapi.testclient import TestClient

import app as api
from store import READABLE, MemoryStore, StoreError, postgrest_params, store_from_env

COMPUTED = "2026-09-13T21:45:00+00:00"


def corridor(cid, code, pair, role, lat=17.497, lon=78.360):
    return {"id": cid, "code": code, "name": f"Demo — {cid}", "pair_id": pair, "role": role,
            "origin_name": "Miyapur", "destination_name": "Hitec City", "origin_lat": lat,
            "origin_lon": lon, "dest_lat": 17.447, "dest_lon": 78.377, "active": True}


def stats(cid, length):
    return {"corridor_id": cid, "window_start": "2026-06-15", "window_end": "2026-09-12",
            "n_expected": 100, "n_ok": 90, "missing_rate": 0.1, "low_confidence": False,
            "length_meters": length, "ff_tomtom_s": 1100.0, "ff_p5_s": 1050.0,
            "computed_at": COMPUTED}


def profile_rows(cid):
    return [{"corridor_id": cid, "hour": h, "n_expected": 90, "n_ok": 80, "missing_rate": 0.11,
             "low_confidence": False, "tt_mean_s": 1300.0 + h, "tt_p50_s": 1250.0 + h,
             "tt_p95_s": 1800.0 + h, "bti": 0.38, "computed_at": COMPUTED} for h in range(24)]


def tables():
    return {
        "corridors": [corridor("miyapur-hitec", "HC-01", "PR-01", "primary"),
                      corridor("miyapur-hitec-alt", "HC-02", "PR-01", "alternate"),
                      corridor("kukatpally-madhapur", "HC-03", "PR-02", "primary")],
        "dataset_stats": [{"id": "window", "window_start": "2026-06-15",
                           "window_end": "2026-09-12", "n_corridors": 3, "n_expected": 300,
                           "n_ok": 270, "missing_rate": 0.1, "low_confidence": False,
                           "method_version": "p02.2", "computed_at": COMPUTED}],
        "corridor_stats": [stats("miyapur-hitec", 9800), stats("miyapur-hitec-alt", None),
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
        "pair_advantage_hourly": [{"pair_id": "PR-01", "hour": h, "advantage_p95_s": 60.0,
                                   "low_confidence": False} for h in range(24)],
        "interventions": [{"id": "signal-retiming", "corridor_id": "miyapur-hitec",
                           "effective_at": "2026-08-01T00:00:00+05:30",
                           "description": "Signal retiming, 6 junctions"}],
        "intervention_audit": [{"intervention_id": "signal-retiming", "status": "ok",
                                "effect": -0.04, "missing_rate": 0.06, "computed_at": COMPUTED}],
        "chain_verifications": [
            {"id": 1, "verified_at": "2026-09-12T22:00:00+00:00", "ok": True, "rows_checked": 9,
             "first_seq": 1, "head_seq": 9, "head_row_hash": "a" * 64, "breaks": 0,
             "first_break_seq": None},
            {"id": 2, "verified_at": "2026-09-13T22:00:00+00:00", "ok": True, "rows_checked": 10,
             "first_seq": 1, "head_seq": 10, "head_row_hash": "b" * 64, "breaks": 0,
             "first_break_seq": None},
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
    assert "as_of" in body and "missingness_rate" in body


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
    assert body["primary"]["origin"] == {"name": "Miyapur", "lat": 17.497, "lon": 78.36}


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
    assert body["as_of"] == "2026-09-13T22:00:00+00:00"


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
