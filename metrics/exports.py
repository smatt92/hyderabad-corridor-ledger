"""The open dataset: every published corridor-hour, with the declared corridor.

Pure: frames in, bytes and manifest rows out. metrics.io uploads them. The
manifest's sha256 lets anyone confirm a downloaded file is the one published.
"""

import gzip
import hashlib
import io

import pandas as pd

CORRIDOR_COLUMNS = [
    "corridor_id", "code", "name", "pair_id", "role", "origin_name", "origin_lat", "origin_lon",
    "destination_name", "dest_lat", "dest_lon",
]
PREFIX = "hyderabad-corridor-ledger"
OBJECTS = {"csv": f"{PREFIX}/metrics_hourly.csv.gz", "parquet": f"{PREFIX}/metrics_hourly.parquet"}


def open_dataset(
    metrics_daily: pd.DataFrame, corridors: pd.DataFrame, stats: pd.DataFrame
) -> pd.DataFrame:
    """metrics_daily rows with corridor identity and the measured length_meters."""
    identity = corridors.reindex(columns=CORRIDOR_COLUMNS)
    lengths = stats[["corridor_id", "length_meters"]]
    out = metrics_daily.merge(identity, on="corridor_id", how="left").merge(
        lengths, on="corridor_id", how="left"
    )
    leading = CORRIDOR_COLUMNS[:5] + ["day", "hour"]
    rest = [c for c in out.columns if c not in leading]
    return out[leading + rest].sort_values(["corridor_id", "day", "hour"], ignore_index=True)


def csv_gz(frame: pd.DataFrame) -> bytes:
    text = frame.to_csv(index=False, date_format="%Y-%m-%d")
    return gzip.compress(text.encode(), mtime=0)  # mtime 0: same data, same bytes


def parquet(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def manifest_row(fmt: str, payload: bytes, frame: pd.DataFrame, dataset: pd.DataFrame,
                 method_version: str) -> dict:
    window = dataset.iloc[0]
    return {
        "format": fmt,
        "object_path": OBJECTS[fmt],
        "window_start": window["window_start"],
        "window_end": window["window_end"],
        "n_rows": len(frame),
        "n_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "missing_rate": window["missing_rate"],
        "method_version": method_version,
    }
