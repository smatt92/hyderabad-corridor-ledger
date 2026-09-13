import json
from datetime import UTC, datetime, timedelta

import pytest

from polyline import (
    RETRY_AFTER,
    PolylineError,
    compare,
    parse_polyline,
    route_checks_due,
    simplify,
)

NOW = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)
# Due north in 0.001-degree steps, about 111 m each. At 17.44 N one degree of longitude
# is about 106.1 km, so 0.0001 degrees east is about 10.6 m.
STRAIGHT = [(round(17.440 + i * 0.001, 6), 78.38) for i in range(11)]


def body(legs, length=1112):
    return json.dumps({"routes": [{
        "summary": {"lengthInMeters": length},
        "legs": [{"points": [{"latitude": a, "longitude": b} for a, b in leg]} for leg in legs],
    }]}).encode()


def test_legs_are_joined_without_repeating_the_point_they_share():
    points, length = parse_polyline(body([STRAIGHT[:6], STRAIGHT[5:]]))
    assert points == STRAIGHT and length == 1112


@pytest.mark.parametrize("bad, message", [
    (b"{}", "no route"),
    (body([STRAIGHT[:1]]), "1 points"),
    (body([STRAIGHT], length=0), "positive integer"),
    (body([[(17.44, 78.38), (19.07, 72.88)]]), "leaves Greater Hyderabad"),
    (json.dumps({"routes": [{"summary": {"lengthInMeters": 5},
                             "legs": [{"points": [{"lat": 1}]}]}]}).encode(), "no points"),
])
def test_unusable_polylines_are_refused(bad, message):
    with pytest.raises(PolylineError, match=message):
        parse_polyline(bad)


def test_simplify_drops_points_on_the_line_and_keeps_real_bends():
    assert simplify(STRAIGHT) == [STRAIGHT[0], STRAIGHT[-1]]
    bent = STRAIGHT[:6] + [(17.445, round(78.38 + i * 0.001, 6)) for i in range(1, 6)]
    assert simplify(bent) == [bent[0], bent[5], bent[-1]]
    wobble = [*STRAIGHT[:5], (17.445, 78.38003), *STRAIGHT[6:]]   # about 3 m off the line
    assert len(simplify(wobble)) == 2
    detour = [*STRAIGHT[:5], (17.445, 78.3802), *STRAIGHT[6:]]    # about 21 m off the line
    assert (17.445, 78.3802) in simplify(detour)


def test_the_same_road_matches_and_a_parallel_road_or_a_longer_route_does_not():
    same = compare(simplify(STRAIGHT), 1112, simplify(STRAIGHT), 1112)
    assert same.matched and same.max_deviation_m < 1 and same.length_change == 0
    parallel = [(lat, 78.3804) for lat, _ in STRAIGHT]            # about 42 m east
    moved = compare(simplify(STRAIGHT), 1112, simplify(parallel), 1112)
    assert not moved.matched and 40 < moved.max_deviation_m < 45
    longer = compare(STRAIGHT, 1000, STRAIGHT, 1030)
    assert not longer.matched and longer.length_change == pytest.approx(0.03)
    assert compare(STRAIGHT, 1000, STRAIGHT, 1015).matched


def check(cid, age, error=None):
    return {"corridor_id": cid, "checked_at": (NOW - age).isoformat(), "error_class": error}


def test_roads_are_fetched_once_failures_retried_hourly_and_stored_roads_refetched_weekly():
    stored = {"a": None, "b": None, "c": 1200, "d": 1200, "e": 1200}  # f: not verified in the db
    recent = [check("b", timedelta(minutes=20), "timeout"),   # failed 20 minutes ago: wait
              check("c", timedelta(days=2)),                  # checked this week: nothing to do
              check("d", timedelta(days=3), "upstream_5xx"),  # only a failure this week: refetch
              check("e", timedelta(minutes=5))]               # just checked: wait
    ids = ["f", "e", "d", "c", "b", "a"]
    assert route_checks_due(ids, stored, recent, NOW) == [("a", "initial"), ("d", "refetch")]
    later = [check("b", RETRY_AFTER + timedelta(seconds=1), "timeout")]
    assert route_checks_due(["b"], stored, later, NOW) == [("b", "initial")]
    assert route_checks_due(["c"], stored, [], NOW) == [("c", "refetch")]
