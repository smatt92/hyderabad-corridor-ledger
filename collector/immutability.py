"""A corridor's geometry is permanent once it has been anything but a draft.

Compares config/corridors.yaml with every committed version of it. Fails when
an id that was ever non-draft now has a different origin, destination,
via_points or direction, or has vanished from the file. To change a measured
road, retire the corridor and declare a new id that supersedes it. Drafts can
be edited freely until they are first activated.

Enforced in CI, and again in the database by the corridors_guard trigger.

    python collector/immutability.py
"""

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REL_PATH = "config/corridors.yaml"


def geometry(raw: dict) -> tuple:
    # The field was named via until 0006; versions committed before then use it.
    points = raw.get("via_points", raw.get("via")) or ()
    via = tuple((float(p["lat"]), float(p["lon"])) for p in points)
    return (float(raw["origin_lat"]), float(raw["origin_lon"]), float(raw["dest_lat"]),
            float(raw["dest_lon"]), raw.get("direction"), via)


def corridors_of(document) -> list[dict]:
    return list((document or {}).get("corridors") or [])


def violations(history: list[list[dict]], current: list[dict]) -> list[str]:
    """history: committed versions, oldest first. Each id's geometry freezes at
    the first version in which it is not a draft."""
    frozen: dict[str, tuple] = {}
    for version in history:
        for raw in version:
            cid = raw.get("id")
            if cid and raw.get("status") != "draft" and cid not in frozen:
                frozen[cid] = geometry(raw)
    now = {raw["id"]: raw for raw in current if raw.get("id")}
    problems = []
    for cid, frozen_geometry in sorted(frozen.items()):
        if cid not in now:
            problems.append(f"{cid} was active and has been removed; retire it instead")
        elif geometry(now[cid]) != frozen_geometry:
            problems.append(f"{cid} was active and its geometry has changed; declare a new "
                            "corridor that supersedes it")
    return problems


def git(*args: str, repo: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def committed_versions(repo: Path = REPO, rel_path: str = REL_PATH) -> list[list[dict]]:
    if git("rev-parse", "--is-shallow-repository", repo=repo).stdout.strip() == "true":
        raise RuntimeError("shallow clone: corridor history is incomplete (fetch-depth: 0)")
    log = git("log", "--reverse", "--format=%H", "--", rel_path, repo=repo)
    if log.returncode != 0:
        raise RuntimeError(log.stderr.strip() or "git log failed")
    versions = []
    for sha in log.stdout.split():
        shown = git("show", f"{sha}:{rel_path}", repo=repo)
        if shown.returncode == 0:  # absent in a commit that deleted it
            versions.append(corridors_of(yaml.safe_load(shown.stdout)))
    return versions


def main() -> int:
    current = corridors_of(yaml.safe_load((REPO / REL_PATH).read_text()))
    problems = violations(committed_versions(), current)
    for problem in problems:
        print(f"::error file={REL_PATH}::{problem}")
    print(f"corridor immutability: {len(problems)} problem(s) across {len(current)} corridors")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
