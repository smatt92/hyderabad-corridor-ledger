import gzip

import numpy as np
import pandas as pd
import pytest

from metrics.raw import combine_sources, decompress_raw, missing_seqs, parse_samples
from tests.helpers import raw_body


def test_decompress_raw_round_trip_and_garbage():
    assert decompress_raw(raw_body(600, 500))["routes"][0]["summary"]["travelTimeInSeconds"] == 600
    assert decompress_raw(b"not gzip at all") is None
    assert decompress_raw(gzip.compress(b"<html>429</html>")) is None


def source(seq, status, body, corridor="a", at="2026-09-01T02:30:00Z"):
    return {"seq": seq, "corridor_id": corridor, "requested_at": at, "http_status": status,
            "raw_gz": body}


def test_parse_samples_keeps_failures_and_reads_travel_time_from_raw():
    rows = pd.DataFrame([
        source(1, 200, raw_body(600, 500)),
        source(2, 429, gzip.compress(b'{"error": "rate limited"}')),
        source(3, 200, raw_body(None, 500)),   # 200 with no travel time
        source(4, 200, raw_body(0, 500)),      # non-positive travel time
        source(5, None, gzip.compress(b"timeout")),
    ])
    out = parse_samples(rows).set_index("seq")

    assert len(out) == 5  # failures are never dropped
    assert out["ok"].tolist() == [True, False, False, False, False]
    assert out.loc[1, "travel_time_s"] == 600
    assert out.loc[1, "no_traffic_travel_time_s"] == 500
    assert np.isnan(out.loc[2, "travel_time_s"])
    assert out.loc[1, "requested_at"] == pd.Timestamp("2026-09-01T02:30:00Z")


def test_combine_sources_dedupes_overlap_and_rejects_altered_bytes():
    archive = pd.DataFrame([source(1, 200, raw_body(600, 500)), source(2, 200, raw_body(700, 500))])
    hot = pd.DataFrame([source(2, 200, raw_body(700, 500)), source(3, 200, raw_body(800, 500))])
    assert combine_sources(archive, hot)["seq"].tolist() == [1, 2, 3]

    altered = pd.DataFrame([source(2, 200, raw_body(999, 500))])
    with pytest.raises(ValueError, match="differing raw bytes"):
        combine_sources(archive, altered)


def test_missing_seqs_finds_holes_in_the_record():
    rows = pd.DataFrame({"seq": [1, 2, 5, 6]})
    assert missing_seqs(rows) == [3, 4]
    assert missing_seqs(pd.DataFrame({"seq": [3, 4]})) == [1, 2]  # archive not supplied
    assert missing_seqs(pd.DataFrame({"seq": pd.Series(dtype="int64")})) == []
