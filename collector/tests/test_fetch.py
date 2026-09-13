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


def panel(active_ids=("placeholder-01",), verified_ids=()):
    doc = yaml.safe_load(FIXTURE.read_text())
    for c in doc["corridors"]:
        if c["id"] in active_ids or active_ids == "all":
            c["status"] = "active"
            c["verified"] = True  # only a verified corridor may leave draft
        if c["id"] in verified_ids:
            c["verified"] = True
    return Panel.model_validate(doc)


class FakeLedger:
    def __init__(self, samples=0, failures=0, runs=0, used=0, recorded=(), refused=False,
                 roads=None, stored=None):
        self.counts = {"samples": samples, "failed_samples": failures, "collector_runs": runs}
        self.used = used
        self.refused = refused
        self.recorded = set(recorded)
        self.samples, self.failures, self.runs, self.responses = [], [], {}, []
        self.roads = roads or {}      # corridor id -> stored road length, None while unstored
        self.stored = stored or {}    # corridor id -> the simplified stored road
        self.route_checks, self.polylines = [], {}

    def count(self, table):
        return self.counts[table]

    def recorded_corridors(self, slot, corridor_ids):
        return {cid for cid, s in self.recorded if s == slot and cid in corridor_ids}

    def attempts_between(self, start, end):
        return self.used

    def quota_refused_since(self, start):
        return self.refused

    def insert_responses(self, rows):
        self.responses.extend(rows)

    def route_state(self, corridor_ids, since):
        return {c: n for c, n in self.roads.items() if c in corridor_ids}, []

    def stored_route(self, corridor_id):
        return self.stored[corridor_id]

    def insert_route_check(self, row):
        self.route_checks.append(row)

    def store_route_polyline(self, corridor_id, values):
        self.polylines[corridor_id] = values
        return True

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
        return item if len(item) == 3 else (item[0], {}, item[1])   # (status, headers, body)

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
    report, _ = go(ledger, [(503, b"busy"), (200, OK_BODY)])
    (row,) = ledger.samples
    assert row["attempts"] == 2 and report.attempts == 2
    # the sample's time is the successful attempt's, after a jittered wait under 2 s
    # and never under the one-second spacing
    waited = datetime.fromisoformat(row["requested_at"]) - MORNING
    assert timedelta(seconds=1) <= waited <= timedelta(seconds=2)


THREE = ("placeholder-01", "placeholder-02", "placeholder-03")


def test_calls_are_at_least_a_second_apart_across_corridors_and_retries():
    clock = Clock(MORNING)
    stamps = []

    def transport(url):
        stamps.append(clock.now)
        return (503, {}, b"busy") if len(stamps) == 1 else (200, {}, OK_BODY)

    run(panel(THREE), FakeLedger(), transport, "k", clock, random.Random(3), clock.sleep,
        "123.1", "a" * 40)
    assert len(stamps) == 4
    assert min((b - a).total_seconds() for a, b in zip(stamps, stamps[1:], strict=False)) >= 1.0


def test_a_429_with_a_short_retry_after_is_waited_out_and_retried():
    ledger = FakeLedger()
    report, _ = go(ledger, [(429, {"retry-after": "7"}, b""), (200, OK_BODY)])
    (row,) = ledger.samples
    assert row["attempts"] == 2 and report.outcome == "ok"
    assert datetime.fromisoformat(row["requested_at"]) - MORNING >= timedelta(seconds=7)
    (kept,) = ledger.responses
    assert (kept["reason"], kept["limit_kind"], kept["http_status"]) == ("status_429", "qps", 429)


def test_a_quota_429_is_never_retried_and_stops_the_run():
    ledger = FakeLedger()
    report, transport = go(ledger, [(429, b'{"error": "limit"}')], active=THREE)
    assert len(transport.calls) == 1
    (row,) = ledger.failures
    assert (row["error_class"], row["http_status"], row["attempts"]) == ("quota_exhausted", 429, 1)
    assert report.quota_refused and report.skipped_quota == 2 and report.attempts == 1
    assert ledger.runs["123.1"]["outcome"] == "quota_exhausted"
    assert ledger.runs["123.1"]["skipped_quota"] == 2
    assert ledger.responses[0]["limit_kind"] == "quota"


def test_after_a_quota_refusal_no_call_is_made_until_the_utc_day_turns():
    ledger = FakeLedger(runs=3, refused=True)
    report, transport = go(ledger, [])
    assert transport.calls == [] and report.skipped_quota == 1
    assert not report.quota_refused and ledger.runs["123.1"]["outcome"] == "quota_exhausted"


def test_headers_are_kept_for_the_first_response_and_every_403_and_429():
    ledger = FakeLedger()
    go(ledger, [
        (200, {"tracking-id": "t1", "set-cookie": "s=1", "location": "https://x/?key=k&a=1"},
         OK_BODY),
        (200, {"tracking-id": "t2"}, OK_BODY),
        (403, {"tracking-id": "t3"}, b"forbidden"),
    ], active=THREE)
    assert [(r["corridor_id"], r["reason"], r["headers"]["tracking-id"])
            for r in ledger.responses] == [("placeholder-01", "first_response", "t1"),
                                           ("placeholder-03", "status_403", "t3")]
    first = ledger.responses[0]
    assert first["headers"]["set-cookie"] == "not kept"
    assert "key=k" not in first["headers"]["location"]
    assert (first["collector_run"], first["attempt"], first["limit_kind"]) == ("123.1", 1, None)


def test_the_first_kept_response_is_the_first_one_that_arrived():
    ledger = FakeLedger()
    failures = [TimeoutError(), TimeoutError(), TimeoutError()]
    go(ledger, [*failures, (200, {"tracking-id": "t"}, OK_BODY)],
       active=("placeholder-01", "placeholder-02"))
    assert [(r["corridor_id"], r["reason"]) for r in ledger.responses] == [
        ("placeholder-02", "first_response")]


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


ROAD = [(17.497, 78.36), (17.48, 78.358), (17.464, 78.357), (17.455, 78.367), (17.447, 78.377)]


def road_body(points=ROAD, length=6100):
    return json.dumps({"routes": [{"summary": {"lengthInMeters": length}, "legs": [
        {"points": [{"latitude": a, "longitude": b} for a, b in points]}]}]}).encode()


NOON = ist(12, 0)  # outside every collection window


def go_roads(ledger, responses, ids=("placeholder-02",), active=(), at=NOON):
    clock = Clock(at)
    transport = transport_from(responses)
    report = run(panel(active, verified_ids=ids), ledger, transport, "k", clock, random.Random(1),
                 clock.sleep, "123.1", "a" * 40)
    return report, transport


def test_a_verified_corridor_without_a_road_gets_one_polyline_call_stored_for_good():
    ledger = FakeLedger(roads={"placeholder-02": None})
    report, transport = go_roads(ledger, [(200, {"tracking-id": "t"}, road_body())])
    (url,) = transport.calls
    assert "routeRepresentation=polyline" in url and "traffic=false" in url
    stored = ledger.polylines["placeholder-02"]
    assert stored["route_polyline"] == ROAD and stored["route_polyline_length_m"] == 6100
    assert 2 <= len(stored["route_polyline_simplified"]) <= len(ROAD)
    (row,) = ledger.route_checks
    assert (row["kind"], row["points"], row["error_class"], row["matched"]) == (
        "initial", 5, None, None)
    assert report.attempts == 1 and report.outcome == "ok"
    assert ledger.runs["123.1"]["attempts"] == 1
    assert ledger.responses[0]["reason"] == "first_response"


def test_no_call_for_a_corridor_the_database_does_not_hold_as_verified():
    report, transport = go_roads(FakeLedger(roads={}), [])
    assert transport.calls == [] and report.route_checks == 0


def test_a_refetch_that_finds_another_road_fails_the_run_and_overwrites_nothing():
    stored = {"placeholder-02": {"route_polyline_simplified": [list(p) for p in ROAD],
                                 "route_polyline_length_m": 6100}}
    same = FakeLedger(roads={"placeholder-02": 6100}, stored=stored)
    report, _ = go_roads(same, [(200, road_body())])
    assert report.outcome == "ok" and same.polylines == {}
    assert (same.route_checks[0]["kind"], same.route_checks[0]["matched"]) == ("refetch", True)

    parallel = [(lat, round(lon + 0.001, 6)) for lat, lon in ROAD]   # a road about 100 m east
    moved = FakeLedger(roads={"placeholder-02": 6100}, stored=stored)
    report, _ = go_roads(moved, [(200, road_body(parallel))])
    (row,) = moved.route_checks
    assert (row["matched"], row["length_change"]) == (False, 0.0) and row["max_deviation_m"] > 60
    assert moved.polylines == {}
    assert report.outcome == "failed" and "different road" in report.problems[0]


def test_a_failed_road_call_is_recorded_and_a_quota_refusal_stops_further_calls():
    ledger = FakeLedger(roads={"placeholder-02": None, "placeholder-04": None})
    report, transport = go_roads(ledger, [(429, b"")], ids=("placeholder-02", "placeholder-04"))
    assert len(transport.calls) == 1
    (row,) = ledger.route_checks
    assert (row["error_class"], row["http_status"], row["points"], row["length_m"]) == (
        "quota_exhausted", 429, None, None)
    assert report.quota_refused and ledger.polylines == {}


def test_road_calls_come_after_the_due_slots_and_stop_at_the_per_run_cap():
    ids = ("placeholder-01", "placeholder-02", "placeholder-03", "placeholder-04")
    ledger = FakeLedger(roads={c: None for c in ids[1:]})
    report, transport = go_roads(ledger, [(200, OK_BODY), (200, road_body()), (200, road_body())],
                                 ids=ids, active=("placeholder-01",), at=MORNING)
    assert len(transport.calls) == 3 and "summaryOnly" in transport.calls[0]
    assert all("routeRepresentation=polyline" in u for u in transport.calls[1:])
    assert sorted(ledger.polylines) == ["placeholder-02", "placeholder-03"]
    assert report.recorded == 1 and report.route_checks == 2 and report.attempts == 3
