"""TomTom calculateRoute: the request, and what is kept of the response.

The request carries a corridor's declared origin, via points and destination,
with live traffic, every travel-time variant, and the summaryOnly
representation. It never asks for alternatives: alternates are declared
corridors, measured in their own right. The API key travels in the query
string, so URLs are redacted before they reach a log or an error.

The full response is stored gzipped. A response containing `points`, or
larger than RAW_GZ_CAP bytes gzipped, means route geometry has leaked in.
That is a collector bug, and it fails loudly rather than eating the storage
budget.
"""

import gzip
import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from config import Corridor

BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
QUERY = {
    "traffic": "true",
    "computeTravelTimeFor": "all",
    "routeRepresentation": "summaryOnly",
    "travelMode": "car",
    "maxAlternatives": "0",
}
RAW_GZ_CAP = 4096


class GeometryLeak(RuntimeError):
    """The response carries route geometry, or is too large to be a summary."""


def route_url(corridor: Corridor, key: str) -> str:
    stops = [(corridor.origin_lat, corridor.origin_lon),
             *((p.lat, p.lon) for p in corridor.via_points),
             (corridor.dest_lat, corridor.dest_lon)]
    locations = ":".join(f"{lat},{lon}" for lat, lon in stops)
    return f"{BASE_URL}/{locations}/json?{urlencode({**QUERY, 'key': key})}"


def redact(text: str) -> str:
    return re.sub(r"(key=)[^&\s\"']+", r"\1REDACTED", text)


@dataclass(frozen=True)
class Summary:
    length_m: int
    travel_time_s: int
    traffic_delay_s: int | None
    no_traffic_travel_time_s: int | None
    historic_travel_time_s: int | None


def _contains_points(node) -> bool:
    if isinstance(node, dict):
        return "points" in node or any(_contains_points(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_points(v) for v in node)
    return False


def compress(body: bytes) -> bytes:
    """gzip with a fixed mtime: the same response always stores the same bytes."""
    raw_gz = gzip.compress(body, mtime=0)
    if len(raw_gz) > RAW_GZ_CAP:
        raise GeometryLeak(
            f"gzipped response is {len(raw_gz)} bytes, over the {RAW_GZ_CAP}-byte cap: "
            "a summary never gets that large"
        )
    return raw_gz


def parse_summary(body: bytes) -> Summary:
    """The route summary. Raises GeometryLeak on points, ValueError on anything malformed."""
    try:
        doc = json.loads(body)
    except ValueError as exc:
        raise ValueError("response is not JSON") from exc
    if _contains_points(doc):
        raise GeometryLeak("response contains route points despite routeRepresentation=summaryOnly")
    try:
        summary = doc["routes"][0]["summary"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response has no route summary") from exc

    def whole(name: str, required: bool) -> int | None:
        value = summary.get(name)
        if value is None:
            if required:
                raise ValueError(f"summary has no {name}")
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"summary {name} is not a non-negative integer: {value!r}")
        return value

    length = whole("lengthInMeters", required=True)
    travel = whole("travelTimeInSeconds", required=True)
    if not length or not travel:
        raise ValueError("summary length or travel time is zero")
    return Summary(
        length_m=length,
        travel_time_s=travel,
        traffic_delay_s=whole("trafficDelayInSeconds", required=False),
        no_traffic_travel_time_s=whole("noTrafficTravelTimeInSeconds", required=False),
        historic_travel_time_s=whole("historicTrafficTravelTimeInSeconds", required=False),
    )
