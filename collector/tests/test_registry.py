"""The junction candidates and the treatment register."""

import datetime as dt

import pytest
from pydantic import ValidationError

from registry import Junctions, Register, load_junctions, load_register, overdue


def junction(**changes):
    return {"id": "a-junction", "name": "A junction", "lat": 17.40, "lon": 78.45,
            "confidence": "medium"} | changes


def test_the_committed_registers_validate_and_no_candidate_is_verified_by_default():
    junctions = load_junctions()
    register = load_register(junctions=junctions)
    by_id = {j.id: j for j in junctions.junctions}
    assert by_id["rethibowli"].distinct_from == ("nanal-nagar",)
    assert all(j.note for j in junctions.junctions if j.confidence == "low")
    assert {"khajaguda", "nfcl-junction"}.isdisjoint(by_id)  # not established, not seeded
    iiit = register.work("iiit-khajaguda-wipro-cluster")
    assert {e.according_to for e in iiit.events if e.event == "target_completion"} == {
        "CMC Commissioner", "GHMC"}  # conflicting official dates are both kept


@pytest.mark.parametrize("junctions, message", [
    ([junction(confidence="low")], "needs a note"),
    ([junction(verified=True)], "needs verified_on"),
    ([junction(verified_on="2026-09-20")], "needs verified_on"),
    ([junction(lat=18.4)], "outside Greater Hyderabad"),
    # about 200 m apart, like Rethibowli and Nanal Nagar: never silently one junction
    ([junction(), junction(id="b-junction", lat=17.4025, lon=78.4486)], "within about 300 m"),
    ([junction(distinct_from=["b-junction"]), junction(id="b-junction", lat=17.47)],
     "must name each other"),
    ([junction(), junction()], "duplicate junction id"),
])
def test_invalid_junction_candidates_are_rejected(junctions, message):
    with pytest.raises(ValidationError, match=message):
        Junctions.model_validate({"version": 1, "junctions": junctions})


def test_near_candidates_that_name_each_other_are_kept_apart():
    Junctions.model_validate({"version": 1, "junctions": [
        junction(distinct_from=["b-junction"]),
        junction(id="b-junction", lat=17.4025, lon=78.4486, distinct_from=["a-junction"])]})


def work(**changes):
    return {"id": "a-work", "name": "A work", "treatment_status": "under_construction",
            "last_checked": "2026-09-14"} | changes


@pytest.mark.parametrize("document, message", [
    ({"works": [work(treatment_status="untreated")]}, "treatment_status"),
    ({"works": [work(sources=[{"url": "example.org/x", "date": "2026-09-01"}])]}, "url"),
    ({"works": [work(sources=[{"url": "https://example.org/x"}])]}, "date"),
    ({"works": [work(events=[{"event": "opened", "date": "Jun 2026"}])]}, "date"),
    ({"works": [work()], "controls": [{"id": "a-work", "name": "Same id",
                                        "screening": "unscreened"}]}, "duplicate"),
    ({"works": [], "controls": [{"id": "c-area", "name": "C area", "screening": "screened"}]},
     "needs last_screened"),
])
def test_invalid_register_entries_are_rejected(document, message):
    with pytest.raises(ValidationError, match=message):
        Register.model_validate({"version": 1} | document)


def test_a_work_is_citable_only_once_it_has_a_source_with_url_and_date():
    unsourced = Register.model_validate({"version": 1, "works": [work()]})
    sourced = Register.model_validate({"version": 1, "works": [work(sources=[
        {"url": "https://example.org/x", "date": "2026-09-01", "claim": "excavation began"}])]})
    assert not unsourced.work("a-work").sourced and sourced.work("a-work").sourced


def test_a_recheck_is_overdue_after_92_days_except_for_finished_works():
    register = Register.model_validate({"version": 1, "works": [
        work(id="building", last_checked="2026-06-01"),
        work(id="done", treatment_status="treated", last_checked="2026-01-01"),
    ], "controls": [
        {"id": "screened-area", "name": "S", "screening": "screened",
         "last_screened": "2026-06-01"},
        {"id": "new-area", "name": "N", "screening": "unscreened"},
    ]})
    assert overdue(register, dt.date(2026, 9, 1)) == []          # exactly 92 days
    late = overdue(register, dt.date(2026, 9, 2))
    assert len(late) == 2 and late[0].startswith("work building")
    assert "first traffic-diversion advisory or excavation report" in late[1]
