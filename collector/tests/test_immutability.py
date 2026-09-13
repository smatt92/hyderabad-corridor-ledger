import subprocess

import yaml

from immutability import committed_versions, violations


def corridor(cid, status="active", lat=17.497, via=()):
    return {"id": cid, "status": status, "direction": "ab", "origin_lat": lat, "origin_lon": 78.36,
            "dest_lat": 17.447, "dest_lon": 78.377,
            "via_points": [{"lat": a, "lon": b} for a, b in via]}


def test_active_geometry_is_frozen():
    history = [[corridor("a")]]
    assert violations(history, [corridor("a")]) == []
    assert violations(history, [corridor("a", lat=17.5)]) == [
        "a was verified or active and its geometry has changed; declare a new corridor "
        "that supersedes it"]
    assert violations(history, [corridor("a", via=[(17.46, 78.357)])])  # via_points count too


def test_versions_committed_before_the_rename_still_freeze_via_points():
    old = corridor("a", via=[(17.46, 78.357)])
    old["via"] = old.pop("via_points")  # the field's name until 0006
    assert violations([[old]], [corridor("a", via=[(17.46, 78.357)])]) == []
    assert violations([[old]], [corridor("a", via=[(17.47, 78.357)])])


def test_status_changes_are_allowed_but_removal_is_not():
    history = [[corridor("a")]]
    assert violations(history, [corridor("a", status="retired")]) == []
    assert violations(history, []) == [
        "a was verified or active and has been removed; retire it instead"]


def test_drafts_are_editable_until_first_activated():
    history = [[corridor("a", status="draft")], [corridor("a", status="draft", lat=17.49)]]
    assert violations(history, [corridor("a", status="active", lat=17.48)]) == []
    assert violations(history, []) == []
    # frozen at the first non-draft version, even if later made a draft again
    history = [[corridor("a", status="draft", lat=17.49)], [corridor("a", lat=17.48)],
               [corridor("a", status="draft", lat=17.48)]]
    assert violations(history, [corridor("a", status="draft", lat=17.49)])


def test_reads_every_committed_version(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    config = tmp_path / "config" / "corridors.yaml"
    config.parent.mkdir()
    git("init", "-q")
    history = ([corridor("a", status="draft")], [corridor("a")], [corridor("a", status="paused")])
    for version in history:
        config.write_text(yaml.safe_dump({"version": 1, "corridors": version}))
        git("add", "-A")
        git("commit", "-q", "-m", "update corridors")

    versions = committed_versions(repo=tmp_path)
    assert [v[0]["status"] for v in versions] == ["draft", "active", "paused"]
    assert violations(versions, [corridor("a", lat=17.3)])


def test_a_verified_draft_is_frozen_because_its_road_is_fetched_at_verification():
    draft = corridor("a", status="draft")
    verified = {**draft, "verified": True}
    assert violations([[draft]], [corridor("a", status="draft", lat=17.49)]) == []
    assert violations([[verified]], [{**verified, "origin_lat": 17.49}]) == [
        "a was verified or active and its geometry has changed; declare a new corridor "
        "that supersedes it"]
    # un-verifying it afterwards unfreezes nothing
    assert violations([[verified]], [{**draft, "origin_lat": 17.49}])
    assert violations([[verified]], []) == [
        "a was verified or active and has been removed; retire it instead"]
