"""Anchoring the chain heads, and checking anchors against a walked chain. Rows are
the chain vectors hashed by the database in test_chain.py."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_chain import S1, S2

import anchor
from anchor import anchor_name, anchor_problems, encode, heads_document
from chain import row_hash

NOW = datetime(2026, 9, 14, 21, 30, tzinfo=UTC)


def walk(table, head_seq, head_hash, minutes_ago=5):
    return {"table_name": table, "verified_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "rows_checked": head_seq or 0, "first_seq": 1 if head_seq else None,
            "head_seq": head_seq, "head_row_hash": head_hash, "breaks": 0,
            "first_break_seq": None, "first_break_problem": None, "ok": True}


def hex_of(row):
    return row["row_hash"].removeprefix("\\x")


def document(samples_seq, samples_hash):
    return heads_document([walk("samples", samples_seq, samples_hash),
                           walk("failed_samples", None, None)], NOW)


def test_the_signed_document_is_the_latest_walk_of_each_chain():
    older = walk("samples", 1, hex_of(S1), minutes_ago=60)
    newer = walk("samples", 2, hex_of(S2), minutes_ago=5)
    doc = heads_document([older, newer, walk("failed_samples", None, None)], NOW)
    assert [c["table_name"] for c in doc["chains"]] == ["failed_samples", "samples"]
    assert doc["chains"][1]["head_seq"] == 2
    assert encode(doc) == encode(json.loads(encode(doc)))  # canonical, byte for byte
    assert anchor_name(doc) == "heads/20260914T212500Z.json"


def test_no_anchor_without_tonights_walk_of_both_chains():
    with pytest.raises(RuntimeError, match="no recorded walk of failed_samples"):
        heads_document([walk("samples", 1, hex_of(S1))], NOW)
    with pytest.raises(RuntimeError, match="older than"):
        heads_document([walk("samples", 1, hex_of(S1), minutes_ago=180),
                        walk("failed_samples", None, None)], NOW)


def test_a_chain_that_extends_every_anchor_passes():
    anchors = [("heads/1.json", document(None, None)),       # anchored while empty
               ("heads/2.json", document(1, hex_of(S1))),
               ("heads/3.json", document(2, hex_of(S2)))]
    assert anchor_problems(anchors, {"samples": [S1, S2], "failed_samples": []}) == []


def test_a_rewrite_after_anchoring_is_caught():
    edited = {**S1, "travel_time_s": 700}
    problems = anchor_problems([("heads/2.json", document(1, hex_of(S1)))],
                               {"samples": [edited, S2], "failed_samples": []})
    assert any("row_hash does not match row contents" in p for p in problems)
    # rehashing the edited row to hide it breaks the link to the next row instead,
    # and still differs from the anchored hash
    rehashed = {**edited, "row_hash": "\\x" + row_hash("samples", edited).hex()}
    problems = anchor_problems([("heads/2.json", document(1, hex_of(S1)))],
                               {"samples": [rehashed, S2], "failed_samples": []})
    assert any("does not link" in p for p in problems)
    assert any("heads/2.json: samples seq 1 now hashes to" in p for p in problems)


def test_a_chain_cut_back_below_an_anchor_is_caught():
    problems = anchor_problems([("heads/3.json", document(2, hex_of(S2)))],
                               {"samples": [S1], "failed_samples": []})
    assert problems == ["heads/3.json: samples was anchored at seq 2, but the chain now "
                        "ends at seq 1"]


class FakeStorage(anchor.Storage):
    def __init__(self, rows):
        self.objects, self.rows = {}, rows

    def read(self, path):
        return self.objects.get(path)

    def write(self, path, payload, content_type, replace):
        if path in self.objects and not replace:
            raise RuntimeError(f"{path} exists")
        self.objects[path] = payload

    def chain(self, table):
        return self.rows[table]


def test_publish_then_check_verifies_signatures_and_the_chain():
    storage = FakeStorage({"samples": [S1, S2], "failed_samples": []})
    name = anchor.publish(storage, encode(document(2, hex_of(S2))), b'{"bundle": 1}')
    assert json.loads(storage.objects["heads/index.json"]) == [
        {"heads": name, "bundle": name.removesuffix(".json") + ".sigstore.json"}]
    with pytest.raises(RuntimeError, match="exists"):  # an anchor is never overwritten
        anchor.publish(storage, encode(document(2, hex_of(S2))), b'{"bundle": 1}')

    problems, n, _ = anchor.check(storage, verify=lambda heads, bundle: None)
    assert (problems, n) == ([], 1)
    problems, n, _ = anchor.check(storage, verify=lambda heads, bundle: "not daily.yml on main")
    assert n == 0 and problems == [f"{name}: signature does not verify: not daily.yml on main"]
