"""The donor count at which the audit's placebo rank holds its nominal size.

    .venv/bin/python scripts/dev/donor_floor.py [--replicates N] [--processes N] [--quick]

19 usable donors is the fewest at which a placebo p can reach 0.05: with n placebos the
smallest attainable p is 1/(n+1). That is where a p-value exists, not where it can be
trusted. docs/audit_power.md section 4 read the standardised rank excluding zero on 10%
of no-effect panels at 20 donors, from 50 panels. This sweeps the number of usable
donors and measures, with the full audit, the published rule's false-positive rate on
panels with no effect and its power at 0.20 and 0.30 BTI, for two placebo designs:

  current          each placebo is fitted on the other donors: one corridor fewer than
                   the treated fit, which had every donor
  treated in pool  the treated corridor joins every placebo's pool (Abadie's in-space
                   placebos), so every run fits on as many corridors

Panels are panel_model's at 30-minute peaks, the only cadence TomTom's free allowance
fits, with every corridor's failure parameter at 1% so that every declared donor stays
usable, 14-day blocks, 12 pre blocks and a 28-day post period. Two Tier A (15-minute)
cells check whether the answer depends on cadence.

The floor for each design is the fewest donors from which, at every larger count
swept, the false-positive rate is not significantly above 5%: its Wilson 95% interval
reaches 5%.

Writes docs/donor_floor.md and .fixtures/donor_floor.csv; --report-only re-renders the
doc from that file.
"""

import argparse
import math
import subprocess
import sys
import time
import zlib
from dataclasses import replace
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
from scripts.dev.panel_model import audit_inputs, inject_bti_effect, scheduled_panel  # noqa: E402

ALPHA, POWER = 0.05, 0.80
DONORS = (19, 20, 23, 26, 29, 35, 40, 50)
CROSS_CHECK = (("A", 20), ("A", 40))
DELTAS = (0.0, 0.20, 0.30)
VARIANTS = {"current": False, "treated in pool": True}
MISS = 0.01
TREATED = "c00"
EFFECTIVE = pd.Timestamp("2026-07-01")
INTERVENTIONS = pd.DataFrame({
    "id": ["works"], "corridor_id": [TREATED],
    "effective_at": [(EFFECTIVE + pd.Timedelta(hours=1)).tz_localize(LOCAL_TZ).isoformat()],
})
OUT = ROOT / "docs" / "donor_floor.md"
RECORDS = ROOT / ".fixtures" / "donor_floor.csv"


def run_panel(task: tuple) -> list[dict]:
    tier, donors, replicate = task
    params = Params()
    span = periods(EFFECTIVE, params)
    days = (span["post_end"] - span["pre_start"]).days + 1
    rng = np.random.default_rng(zlib.crc32(f"donor-floor|{tier}|{donors}|{replicate}".encode()))
    samples = scheduled_panel(donors + 1, span["pre_start"], days, tier, rng,
                              profiles={i: {"miss": MISS} for i in range(donors + 1)})
    calls, cells, corridors = audit_inputs(samples, tier, params)
    peak = calls[pooled.is_peak(calls["requested_at"], params)]
    frames = {d: peak if d == 0 else inject_bti_effect(peak, TREATED, span["post_start"],
                                                       span["post_end"], d, params)[0]
              for d in DELTAS}
    rows = []
    for variant, includes in VARIANTS.items():
        # audit_min_donors=0: this measures the rank below any floor, to find one
        variant_params = replace(params, audit_placebo_includes_treated=includes,
                                 audit_min_donors=0)
        for delta, frame in frames.items():
            tables = intervention_audits(frame, cells, corridors, INTERVENTIONS, variant_params,
                                         sensitivity=False)
            a = tables["intervention_audit"].iloc[0]
            ran = a.status == "ok"
            rows.append({
                "tier": tier, "donors": donors, "replicate": replicate, "variant": variant,
                "delta": delta, "status": a.status, "n_donors": a.n_donors,
                "n_placebos": a.n_placebos, "p": a.placebo_p_value if ran else np.nan,
                "effect": a.effect if ran else np.nan,
                "extreme": bool(ran and a.placebo_extreme and (delta == 0 or a.effect > 0)),
            })
    return rows


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return math.nan, math.nan
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denominator = 1 + z * z / n
    return (centre - half) / denominator, (centre + half) / denominator


def floor_for(sizes: dict[int, tuple[float, float, float]]) -> str:
    """Fewest donors from which every larger count's interval reaches ALPHA."""
    found = None
    for donors in sorted(sizes, reverse=True):
        if sizes[donors][1] > ALPHA:
            break
        found = donors
    if found is None:
        return f"above {max(sizes)}"
    return str(found)


def findings(frame: pd.DataFrame, floors: dict[str, str],
             sizes: dict[str, dict[int, tuple[float, float, float]]]) -> list[str]:
    """What the sweep settles, in words, from the same records as the tables."""
    first_p = round(1 / ALPHA) - 1
    lines = ["## What it found", ""]
    if all(f == str(first_p) for f in floors.values()):
        lines.append(f"- The rank held its nominal size at every count swept, from {first_p} "
                     "donors up, under both placebo designs. The fewest donors at which a p "
                     "of 0.05 exists is also, in this model, where the rule holds its size, "
                     f"so the floor is {first_p}.")
    else:
        lines.append("- Floors: " + "; ".join(f"{v}, {f} donors" for v, f in floors.items())
                     + ".")
    a, b = sizes["current"], sizes["treated in pool"]
    apart = [n for n in a if not (b[n][1] <= a[n][0] <= b[n][2] and a[n][1] <= b[n][0] <= a[n][2])]
    lines.append("- Putting the treated corridor in every placebo pool moved no count's size "
                 "outside the other design's interval (both designs ran on the same panels)."
                 if not apart else f"- The two placebo designs differ at {apart} donors.")
    tier_a = frame[(frame["tier"] == "A") & (frame["donors"] == 20)
                   & (frame["variant"] == "current") & (frame["delta"] == 0)
                   & (frame["status"] == "ok")]
    low, high = wilson(5, 50)
    if len(tier_a):
        lines.append(f"- docs/audit_power.md section 4 read a size of 10% at 20 Tier A donors: "
                     f"5 of 50 panels, whose Wilson 95% interval runs {low:.1%} to {high:.1%}. "
                     f"Tier A at 20 donors here, every donor usable, reads "
                     f"{tier_a['extreme'].mean():.1%} on {len(tier_a)} panels.")
    return lines + [""]


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(r) + " |" for r in rows])


def sha() -> str:
    found = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
    return found.stdout.strip() or "unknown"


def report(frame: pd.DataFrame, minutes: float | None) -> str:
    replicates = int(frame["replicate"].max()) + 1
    lines = [
        "# The donor floor: where the placebo rank holds its size", "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/dev/donor_floor.py` at "
        f"{sha()} (plus uncommitted changes), {replicates} panels per cell at 30-minute peaks, "
        + (f"{minutes:.0f} min." if minutes is not None else "rendered from the saved records."),
        "",
        "19 usable donors is where a placebo p first can reach 0.05, since with n placebos "
        "the smallest p is 1/(n+1). This asks where the rank rule's false-positive rate is "
        "actually at its nominal 5%. Every audit is the full `metrics.audit` run on "
        "panel_model panels with no effect (size) or a known BTI effect injected into the "
        f"treated corridor's post period (power), failure parameter {MISS:.0%} so that every "
        "declared donor is usable, 14-day blocks, 12 pre blocks, 28-day post period.", "",
        "- `size`: share of no-effect audits reading extreme, with its Wilson 95% interval. "
        "`by rank alone`: floor(0.05 x (n + 1)) / (n + 1), what an exactly exchangeable "
        "placebo rank would give.",
        "- `floor`: the fewest donors from which, at every larger count swept, the "
        "interval reaches 5%. A count whose interval sits wholly above 5% has a size "
        "distinguishably above nominal.", "",
    ]
    intro, floors, sections, all_sizes = len(lines), {}, [], {}
    for variant in VARIANTS:
        sizes, rows = {}, []
        for donors in DONORS:
            g = frame[(frame["tier"] == "B") & (frame["donors"] == donors)
                      & (frame["variant"] == variant)]
            if g.empty:
                continue
            null = g[g["delta"] == 0]
            ran = null[null["status"] == "ok"]
            k = int(ran["extreme"].sum())
            low, high = wilson(k, len(ran))
            sizes[donors] = (k / len(ran) if len(ran) else math.nan, low, high)
            n = donors
            exact = math.floor(ALPHA * (n + 1)) / (n + 1)
            power = {d: g[g["delta"] == d]["extreme"].mean() for d in DELTAS[1:]}
            rows.append([str(donors), str(len(null)), f"{1 - len(ran) / len(null):.0%}",
                         f"{ran['n_placebos'].mean():.1f}",
                         f"{sizes[donors][0]:.1%} ({low:.1%} to {high:.1%})", f"{exact:.1%}",
                         *[f"{power[d]:.2f}" for d in DELTAS[1:]]])
        floors[variant], all_sizes[variant] = floor_for(sizes), sizes
        sections += [f"## Placebos: {variant}", "", f"Floor: **{floors[variant]} donors**.", "",
                  *table(["donors", "panels", "withheld", "placebos", "size (95% interval)",
                          "by rank alone", *[f"power {d:.2f}" for d in DELTAS[1:]]], rows), ""]
    lines += sections
    cross = []
    for tier, donors in CROSS_CHECK:
        for variant in VARIANTS:
            g = frame[(frame["tier"] == tier) & (frame["donors"] == donors)
                      & (frame["variant"] == variant) & (frame["delta"] == 0)]
            ran = g[g["status"] == "ok"]
            if ran.empty:
                continue
            k = int(ran["extreme"].sum())
            low, high = wilson(k, len(ran))
            cross.append([tier, str(donors), variant, str(len(ran)),
                          f"{k / len(ran):.1%} ({low:.1%} to {high:.1%})"])
    if cross:
        lines += ["## Cross-check at 15-minute peaks (Tier A)", "",
                  *table(["tier", "donors", "placebos", "panels", "size (95% interval)"], cross),
                  ""]
    lines += ["## Limits", "",
              "- The panels are panel_model's. Its noise sizes are assumptions, and size depends "
              "on how alike the treated corridor and its donors are; real corridors differ more "
              "than these.",
              "- Every donor here is usable. On a real panel failures exclude some, and the "
              "floor applies to the donors that remain.", ""]
    lines[intro:intro] = findings(frame, floors, all_sizes)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=800)
    parser.add_argument("--processes", type=int, default=9)
    parser.add_argument("--quick", action="store_true", help="3 replicates, not written")
    parser.add_argument("--report-only", action="store_true",
                        help="re-render docs/donor_floor.md from the saved records")
    args = parser.parse_args()
    if args.report_only:
        text = report(pd.read_csv(RECORDS), None)
        OUT.write_text(text + "\n")
        print(text)
        return 0
    replicates = 3 if args.quick else args.replicates
    donors = (19, 26) if args.quick else DONORS
    tasks = [("B", n, r) for n in donors for r in range(replicates)]
    tasks += [(tier, n, r) for tier, n in CROSS_CHECK for r in range(max(1, replicates // 2))]
    started = time.time()
    with Pool(args.processes) as pool:
        records = [row for batch in pool.imap_unordered(run_panel, tasks, chunksize=4)
                   for row in batch]
    frame = pd.DataFrame(records)
    text = report(frame, (time.time() - started) / 60)
    print(text)
    if not args.quick:
        RECORDS.parent.mkdir(exist_ok=True)
        frame.to_csv(RECORDS, index=False)
        OUT.write_text(text + "\n")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
