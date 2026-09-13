"""The Python port against rows hashed by the database itself.

The vectors were produced by applying 0003_collector.sql to the linked
project inside a transaction that was rolled back: real trigger output, as
PostgREST returns it (bytea as \\x hex, timestamps as ISO text).
"""

from chain import GENESIS, as_bytes, breaks, canonical, row_hash

S1 = {"seq": 1, "corridor_id": "t-core", "requested_at": "2026-06-05T10:18:02+00:00",
      "http_status": 200, "length_m": 9800, "travel_time_s": 901, "traffic_delay_s": None,
      "no_traffic_travel_time_s": None, "historic_travel_time_s": None,
      "raw_gz": "\\x1f8b0800000000000003",
      "raw_gz_sha256": "\\x9d1011ce9a9221ec2cbde2cc63ce50401fda24a6ffbf96a97b55552cc9e035e3",
      "collector_run": None, "collector_sha": None,
      "inserted_at": "2026-09-13T10:03:02.185651+00:00",
      "prev_hash": "\\x" + "00" * 32,
      "row_hash": "\\x3d796ba5ca3c1f6a4a241fcd8e1229e7cf3a755d0ff21ea1ac2aaf920e465699",
      "scheduled_slot": "2026-06-05T10:18:00+00:00", "attempts": 1}
S2 = {**S1, "seq": 2, "requested_at": "2026-06-05T10:33:02+00:00", "travel_time_s": 902,
      "inserted_at": "2026-09-13T10:03:02.197221+00:00", "prev_hash": S1["row_hash"],
      "row_hash": "\\x0a8e3d9757230ac5611ffc276d77dfccdab39252bb3943207cbb7dea34b95301",
      "scheduled_slot": "2026-06-05T10:33:00+00:00"}
F1 = {"seq": 1, "corridor_id": "t-core", "scheduled_slot": "2026-06-05T12:33:00+00:00",
      "requested_at": "2026-06-05T12:33:00+00:00", "attempts": 3, "error_class": "rate_limited",
      "http_status": 429, "detail_gz": "\\x1f8b0800000000000003",
      "detail_gz_sha256": "\\x9d1011ce9a9221ec2cbde2cc63ce50401fda24a6ffbf96a97b55552cc9e035e3",
      "collector_run": "123.1", "collector_sha": None,
      "inserted_at": "2026-09-13T10:03:02.201524+00:00", "prev_hash": "\\x" + "00" * 32,
      "row_hash": "\\xda5c61db95cb549cea86cd6c684628febcab73d83916cb5319a521f3d2d93253"}
F2 = {"seq": 2, "corridor_id": "t-core", "scheduled_slot": "2026-06-05T12:48:00+00:00",
      "requested_at": "2026-06-05T12:48:00+00:00", "attempts": 3, "error_class": "timeout",
      "http_status": None, "detail_gz": None, "detail_gz_sha256": None, "collector_run": None,
      "collector_sha": None, "inserted_at": "2026-09-13T10:03:02.204664+00:00",
      "prev_hash": F1["row_hash"],
      "row_hash": "\\xef91de0d1d40b75f14eac57d79674cc75ce15a01183f9ab680d11ec1b7766392"}


def test_canonical_text_matches_format_v1():
    assert canonical("samples", S1) == (
        "v1|1|t-core|2026-06-05T10:18:02.000000Z|200|9800|901||||"
        "9d1011ce9a9221ec2cbde2cc63ce50401fda24a6ffbf96a97b55552cc9e035e3|||"
        "2026-09-13T10:03:02.185651Z"
    )


def test_python_hashes_match_the_database():
    for table, row in (("samples", S1), ("samples", S2),
                       ("failed_samples", F1), ("failed_samples", F2)):
        assert row_hash(table, row) == as_bytes(row["row_hash"]), (table, row["seq"])


def test_intact_chains_have_no_breaks():
    assert breaks("samples", [S1, S2]) == []
    assert breaks("failed_samples", [F1, F2]) == []
    assert breaks("samples", [S2], before=as_bytes(S1["row_hash"])) == []


def test_an_edited_row_is_the_first_break():
    edited = {**S2, "travel_time_s": 700}
    assert breaks("samples", [S1, edited]) == [(2, "row_hash does not match row contents")]


def test_a_swapped_payload_breaks_its_digest():
    swapped = {**F1, "detail_gz": "\\x1f8b0800000000000004"}
    assert breaks("failed_samples", [swapped])[0] == (
        1, "detail_gz_sha256 does not match detail_gz")


def test_a_removed_row_breaks_the_seq_and_the_link():
    renumbered = {**F2, "seq": 3}
    assert breaks("failed_samples", [F1, renumbered]) == [
        (3, "row_hash does not match row contents"), (3, "seq gap before this row")]
    assert breaks("samples", [S2], before=GENESIS) == [
        (2, "prev_hash does not link to the previous row")]
