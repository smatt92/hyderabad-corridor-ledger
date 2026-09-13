"""Stored raw responses to a samples frame.

Travel times are read from the gzipped response body, never from the parsed
columns in public.samples: raw is the source of truth.
"""

import gzip
import json
import zlib

import numpy as np
import pandas as pd

SOURCE_COLUMNS = ["seq", "corridor_id", "requested_at", "http_status", "raw_gz"]


def decompress_raw(raw_gz: bytes) -> dict | None:
    """Decompress and parse one stored response. None if it is not gzipped JSON."""
    try:
        return json.loads(gzip.decompress(raw_gz))
    except (OSError, EOFError, ValueError, zlib.error):
        return None


def _summary(doc: dict | None) -> dict | None:
    try:
        return doc["routes"][0]["summary"]
    except (KeyError, IndexError, TypeError):
        return None


def combine_sources(*frames: pd.DataFrame) -> pd.DataFrame:
    """Union of source rows (archive files, hot table), one row per seq.

    The archive and the hot table overlap. An overlapping seq must carry
    identical bytes; anything else means the record was altered, so raise.
    """
    rows = pd.concat([f[SOURCE_COLUMNS] for f in frames], ignore_index=True)
    dupes = rows[rows.duplicated("seq", keep=False)]
    conflicting = dupes.groupby("seq")["raw_gz"].nunique()
    conflicting = conflicting[conflicting > 1]
    if not conflicting.empty:
        raise ValueError(f"seq values with differing raw bytes: {list(conflicting.index[:10])}")
    return rows.drop_duplicates("seq").sort_values("seq").reset_index(drop=True)


def missing_seqs(rows: pd.DataFrame) -> list[int]:
    """seq values between 1 and the highest seq that no source supplied.

    The chain starts at seq 1 and has no gaps, so any hole means raw history
    is absent (usually an archive that was not passed in). Metrics computed
    over a hole would silently rewrite history, so callers refuse to run.
    """
    if rows.empty:
        return []
    present = rows["seq"].to_numpy(dtype="int64")
    return np.setdiff1d(np.arange(1, present.max() + 1), present).tolist()


def parse_samples(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per call: ok is True only for HTTP 200 with a usable travel time.

    Failed calls stay in the frame with ok = False. They are the numerator of
    the missingness rate, so they are never dropped here.
    """
    summaries = rows["raw_gz"].map(decompress_raw).map(_summary)

    def field(name: str) -> pd.Series:
        values = summaries.map(lambda s: s.get(name) if isinstance(s, dict) else None)
        return pd.to_numeric(values, errors="coerce").astype("float64")

    status = pd.to_numeric(rows["http_status"], errors="coerce")
    travel = field("travelTimeInSeconds")
    no_traffic = field("noTrafficTravelTimeInSeconds")
    travel = travel.where(travel > 0)
    no_traffic = no_traffic.where(no_traffic > 0)
    ok = (status == 200) & travel.notna()

    out = pd.DataFrame(
        {
            "seq": rows["seq"].astype("int64"),
            "corridor_id": rows["corridor_id"].astype(str),
            "requested_at": pd.to_datetime(rows["requested_at"], utc=True),
            "http_status": status.astype("Int64"),
            "ok": ok.astype(bool),
            "travel_time_s": travel.where(ok),
            "no_traffic_travel_time_s": no_traffic.where(ok),
            "length_m": field("lengthInMeters").where(ok),
        }
    )
    return out.sort_values(["corridor_id", "requested_at", "seq"]).reset_index(drop=True)
