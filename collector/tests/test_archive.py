import gzip
import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest

from archive import SCHEMAS, cutoff, from_parquet, object_path, take_block, to_parquet
from chain import GENESIS, breaks, row_hash

pytest.importorskip("pyarrow")

T0 = datetime(2026, 6, 1, 2, 30, tzinfo=UTC)


def sample_rows(n, start_seq=1, prev=GENESIS):
    rows = []
    for i in range(n):
        raw = gzip.compress(b'{"routes": [{"summary": {}}]}', mtime=0)
        at = T0 + timedelta(minutes=15 * i)
        row = {"seq": start_seq + i, "corridor_id": "c", "scheduled_slot": at,
               "requested_at": at + timedelta(seconds=3), "attempts": 1, "http_status": 200,
               "length_m": 9800, "travel_time_s": 900 + i, "traffic_delay_s": None,
               "no_traffic_travel_time_s": 800, "historic_travel_time_s": None, "raw_gz": raw,
               "raw_gz_sha256": hashlib.sha256(raw).digest(), "collector_run": "1.1",
               "collector_sha": None, "inserted_at": at + timedelta(seconds=4, microseconds=123456),
               "prev_hash": prev}
        row["row_hash"] = prev = row_hash("samples", row)
        rows.append(row)
    return rows


def as_postgrest(row):
    """The shape the REST API returns: bytea as \\x hex, timestamps as ISO text."""
    out = {}
    for key, value in row.items():
        if isinstance(value, bytes):
            out[key] = "\\x" + value.hex()
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def test_parquet_round_trip_keeps_the_chain_verifiable():
    rows = sample_rows(5)
    back = from_parquet(to_parquet("samples", [as_postgrest(r) for r in rows]))
    assert breaks("samples", back) == []
    assert [r["raw_gz"] for r in back] == [r["raw_gz"] for r in rows]
    assert [name for name, _ in SCHEMAS["samples"]] == list(back[0])


def test_a_tampered_archive_is_caught():
    back = from_parquet(to_parquet("samples", sample_rows(5)))
    back[2]["travel_time_s"] = 600
    assert breaks("samples", back)[0] == (3, "row_hash does not match row contents")


def test_a_later_archive_links_to_the_previous_one():
    first = sample_rows(3)
    second = sample_rows(3, start_seq=4, prev=first[-1]["row_hash"])
    assert breaks("samples", second, before=first[-1]["row_hash"]) == []
    assert breaks("samples", second, before=GENESIS)[0][1].startswith("prev_hash does not link")


def test_unknown_columns_stop_the_archive():
    row = {**sample_rows(1)[0], "new_column": 1}
    with pytest.raises(RuntimeError, match="new_column"):
        to_parquet("samples", [row])


def test_blocks_stop_at_the_hot_window_and_never_take_the_chain_head():
    rows = sample_rows(10)
    before = rows[6]["requested_at"]
    assert [r["seq"] for r in take_block(rows, newest_seq=10, before=before)] == [1, 2, 3, 4, 5, 6]
    assert [r["seq"] for r in take_block(rows, newest_seq=4, before=before)] == [1, 2, 3]
    assert len(take_block(rows, newest_seq=10, before=before, limit=2)) == 2


def test_cutoff_is_a_utc_midnight_at_least_90_days_back():
    now = datetime(2026, 12, 15, 5, 0, tzinfo=UTC)
    assert cutoff(now) == datetime(2026, 9, 16, tzinfo=UTC)
    assert now - cutoff(now) >= timedelta(days=90)


def test_object_paths_satisfy_the_manifest_check():
    for table in SCHEMAS:
        assert re.fullmatch(r"[a-z0-9][a-z0-9._/-]{1,200}", object_path(table, 1, 20000))
