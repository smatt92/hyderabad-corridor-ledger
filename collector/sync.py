"""Sync config/corridors.yaml into the corridors table: python collector/sync.py

Runs in GitHub Actions on pushes that change the file, after CI has validated
it and checked geometry immutability. Declared corridors are upserted, cores
and donors before alternates so each alternate finds its core. Drafts that
left the file, or whose geometry changed, are deleted first and re-inserted.
A corridor that has ever been active is never deleted: CI refuses the change
and the database's corridors_guard trigger refuses it again.
"""

import sys

from config import Corridor, Panel, load_panel
from immutability import geometry
from store import Database

ORDER = {"core": 0, "donor": 0, "alternate": 1}


def row_for(c: Corridor) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "class": c.corridor_class, "tier": c.tier,
        "direction": c.direction, "pair_id": c.pair_id, "origin_name": c.origin_name,
        "destination_name": c.destination_name, "origin_lat": c.origin_lat,
        "origin_lon": c.origin_lon, "dest_lat": c.dest_lat, "dest_lon": c.dest_lon,
        "via_points": [{"lat": p.lat, "lon": p.lon} for p in c.via_points], "status": c.status,
        "active": c.status == "active", "supersedes": c.supersedes, "verified": c.verified,
        "treatment_status": c.treatment_status, "treatment_work": c.treatment_work,
    }


def plan_sync(panel: Panel, existing: list[dict]) -> tuple[list[str], list[dict]]:
    """(ids to delete first, rows to upsert in order)."""
    declared = {c.id: row_for(c) for c in panel.corridors}
    deletes = []
    for row in existing:
        if row.get("activated_at") is not None:
            continue  # never deleted; CI has already checked it is still declared unchanged
        wanted = declared.get(row["id"])
        if wanted is None or geometry(wanted) != geometry(row):
            deletes.append(row)
    deletes.sort(key=lambda r: -ORDER.get(r.get("class"), 0))  # alternates go first
    upserts = sorted(declared.values(), key=lambda r: (ORDER[r["class"]], r["id"]))
    return [r["id"] for r in deletes], upserts


def main() -> int:
    db = Database.from_env()
    columns = ("id,class,status,activated_at,origin_lat,origin_lon,dest_lat,dest_lon,"
               "via_points,direction")
    _, existing = db.request("GET", "corridors", [("select", columns)])
    deletes, upserts = plan_sync(load_panel(), existing or [])
    for cid in deletes:
        db.request("DELETE", "corridors", [("id", f"eq.{cid}")], prefer="return=minimal")
    for row in upserts:
        db.request("POST", "corridors", [("on_conflict", "id")], body=row,
                   prefer="resolution=merge-duplicates,return=minimal")
    print(f"corridors: {len(deletes)} draft(s) removed, {len(upserts)} declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
