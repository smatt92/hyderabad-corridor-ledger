"""How often the standardised placebo rank leaves a placebo unranked.

    .venv/bin/python scripts/dev/unranked_placebos.py [--replicates N] [--processes N]

A placebo is unranked when its leave-one-block-out pre-period error is at or below
metrics.audit.MIN_HELD_OUT: every pre block is predicted exactly by weights fitted on the
other blocks, so its effect has no scale. An audit whose ranked placebos fall below the
donor floor is withheld as too_few_placebos.

This is not the exact in-sample fit that docs/methodology.md measured when comparing
weightings (pre RMSPE below 1e-6, the treated corridor's own fit): an exact in-sample fit
does not imply a zero held-out error. Both are counted here, on the same panels. Earlier
records in .fixtures/audit_power_*.csv show placebo counts below donor counts that came from
the RMSPE-ratio rank, which could not rank a placebo with a thin post block; the current
rank does not use post RMSPE.

Panels are panel_model's at 30-minute peaks, failure parameter 1%, 20 declared donors,
demeaned weights, 14-day blocks, 28-day post period, no effect. Writes
docs/unranked_placebos.md.
"""

import argparse
import math
import sys
import time
import zlib
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from metrics import pooled  # noqa: E402
from metrics.audit import intervention_audits, periods  # noqa: E402
from metrics.params import LOCAL_TZ, Params  # noqa: E402
from scripts.dev.panel_model import audit_inputs, scheduled_panel  # noqa: E402

PRE_BLOCKS = (6, 12)
DONORS, MISS, TIER = 20, 0.01, "B"
TREATED = "c00"
EFFECTIVE = pd.Timestamp("2026-07-01")
INTERVENTIONS = pd.DataFrame({
    "id": ["works"], "corridor_id": [TREATED],
    "effective_at": [(EFFECTIVE + pd.Timedelta(hours=1)).tz_localize(LOCAL_TZ).isoformat()],
})
OUT = ROOT / "docs" / "unranked_placebos.md"


def run_panel(task: tuple) -> dict:
    pre_blocks, replicate = task
    # audit_min_donors=0: count unranked placebos without withholding on them
    params = Params(audit_pre_blocks=pre_blocks, audit_min_donors=0)
    span = periods(EFFECTIVE, params)
    days = (span["post_end"] - span["pre_start"]).days + 1
    rng = np.random.default_rng(zlib.crc32(f"unranked|{pre_blocks}|{replicate}".encode()))
    samples = scheduled_panel(DONORS + 1, span["pre_start"], days, TIER, rng,
                              profiles={i: {"miss": MISS} for i in range(DONORS + 1)})
    calls, cells, corridors = audit_inputs(samples, TIER, params)
    peak = calls[pooled.is_peak(calls["requested_at"], params)]
    tables = intervention_audits(peak, cells, corridors, INTERVENTIONS, params,
                                 sensitivity=False)
    a = tables["intervention_audit"].iloc[0]
    placebos = tables["audit_placebos"]
    ran = a.status == "ok"
    return {"pre_blocks": pre_blocks, "replicate": replicate, "status": a.status,
            "n_donors": a.n_donors, "placebo_runs": len(placebos),
            "unranked": int(placebos["std_effect"].isna().sum()) if ran else 0,
            "exact_in_sample": bool(ran and a.pre_rmspe < 1e-6)}


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - half) / (1 + z * z / n)), (centre + half) / (1 + z * z / n)


def share(k: int, n: int) -> str:
    low, high = wilson(k, n)
    return f"{k} of {n} ({k / n:.1%}; {low:.1%} to {high:.1%})"


def report(frame: pd.DataFrame, minutes: float) -> str:
    replicates = int(frame["replicate"].max()) + 1
    rows = []
    for blocks, g in frame.groupby("pre_blocks"):
        ran = g[g["status"] == "ok"]
        rows.append(f"| {blocks} | {len(g)} | {len(ran)} | "
                    f"{share(int((ran['unranked'] > 0).sum()), len(ran))} | "
                    f"{int(ran['unranked'].sum())} of {int(ran['placebo_runs'].sum())} | "
                    f"{share(int(ran['exact_in_sample'].sum()), len(ran))} |")
    return "\n".join([
        "# Unranked placebos", "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/dev/unranked_placebos.py`, "
        f"{replicates} panels per pre-block count, {minutes:.0f} min. panel_model panels at "
        f"30-minute peaks, failure parameter {MISS:.0%}, {DONORS} declared donors, demeaned "
        "weights, 14-day blocks, 28-day post period, no effect.", "",
        "A placebo is unranked when its leave-one-block-out pre-period error is zero: every "
        "pre block is predicted exactly by weights fitted on the others, so its effect has no "
        "scale. An audit left with fewer ranked placebos than the donor floor is withheld as "
        "`too_few_placebos`. The last column is a different condition, the treated corridor's "
        "exact in-sample fit, which docs/methodology.md measured when comparing weightings; "
        "it does not imply the first.", "",
        "| pre blocks | panels | audits run | audits with an unranked placebo (95% interval) | "
        "unranked of placebo runs | treated fit exact in sample (95% interval) |",
        "|---|---|---|---|---|---|", *rows, "",
        "- Every panel here has near-complete data; a real panel loses donors to failures, "
        "which leaves fewer placebo runs but does not by itself unrank one.",
        "- panel_model's corridors are more alike than real ones. Re-measure on real data.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=800)
    parser.add_argument("--processes", type=int, default=9)
    args = parser.parse_args()
    tasks = [(blocks, r) for blocks in PRE_BLOCKS for r in range(args.replicates)]
    started = time.time()
    with Pool(args.processes) as pool:
        frame = pd.DataFrame(list(pool.imap_unordered(run_panel, tasks, chunksize=4)))
    text = report(frame, (time.time() - started) / 60)
    OUT.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
