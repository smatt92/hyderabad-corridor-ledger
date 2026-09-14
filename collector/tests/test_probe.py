import random
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
import yaml

import probe
from config import Panel
from probe import (
    ProbeConfig,
    check_probe,
    final_quota_refusal,
    headers_only,
    run_probe,
    summarize,
)
from schedule import IST, slots_for_day
from store import iso

FIXTURE = Path(__file__).parent / "fixtures" / "corridors.yaml"
DAY = date(2026, 9, 14)
KEPT = {"corridor_id", "requested_at", "attempt", "http_status", "latency_ms"}


def ist(h, m, s=0, day=DAY):
    return datetime.combine(day, time(h, m, s), IST)


MORNING = ist(8, 0, 30)


def panel(active=()):
    doc = yaml.safe_load(FIXTURE.read_text())
    for c in doc["corridors"]:
        if c["id"] in active:
            c["status"], c["verified"] = "active", True
    return Panel.model_validate(doc)


def config(**changes):
    return ProbeConfig.model_validate({
        "tier": "B", "first_day": "2026-09-10", "last_day": "2026-09-23",
        "corridors": ["placeholder-01", "placeholder-02"], **changes})


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakeLedger:
    def __init__(self, probed=(), retries_and_refusals=(), used=0):
        self.probed, self.used = set(probed), used
        self.earlier = list(retries_and_refusals)
        self.rows = []

    def probed_since(self, start, corridor_ids):
        return {c for c in self.probed if c in corridor_ids}

    def probe_retries_and_refusals(self, start):
        return self.earlier

    def attempts_between(self, start, end):
        return self.used

    def insert_probe_calls(self, rows):
        self.rows.extend(rows)


def transport_from(responses):
    """Each response is (status, latency) or (status, headers, latency)."""
    calls = []

    def transport(url):
        calls.append(url)
        item = responses[len(calls) - 1]
        return item if len(item) == 3 else (item[0], {}, item[1])

    transport.calls = calls
    return transport


def go(ledger, responses, at=MORNING, cfg=None, active=()):
    clock = Clock(at)
    transport = transport_from(responses)
    report = run_probe(cfg or config(), panel(active), ledger, transport, "k", clock,
                       random.Random(1), clock.sleep)
    return report, transport


def test_only_the_corridor_time_attempt_status_and_latency_are_kept():
    ledger = FakeLedger()
    report, transport = go(ledger, [(200, {"tracking-id": "t"}, 0.412), (200, 0.3)])
    assert [set(r) for r in ledger.rows] == [KEPT, KEPT]
    first = ledger.rows[0]
    assert (first["corridor_id"], first["attempt"], first["http_status"], first["latency_ms"]) == (
        "placeholder-01", 1, 200, 412)
    assert first["requested_at"] == iso(MORNING)
    assert "routeRepresentation=summaryOnly" in transport.calls[0]   # the collector's own call
    assert (report.probed, report.attempts) == (2, 2)


class Unreadable:
    """A response whose body must never be read."""

    def __init__(self, status=200):
        self.status, self.headers, self.closed = status, {"Retry-After": "1"}, False

    def read(self, *args):
        raise AssertionError("the probe read a response body")

    def close(self):
        self.closed = True


def test_the_response_body_is_never_read(monkeypatch):
    response = Unreadable()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: response)
    status, headers, latency = headers_only("https://api.tomtom.com/x?key=k")
    assert (status, headers) == (200, {"retry-after": "1"}) and latency >= 0 and response.closed

    body = Unreadable()

    def refuse(request, timeout):
        raise urllib.error.HTTPError("https://x", 429, "Too Many Requests", {"Retry-After": "3"},
                                     body)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert headers_only("https://x")[:2] == (429, {"retry-after": "3"})

    def silent(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", silent)
    assert headers_only("https://x")[:2] == (None, {})


def test_retries_follow_the_collector_and_every_attempt_is_a_row():
    ledger = FakeLedger()
    clock_start = MORNING
    report, _ = go(ledger, [(503, 0.1), (None, 20.0), (200, 0.2), (200, 0.2)], at=clock_start)
    assert [(r["corridor_id"], r["attempt"], r["http_status"]) for r in ledger.rows] == [
        ("placeholder-01", 1, 503), ("placeholder-01", 2, None), ("placeholder-01", 3, 200),
        ("placeholder-02", 1, 200)]
    times = [datetime.fromisoformat(r["requested_at"]) for r in ledger.rows]
    assert min((b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)) >= 1.0
    assert report.attempts == 4


def test_a_quota_refusal_stops_the_probe_and_is_not_retried():
    ledger = FakeLedger()
    report, transport = go(ledger, [(429, {}, 0.1)])
    assert len(transport.calls) == 1 and [r["http_status"] for r in ledger.rows] == [429]
    assert report.quota_refused and report.skipped_quota == 1


def test_after_a_429_that_ended_its_slot_today_no_probe_call_is_made():
    earlier = [{"corridor_id": "placeholder-01", "requested_at": iso(ist(7, 0)), "attempt": 1,
                "http_status": 429}]
    report, transport = go(FakeLedger(retries_and_refusals=earlier), [])
    assert transport.calls == [] and report.skipped_quota == 2


def test_a_429_is_a_quota_refusal_only_when_nothing_retried_it():
    def row(attempt, at, status):
        return {"corridor_id": "c", "requested_at": iso(at), "attempt": attempt,
                "http_status": status}

    retried = [row(1, ist(8, 0), 429), row(2, ist(8, 0, 9), 200)]
    assert not final_quota_refusal(retried)
    assert final_quota_refusal([row(1, ist(8, 0), 429)])
    assert final_quota_refusal([row(2, ist(8, 0, 5), 429)])                 # a retry that ended it
    assert final_quota_refusal([row(1, ist(8, 0), 429), row(2, ist(8, 5), 200)])  # too late


def test_nothing_is_called_for_a_probed_slot_outside_the_window_or_with_the_probe_off():
    report, transport = go(FakeLedger(probed={"placeholder-01"}), [(200, 0.1)])
    assert len(transport.calls) == 1 and report.skipped_existing == 1
    assert go(FakeLedger(), [], cfg=config(first_day="2026-09-20"))[1].calls == []
    assert go(FakeLedger(), [], cfg=ProbeConfig())[1].calls == []
    assert go(FakeLedger(), [], at=ist(12, 0))[1].calls == []


def test_a_probe_never_runs_beside_collection_and_must_fit_the_monthly_allowance(monkeypatch):
    assert check_probe(config(), panel()) == []
    assert check_probe(ProbeConfig(), panel(active=("placeholder-01",))) == []   # probe off
    (problem,) = check_probe(config(), panel(active=("placeholder-01",)))
    assert "never runs while collection does" in problem
    with pytest.raises(RuntimeError, match="never runs while collection does"):
        go(FakeLedger(), [], active=("placeholder-01",))
    assert "not declared" in check_probe(config(corridors=["nowhere-01"]), panel())[0]
    monkeypatch.setattr(probe, "CAPACITY_PER_DAY", 50)   # 2 corridors x 25 slots > 42
    assert "first attempts a day" in check_probe(config(), panel())[0]


@pytest.mark.parametrize("changes, message", [
    ({"first_day": None}, "needs first_day and last_day"),
    ({"last_day": "2026-09-01"}, "before first_day"),
    ({"last_day": "2026-10-12"}, "at most 31 days"),
    ({"corridors": ["placeholder-01", "placeholder-01"]}, "listed twice"),
])
def test_the_probe_window_is_bounded(changes, message):
    with pytest.raises(ValueError, match=message):
        config(**changes)


def test_the_report_counts_missed_and_failed_slots_together():
    cfg = config(first_day=str(DAY), last_day=str(DAY), corridors=["placeholder-01"])
    peak = [s for s in slots_for_day("B", DAY) if probe._is_peak(s)]
    night = [s for s in slots_for_day("B", DAY) if not probe._is_peak(s)]

    def attempt(slot, n, status, latency=300):
        return {"corridor_id": "placeholder-01", "requested_at": iso(slot + timedelta(seconds=n)),
                "attempt": n, "http_status": status, "latency_ms": latency}

    rows = [attempt(s, 1, 200) for s in peak[:15] + night]
    rows += [attempt(peak[15], n, 503) for n in (1, 2, 3)]      # failed after its retries
    # peak[16] has no attempt at all: a collector run GitHub dropped
    lines = summarize(rows, cfg, DAY)
    assert "| peak | 17 | 5.9% | 5.9% | 11.8% | 1.12 |" in lines
    assert "| night | 8 | 0.0% | 0.0% | 0.0% | 1.00 |" in lines
    assert any(line == "Why peak slots failed after retries: 5xx 1" for line in lines)
