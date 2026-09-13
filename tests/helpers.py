"""Fixture builders. Expected values in tests are computed by hand, not by the
code under test."""

import gzip
import json

import numpy as np
import pandas as pd

LOCAL_TZ = "Asia/Kolkata"


def local(wall_time: str) -> pd.Timestamp:
    """Asia/Kolkata wall-clock time as a UTC timestamp."""
    return pd.Timestamp(wall_time, tz=LOCAL_TZ).tz_convert("UTC")


def raw_body(travel=None, no_traffic=None, length=5000) -> bytes:
    summary = {"lengthInMeters": length}
    if travel is not None:
        summary["travelTimeInSeconds"] = travel
    if no_traffic is not None:
        summary["noTrafficTravelTimeInSeconds"] = no_traffic
    return gzip.compress(json.dumps({"routes": [{"summary": summary}]}).encode())


def parsed(rows) -> pd.DataFrame:
    """Parsed samples from (corridor_id, local wall time, http_status, travel_s, no_traffic_s)."""
    records = []
    for seq, (corridor_id, wall_time, status, travel, no_traffic) in enumerate(rows, start=1):
        ok = status == 200 and travel is not None
        records.append(
            {
                "seq": seq,
                "corridor_id": corridor_id,
                "requested_at": local(wall_time),
                "http_status": status,
                "ok": ok,
                "travel_time_s": float(travel) if ok else np.nan,
                "no_traffic_travel_time_s": (
                    float(no_traffic) if ok and no_traffic is not None else np.nan
                ),
                "length_m": 5000.0 if ok else np.nan,
            }
        )
    return pd.DataFrame(records)
