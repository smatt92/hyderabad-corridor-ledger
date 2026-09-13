"""Read-only API for the Hyderabad corridor ledger.

It selects precomputed rows and shapes them into JSON. It never reads
samples, never computes a metric, and holds only the publishable key. Every
response carries as_of and missingness_rate, including errors, where both
are null. The frontend renders staleness and low confidence from them.
"""

from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Path, Query
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from store import Row, Store, StoreError, store_from_env

CACHE = "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400"
NO_STORE = "no-store"
MAX_SERIES_DAYS = 92
CORRIDOR_ID = r"^[a-z0-9][a-z0-9-]{1,62}$"
PAIR_ID = r"^[A-Z]{2}-[0-9]{2,4}$"
INTERVENTION_ID = r"^[a-z0-9][a-z0-9-]{1,62}$"
BASES = ("tomtom", "p5")
CHAINS = ("samples", "failed_samples")
# corridors.class is the collector's vocabulary (core, alternate, donor). Payloads
# name a pair's two sides primary and alternate: a paired core corridor is its
# pair's primary. Donors are never paired and have no role.
PAIR_ROLE = {"core": "primary", "alternate": "alternate"}

# An hour or a day holds too few calls for a p95: tail statistics are served only
# from the pooled tables, each with its window, count and interval.
HOURLY_COLUMNS = [
    "day", "hour", "n_expected", "n_ok", "missing_rate", "low_confidence", "tt_mean_s",
    "tti_tomtom", "tti_p5", "tti_tomtom_delta_wk", "tti_p5_delta_wk", "tt_ratio_own_median",
]
DAILY_COLUMNS = ["day", "n_expected", "n_ok", "missing_rate", "low_confidence", "tt_mean_s",
                 "tti_tomtom", "tti_p5"]
PROFILE_COLUMNS = [
    "hour", "n_expected", "n_ok", "missing_rate", "low_confidence", "n_tti_p5", "tt_mean_s",
    "tt_p50_s", "tt_p95_s", "bti",
    *[f"tti_{b}_{s}" for b in BASES for s in ("p25", "p50", "p75", "p95")],
]
COMPARE_PROFILE_COLUMNS = [
    "hour", "n_ok", "tt_p50_s", "tt_p95_s", "bti", "missing_rate", "low_confidence",
]
ADVANTAGE_COLUMNS = [
    "hour", "primary_n", "alternate_n", "primary_tt_p95_s", "alternate_tt_p95_s",
    "advantage_p95_s", "low_confidence",
]
FLOOR_FIELDS = ("p95_min_samples", "central_min_samples")
PEAK_HOURS = "06:30-10:30, 16:30-21:00 IST"
PROFILE_POOLING = "all successful calls at each local hour across the window"
AUDIT_FIELDS = [
    "status", "effective_day", "settle_days", "pre_start", "pre_end", "settle_start", "settle_end",
    "post_start", "post_end", "block_days", "pre_blocks", "post_blocks", "post_blocks_complete",
    "n_pre", "n_post", "n_donors", "treated_pre", "treated_post", "synthetic_pre",
    "synthetic_post", "effect", "pre_rmspe", "post_rmspe", "rmspe_ratio",
    "cv_pre_rmspe", "overfit_ratio", "pre_fit_overfit", "n_active_donors", "std_effect",
    "n_placebos",
    "placebo_rank", "placebo_p_value", "placebo_p_floor", "placebo_extreme",
    "placebo_verdict", "equal_control_pre", "equal_control_post", "equal_effect", "estimator_gap",
    "estimators_disagree", "n_excluded_incomplete_pre",
    "included_pre_missing_rate",
    "excluded_pre_missing_rate", "included_pre_bti", "excluded_pre_bti", "sensitivity_min_effect",
    "sensitivity_max_effect", "sensitivity_material", "alpha", "low_confidence",
    "method_version",
]
DONOR_FIELDS = ["corridor_id", "included", "weight", "exclusion", "n_pre", "n_post", "pre_bti",
                "post_bti", "pre_missing_rate", "short_pre_blocks", "min_pre_block_n"]
SENSITIVITY_FIELDS = ["variant", "block_floor", "max_short_blocks", "status", "n_donors",
                      "n_fit_blocks", "effect", "equal_effect",
                      "placebo_rank", "n_placebos", "placebo_p_value", "placebo_p_floor"]
VARIANT_ORDER = ["base", "strict_125", "strict_150", "relaxed_one_block"]
PLACEBO_FIELDS = ["corridor_id", "effect", "pre_rmspe", "cv_pre_rmspe", "std_effect",
                  "post_rmspe", "rmspe_ratio", "poor_pre_fit", "weights"]
BLOCK_FIELDS = ["block", "block_start", "block_end", "complete", "n_treated", "treated_bti",
                "synthetic_bti", "gap"]

VERIFICATION_FIELDS = [
    "verified_at", "ok", "rows_checked", "first_seq", "head_seq", "head_row_hash", "breaks",
    "first_break_seq", "first_break_problem",
]

app = FastAPI(
    title="Hyderabad Corridor Ledger read API",
    docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None,
)
router = APIRouter(prefix="/api")
_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = store_from_env()
    return _store


StoreDep = Annotated[Store, Depends(get_store)]


def respond(store: Store | None, body: dict, as_of: Any, missingness_rate: Any,
            status: int = 200, cache: str = CACHE, headers: dict | None = None) -> JSONResponse:
    payload = {"as_of": as_of, "missingness_rate": missingness_rate, **body}
    if store is not None and store.sample:
        payload["sample"] = True
    return JSONResponse(payload, status_code=status,
                        headers={"Cache-Control": cache, **(headers or {})})


def columnar(rows: list[Row], keys: list[str]) -> dict[str, list]:
    return {k: [r.get(k) for r in rows] for k in keys}


def one(rows: list[Row]) -> Row | None:
    return rows[0] if rows else None


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    return respond(None, {"error": exc.detail}, None, None, exc.status_code, NO_STORE)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc: RequestValidationError):
    detail = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return respond(None, {"error": detail}, None, None, 422, NO_STORE)


@app.exception_handler(StoreError)
async def store_error(_request, exc: StoreError):
    return respond(None, {"error": str(exc)}, None, None, 502, NO_STORE)


def dataset(store: Store) -> Row | None:
    return one(store.select("dataset_stats", limit=1))


def floors(ds: Row | None) -> dict | None:
    """The floors the published numbers were held to, as recorded by the pipeline that
    computed them."""
    return ds and {k: ds.get(k) for k in FLOOR_FIELDS}


# What the API reads from corridors. Never route_polyline, the full stored road: only its
# simplified copy is served, and the full one would ride along with every request.
CORRIDOR_COLUMNS = (
    "id", "code", "name", "pair_id", "class", "origin_name", "destination_name",
    "origin_lat", "origin_lon", "dest_lat", "dest_lon",
    "route_polyline_simplified", "route_polyline_fetched_at",
)


def corridor_or_404(store: Store, corridor_id: str) -> Row:
    row = one(store.select("corridors", [("id", "eq", corridor_id)], limit=1,
                           columns=CORRIDOR_COLUMNS))
    if row is None:
        raise HTTPException(404, f"no corridor {corridor_id}")
    return row


def pair_role(row: Row) -> str | None:
    return PAIR_ROLE.get(row.get("class")) if row.get("pair_id") else None


def corridor_view(row: Row, stats: Row | None) -> dict:
    """length_meters is passed through from the measured value, or null. It is
    never derived from the coordinates. ledger holds the pooled peak-hour statistics:
    null values below their floor, with the pooled count beside them."""
    stats = stats or {}
    ledger = stats and {
        "window": {"start": stats["window_start"], "end": stats["window_end"]},
        "hours": PEAK_HOURS, "n": stats.get("n_peak"), "tt_mean_s": stats.get("tt_mean_peak_s"),
        "tt_p95_s": stats.get("tt_p95_peak_s"), "bti": stats.get("bti_peak"),
        "pti_tomtom": stats.get("pti_tomtom_peak"), "pti_p5": stats.get("pti_p5_peak"),
    }
    return {
        "id": row["id"], "code": row.get("code"), "name": row["name"],
        "pair_id": row.get("pair_id"), "role": pair_role(row),
        "origin": {"name": row.get("origin_name"), "lat": row["origin_lat"],
                   "lon": row["origin_lon"]},
        "destination": {"name": row.get("destination_name"), "lat": row["dest_lat"],
                        "lon": row["dest_lon"]},
        "length_meters": stats.get("length_meters"),
        "free_flow": {"tomtom_s": stats.get("ff_tomtom_s"), "p5_s": stats.get("ff_p5_s")},
        "missingness_rate": stats.get("missing_rate"),
        "low_confidence": stats.get("low_confidence"),
        "ledger": ledger or None,
        # The road TomTom routes through the corridor's declared points, fetched once when
        # the corridor was verified. Null until then, and the map draws a straight
        # connector and says so.
        "path": row.get("route_polyline_simplified") and {
            "points": row["route_polyline_simplified"],
            "fetched_at": row.get("route_polyline_fetched_at"),
            "source": "TomTom calculateRoute, fetched once at verification, simplified to 5 m",
        },
    }


@router.get("/corridors")
def corridors(store: StoreDep):
    ds = dataset(store)
    stats = {r["corridor_id"]: r for r in store.select("corridor_stats")}
    rankings: dict[str, dict] = {}
    for r in store.select("corridor_rankings"):
        rankings.setdefault(r["corridor_id"], {})[r["index_name"]] = {
            k: r.get(k) for k in ("n", "raw", "shrunk", "city_mean", "rank")
        }
    rows = store.select("corridors", [("active", "eq", True)], [("code", "asc"), ("id", "asc")],
                        columns=CORRIDOR_COLUMNS)
    body = {
        "window": ds and {"start": ds["window_start"], "end": ds["window_end"]},
        "low_confidence": ds and ds["low_confidence"],
        "method_version": ds and ds["method_version"],
        "floors": floors(ds),
        "corridors": [
            corridor_view(r, stats.get(r["id"])) | {"rankings": rankings.get(r["id"], {})}
            for r in rows
        ],
    }
    return respond(store, body, ds and ds["computed_at"], ds and ds["missing_rate"])


@router.get("/corridors/{corridor_id}/series")
def series(
    store: StoreDep,
    corridor_id: Annotated[str, Path(pattern=CORRIDOR_ID)],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    granularity: Literal["hour", "day"] = "hour",
):
    corridor_or_404(store, corridor_id)
    stats = one(store.select("corridor_stats", [("corridor_id", "eq", corridor_id)], limit=1))
    if stats is None:
        return respond(store, {"corridor_id": corridor_id, "granularity": granularity,
                               "status": "no_data", "series": None}, None, None)
    start = from_ or date.fromisoformat(stats["window_start"])
    end = to or date.fromisoformat(stats["window_end"])
    if end < start:
        raise HTTPException(422, "to is before from")
    if end - start > timedelta(days=MAX_SERIES_DAYS - 1):
        raise HTTPException(422, f"at most {MAX_SERIES_DAYS} days per request")
    table, keys, order = (
        ("metrics_daily", HOURLY_COLUMNS, [("day", "asc"), ("hour", "asc")])
        if granularity == "hour" else ("metrics_day", DAILY_COLUMNS, [("day", "asc")])
    )
    rows = store.select(
        table,
        [("corridor_id", "eq", corridor_id), ("day", "gte", start.isoformat()),
         ("day", "lte", end.isoformat())],
        order,
    )
    body = {"corridor_id": corridor_id, "granularity": granularity,
            "from": start.isoformat(), "to": end.isoformat(), "series": columnar(rows, keys)}
    return respond(store, body, stats["computed_at"], stats["missing_rate"])


@router.get("/corridors/{corridor_id}/profile")
def profile(store: StoreDep, corridor_id: Annotated[str, Path(pattern=CORRIDOR_ID)]):
    corridor_or_404(store, corridor_id)
    stats = one(store.select("corridor_stats", [("corridor_id", "eq", corridor_id)], limit=1))
    rows = store.select("profile_hourly", [("corridor_id", "eq", corridor_id)], [("hour", "asc")])
    first = one(rows)
    body = {
        "corridor_id": corridor_id,
        "window": first and {"start": first["window_start"], "end": first["window_end"]},
        "pooling": PROFILE_POOLING,
        "floors": floors(dataset(store)),
        "profile": columnar(rows, PROFILE_COLUMNS),
    }
    return respond(store, body, stats and stats["computed_at"], stats and stats["missing_rate"])


def heatmap_body(rows: list[Row]) -> dict:
    """7 x 24 matrices, Sunday first. Unpublished cells stay null."""
    cells = {(r["dow"], r["hour"]): r for r in rows}

    def matrix(key: str) -> list[list]:
        return [[(cells.get((d, h)) or {}).get(key) for h in range(24)] for d in range(7)]

    first = rows[0] if rows else {}
    return {
        "days": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "window": first and {"start": first["window_start"], "end": first["window_end"]},
        "tti_tomtom_p50": matrix("tti_tomtom_p50"), "tti_p5_p50": matrix("tti_p5_p50"),
        "n_days": matrix("n_days"), "n_ok": matrix("n_ok"), "missing_rate": matrix("missing_rate"),
        "low_confidence": matrix("low_confidence"),
    }


@router.get("/corridors/{corridor_id}/heatmap")
def heatmap(store: StoreDep, corridor_id: Annotated[str, Path(pattern=CORRIDOR_ID)]):
    corridor_or_404(store, corridor_id)
    stats = one(store.select("corridor_stats", [("corridor_id", "eq", corridor_id)], limit=1))
    rows = store.select("heatmap_weekly", [("scope", "eq", "corridor"),
                                           ("corridor_id", "eq", corridor_id)])
    body = {"corridor_id": corridor_id} | heatmap_body(rows) | {"floors": floors(dataset(store))}
    return respond(store, body, stats and stats["computed_at"], stats and stats["missing_rate"])


@router.get("/network/heatmap")
def network_heatmap(store: StoreDep):
    ds = dataset(store)
    rows = store.select("heatmap_weekly", [("scope", "eq", "network")])
    return respond(store, {"scope": "network"} | heatmap_body(rows) | {"floors": floors(ds)},
                   ds and ds["computed_at"], ds and ds["missing_rate"])


@router.get("/pairs/{pair_id}/compare")
def compare(
    store: StoreDep,
    pair_id: Annotated[str, Path(pattern=PAIR_ID)],
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
):
    """The pair's declared corridors only. One corridor is a valid answer:
    alternate is null and nothing is derived to stand in for it."""
    members = {pair_role(r): r for r in store.select("corridors", [("pair_id", "eq", pair_id)],
                                                     columns=CORRIDOR_COLUMNS)}
    if "primary" not in members:
        raise HTTPException(404, f"no pair {pair_id}")

    def side(row: Row | None) -> dict | None:
        if row is None:
            return None
        stats = one(store.select("corridor_stats", [("corridor_id", "eq", row["id"])], limit=1))
        prof = store.select("profile_hourly", [("corridor_id", "eq", row["id"])],
                            [("hour", "asc")])
        return corridor_view(row, stats) | {"profile": columnar(prof, COMPARE_PROFILE_COLUMNS)}

    primary, alternate = side(members["primary"]), side(members.get("alternate"))
    advantage = None
    if alternate is not None:
        rows = store.select("pair_advantage_hourly", [("pair_id", "eq", pair_id)],
                            [("hour", "asc")])
        advantage = columnar(rows, ADVANTAGE_COLUMNS)
    stats = one(store.select("corridor_stats", [("corridor_id", "eq", members["primary"]["id"])],
                             limit=1))
    pooled = one(store.select("profile_hourly", [("corridor_id", "eq", members["primary"]["id"])],
                              limit=1))
    body = {"pair_id": pair_id, "hour": hour,
            "window": pooled and {"start": pooled["window_start"], "end": pooled["window_end"]},
            "floors": floors(dataset(store)), "primary": primary, "alternate": alternate,
            "advantage": advantage}
    return respond(store, body, stats and stats["computed_at"], primary["missingness_rate"])


@router.get("/network/state")
def network_state(
    store: StoreDep,
    day: date | None = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
):
    """One wall-mode number: citywide travel time against normal for this hour."""
    if (day is None) != (hour is None):
        raise HTTPException(422, "pass both day and hour, or neither")
    filters = [("pct_vs_normal", "notnull", None)]
    if day is not None:
        filters += [("day", "eq", day.isoformat()), ("hour", "eq", hour)]
    row = one(store.select("network_hourly", filters, [("day", "desc"), ("hour", "desc")],
                           limit=1))
    if row is None:
        return respond(store, {"status": "no_data", "value": None}, None, None)
    body = {
        "status": "ok", "day": row["day"], "hour": row["hour"],
        "value": row["pct_vs_normal"], "unit": "percent vs normal for this hour",
        "state": row["state"], "n_corridors": row["n_corridors"],
        "low_confidence": row["low_confidence"],
        "tti": {"tomtom_p50": row["tti_tomtom_p50"], "p5_p50": row["tti_p5_p50"]},
    }
    return respond(store, body, row["computed_at"], row["missing_rate"])


@router.get("/interventions")
def interventions(store: StoreDep):
    ds = dataset(store)
    audits = {r["intervention_id"]: r for r in store.select("intervention_audit")}
    rows = store.select("interventions", order=[("effective_at", "asc")])
    body = {"interventions": [
        {k: r[k] for k in ("id", "corridor_id", "effective_at", "description")}
        | {"audit_status": (audits.get(r["id"]) or {}).get("status")}
        for r in rows
    ]}
    return respond(store, body, ds and ds["computed_at"], ds and ds["missing_rate"])


@router.get("/interventions/{intervention_id}/audit")
def audit(store: StoreDep, intervention_id: Annotated[str, Path(pattern=INTERVENTION_ID)]):
    iv = one(store.select("interventions", [("id", "eq", intervention_id)], limit=1))
    if iv is None:
        raise HTTPException(404, f"no intervention {intervention_id}")
    row = one(store.select("intervention_audit", [("intervention_id", "eq", intervention_id)],
                           limit=1))
    corridor = corridor_or_404(store, iv["corridor_id"])
    by_intervention = [("intervention_id", "eq", intervention_id)]
    codes = {c["id"]: c.get("code") for c in store.select("corridors", columns=("id", "code"))}
    donors = store.select("audit_donors", by_intervention, [("corridor_id", "asc")])
    placebos = store.select("audit_placebos", by_intervention, [("corridor_id", "asc")])
    blocks = store.select("audit_blocks", by_intervention, [("block", "asc")])
    variants = store.select("audit_sensitivity", by_intervention)
    variants.sort(key=lambda v: VARIANT_ORDER.index(v["variant"]))
    body = {
        "intervention": {k: iv[k] for k in ("id", "corridor_id", "effective_at", "description")},
        "corridor": {"id": corridor["id"], "code": corridor.get("code"), "name": corridor["name"]},
        "metric": "bti",
        "floors": floors(dataset(store)),
        "audit": row and {k: row.get(k) for k in AUDIT_FIELDS},
        # every donor considered, with its weight or the reason it was excluded
        "donors": [{k: d.get(k) for k in DONOR_FIELDS} | {"code": codes.get(d["corridor_id"])}
                   for d in donors],
        "placebos": [{k: p.get(k) for k in PLACEBO_FIELDS} for p in placebos],
        "blocks": {period: columnar([b for b in blocks if b["period"] == period], BLOCK_FIELDS)
                   for period in ("pre", "post")},
        # the estimate under stricter and looser donor completeness thresholds
        "sensitivity": [{k: v.get(k) for k in SENSITIVITY_FIELDS} for v in variants],
    }
    return respond(store, body, row and row["computed_at"], row and row["missing_rate"])


@router.get("/verify")
def verify(store: StoreDep):
    """The latest walk of each hash chain: samples (format v1) and failed_samples
    (format f1). The walks run in scheduled jobs because they read every row;
    this endpoint reports them and when they ran. A break in either is a break."""
    ds = dataset(store)
    latest = {t: one(store.select("chain_verifications", [("table_name", "eq", t)],
                                  [("id", "desc")], limit=1)) for t in CHAINS}
    walked = [r for r in latest.values() if r is not None]
    status = ("never_verified" if latest["samples"] is None
              else "ok" if all(r["ok"] for r in walked) else "broken")
    body = {
        "status": status,
        "verification": latest["samples"] and {k: latest["samples"].get(k)
                                               for k in VERIFICATION_FIELDS},
        "chains": {t: r and {k: r.get(k) for k in VERIFICATION_FIELDS}
                   for t, r in latest.items()},
        "method": "sha256 hash chains: row_hash = sha256(prev_hash || canonical row); "
                  "samples use format v1, failed_samples format f1",
        "reproduce": "collector/chain.py re-verifies rows read from the public tables "
                     "or the archive; an empty list of breaks means intact",
    }
    return respond(store, body, latest["samples"] and latest["samples"]["verified_at"],
                   ds and ds["missing_rate"])


def export(store: Store, fmt: str, public_base: str) -> JSONResponse:
    row = one(store.select("export_manifest", [("format", "eq", fmt)], limit=1))
    if row is None:
        raise HTTPException(503, f"no {fmt} export has been published yet")
    location = f"{public_base.rstrip('/')}/storage/v1/object/public/exports/{row['object_path']}"
    body = {"format": fmt, "location": location, "sha256": row["sha256"], "rows": row["n_rows"],
            "window": {"start": row["window_start"], "end": row["window_end"]}}
    headers = {
        "Location": location, "X-Ledger-As-Of": str(row["computed_at"]),
        "X-Ledger-Missingness-Rate": str(row["missing_rate"]),
        "X-Ledger-SHA256": row["sha256"],
    }
    return respond(store, body, row["computed_at"], row["missing_rate"], 307, CACHE, headers)


def public_base() -> str:
    import os

    return os.environ.get("SUPABASE_URL", "")


@router.get("/export.csv")
def export_csv(store: StoreDep, base: Annotated[str, Depends(public_base)]):
    return export(store, "csv", base)


@router.get("/export.parquet")
def export_parquet(store: StoreDep, base: Annotated[str, Depends(public_base)]):
    return export(store, "parquet", base)


@router.get("/health")
def health(store: StoreDep):
    """For wall mode. Never cached, so an outage shows up as one."""
    try:
        ds = dataset(store)
    except StoreError:
        return respond(store, {"status": "degraded", "api": "up", "database": "unreachable"},
                       None, None, 503, NO_STORE)
    body = {"status": "ok", "api": "up", "database": "reachable",
            "data": "present" if ds else "none"}
    return respond(store, body, ds and ds["computed_at"], ds and ds["missing_rate"],
                   cache=NO_STORE)


app.include_router(router)
