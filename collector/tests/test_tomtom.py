import gzip
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from config import load_panel
from tomtom import RAW_GZ_CAP, GeometryLeak, compress, parse_summary, redact, route_url

FIXTURE = Path(__file__).parent / "fixtures" / "corridors.yaml"

PANEL = {c.id: c for c in load_panel(FIXTURE).corridors}

SUMMARY = {
    "lengthInMeters": 9812, "travelTimeInSeconds": 1502, "trafficDelayInSeconds": 212,
    "trafficLengthInMeters": 3100, "departureTime": "2026-09-14T08:00:05+05:30",
    "arrivalTime": "2026-09-14T08:25:07+05:30", "noTrafficTravelTimeInSeconds": 1180,
    "historicTrafficTravelTimeInSeconds": 1420, "liveTrafficIncidentsTravelTimeInSeconds": 1502,
}
BODY = json.dumps({
    "formatVersion": "0.0.12",
    "routes": [{
        "summary": SUMMARY,
        "legs": [{"summary": SUMMARY}],
        "sections": [{"startPointIndex": 0, "endPointIndex": 412, "sectionType": "TRAVEL_MODE",
                      "travelMode": "car"}],
    }],
}).encode()


def test_url_carries_declared_stops_and_summary_only_params():
    url = urlparse(route_url(PANEL["placeholder-02"], "secret-key"))
    assert url.netloc == "api.tomtom.com"
    assert url.path == "/routing/1/calculateRoute/17.497,78.36:17.464,78.357:17.447,78.377/json"
    assert parse_qs(url.query) == {
        "traffic": ["true"], "computeTravelTimeFor": ["all"],
        "routeRepresentation": ["summaryOnly"], "travelMode": ["car"], "maxAlternatives": ["0"],
        "key": ["secret-key"],
    }


def test_core_without_via_goes_origin_to_destination():
    url = urlparse(route_url(PANEL["placeholder-01"], "k"))
    assert url.path.endswith("/17.497,78.36:17.447,78.377/json")


def test_redact_hides_the_key_everywhere():
    url = route_url(PANEL["placeholder-01"], "abc123")
    assert "abc123" not in redact(url)
    assert "key=REDACTED" in redact(f"HTTP 403 for {url}")


def test_parse_summary():
    s = parse_summary(BODY)
    assert (s.length_m, s.travel_time_s, s.traffic_delay_s) == (9812, 1502, 212)
    assert (s.no_traffic_travel_time_s, s.historic_travel_time_s) == (1180, 1420)


def test_summary_stays_well_under_the_cap():
    assert len(compress(BODY)) < 1024
    assert gzip.decompress(compress(BODY)) == BODY
    assert compress(BODY) == compress(BODY)  # fixed mtime: reproducible bytes


def test_points_in_the_response_fail_loudly():
    leaked = json.loads(BODY)
    leaked["routes"][0]["legs"][0]["points"] = [{"latitude": 17.4, "longitude": 78.3}]
    with pytest.raises(GeometryLeak, match="points"):
        parse_summary(json.dumps(leaked).encode())


def test_oversize_response_fails_loudly():
    padded = json.loads(BODY)
    padded["routes"][0]["guidance"] = os.urandom(6000).hex()
    with pytest.raises(GeometryLeak, match=f"{RAW_GZ_CAP}-byte cap"):
        compress(json.dumps(padded).encode())


@pytest.mark.parametrize("body, message", [
    (b"<html>429 Too Many Requests</html>", "not JSON"),
    (json.dumps({"routes": []}).encode(), "no route summary"),
    (json.dumps({"routes": [{"summary": {"lengthInMeters": 10}}]}).encode(), "travelTimeInSeconds"),
    (json.dumps({"routes": [{"summary": {**SUMMARY, "travelTimeInSeconds": -1}}]}).encode(),
     "non-negative"),
    (json.dumps({"routes": [{"summary": {**SUMMARY, "lengthInMeters": 0}}]}).encode(), "zero"),
])
def test_malformed_summaries_are_errors_not_samples(body, message):
    with pytest.raises(ValueError, match=message):
        parse_summary(body)
