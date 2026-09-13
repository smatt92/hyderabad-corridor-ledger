"""Local preview data: synthetic samples run through the real metrics pipeline.

Writes one JSON file per read-model table to .fixtures/tables/, which the read
API loads when LEDGER_FIXTURE_DIR is set. Every corridor name starts with
"Demo —" and the API marks every response sample: true, so the frontend shows
its sample-data banner. None of it can reach a deployment: .fixtures/ is
gitignored and excluded from Vercel, and the API refuses fixture data when
VERCEL is set.

The generator follows the P-03 design's sample model: a morning and evening
peak, a weekly cycle, corridor-specific volatility, failures that cluster at
peaks, four interventions, and a few declared lengths absent from the payload.

    .venv/bin/python scripts/dev/build_fixtures.py
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from metrics.io import to_records  # noqa: E402
from metrics.pipeline import compute_all  # noqa: E402

OUT = ROOT / ".fixtures" / "tables"
LAST_DAY = pd.Timestamp("2026-09-12")
DAYS = 120
CADENCE_S = 1800
RNG = np.random.default_rng(20260913)

PLACES = {
    "Hitec City": (17.447, 78.377), "Gachibowli": (17.440, 78.348), "Madhapur": (17.448, 78.391),
    "Kondapur": (17.464, 78.357), "Nanakramguda": (17.420, 78.340), "Manikonda": (17.402, 78.385),
    "Jubilee Hills": (17.431, 78.407), "Banjara Hills": (17.412, 78.437),
    "Panjagutta": (17.427, 78.450), "Ameerpet": (17.437, 78.448), "SR Nagar": (17.443, 78.442),
    "Erragadda": (17.457, 78.435), "Moosapet": (17.466, 78.424), "Kukatpally": (17.485, 78.411),
    "Miyapur": (17.497, 78.360), "Balanagar": (17.474, 78.442), "Bowenpally": (17.478, 78.474),
    "Begumpet": (17.444, 78.470), "Secunderabad": (17.437, 78.501), "Tarnaka": (17.427, 78.529),
    "Habsiguda": (17.406, 78.545), "Uppal": (17.398, 78.559), "Nagole": (17.371, 78.559),
    "LB Nagar": (17.348, 78.552), "Dilsukhnagar": (17.368, 78.524), "Malakpet": (17.376, 78.503),
    "Koti": (17.386, 78.477), "Abids": (17.390, 78.474), "Mehdipatnam": (17.396, 78.437),
    "Masab Tank": (17.402, 78.447), "Lakdikapul": (17.401, 78.461), "Khairatabad": (17.412, 78.462),
    "Narsingi": (17.392, 78.340), "Gandipet": (17.386, 78.320), "Patancheru": (17.531, 78.264),
    "BHEL": (17.494, 78.318), "Alwal": (17.504, 78.503), "Tolichowki": (17.400, 78.409),
}
PAIRS = [
    ("Miyapur", "Hitec City"), ("Kukatpally", "Madhapur"), ("Gachibowli", "Ameerpet"),
    ("Nanakramguda", "Panjagutta"), ("Manikonda", "Mehdipatnam"), ("Narsingi", "Gachibowli"),
    ("Gandipet", "Mehdipatnam"), ("Patancheru", "BHEL"), ("BHEL", "Hitec City"),
    ("Madhapur", "Jubilee Hills"), ("Kondapur", "Panjagutta"), ("Hitec City", "Begumpet"),
    ("Jubilee Hills", "Khairatabad"), ("Banjara Hills", "Lakdikapul"),
    ("Panjagutta", "Secunderabad"), ("Ameerpet", "Koti"), ("SR Nagar", "Erragadda"),
    ("Erragadda", "Balanagar"), ("Moosapet", "Bowenpally"), ("Balanagar", "Secunderabad"),
    ("Bowenpally", "Alwal"), ("Begumpet", "Secunderabad"), ("Secunderabad", "Uppal"),
    ("Tarnaka", "Habsiguda"), ("Habsiguda", "Nagole"), ("Uppal", "LB Nagar"),
    ("Nagole", "Dilsukhnagar"), ("LB Nagar", "Malakpet"), ("Dilsukhnagar", "Koti"),
    ("Malakpet", "Abids"),
]
# Per pair: (length_meters, free_flow_seconds) for the primary and, where the pair
# declares one, its alternate. None: the payload carries no length.
PAYLOAD = [
    [(9800, 1100), (10600, 1190)], [(11200, 1260)], [(13500, 1520), (14400, 1620)],
    [(14100, 1590)], [(7300, 820), (7900, 890)], [(8200, 920)], [(12600, 1420), (None, 1510)],
    [(8700, 980)], [(9400, 1060), (10100, 1140)], [(5200, 590)], [(12900, 1450), (13700, 1540)],
    [(11800, 1330)], [(6400, 720), (6900, 780)], [(5100, 570)], [(6900, 780), (7400, 830)],
    [(7200, 810)], [(2800, 320), (None, 340)], [(3600, 400)], [(6100, 690), (6600, 740)],
    [(8600, 970)], [(5300, 600), (5700, 640)], [(4200, 470)], [(9700, 1090), (10400, 1170)],
    [(3100, 350)], [(5600, 630), (6000, 680)], [(6300, 710)], [(4700, 530), (None, 560)],
    [(6600, 740)], [(5900, 660), (6300, 710)], [(2600, 290)],
]
INTERVENTIONS = [(0, 22, "Signal retiming, 6 junctions", 0.93), (4, 36, "Flyover opened", 0.86),
                 (10, 50, "Bus-lane enforcement", 0.96), (16, 64, "Left-turn free flow", 0.90)]
DOW_FACTOR = [0.86, 1.00, 1.05, 1.05, 1.03, 1.13, 0.72]  # Monday first (pandas dayofweek)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def hour_factor(h: np.ndarray) -> np.ndarray:
    def bump(mean, sd, amp):
        return amp * np.exp(-((h - mean) ** 2) / (2 * sd * sd))

    f = 1 + bump(9.4, 1.35, 0.62) + bump(18.9, 1.8, 0.86) + bump(13, 2.4, 0.14)
    return np.where(h < 6, f * (0.9 - 0.02 * (6 - h)), f)


def declared_corridors() -> pd.DataFrame:
    rows = []
    for pi, ((origin, dest), payload) in enumerate(zip(PAIRS, PAYLOAD, strict=True)):
        pair_id = f"PR-{pi + 1:02d}"
        for role, (length, free) in zip(("primary", "alternate"), payload, strict=False):
            code = f"HC-{len(rows) + 1:02d}"
            suffix = " · alternate" if role == "alternate" else ""
            rows.append({
                "id": slug(f"{code} {origin} {dest}{' alt' if suffix else ''}"), "code": code,
                "name": f"Demo — {origin} → {dest}{suffix}", "pair_id": pair_id, "role": role,
                "origin_name": origin, "destination_name": dest,
                "origin_lat": PLACES[origin][0], "origin_lon": PLACES[origin][1],
                "dest_lat": PLACES[dest][0], "dest_lon": PLACES[dest][1],
                "cadence_s": CADENCE_S, "active": True, "osm_path": None,
                "length": length, "free_s": free,
            })
    return pd.DataFrame(rows)


def synthetic_samples(corridors: pd.DataFrame) -> pd.DataFrame:
    first = LAST_DAY - pd.Timedelta(days=DAYS - 1)
    last_slot = LAST_DAY + pd.Timedelta(hours=23, minutes=30)
    slots = pd.date_range(first.tz_localize("Asia/Kolkata"), last_slot.tz_localize("Asia/Kolkata"),
                          freq=f"{CADENCE_S}s")
    local_hour = slots.hour + slots.minute / 60
    day_index = ((slots.normalize() - slots[0].normalize()).days).to_numpy()
    dow = DOW_FACTOR_ARRAY[slots.dayofweek]
    treated = {iv[0]: iv for iv in INTERVENTIONS}
    primaries = corridors.index[corridors["role"] == "primary"].tolist()
    parts, base_by_pair = [], {}
    for i, c in corridors.iterrows():
        base = base_by_pair.get(c["pair_id"])
        base = 1.12 + RNG.random() * 1.25 if base is None else base * (0.93 + RNG.random() * 0.15)
        base_by_pair.setdefault(c["pair_id"], base)
        volatility = 0.05 + RNG.random() * 0.16
        spread = 1.22 + RNG.random() * 0.62
        miss = 0.16 + RNG.random() * 0.22 if RNG.random() < 0.18 else RNG.random() * 0.12
        tti = base * hour_factor(local_hour) * dow
        tti *= 1 + RNG.normal(0, volatility, len(slots)) * (0.4 + (hour_factor(local_hour) - 1))
        tail = RNG.random(len(slots)) < 0.08
        tti = np.where(tail, tti * spread, tti)
        pk = primaries.index(i) if i in primaries else None
        if pk in treated:
            _, start_day, _, effect = treated[pk]
            ramp = np.clip((day_index - (DAYS - 90 + start_day)) / 9, 0, 1)
            tti = 1 + (tti - 1) * (1 + (effect - 1) * ramp)
        tti = np.clip(tti, 1.0, 4.3)
        peakiness = (hour_factor(local_hour) - 1) / 0.9
        fail = RNG.random(len(slots)) < miss * (0.5 + peakiness)
        dark_days = RNG.random(DAYS) < miss / 6  # whole days lost
        fail |= dark_days[day_index]
        parts.append(pd.DataFrame({
            "corridor_id": c["id"], "requested_at": slots.tz_convert("UTC"),
            "http_status": np.where(fail, 429, 200), "ok": ~fail,
            "travel_time_s": np.where(fail, np.nan, c["free_s"] * tti),
            "no_traffic_travel_time_s": np.where(
                fail, np.nan, c["free_s"] * (1 + RNG.normal(0, 0.015, len(slots)))),
            "length_m": np.nan if pd.isna(c["length"]) or fail.all() else float(c["length"]),
        }))
        parts[-1].loc[parts[-1]["http_status"] != 200, "length_m"] = np.nan
    samples = pd.concat(parts, ignore_index=True)
    samples["seq"] = np.arange(1, len(samples) + 1)
    samples["http_status"] = samples["http_status"].astype("Int64")
    return samples


DOW_FACTOR_ARRAY = np.array(DOW_FACTOR)


def main() -> None:
    corridors = declared_corridors()
    samples = synthetic_samples(corridors)
    primaries = corridors[corridors["role"] == "primary"].reset_index(drop=True)
    first = LAST_DAY - pd.Timedelta(days=89)
    interventions = pd.DataFrame([
        {"id": slug(label), "corridor_id": primaries.loc[k, "id"],
         "effective_at": (first + pd.Timedelta(days=day)).tz_localize("Asia/Kolkata").isoformat(),
         "description": label}
        for k, day, label, _ in INTERVENTIONS
    ])
    print(f"{len(corridors)} corridors, {len(samples):,} samples; computing metrics...")
    tables = compute_all(samples, corridors.rename(columns={"id": "corridor_id"}), interventions)

    OUT.mkdir(parents=True, exist_ok=True)
    computed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    declared = corridors.drop(columns=["length", "free_s"])
    tables_out = {name: to_records(frame) for name, frame in tables.items()}
    tables_out["corridors"] = json.loads(declared.to_json(orient="records"))
    tables_out["interventions"] = json.loads(interventions.to_json(orient="records"))
    tables_out["chain_verifications"] = [{
        "id": 1, "verified_at": computed_at, "ok": True, "rows_checked": len(samples),
        "first_seq": 1, "head_seq": len(samples), "head_row_hash": "0" * 64, "breaks": 0,
        "first_break_seq": None,
    }]
    for name, rows in tables_out.items():
        for row in rows:
            row.setdefault("computed_at", computed_at)
        (OUT / f"{name}.json").write_text(json.dumps(rows))
        print(f"  {name}: {len(rows):,} rows")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
