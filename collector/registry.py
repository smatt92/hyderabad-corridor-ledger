"""Junction candidates and the treatment register, validated.

    python collector/registry.py           # config/junctions.yaml and interventions.yaml
    python collector/registry.py overdue   # fails when a recheck is overdue

Junctions (config/junctions.yaml). Public sources give neighbourhood centroids,
bus stops and metro stations, not junction centres, and a corridor's endpoints
and via_points freeze the moment it is measured. Every junction is therefore a
candidate until Sahil verifies its centre on satellite imagery (verified with
verified_on). A low-confidence candidate says why. Two candidates within about
300 m of each other must name each other in distinct_from, so near neighbours
are never conflated.

Works (config/interventions.yaml). Every road work that treats, is treating or
will treat a corridor: its events, each with who gave the date (conflicting
official dates are all kept), and its sources. A corridor may cite a work only
once the work has at least one source with a URL and a date.

Controls. Candidate control areas with no announced works; none is usable until
screened against Hyderabad Metro Phase-2 alignments and traffic advisories.

Recheck. Each screened control and each work not yet treated is checked again
every RECHECK_DAYS days. A control moves to under_construction, as a work, on
the first traffic-diversion advisory or excavation report for its junction; a
will_be_treated work moves to under_construction on its first excavation report.
"""

import datetime as dt
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import ID_PATTERN, check_in_hyderabad

CONFIG = Path(__file__).resolve().parent.parent / "config"
JUNCTIONS_PATH = CONFIG / "junctions.yaml"
REGISTER_PATH = CONFIG / "interventions.yaml"
RECHECK_DAYS = 92
# About 300 m of latitude, and a little less of longitude at Hyderabad. A plain
# box, not a distance: nothing is measured from coordinates.
NEAR_DEGREES = 0.003
PARTIAL_DATE = r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"
Treatment = Literal["will_be_treated", "under_construction", "treated"]


def _unique(label: str, ids: list[str]) -> None:
    repeated = sorted(i for i, n in Counter(ids).items() if n > 1)
    if repeated:
        raise ValueError(f"duplicate {label} id: {', '.join(repeated)}")


class Junction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    lat: float
    lon: float
    confidence: Literal["high", "medium", "low"]
    verified: bool = False
    verified_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=500)
    distinct_from: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _rules(self) -> "Junction":
        check_in_hyderabad(self.lat, self.lon, f"junction {self.id}")
        if self.verified != (self.verified_on is not None):
            raise ValueError(f"junction {self.id}: verified: true needs verified_on, the date "
                             "the centre was checked on satellite imagery, and only then")
        if self.confidence == "low" and not self.note:
            raise ValueError(f"junction {self.id}: a low-confidence candidate needs a note "
                             "saying why")
        return self


class Junctions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    junctions: tuple[Junction, ...]

    @model_validator(mode="after")
    def _cross_rules(self) -> "Junctions":
        _unique("junction", [j.id for j in self.junctions])
        by_id = {j.id: j for j in self.junctions}
        for j in self.junctions:
            for other in j.distinct_from:
                if other not in by_id:
                    raise ValueError(f"junction {j.id}: distinct_from names unknown {other}")
                if j.id not in by_id[other].distinct_from:
                    raise ValueError(f"junctions {j.id} and {other}: distinct_from must name "
                                     "each other")
        for i, a in enumerate(self.junctions):
            for b in self.junctions[i + 1:]:
                near = abs(a.lat - b.lat) < NEAR_DEGREES and abs(a.lon - b.lon) < NEAR_DEGREES
                if near and b.id not in a.distinct_from:
                    raise ValueError(f"junctions {a.id} and {b.id} are within about 300 m: "
                                     "name each other in distinct_from, or they are one junction")
        return self

    def get(self, junction_id: str) -> Junction | None:
        return next((j for j in self.junctions if j.id == junction_id), None)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["opened", "excavation_began", "excavation_reported", "target_completion",
                   "price_bids_opened", "awarded"]
    date: str = Field(pattern=PARTIAL_DATE)
    according_to: str | None = None
    note: str | None = None


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(pattern=r"^https?://\S+$")
    date: dt.date
    claim: str | None = None


class Work(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    treatment_status: Treatment
    junctions: tuple[str, ...] = ()
    events: tuple[Event, ...] = ()
    cost: str | None = None
    contract: str | None = None
    notes: str | None = None
    sources: tuple[Source, ...] = ()
    last_checked: dt.date

    @property
    def sourced(self) -> bool:
        """At least one source with a URL and a date: citable by a corridor."""
        return bool(self.sources)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    junctions: tuple[str, ...] = ()
    screening: Literal["unscreened", "screened"]
    last_screened: dt.date | None = None
    flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _rules(self) -> "Control":
        if (self.screening == "screened") != (self.last_screened is not None):
            raise ValueError(f"control {self.id}: screened needs last_screened, and only then")
        return self


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    works: tuple[Work, ...]
    controls: tuple[Control, ...] = ()

    @model_validator(mode="after")
    def _cross_rules(self) -> "Register":
        _unique("work or control", [w.id for w in self.works] + [c.id for c in self.controls])
        return self

    def work(self, work_id: str) -> Work | None:
        return next((w for w in self.works if w.id == work_id), None)


def load_junctions(path: Path = JUNCTIONS_PATH) -> Junctions:
    with open(path, encoding="utf-8") as f:
        return Junctions.model_validate(yaml.safe_load(f))


def load_register(path: Path = REGISTER_PATH, junctions: Junctions | None = None) -> Register:
    with open(path, encoding="utf-8") as f:
        register = Register.model_validate(yaml.safe_load(f))
    known = {j.id for j in (junctions or load_junctions()).junctions}
    for item in (*register.works, *register.controls):
        unknown = sorted(set(item.junctions) - known)
        if unknown:
            raise ValueError(f"{item.id} names unknown junctions: {', '.join(unknown)}")
    return register


def overdue(register: Register, today: dt.date) -> list[str]:
    """Every recheck older than RECHECK_DAYS days."""
    limit = today - dt.timedelta(days=RECHECK_DAYS)
    late = [f"work {w.id} ({w.treatment_status}) last checked {w.last_checked}: look for its "
            "first excavation report or traffic-diversion advisory"
            for w in register.works if w.treatment_status != "treated" and w.last_checked < limit]
    late += [f"control {c.id} last screened {c.last_screened}: it becomes under_construction "
             "on the first traffic-diversion advisory or excavation report for its junction"
             for c in register.controls if c.screening == "screened" and c.last_screened < limit]
    return late


def main(argv: list[str]) -> int:
    junctions = load_junctions()
    register = load_register(junctions=junctions)
    if argv[1:] == ["overdue"]:
        late = overdue(register, dt.date.today())
        for message in late:
            print(f"::error::{message}", file=sys.stderr)
        print(f"{len(late)} recheck(s) overdue")
        return 1 if late else 0
    statuses = Counter(w.treatment_status for w in register.works)
    print(f"{len(junctions.junctions)} junction candidates, "
          f"{sum(j.verified for j in junctions.junctions)} verified; works "
          f"{dict(statuses)}, {sum(w.sourced for w in register.works)} sourced; "
          f"{len(register.controls)} control candidates, "
          f"{sum(c.screening == 'screened' for c in register.controls)} screened")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
