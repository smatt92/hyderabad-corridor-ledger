"""A corridor's road, fetched once: parse it, simplify it, compare a refetch with it.

Samples request routeRepresentation=summaryOnly and store no geometry. A
corridor's road is fixed by its declared points, so the collector fetches the
road once, when the corridor is verified (fetch.check_route), and stores it on the
corridor row for the map. The stored road is permanent. A weekly refetch that
differs from it is a rerouting alarm, never an update: TomTom now routes the
corridor down a different road, and the corridor no longer measures the road it
was verified on.

Pure: no network, no database.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

Point = tuple[float, float]  # (lat, lon)

MAX_POINTS = 20_000             # 0012's route_polyline_valid holds the same limit
LAT_BOUNDS = (17.00, 17.85)     # 0012: a little beyond config.py's corridor bounds,
LON_BOUNDS = (77.95, 78.95)     # since a road between two points can briefly leave them
SIMPLIFY_TOLERANCE_M = 5.0
# Rerouting thresholds. Not calibrated: no real corridor has been refetched yet. Two
# calls routing the same road through the same points should return near-identical
# polylines, and parallel roads are usually tens of metres apart or more. A flyover and
# the road beneath it are a few metres apart in plan, so the deviation cannot tell
# them apart; only the length threshold might.
REROUTE_DEVIATION_M = 30.0
REROUTE_LENGTH_SHARE = 0.02
REFETCH_EVERY = timedelta(days=7)
RETRY_AFTER = timedelta(hours=1)
ROUTE_CHECKS_PER_RUN = 2
EARTH_RADIUS_M = 6_371_008.8


class PolylineError(ValueError):
    """The response carries no usable road polyline."""


def parse_polyline(body: bytes) -> tuple[list[Point], int]:
    """The route's points, its legs joined, and its lengthInMeters."""
    try:
        route = json.loads(body)["routes"][0]
        legs = route["legs"]
        length = route["summary"]["lengthInMeters"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise PolylineError("response has no route with legs and a summary") from exc
    if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
        raise PolylineError(f"lengthInMeters is not a positive integer: {length!r}")
    points: list[Point] = []
    try:
        for leg in legs:
            for p in leg["points"]:
                point = (round(float(p["latitude"]), 6), round(float(p["longitude"]), 6))
                if not points or points[-1] != point:  # consecutive legs share a point
                    points.append(point)
    except (KeyError, TypeError, ValueError) as exc:
        raise PolylineError("a leg has no points with latitude and longitude") from exc
    if not 2 <= len(points) <= MAX_POINTS:
        raise PolylineError(f"polyline has {len(points)} points, outside 2 to {MAX_POINTS}")
    for lat, lon in points:
        if not (LAT_BOUNDS[0] <= lat <= LAT_BOUNDS[1] and LON_BOUNDS[0] <= lon <= LON_BOUNDS[1]):
            raise PolylineError(f"polyline leaves Greater Hyderabad at {lat},{lon}")
    return points, length


def _projector(origin: Sequence[float]):
    """Metres east and north of `origin`. Equirectangular: within a fraction of a percent
    across a city."""
    cos_lat = math.cos(math.radians(origin[0]))

    def project(p: Sequence[float]) -> tuple[float, float]:
        return (math.radians(p[1] - origin[1]) * EARTH_RADIUS_M * cos_lat,
                math.radians(p[0] - origin[0]) * EARTH_RADIUS_M)

    return project


def _to_segment(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def simplify(points: Sequence[Sequence[float]],
             tolerance_m: float = SIMPLIFY_TOLERANCE_M) -> list[Point]:
    """Douglas-Peucker: every dropped point lies within tolerance_m of the kept line."""
    kept_points = [(float(p[0]), float(p[1])) for p in points]
    if len(kept_points) <= 2:
        return kept_points
    project = _projector(kept_points[0])
    xy = [project(p) for p in kept_points]
    keep = [False] * len(xy)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        first, last = stack.pop()
        worst, index = tolerance_m, None
        for i in range(first + 1, last):
            distance = _to_segment(xy[i], xy[first], xy[last])
            if distance > worst:
                worst, index = distance, i
        if index is not None:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [p for p, k in zip(kept_points, keep, strict=True) if k]


def _farthest(points, line) -> float:
    segments = list(zip(line, line[1:], strict=False))
    return max(min(_to_segment(p, a, b) for a, b in segments) for p in points)


def max_deviation_m(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> float:
    """The farthest any vertex of either polyline lies from the other polyline, in metres."""
    project = _projector(a[0])
    return max(_farthest([project(p) for p in a], [project(p) for p in b]),
               _farthest([project(p) for p in b], [project(p) for p in a]))


@dataclass(frozen=True)
class Comparison:
    max_deviation_m: float
    length_change: float  # (refetched - stored) / stored
    matched: bool


def compare(stored: Sequence[Sequence[float]], stored_length_m: int,
            fresh: Sequence[Sequence[float]], fresh_length_m: int) -> Comparison:
    """A refetch against the stored road. Both polylines are the simplified copies, so
    the deviation is exact to within twice SIMPLIFY_TOLERANCE_M."""
    deviation = max_deviation_m(stored, fresh)
    change = (fresh_length_m - stored_length_m) / stored_length_m
    matched = deviation <= REROUTE_DEVIATION_M and abs(change) <= REROUTE_LENGTH_SHARE
    return Comparison(deviation, change, matched)


def route_checks_due(corridor_ids: Sequence[str], stored_lengths: dict[str, int | None],
                     recent: list[dict], now: datetime) -> list[tuple[str, str]]:
    """(corridor_id, kind) for verified corridors whose road needs a call, in id order.

    stored_lengths maps each corridor the database holds as verified to its
    route_polyline_length_m, None while no road is stored. A corridor absent from it is
    not verified in the database yet and waits for the sync. recent holds the route
    checks of the last REFETCH_EVERY, each with corridor_id, checked_at and error_class.

    initial: no stored road. refetch: no successful check within REFETCH_EVERY. A call
    within RETRY_AFTER, failed or not, holds a corridor back, so a failing call is
    retried hourly rather than on every run."""
    due = []
    for cid in sorted(corridor_ids):
        if cid not in stored_lengths:
            continue
        ages = [(now - datetime.fromisoformat(r["checked_at"]), r["error_class"])
                for r in recent if r["corridor_id"] == cid]
        if any(age < RETRY_AFTER for age, _ in ages):
            continue
        if stored_lengths[cid] is None:
            due.append((cid, "initial"))
        elif not any(age < REFETCH_EVERY and error is None for age, error in ages):
            due.append((cid, "refetch"))
    return due
