import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from config import Panel, check_references, load_panel
from registry import Junctions, Register

FIXTURE = Path(__file__).parent / "fixtures" / "corridors.yaml"

BASE = yaml.safe_load(FIXTURE.read_text())


def panel_with(mutate):
    doc = copy.deepcopy(BASE)
    mutate(doc["corridors"])
    return doc


def by_id(corridors, cid):
    return next(c for c in corridors if c["id"] == cid)


def test_seeded_panel_is_valid_and_collects_nothing():
    panel = load_panel(FIXTURE)
    assert len(panel.corridors) == 10
    assert {c.status for c in panel.corridors} == {"draft"}
    assert panel.active() == []
    assert {c.corridor_class for c in panel.corridors} == {"core", "alternate", "donor"}
    pair_sizes = {}
    for c in panel.corridors:
        if c.pair_id:
            pair_sizes[c.pair_id] = pair_sizes.get(c.pair_id, 0) + 1
    assert 1 in pair_sizes.values()  # a one-corridor pair is valid


@pytest.mark.parametrize("mutate, message", [
    (lambda cs: cs.append(copy.deepcopy(cs[0])), "duplicate corridor id"),
    # every class needs via_points: TomTom must never choose a corridor's road
    (lambda cs: by_id(cs, "placeholder-02").update(via_points=[]), "no via_points"),
    (lambda cs: by_id(cs, "placeholder-01").update(via_points=[]), "no via_points"),
    (lambda cs: by_id(cs, "placeholder-09").update(via_points=[]), "no via_points"),
    (lambda cs: by_id(cs, "placeholder-04").pop("via_points"), "via_points"),
    (lambda cs: by_id(cs, "placeholder-04").update(via_points=[{"lat": 17.46, "lon": 78.4}] * 26),
     "at most 25"),
    (lambda cs: by_id(cs, "placeholder-02").update(via_points=[{"lat": 18.2, "lon": 78.357}]),
     "outside Greater Hyderabad"),
    (lambda cs: by_id(cs, "placeholder-02").update(via=[{"lat": 17.464, "lon": 78.357}]),
     "Extra inputs"),
    # a pair whose members share via_points would measure one road twice
    (lambda cs: by_id(cs, "placeholder-02").update(
        via_points=copy.deepcopy(by_id(cs, "placeholder-01")["via_points"])),
     "identical via_points"),
    (lambda cs: by_id(cs, "placeholder-09").update(pair_id="PL-09"), "never paired"),
    (lambda cs: by_id(cs, "placeholder-02").update(dest_lat=17.45), "share origin and destination"),
    (lambda cs: by_id(cs, "placeholder-02").update({"class": "core"}), "one core"),
    (lambda cs: by_id(cs, "placeholder-03").update(dest_lat=17.490), "must reverse"),
    (lambda cs: by_id(cs, "placeholder-04").update(supersedes="placeholder-05"), "not retired"),
    (lambda cs: by_id(cs, "placeholder-04").update(supersedes="nowhere"), "not declared"),
    (lambda cs: by_id(cs, "placeholder-04").update(origin_lat=78.411, origin_lon=17.485),
     "outside Greater Hyderabad"),
    (lambda cs: by_id(cs, "placeholder-04").update(colour="red"), "Extra inputs"),
    (lambda cs: by_id(cs, "placeholder-04").update(tier="D"), "tier"),
    # unverified coordinates may only ever be a draft: they freeze once measured
    (lambda cs: by_id(cs, "placeholder-04").update(status="active"), "needs verified: true"),
    (lambda cs: by_id(cs, "placeholder-04").update(status="paused"), "needs verified: true"),
    (lambda cs: by_id(cs, "placeholder-04").update(treatment_status="treated"),
     "needs a treatment_work"),
    (lambda cs: by_id(cs, "placeholder-04").update(treatment_work="bachupally-flyover"),
     "needs a treatment_work"),
    (lambda cs: by_id(cs, "placeholder-09").update(treatment_status="will_be_treated",
                                                   treatment_work="miyapur-allwyn-flyover"),
     "must be untreated"),
    (lambda cs: by_id(cs, "placeholder-04").update(treatment_status="demolished",
                                                   treatment_work="x-y"), "treatment_status"),
])
def test_invalid_panels_are_rejected(mutate, message):
    with pytest.raises(ValidationError, match=message):
        Panel.model_validate(panel_with(mutate))


def test_superseding_a_retired_corridor():
    def retire_and_replace(cs):
        by_id(cs, "placeholder-07").update(status="retired", verified=True)
        new = copy.deepcopy(by_id(cs, "placeholder-07"))
        new.update(id="placeholder-11", code="PL-11", status="active", pair_id="PL-06",
                   supersedes="placeholder-07", dest_lat=17.390, verified=True)
        cs.append(new)

    panel = Panel.model_validate(panel_with(retire_and_replace))
    assert [c.id for c in panel.active()] == ["placeholder-11"]


JUNCTIONS = Junctions.model_validate({"version": 1, "junctions": [
    {"id": "checked", "name": "Checked", "lat": 17.497, "lon": 78.360, "confidence": "high",
     "verified": True, "verified_on": "2026-09-20"},
    {"id": "unchecked", "name": "Unchecked", "lat": 17.447, "lon": 78.377,
     "confidence": "low", "note": "a bus stop"},
]})


def register(sources):
    return Register.model_validate({"version": 1, "works": [
        {"id": "a-flyover", "name": "A flyover", "treatment_status": "will_be_treated",
         "sources": sources, "last_checked": "2026-09-14"}]})


SOURCED = [{"url": "https://example.org/award", "date": "2026-02-10"}]


def placeholder(**changes):
    doc = copy.deepcopy(BASE)
    by_id(doc["corridors"], "placeholder-01").update(changes)
    return Panel.model_validate(doc)


def test_a_corridor_cites_only_a_sourced_work_with_its_own_status():
    cited = placeholder(treatment_status="will_be_treated", treatment_work="a-flyover")
    check_references(cited, JUNCTIONS, register(SOURCED))
    with pytest.raises(ValueError, match="no source with a URL and a date"):
        check_references(cited, JUNCTIONS, register([]))
    mismatched = placeholder(treatment_status="treated", treatment_work="a-flyover")
    with pytest.raises(ValueError, match="but a-flyover is will_be_treated"):
        check_references(mismatched, JUNCTIONS, register(SOURCED))
    unknown = placeholder(treatment_status="treated", treatment_work="nowhere")
    with pytest.raises(ValueError, match="not in config/interventions.yaml"):
        check_references(unknown, JUNCTIONS, register(SOURCED))


def test_named_junctions_are_the_endpoints_and_verification_needs_verified_junctions():
    # placeholder-01 runs from 17.497,78.360 to 17.447,78.377
    check_references(placeholder(origin_junction="checked", destination_junction="unchecked"),
                     JUNCTIONS, register([]))
    with pytest.raises(ValueError, match="is not junction checked"):
        check_references(placeholder(destination_junction="checked"), JUNCTIONS, register([]))
    with pytest.raises(ValueError, match="destination junction unchecked is not"):
        check_references(placeholder(origin_junction="checked", destination_junction="unchecked",
                                     verified=True), JUNCTIONS, register([]))
    with pytest.raises(ValueError, match="not in config/junctions.yaml"):
        check_references(placeholder(origin_junction="elsewhere"), JUNCTIONS, register([]))
