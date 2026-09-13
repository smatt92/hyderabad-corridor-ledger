import gzip
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
import yaml

from budget import check_fits, day_plan
from config import Panel
from fetch import measure, run
from schedule import IST
from store import DatabaseError

FIXTURE = Path(__file__).parent / "fixtures" / "corridors.yaml"

DAY = date(2026, 9, 14)
SUMMARY = {"lengthInMeters": 9812, "travelTimeInSeconds": 1502, "trafficDelayInSeconds": 212,
           "noTrafficTravelTimeInSeconds": 1180, "historicTrafficTravelTimeInSeconds": 1420}
OK_BODY = json.dumps({"routes": [{"summary": SUMMARY}]}).encode()


def ist(h, m, s=0):
    return datetime.combine(DAY, time(h, m, s), IST)


MORNING = ist(8, 0, 30)


def panel(active_ids=("placeholder-01",)):
    doc = yaml.safe_load(FIXTURE.read_text())
    for c in doc["corridors"]:
        if c["id"] in active_ids or active_ids == "all":
            c["status"] = "active"
            c["verified"] = True  # only a verified corridor may leave draft
    return Panel.model_validate(doc)


class FakeLedger:
    def __init__(self, samples=0, failures=0, runs=0, used=0, recorded=()):
        self.counts = {"samples": samples, "failed_samples": failures, "collector_runs": runs}
        self.used = used
        self.recorded = set(recorded)
        self.samples, self.failures, self.runs = [], [], {}

    def count(self, table):
        return self.counts[table]

    def recorded_corridors(self, slot, corridor_ids):
        return {cid for cid, s in self.recorded if s == slot and cid in corridor_ids}

    def attempts_between(self, start, end):
        return self.used

    def start_run(self, run_id, sha):
        self.runs[run_id] = {"sha": sha}

    def finish_run(self, run_id, values):
        self.runs[run_id].update(values)

    def insert_sample(self, row):
        self.samples.append(row)
        return True

    def insert_failure(self, row):
        self.failures.append(row)
        return True


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


def transport_from(responses):
    calls = []

    def transport(url):
        calls.append(url)
        item = responses[len(calls) - 1]
        if isinstance(item, BaseException):
            raise item
        return item

    transport.calls = calls
    return transport


def go(ledger, responses, at=MORNING, active=("placeholder-01",), capacity=2400):
    clock = Clock(at)
    transport = transport_from(responses)
    report = run(panel(active), ledger, transport, "k", clock, random.Random(1), clock.sleep,
                 "123.1", "a" * 40, capacity=capacity)
    return report, transport


def test_records_one_sample_for_the_due_slot():
    ledger = FakeLedger()
    report, transport = go(ledger, [(200, OK_BODY)])
    assert (report.slots_due, report.recorded, report.attempts, report.outcome) == (1, 1, 1, "ok")
    (row,) = ledger.samples
    assert row["corridor_id"] == "placeholder-01"
    assert row["scheduled_slot"] == "2026-09-14T02:30:00+00:00"   # 08:00 IST
    assert row["requested_at"] == "2026-09-14T02:30:30+00:00"
    assert (row["travel_time_s"], row["length_m"], row["attempts"]) == (1502, 9812, 1)
    assert gzip.decompress(bytes.fromhex(row["raw_gz"][2:])) == OK_BODY
    assert "key=k" in transport.calls[0]
    assert ledger.runs["123.1"]["outcome"] == "ok"


def test_retry_with_jitter_then_success():
    ledger = FakeLedger()
    report, _ = go(ledger, [(429, b"slow down"), (200, OK_BODY)])
    (row,) = ledger.samples
    assert row["attempts"] == 2 and report.attempts == 2
    # the sample's time is the successful attempt's, after a jittered wait under 2 s
    waited = datetime.fromisoformat(row["requested_at"]) - MORNING
    assert timedelta(0) <= waited <= timedelta(seconds=2)


def test_exhausted_retries_record_a_failure_never_a_silent_drop():
    ledger = FakeLedger()
    report, transport = go(ledger, [(503, b"busy"), TimeoutError(), (503, b"busy")])
    assert len(transport.calls) == 3 and ledger.samples == []
    (row,) = ledger.failures
    assert (row["error_class"], row["http_status"], row["attempts"]) == ("upstream_5xx", 503, 3)
    assert row["requested_at"] == "2026-09-14T02:30:30+00:00"      # first attempt
    assert gzip.decompress(bytes.fromhex(row["detail_gz"][2:])) == b"busy"
    assert report.failed == 1 and report.outcome == "ok"


def test_failure_detail_never_carries_the_key():
    ledger = FakeLedger()
    go(ledger, [(403, b'{"detailedError": "bad key=k&traffic=true"}')])
    detail = gzip.decompress(bytes.fromhex(ledger.failures[0]["detail_gz"][2:]))
    assert b"key=k" not in detail and b"key=REDACTED" in detail


def test_client_error_is_not_retried():
    ledger = FakeLedger()
    _, transport = go(ledger, [(403, b"forbidden")])
    assert len(transport.calls) == 1
    assert ledger.failures[0]["error_class"] == "client_403"


def test_slot_with_an_outcome_is_never_measured_again_and_writes_no_run():
    ledger = FakeLedger(runs=5, recorded={("placeholder-01", ist(8, 0))})
    report, transport = go(ledger, [])
    assert transport.calls == [] and report.skipped_existing == 1
    assert ledger.runs == {}


def test_empty_budget_skips_instead_of_calling():
    ledger = FakeLedger(runs=5, used=10_000)
    report, transport = go(ledger, [])
    assert transport.calls == [] and report.skipped_budget == 1
    assert ledger.runs["123.1"]["outcome"] == "budget_exhausted"


def test_budget_caps_attempts_on_the_last_tokens():
    # One Tier A corridor plans 42 calls. By 08:00 IST, 15 slots are due (8 night,
    # 7 morning): floor(50 * 15 / 42) = 17 tokens released, 16 spent, 1 left.
    ledger = FakeLedger(runs=1, used=16)
    _, transport = go(ledger, [(503, b"x"), (503, b"x"), (503, b"x")], capacity=50)
    assert len(transport.calls) == 1 and ledger.failures[0]["attempts"] == 1


def test_geometry_leak_is_recorded_and_fails_the_run():
    leaked = json.dumps({"routes": [{"summary": SUMMARY, "legs": [{"points": [{"latitude": 1}]}]}]})
    ledger = FakeLedger()
    report, _ = go(ledger, [(200, leaked.encode())])
    assert ledger.failures[0]["error_class"] == "geometry_leak"
    assert report.outcome == "failed" and report.problems


def test_malformed_200_is_a_parse_error_failure():
    ledger = FakeLedger()
    go(ledger, [(200, b"{}")])
    assert ledger.failures[0]["error_class"] == "parse_error"


def test_refuses_to_start_on_rows_that_predate_any_run():
    with pytest.raises(RuntimeError, match="genuine first row"):
        go(FakeLedger(samples=3, runs=0), [])


def test_a_crashed_run_is_closed_as_failed_and_still_raises():
    class Broken(FakeLedger):
        def insert_sample(self, row):
            raise DatabaseError("POST samples: HTTP 503")

    ledger = Broken()
    with pytest.raises(DatabaseError):
        go(ledger, [(200, OK_BODY)])
    assert ledger.runs["123.1"]["outcome"] == "failed"
    assert "run aborted" in ledger.runs["123.1"]["detail"]


def test_drafts_and_undue_corridors_are_never_called():
    report, transport = go(FakeLedger(), [], active=())
    assert (report.slots_due, transport.calls) == (0, [])
    report, transport = go(FakeLedger(), [], at=ist(12, 0))
    assert (report.slots_due, transport.calls) == (0, [])


def test_measure_uses_declared_via_points():
    p = panel(("placeholder-01", "placeholder-02"))
    alt = next(c for c in p.corridors if c.id == "placeholder-02")
    clock = Clock(ist(8, 0))
    transport = transport_from([(200, OK_BODY)])
    measure(alt, "k", transport, clock, random.Random(1), clock.sleep)
    assert "17.497,78.36:17.464,78.357:17.447,78.377" in transport.calls[0]


def test_whole_seeded_panel_fits_the_budget_when_active():
    tiers = [c.tier for c in panel("all").active()]
    assert len(tiers) == 10
    assert check_fits(day_plan(tiers, DAY)) <= 2040
