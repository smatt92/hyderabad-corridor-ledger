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


def _check_in_hyderabad(lat: float, lon: float, what: str) -> None:
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise ValueError(f"{what} {lat},{lon} is outside Greater Hyderabad")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float
    lon: float

    @model_validator(mode="after")
    def _bounds(self) -> "Point":
        _check_in_hyderabad(self.lat, self.lon, "via point")
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

    @model_validator(mode="after")
    def _rules(self) -> "Corridor":
        _check_in_hyderabad(self.origin_lat, self.origin_lon, f"{self.id} origin")
        _check_in_hyderabad(self.dest_lat, self.dest_lon, f"{self.id} destination")
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


def load_panel(path: Path = CONFIG_PATH) -> Panel:
    with open(path, encoding="utf-8") as f:
        return Panel.model_validate(yaml.safe_load(f))


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
