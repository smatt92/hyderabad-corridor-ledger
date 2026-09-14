"""Anchoring the chain heads, and checking anchors against a walked chain. Rows are
the chain vectors hashed by the database in test_chain.py."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_chain import S1, S2

import anchor
from anchor import anchor_name, anchor_problems, encode, heads_document
from chain import row_hash
from store import DatabaseError

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

    def read_stored(self, path):
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


NOT_FOUND = '{"statusCode":"404","error":"not_found","message":"Object not found"}'


class CachedStorageApi:
    """The storage API as the project URL serves it. A write lands at once. The public URL
    keeps serving the first version of an object it cached. The authenticated read of a
    replaced object returns the previous version `lag` more times before the new one."""

    def __init__(self, lag=0):
        self.objects, self.previous, self.cached = {}, {}, {}
        self.lag, self.stale, self.requests = lag, 0, []

    def raw(self, method, path, data=None, headers=None):
        self.requests.append((method, path))
        name = path.split(f"/{anchor.BUCKET}/", 1)[1]
        if method == "POST":
            if name in self.objects:
                self.previous[name], self.stale = self.objects[name], self.lag
            self.objects[name] = data
            return {}, b'{"Key": "archive"}'
        if "/public/" in path:
            if name not in self.cached and name in self.objects:
                self.cached[name] = self.objects[name]
            body = self.cached.get(name)
        elif self.stale and name in self.previous:
            self.stale -= 1
            body = self.previous[name]
        else:
            body = self.objects.get(name)
        if body is None:
            raise DatabaseError(f"GET {path}: HTTP 400: {NOT_FOUND}")
        return {}, body


def storage_over(api):
    sleeps = []
    return anchor.Storage(api, sleep=sleeps.append), sleeps


def test_a_replaced_object_that_reads_back_stale_is_confirmed_from_storage_itself():
    api = CachedStorageApi(lag=1)
    storage, sleeps = storage_over(api)
    storage.write(anchor.INDEX, b"[1]", "application/json", replace=True)
    assert storage.read(anchor.INDEX) == b"[1]"                # the public copy is now cached
    storage.write(anchor.INDEX, b"[1, 2]", "application/json", replace=True)
    assert sleeps == [anchor.READ_BACK_WAITS[0]]               # one stale read, then the bytes
    assert storage.read(anchor.INDEX) == b"[1]"                # the public URL is still stale,
    assert sum("/public/" in p for _, p in api.requests) == 2  # and write never read it


def test_bytes_that_never_match_still_fail_the_write_loudly():
    api = CachedStorageApi(lag=99)
    storage, sleeps = storage_over(api)
    storage.write(anchor.INDEX, b"[1]", "application/json", replace=True)
    with pytest.raises(RuntimeError, match="did not read back as written: wrote 6 bytes, "
                                           "storage still held 3 different bytes"):
        storage.write(anchor.INDEX, b"[1, 2]", "application/json", replace=True)
    assert sleeps == list(anchor.READ_BACK_WAITS)


def test_a_write_storage_never_holds_fails_and_an_auth_refusal_is_never_read_as_absent():
    class Dropping(CachedStorageApi):
        def raw(self, method, path, data=None, headers=None):
            if method == "POST":
                return {}, b"{}"
            return super().raw(method, path, data, headers)

    storage, _ = storage_over(Dropping())
    with pytest.raises(RuntimeError, match="storage still held no object"):
        storage.write("heads/x.json", b"{}", "application/json", replace=False)

    class Unauthorised(CachedStorageApi):
        def raw(self, method, path, data=None, headers=None):
            raise DatabaseError(f"GET {path}: HTTP 400: headers must have required property "
                                "'authorization'")

    storage, _ = storage_over(Unauthorised())
    with pytest.raises(DatabaseError, match="authorization"):
        storage.read_stored(anchor.INDEX)


def test_publish_appends_to_the_index_storage_holds_not_a_stale_public_copy():
    api = CachedStorageApi()
    storage, _ = storage_over(api)
    first = [{"heads": "heads/a.json", "bundle": "heads/a.sigstore.json"}]
    both = [*first, {"heads": "heads/b.json", "bundle": "heads/b.sigstore.json"}]
    api.objects[anchor.INDEX] = json.dumps(first).encode()
    assert storage.read(anchor.INDEX)                      # the CDN caches the first index
    api.objects[anchor.INDEX] = json.dumps(both).encode()  # the second anchor's index lands
    name = anchor.publish(storage, encode(document(2, hex_of(S2))), b'{"bundle": 1}')
    assert [e["heads"] for e in json.loads(api.objects[anchor.INDEX])] == [
        "heads/a.json", "heads/b.json", name]
