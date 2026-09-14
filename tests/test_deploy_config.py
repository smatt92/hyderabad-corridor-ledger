"""The Vercel upload keeps everything a deployed service is built from.

.vercelignore uses .gitignore syntax, and Vercel removes the files it matches before
building. A bare name matches at any depth, so `scripts`, meant for the repository's own
scripts/, also removed web/scripts/check-bundle.mjs. `npm run build` runs that file as a
build gate, so the first deploy failed with "Cannot find module". git's matcher removes the
same 83 files Vercel reported for that commit, so it is the oracle here.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(),
                                reason="needs git and a checkout")


def tracked() -> list[str]:
    found = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True,
                           text=True, check=True)
    return found.stdout.splitlines()


def removed_by_vercelignore(paths: list[str]) -> set[str]:
    """The paths .vercelignore removes, matched by git in an empty repository so that no
    other ignore file applies."""
    with tempfile.TemporaryDirectory() as empty:
        subprocess.run(["git", "init", "-q", empty], check=True)
        found = subprocess.run(
            ["git", "-c", f"core.excludesFile={ROOT / '.vercelignore'}", "check-ignore",
             "--no-index", "--stdin"],
            cwd=empty, input="\n".join(paths), capture_output=True, text=True)
    assert found.returncode in (0, 1), found.stderr   # 1: nothing matched
    return set(found.stdout.splitlines())


def services() -> dict:
    return json.loads((ROOT / "vercel.json").read_text())["services"]


def may_drop(path: str) -> bool:
    """Inside a service, only its tests, build output and installs may stay behind."""
    return (path.startswith(("api/tests/", "web/dist/"))
            or "/node_modules/" in path or "/.venv/" in path)


def test_the_oracle_matches_directories_by_bare_name():
    probes = ["metrics/audit.py", "scripts/ci/check-authorship.sh", "api/tests/test_app.py",
              "web/package.json"]
    assert removed_by_vercelignore(probes) == set(probes[:3])


def test_the_bundle_check_the_build_runs_survives_the_upload():
    web = services()["web"]
    root = web["root"].rstrip("/")
    assert web["buildCommand"] == "npm run build"
    build = json.loads((ROOT / root / "package.json").read_text())["scripts"]["build"]
    scripts = re.findall(r"\bnode\s+(\S+)", build)
    assert "scripts/check-bundle.mjs" in scripts, f"the build skips the bundle check: {build}"
    for script in scripts:
        path = f"{root}/{script}"
        assert (ROOT / path).is_file(), path
        assert not removed_by_vercelignore([path]), f".vercelignore removes {path}, a build step"


def test_the_upload_keeps_every_tracked_file_of_every_service():
    roots = tuple(s["root"].rstrip("/") + "/" for s in services().values())
    inside = [p for p in tracked() if p.startswith(roots)]
    assert inside
    dropped = sorted(p for p in removed_by_vercelignore(inside) if not may_drop(p))
    assert dropped == [], f".vercelignore removes files a service is built from: {dropped}"
