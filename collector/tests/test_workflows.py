from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def test_only_one_collector_ever_calls_tomtom_at_a_time():
    """fetch.py spaces calls a second apart within a run. That is a ceiling on the whole
    project's request rate only while no other workflow holds the key and two collector
    runs never overlap."""
    holders = sorted(p.name for p in WORKFLOWS.glob("*.yml") if "TOMTOM_API_KEY" in p.read_text())
    assert holders == ["collector.yml"]
    collector = yaml.safe_load((WORKFLOWS / "collector.yml").read_text())
    assert collector["concurrency"] == {"group": "collector", "cancel-in-progress": False}
    assert list(collector["jobs"]) == ["collect"]
