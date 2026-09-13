"""Corridor declarations: config/corridors.yaml, validated.

The file is the only place a corridor is defined. Alternates are declared
here, never derived at runtime, and a pair holding one corridor is valid: it
means "no measured alternate".

Every corridor, whatever its class, declares via_points: an ordered list of
points the collector sends to TomTom as waypoints on every call. Without them
TomTom picks the road each time and may pick a different one next time, so the
series would not measure a fixed corridor, and two corridors sharing endpoints
would measure the same road twice. The members of a pair share endpoints and
must differ in via_points. via_points are declared by a person and measured
for months; they are never shown to users as a route.

A corridor leaves draft only once verified: a person has confirmed every
coordinate on satellite imagery. Coordinates freeze once a corridor is measured,
and public sources give neighbourhood centroids and metro stations, not junction
centres, so an unchecked coordinate would become a permanent wrong one. A
corridor may name its endpoint junctions from config/junctions.yaml, and cannot
be verified while one of them is not.

treatment_status records whether the corridor's road is untreated, will be
treated, is under construction or has been treated; anything but untreated cites
a sourced work in config/interventions.yaml. A donor is a control and is always
untreated.
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "corridors.yaml"
# Greater Hyderabad, generously bounded, to catch swapped or mistyped coordinates.
LAT_RANGE = (17.10, 17.75)
LON_RANGE = (78.05, 78.85)
ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
LABEL_PATTERN = r"^[A-Z]{2}-[0-9]{2,4}$"
MAX_VIA_POINTS = 25  # 0006's corridors_via_points_valid holds the same limit


def check_in_hyderabad(lat: float, lon: float, what: str) -> None:
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise ValueError(f"{what} {lat},{lon} is outside Greater Hyderabad")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float
    lon: float

    @model_validator(mode="after")
    def _bounds(self) -> "Point":
        check_in_hyderabad(self.lat, self.lon, "via point")
        return self


class Corridor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str = Field(pattern=ID_PATTERN)
    code: str | None = Field(default=None, pattern=LABEL_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    corridor_class: Literal["core", "alternate", "donor"] = Field(alias="class")
    tier: Literal["A", "B", "C"]
    direction: Literal["ab", "ba"]
    pair_id: str | None = Field(default=None, pattern=LABEL_PATTERN)
    origin_name: str | None = Field(default=None, min_length=1, max_length=80)
    destination_name: str | None = Field(default=None, min_length=1, max_length=80)
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    via_points: tuple[Point, ...]
    status: Literal["draft", "active", "paused", "retired"]
    supersedes: str | None = Field(default=None, pattern=ID_PATTERN)
    verified: bool = False
    treatment_status: Literal["untreated", "will_be_treated", "under_construction",
                              "treated"] = "untreated"
    treatment_work: str | None = Field(default=None, pattern=ID_PATTERN)
    origin_junction: str | None = Field(default=None, pattern=ID_PATTERN)
    destination_junction: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def _rules(self) -> "Corridor":
        check_in_hyderabad(self.origin_lat, self.origin_lon, f"{self.id} origin")
        check_in_hyderabad(self.dest_lat, self.dest_lon, f"{self.id} destination")
        if (self.origin_lat, self.origin_lon) == (self.dest_lat, self.dest_lon):
            raise ValueError(f"{self.id}: origin and destination are the same point")
        if not self.via_points:
            raise ValueError(f"{self.id}: no via_points, so TomTom would choose its road "
                             "on every call")
        if len(self.via_points) > MAX_VIA_POINTS:
            raise ValueError(f"{self.id}: at most {MAX_VIA_POINTS} via_points")
        if self.corridor_class == "alternate" and self.pair_id is None:
            raise ValueError(f"{self.id}: an alternate needs a pair_id")
        if self.corridor_class == "donor" and self.pair_id is not None:
            raise ValueError(f"{self.id}: a donor corridor is never paired")
        if self.supersedes == self.id:
            raise ValueError(f"{self.id} cannot supersede itself")
        if self.status != "draft" and not self.verified:
            raise ValueError(f"{self.id}: status {self.status} needs verified: true. An "
                             "unverified corridor may only be a draft, because its coordinates "
                             "freeze once it is measured")
        if (self.treatment_status == "untreated") != (self.treatment_work is None):
            raise ValueError(f"{self.id}: treatment_status {self.treatment_status} needs a "
                             "treatment_work from config/interventions.yaml when it is not "
                             "untreated, and none when it is")
        if self.corridor_class == "donor" and self.treatment_status != "untreated":
            raise ValueError(f"{self.id}: a donor is a control and must be untreated")
        return self

    @property
    def endpoints(self) -> tuple[float, float, float, float]:
        return (self.origin_lat, self.origin_lon, self.dest_lat, self.dest_lon)


class Panel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    corridors: tuple[Corridor, ...]

    @model_validator(mode="after")
    def _cross_rules(self) -> "Panel":
        for label, values in (("id", [c.id for c in self.corridors]),
                              ("code", [c.code for c in self.corridors if c.code])):
            repeated = sorted(v for v, n in Counter(values).items() if n > 1)
            if repeated:
                raise ValueError(f"duplicate corridor {label}: {', '.join(repeated)}")

        members: dict[tuple[str, str], list[Corridor]] = defaultdict(list)
        for c in self.corridors:
            if c.pair_id:
                members[(c.pair_id, c.direction)].append(c)
        cores: dict[str, dict[str, Corridor]] = defaultdict(dict)
        for (pair, direction), group in members.items():
            classes = Counter(c.corridor_class for c in group)
            if classes["core"] != 1:
                raise ValueError(f"pair {pair} {direction}: needs exactly one core corridor, "
                                 f"found {classes['core']}")
            if classes["alternate"] > 1:
                raise ValueError(f"pair {pair} {direction}: at most one declared alternate")
            if len({c.endpoints for c in group}) > 1:
                raise ValueError(f"pair {pair} {direction}: corridors must share origin and "
                                 "destination")
            declared: dict[tuple[Point, ...], str] = {}
            for c in group:
                if c.via_points in declared:
                    raise ValueError(
                        f"pair {pair} {direction}: {declared[c.via_points]} and {c.id} declare "
                        "identical via_points, so they would measure the same road")
                declared[c.via_points] = c.id
            cores[pair][direction] = next(c for c in group if c.corridor_class == "core")
        for pair, directions in cores.items():
            if "ab" in directions and "ba" in directions:
                ab, ba = directions["ab"], directions["ba"]
                if ba.endpoints != (ab.dest_lat, ab.dest_lon, ab.origin_lat, ab.origin_lon):
                    raise ValueError(f"pair {pair}: direction ba must reverse direction ab")

        by_id = {c.id: c for c in self.corridors}
        for c in self.corridors:
            seen = {c.id}
            target_id = c.supersedes
            while target_id:
                target = by_id.get(target_id)
                if target is None:
                    raise ValueError(f"{c.id} supersedes {target_id}, which is not declared")
                if target.status != "retired":
                    raise ValueError(f"{c.id} supersedes {target_id}, which is not retired")
                if target_id in seen:
                    raise ValueError(f"supersedes cycle through {target_id}")
                seen.add(target_id)
                target_id = target.supersedes
        return self

    def active(self) -> list[Corridor]:
        return [c for c in self.corridors if c.status == "active"]


def check_references(panel: Panel, junctions, register) -> None:
    """Rules across files. A cited work exists, has the corridor's treatment_status and
    carries a source with a URL and a date. A named junction exists and is the
    corridor's endpoint, and a verified corridor names only verified junctions."""
    for c in panel.corridors:
        if c.treatment_work is not None:
            work = register.work(c.treatment_work)
            if work is None:
                raise ValueError(f"{c.id}: treatment_work {c.treatment_work} is not in "
                                 "config/interventions.yaml")
            if work.treatment_status != c.treatment_status:
                raise ValueError(f"{c.id}: treatment_status {c.treatment_status}, but "
                                 f"{work.id} is {work.treatment_status}")
            if not work.sourced:
                raise ValueError(f"{c.id}: {work.id} has no source with a URL and a date, so "
                                 "no corridor may cite it yet")
        for end, junction_id, lat, lon in (
                ("origin", c.origin_junction, c.origin_lat, c.origin_lon),
                ("destination", c.destination_junction, c.dest_lat, c.dest_lon)):
            if junction_id is None:
                continue
            junction = junctions.get(junction_id)
            if junction is None:
                raise ValueError(f"{c.id}: {end}_junction {junction_id} is not in "
                                 "config/junctions.yaml")
            if (junction.lat, junction.lon) != (lat, lon):
                raise ValueError(f"{c.id}: {end} {lat},{lon} is not junction {junction_id} "
                                 f"at {junction.lat},{junction.lon}")
            if c.verified and not junction.verified:
                raise ValueError(f"{c.id}: verified, but its {end} junction {junction_id} is not")


def load_panel(path: Path = CONFIG_PATH, registry: bool = True) -> Panel:
    """The declarations, checked against the junction and treatment registers."""
    with open(path, encoding="utf-8") as f:
        panel = Panel.model_validate(yaml.safe_load(f))
    if registry:
        from registry import load_junctions, load_register

        junctions = load_junctions()
        check_references(panel, junctions, load_register(junctions=junctions))
    return panel


def main() -> int:
    """CI: the declarations validate and the active panel fits the daily budget."""
    from datetime import datetime

    from budget import check_fits, day_plan
    from schedule import IST

    panel = load_panel()
    active = panel.active()
    planned = check_fits(day_plan([c.tier for c in active], datetime.now(IST).date()))
    print(f"{len(panel.corridors)} corridors declared, {len(active)} active, "
          f"{planned} first attempts planned per day")
    return 0


if __name__ == "__main__":
    sys.exit(main())
