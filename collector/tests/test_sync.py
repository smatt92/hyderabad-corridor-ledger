from pathlib import Path

from config import load_panel
from sync import plan_sync, row_for

FIXTURE = Path(__file__).parent / "fixtures" / "corridors.yaml"


def db_row(row, activated=False):
    return {**row, "activated_at": "2026-09-01T00:00:00+00:00" if activated else None}


def test_rows_carry_every_declared_field_and_active_matches_status():
    panel = load_panel(FIXTURE)
    row = row_for(next(c for c in panel.corridors if c.id == "placeholder-02"))
    assert row["class"] == "alternate" and row["pair_id"] == "PL-01"
    assert row["via"] == [{"lat": 17.464, "lon": 78.357}]
    assert row["active"] is False and row["status"] == "draft"


def test_alternates_are_upserted_after_their_cores():
    _, upserts = plan_sync(load_panel(FIXTURE), [])
    classes = [r["class"] for r in upserts]
    assert classes.index("alternate") > max(i for i, c in enumerate(classes) if c != "alternate")


def test_removed_or_redrawn_drafts_are_deleted_first_active_corridors_never():
    panel = load_panel(FIXTURE)
    rows = {c.id: row_for(c) for c in panel.corridors}
    redrawn = {**rows["placeholder-04"], "dest_lat": 17.40}
    gone_draft = {**rows["placeholder-05"], "id": "old-draft"}
    gone_active = {**rows["placeholder-05"], "id": "old-active"}
    existing = [db_row(rows["placeholder-01"]), db_row(redrawn), db_row(gone_draft),
                db_row(gone_active, activated=True)]
    deletes, _ = plan_sync(panel, existing)
    assert deletes == ["placeholder-04", "old-draft"]
