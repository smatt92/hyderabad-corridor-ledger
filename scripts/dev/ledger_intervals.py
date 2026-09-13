"""Calibration of the ledger's intervals: coverage, spread and size.

    .venv/bin/python scripts/dev/ledger_intervals.py [--replicates N] [--processes N] [--quick]

The ledger publishes a call-level percentile bootstrap interval beside each pooled
peak-hour p95 travel time, BTI and PTI (corridor_stats, 90-day read window), each
hour's p95 and BTI in the 24-hour profile (120-day profile window), and the p95
advantage of a pair's primary over its alternate per hour
(pair_advantage_hourly). Resampling calls treats every call in a window as
independent. Traffic is not: a city-wide shock moves every corridor on the same
day and each corridor drifts from week to week, so calls from one day or one week
move together. The intervention audit's interval, built the same way, failed when
that drift was large.

Each replicate simulates one 120-day panel of three corridors with fixed profiles
(scripts/dev/panel_model.py): c00 and c01 identical, a pair whose true advantage
is zero, and c02 more congested. It computes every interval with the pipeline's
resampling over the pipeline's windows (the call-level bootstrap with the keys the
pipeline used before 0009 withdrew these intervals), and compares it with the true value:
the same statistic of the stationary process, from one panel of TRUTH_DAYS days.
Scenarios:
  independent calls    no shared shock, no drift: checks the harness itself
  default correlation  panel_model's daily shock (sd 0.10) and weekly drift (0.08)
  weekly drift 0.20    the drift at which the audit interval failed

Coverage: share of intervals containing the true value (nominal 0.95).
SE/SD: the interval's implied standard error, (high - low) / 3.92, averaged over
replicates, over the standard deviation of the point value across replicates.
Size (pair advantage only): share of intervals excluding zero when the pair's two
corridors are identical (nominal 0.05); the route comparison counts a lead only
where the interval excludes zero.

Writes docs/ledger_intervals.md and .fixtures/ledger_intervals.csv.
"""

import argparse
import subprocess
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
from metrics.cells import local_day_hour  # noqa: E402
from metrics.params import Params  # noqa: E402
from scripts.dev.panel_model import scheduled_panel  # noqa: E402

FIRST_DAY = pd.Timestamp("2026-01-01")
PAIR = {"base": 1.6, "volatility": 0.12, "spread": 1.5, "miss": 0.06, "free": 800.0}
PROFILES = {0: PAIR, 1: PAIR,
            2: {"base": 2.2, "volatility": 0.20, "spread": 1.8, "miss": 0.10, "free": 1200.0}}
SCENARIOS = {
    "independent calls": {"shared_day_sd": 0.0, "corridor_week_sd": 0.0},
    "default correlation": {"shared_day_sd": 0.10, "corridor_week_sd": 0.08},
    "weekly drift 0.20": {"shared_day_sd": 0.10, "corridor_week_sd": 0.20},
}
TIERS = ("A", "B")
HOURS = (9, 18)
TRUTH_DAYS = 4800
Z = 1.959964
KEYS = ["scenario", "tier", "statistic", "corridor", "hour"]
OUT = ROOT / "docs" / "ledger_intervals.md"
RECORDS = ROOT / ".fixtures" / "ledger_intervals.csv"


def panel(scenario: str, tier: str, days: int, seed_key: str) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(seed_key.encode()))
    samples = scheduled_panel(3, FIRST_DAY, days, tier, rng, profiles=PROFILES,
                              **SCENARIOS[scenario])
    ok = samples[samples["ok"]]
    return ok.join(local_day_hour(ok["requested_at"]))


def record(statistic, corridor, hour, value, low, high, n) -> dict:
    return {"statistic": statistic, "corridor": corridor, "hour": -1 if hour is None else hour,
            "value": value, "ci_low": low, "ci_high": high, "n": n}


def travel_intervals(values, params: Params, key) -> dict:
    """pooled.travel with the percentile intervals the ledger published before 0009."""
    v = pooled.clean(values)
    out = pooled.travel(v, params) | dict.fromkeys(
        ("p95_ci_low", "p95_ci_high", "bti_ci_low", "bti_ci_high"), np.nan)
    if len(v) >= params.p95_min_samples:
        p95_draws, bti_draws = pooled.draws(v, [pooled.p95_rows, pooled.bti_rows], params, key)
        out["p95_ci_low"], out["p95_ci_high"] = pooled.interval(p95_draws, params)
        out["bti_ci_low"], out["bti_ci_high"] = pooled.interval(bti_draws, params)
    return out


def free_flow_p5(calls: pd.DataFrame, params: Params) -> float:
    start, end = params.ff_p5_night_hours
    night = calls.loc[calls["hour"].between(start, end - 1), "travel_time_s"].to_numpy(float)
    return float(np.quantile(night, 0.05)) if len(night) >= params.ff_p5_min_samples else np.nan


def intervals(ok: pd.DataFrame, params: Params) -> list[dict]:
    """Every published ledger interval for a panel, on the pipeline's windows."""
    end = ok["day"].max()
    read = ok[ok["day"] > end - pd.Timedelta(days=params.read_window_days)]
    profile = ok[ok["day"] > end - pd.Timedelta(days=params.profile_window_days)]
    recent = ok[ok["day"] > end - pd.Timedelta(days=params.ff_p5_window_days)]
    out = []
    peak = read[pooled.is_peak(read["requested_at"], params)]
    for cid, group in peak.groupby("corridor_id"):
        s = travel_intervals(group["travel_time_s"], params, ("ledger", cid))
        out.append(record("ledger p95 travel time", cid, None, s["p95"], s["p95_ci_low"],
                          s["p95_ci_high"], s["n"]))
        out.append(record("ledger BTI", cid, None, s["bti"], s["bti_ci_low"],
                          s["bti_ci_high"], s["n"]))
        # corridor_stats divides the p95 and its interval by each free-flow reference
        references = {"tomtom": float(read.loc[read["corridor_id"] == cid,
                                               "no_traffic_travel_time_s"].median()),
                      "p5": free_flow_p5(recent[recent["corridor_id"] == cid], params)}
        for basis, reference in references.items():
            out.append(record(f"ledger PTI ({basis})", cid, None,
                              s["p95"] / reference, s["p95_ci_low"] / reference,
                              s["p95_ci_high"] / reference, s["n"]))
    for hour in HOURS:
        calls = {cid: g["travel_time_s"].to_numpy(float)
                 for cid, g in profile[profile["hour"] == hour].groupby("corridor_id")}
        for cid, values in calls.items():
            s = travel_intervals(values, params, ("profile", cid, hour))
            out.append(record("profile p95 travel time", cid, hour, s["p95"], s["p95_ci_low"],
                              s["p95_ci_high"], s["n"]))
            out.append(record("profile BTI", cid, hour, s["bti"], s["bti_ci_low"],
                              s["bti_ci_high"], s["n"]))
        a, b = calls.get("c00", np.empty(0)), calls.get("c01", np.empty(0))
        advantage, low, high = pooled.difference(a, b, pooled.p95_rows, params,
                                                 ("pair", "c00-c01", hour))
        out.append(record("pair p95 advantage", "c00-c01", hour, advantage, low, high,
                          min(len(a), len(b))))
    return out


def truths(ok: pd.DataFrame, params: Params) -> list[dict]:
    """The same statistics of the stationary process, from one long panel."""
    peak = ok[pooled.is_peak(ok["requested_at"], params)]
    out = []

    def bti(v):
        return (np.quantile(v, 0.95) - v.mean()) / v.mean()

    for cid, group in peak.groupby("corridor_id"):
        v = group["travel_time_s"].to_numpy(float)
        p95 = float(np.quantile(v, 0.95))
        mine = ok[ok["corridor_id"] == cid]
        references = {"tomtom": float(mine["no_traffic_travel_time_s"].median()),
                      "p5": free_flow_p5(mine, params)}
        out += [record("ledger p95 travel time", cid, None, p95, None, None, len(v)),
                record("ledger BTI", cid, None, float(bti(v)), None, None, len(v))]
        out += [record(f"ledger PTI ({b})", cid, None, p95 / r, None, None, len(v))
                for b, r in references.items()]
    for hour in HOURS:
        at = ok[ok["hour"] == hour]
        for cid, group in at.groupby("corridor_id"):
            v = group["travel_time_s"].to_numpy(float)
            out += [record("profile p95 travel time", cid, hour, float(np.quantile(v, 0.95)),
                           None, None, len(v)),
                    record("profile BTI", cid, hour, float(bti(v)), None, None, len(v))]
        out.append(record("pair p95 advantage", "c00-c01", hour, 0.0, None, None, 0))
    return out


def run_replicate(task: tuple) -> list[dict]:
    scenario, tier, replicate = task
    params = Params()
    ok = panel(scenario, tier, params.profile_window_days, f"{scenario}|{tier}|{replicate}")
    return [r | {"scenario": scenario, "tier": tier, "replicate": replicate}
            for r in intervals(ok, params)]


def run_truth(task: tuple) -> list[dict]:
    scenario, tier, days = task
    ok = panel(scenario, tier, days, f"truth|{scenario}|{tier}")
    return [r | {"scenario": scenario, "tier": tier} for r in truths(ok, Params())]


def summarise(records: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    frame = records.merge(truth[KEYS + ["value"]].rename(columns={"value": "truth"}), on=KEYS)
    rows = []
    for key, g in frame.groupby(KEYS, sort=False):
        g = g[g["ci_low"].notna() & g["ci_high"].notna() & g["value"].notna()]
        if len(g) < 3:
            continue
        truth_value = g["truth"].iloc[0]
        implied = (g["ci_high"] - g["ci_low"]) / (2 * Z)
        rows.append(dict(zip(KEYS, key, strict=True)) | {
            "replicates": len(g), "calls": g["n"].mean(),
            "coverage": ((g["ci_low"] <= truth_value) & (g["ci_high"] >= truth_value)).mean(),
            "se_over_sd": implied.mean() / g["value"].std(ddof=1),
            "excludes_zero": ((g["ci_low"] > 0) | (g["ci_high"] < 0)).mean(),
            "bias_pct": 100 * (g["value"].mean() - truth_value) / truth_value
            if truth_value else np.nan,
            "width": (g["ci_high"] - g["ci_low"]).median(),
        })
    order = {name: i for i, name in enumerate(SCENARIOS)}
    return (pd.DataFrame(rows).assign(_order=lambda f: f["scenario"].map(order))
            .sort_values(["_order", "tier", "statistic", "corridor", "hour"], kind="stable")
            .drop(columns="_order").reset_index(drop=True))


def cell(value, digits=2) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.{digits}f}"


def report(summary: pd.DataFrame, replicates: int, minutes: float) -> str:
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "unknown"
    lines = [
        "# Ledger intervals: calibration",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/dev/ledger_intervals.py` "
        f"at {sha} (plus uncommitted changes), {replicates} simulated panels per scenario and "
        f"tier, truth from one {TRUTH_DAYS}-day panel each, {minutes:.0f} min.",
        "",
        __doc__.split("Coverage:")[0].split("\n\n", 1)[1].strip(),
        "",
        "Coverage is nominal at 0.95; SE/SD is 1 when the interval reports the spread the "
        "value actually has, below 1 when it is too narrow. Size (pair rows, `excludes zero`) "
        "is nominal at 0.05.",
        "",
        "## Pooled by scenario",
        "",
        "| scenario | tier | statistic | coverage mean | coverage worst | SE/SD mean | "
        "SE/SD worst | excludes zero (pair) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for (scenario, tier, statistic), g in summary.groupby(["scenario", "tier", "statistic"],
                                                          sort=False):
        pair = statistic.startswith("pair")
        lines.append(f"| {scenario} | {tier} | {statistic} | {cell(g['coverage'].mean())} | "
                     f"{cell(g['coverage'].min())} | {cell(g['se_over_sd'].mean())} | "
                     f"{cell(g['se_over_sd'].min())} | "
                     f"{cell(g['excludes_zero'].mean()) if pair else '—'} |")
    lines += ["", "## Every interval", "",
              "| scenario | tier | statistic | corridor | hour | panels | calls | coverage | "
              "SE/SD | excludes zero | bias % | median width |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in summary.itertuples(index=False):
        lines.append(f"| {r.scenario} | {r.tier} | {r.statistic} | {r.corridor} | "
                     f"{'peak' if r.hour < 0 else r.hour} | {r.replicates} | {r.calls:.0f} | "
                     f"{cell(r.coverage)} | {cell(r.se_over_sd)} | "
                     f"{cell(r.excludes_zero) if r.statistic.startswith('pair') else '—'} | "
                     f"{cell(r.bias_pct, 1)} | {cell(r.width, 3)} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--processes", type=int, default=9)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    replicates = 3 if args.quick else args.replicates
    truth_days = 600 if args.quick else TRUTH_DAYS
    started = time.time()
    with Pool(args.processes) as pool:
        truth = pd.DataFrame([r for batch in pool.imap_unordered(
            run_truth, [(s, t, truth_days) for s in SCENARIOS for t in TIERS]) for r in batch])
        tasks = [(s, t, i) for s in SCENARIOS for t in TIERS for i in range(replicates)]
        records = pd.DataFrame([r for batch in pool.imap_unordered(run_replicate, tasks,
                                                                   chunksize=4) for r in batch])
    summary = summarise(records, truth)
    text = report(summary, replicates, (time.time() - started) / 60)
    print(text)
    if not args.quick:
        RECORDS.parent.mkdir(exist_ok=True)
        records.to_csv(RECORDS, index=False)
        OUT.write_text(text)
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
