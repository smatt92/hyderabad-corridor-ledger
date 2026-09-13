import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from config import Panel, load_panel

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
])
def test_invalid_panels_are_rejected(mutate, message):
    with pytest.raises(ValidationError, match=message):
        Panel.model_validate(panel_with(mutate))


def test_superseding_a_retired_corridor():
    def retire_and_replace(cs):
        by_id(cs, "placeholder-07").update(status="retired")
        new = copy.deepcopy(by_id(cs, "placeholder-07"))
        new.update(id="placeholder-11", code="PL-11", status="active", pair_id="PL-06",
                   supersedes="placeholder-07", dest_lat=17.390)
        cs.append(new)

    panel = Panel.model_validate(panel_with(retire_and_replace))
    assert [c.id for c in panel.active()] == ["placeholder-11"]
