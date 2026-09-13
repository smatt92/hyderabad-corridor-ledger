import gzip
import hashlib
import io

import numpy as np
import pandas as pd

from metrics.exports import OBJECTS, csv_gz, manifest_row, open_dataset, parquet

METRICS = pd.DataFrame({
    "corridor_id": ["b", "a", "a"], "day": pd.to_datetime(["2026-09-01"] * 3), "hour": [8, 9, 8],
    "tti_tomtom": [1.2, 1.5, np.nan], "missing_rate": [0.0, 0.25, 1.0],
})
CORRIDORS = pd.DataFrame({
    "corridor_id": ["a", "b"], "code": ["HC-01", "HC-02"], "name": ["A", "B"],
    "pair_id": ["PR-01", "PR-01"], "role": ["primary", "alternate"], "origin_name": "Miyapur",
    "origin_lat": 17.497, "origin_lon": 78.36, "destination_name": "Hitec City",
    "dest_lat": 17.447, "dest_lon": 78.377, "cadence_s": 900,
})
STATS = pd.DataFrame({"corridor_id": ["a", "b"], "length_meters": pd.array([9800, None], "Int64")})
DATASET = pd.DataFrame([{"window_start": pd.Timestamp("2026-06-04"),
                         "window_end": pd.Timestamp("2026-09-01"), "missing_rate": 0.1}])


def test_open_dataset_joins_identity_and_measured_length_in_stable_order():
    out = open_dataset(METRICS, CORRIDORS, STATS)
    leading = ["corridor_id", "code", "name", "pair_id", "role", "day", "hour"]
    assert list(out.columns[:7]) == leading
    assert "cadence_s" not in out.columns
    order = list(zip(out["corridor_id"], out["hour"], strict=True))
    assert order == [("a", 8), ("a", 9), ("b", 8)]
    assert out["length_meters"].tolist()[:2] == [9800, 9800]
    assert pd.isna(out["length_meters"].iloc[2])  # absent stays absent
    assert np.isnan(out["tti_tomtom"].iloc[0])     # missing stays missing


def test_exports_are_reproducible_and_round_trip():
    frame = open_dataset(METRICS, CORRIDORS, STATS)
    assert csv_gz(frame) == csv_gz(frame)
    back = pd.read_csv(io.BytesIO(gzip.decompress(csv_gz(frame))))
    assert back["day"].tolist() == ["2026-09-01"] * 3
    assert len(pd.read_parquet(io.BytesIO(parquet(frame)))) == 3


def test_manifest_checksum_matches_payload():
    frame = open_dataset(METRICS, CORRIDORS, STATS)
    payload = csv_gz(frame)
    row = manifest_row("csv", payload, frame, DATASET, "p02.2")
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (row["object_path"], row["n_rows"], row["n_bytes"]) == (OBJECTS["csv"], 3, len(payload))
