"""Validity, power and minimum detectable effect of the intervention audit.

    .venv/bin/python scripts/dev/audit_power.py [--part design|bootstrap|preblocks|freetier|all]
        [--replicates N] [--processes N] [--quick] [--report-only]

Panels come from scripts/dev/panel_model.py. The treated corridor c00 is drawn
from the same model as its donors, so it is exchangeable with them, and under no
effect its rank among the placebos is uniform by construction. An effect of
known size delta is injected into c00's pooled post-period BTI
(inject_bti_effect). That moves the headline estimate by exactly delta and
leaves every placebo run untouched, so each panel's placebos run once and only
the treated estimate is recomputed per delta.

Design sweep, no bootstrap: tier, block length, pre blocks, donors, post length,
and three weightings (demeaned, sparse = at most 5 active donors, levels).
Detection rules:
  ratio     treated post/pre RMSPE ratio ranked among placebos (the published p)
  cv ratio  the same with the leave-one-block-out pre RMSPE in the denominator
  |effect|  treated |effect| ranked among placebo |effects|
  cs        the block confidence sequence at the last post block excludes zero
  oracle    (z 0.975 + z 0.80) x sd of the null effect across panels: the effect a
            test that knew the estimator's true spread would detect 80% of the time
Pre-block sweep: how many 14-day pre blocks an effect of 0.10 or 0.20 BTI needs
at 20 and 40 donors, with demeaned and levels weights and a 28-day post period.
Bootstrap sweep: call-level resampling against whole units of 7 and 14 days,
compared on interval width, bootstrap standard error against the true spread of
the estimate, false-positive rate and power.
Free-tier sweep: panels sized to TomTom's published free allowance of 20,000
routing calls a month, at 15, 20 and 30-minute peak cadence, with the call
budget each design spends and the share of audits withheld or unable to reach
p 0.05, and power counted over every declared audit, withheld ones included.

A rule is valid where its false-positive rate at delta 0 is at most about 0.05.
MDE = smallest delta from which every larger delta is detected, with the right
sign, in at least 80% of the panels the audit did not withhold.

The noise sizes in panel_model are assumptions, not Hyderabad estimates.
Re-estimate once real data covers a full audit. Writes docs/audit_power.md and
the per-panel records to .fixtures/.
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
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from metrics import pooled, schedule  # noqa: E402
from metrics.audit import (  # noqa: E402
    Audit,
    Calls,
    intervention_audits,
    periods,
    pooled_bti,
    rmspe,
    rmspe_ratio,
)
from metrics.params import LOCAL_TZ, Params  # noqa: E402
from scripts.dev.panel_model import audit_inputs, inject_bti_effect, scheduled_panel  # noqa: E402

EFFECTIVE = pd.Timestamp("2026-07-01")
TREATED = "c00"
ALPHA, POWER, EXACT_FIT = 0.05, 0.80, 1e-6
Z = 1.959964 + 0.841621
RESAMPLES = 200
DESIGN_DELTAS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.45)
BOOTSTRAP_DELTAS = (0.0, 0.05, 0.10, 0.20, 0.30)
PREBLOCK_DELTAS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
PREBLOCKS = (6, 9, 12, 15, 18, 24, 30)
CONFIGS = {"demeaned": {"audit_weights": "demeaned"},
           "sparse5": {"audit_weights": "demeaned", "audit_max_donors": 5},
           "levels": {"audit_weights": "levels"}}
PREBLOCK_CONFIGS = {k: CONFIGS[k] for k in ("demeaned", "levels")}
# Whole-week and whole-block resampling ("blocks7", "blocks14") and the block confidence
# sequence were evaluated at commit f8f2be8 and removed from metrics.audit: they did not
# hold size. Their rows stay in the saved records and in docs/audit_power.md.
BOOTSTRAPS = {
    "calls": {"audit_weights": "demeaned"},
    "calls-levels": {"audit_weights": "levels"},
}
RULES = {"ratio": "ratio", "cv_ratio": "cv ratio", "abs_effect": "|effect|",
         "std_effect": "std |effect|", "cs": "cs"}
RANKS = ("ratio", "cv_ratio", "abs_effect", "std_effect")
# the most congested, most volatile corridor panel_model can draw
STRESS = {"base": 2.37, "volatility": 0.21, "spread": 1.84}
DRIFT_WEEK_SD = 0.20  # 2.5 times panel_model's default corridor weekly drift
STRESS_VARIANTS = {"demeaned": {"audit_weights": "demeaned"}}
SCENARIO = ["tier", "block_days", "pre_blocks", "donors", "post_blocks"]
INTERVENTIONS = pd.DataFrame({
    "id": ["works"], "corridor_id": [TREATED],
    "effective_at": [(EFFECTIVE + pd.Timedelta(hours=1)).tz_localize(LOCAL_TZ).isoformat()],
})
# Free-tier designs (section 6): (peak cadence in minutes, corridor ids). Four ids are the
# treated Miyapur-Allwyn package, so an audit of one declares ids - 4 donors: the other
# three are treated, and a treated corridor's own alternate is among them.
FREE_TIER_DESIGNS = ((30, 34), (30, 30), (20, 24), (15, 20))
TREATED_IDS = 4
MONTHLY_ALLOWANCE, LONGEST_MONTH = 20_000, 31
FREE_TIER_DELTAS = (0.0, 0.10, 0.15, 0.20, 0.30, 0.45)
# The same designs with every corridor's call failure rate fixed low, because a 30-minute
# block has 16% slack on the floor and the model's failure rates are an assumption.
LOW_MISS = 0.03
CADENCE_TIER = {15: "A", 20: "M20", 30: "B"}
# metrics.schedule has no 20-minute cadence; the sweep adds one to its own processes only.
schedule.CADENCE_MINUTES.setdefault("M20", 20)
OUT = ROOT / "docs" / "audit_power.md"
RECORDS = {part: ROOT / ".fixtures" / f"audit_power_{part}.csv"
           for part in ("design", "bootstrap", "preblocks", "stress", "drift", "freetier",
                        "freetier_lowfail")}


def design_grid(quick: bool) -> list[tuple]:
    if quick:
        return [("A", 14, 6, 20, 2), ("A", 14, 12, 20, 2)]
    grid = [(tier, 14, pre, donors, post) for tier in ("A", "B") for pre in (6, 12, 18)
            for donors in (10, 20, 40) for post in (2, 4)]
    # the same collection windows cut into 7-day blocks: Tier A only, since Tier B's
    # peak slots cannot reach the 200-call floor in a week
    grid += [("A", 7, pre, donors, post) for pre in (12, 24) for donors in (20, 40)
             for post in (4, 8)]
    return grid


def bootstrap_grid(quick: bool) -> list[tuple]:
    if quick:
        return [("A", 14, 6, 20, 2)]
    return ([("A", 14, pre, 20, post) for pre in (6, 12, 18) for post in (2, 4)]
            + [("A", 14, pre, 40, 2) for pre in (6, 12)]
            + [("B", 14, pre, 20, 2) for pre in (6, 12)])


def preblock_grid(quick: bool) -> list[tuple]:
    if quick:
        return [("A", 14, 6, 20, 2), ("A", 14, 15, 20, 2)]
    return [(tier, 14, pre, donors, 2) for tier in ("A", "B") for donors in (20, 40)
            for pre in PREBLOCKS]


def stress_grid(quick: bool) -> list[tuple]:
    if quick:
        return [("A", 14, 12, 20, 2)]
    return [("A", 14, 6, 40, 2), ("A", 14, 12, 20, 2), ("A", 14, 12, 40, 2), ("A", 14, 18, 40, 2)]


def freetier_grid(quick: bool) -> list[tuple]:
    designs = FREE_TIER_DESIGNS[:1] if quick else FREE_TIER_DESIGNS
    return [(CADENCE_TIER[minutes], 14, 12, ids - TREATED_IDS, 2) for minutes, ids in designs]


PARTS = {  # grid, variants, deltas, bootstrap resamples, scheduled_panel arguments
    "design": (design_grid, CONFIGS, DESIGN_DELTAS, 0, {}),
    "bootstrap": (bootstrap_grid, BOOTSTRAPS, BOOTSTRAP_DELTAS, RESAMPLES, {}),
    "preblocks": (preblock_grid, PREBLOCK_CONFIGS, PREBLOCK_DELTAS, 0, {}),
    "stress": (stress_grid, STRESS_VARIANTS, (0.0, 0.10, 0.20), RESAMPLES, {"first": STRESS}),
    "drift": (stress_grid, STRESS_VARIANTS, (0.0, 0.10, 0.20), RESAMPLES,
              {"corridor_week_sd": DRIFT_WEEK_SD}),
    "freetier": (freetier_grid, {"demeaned": {"audit_weights": "demeaned"}}, FREE_TIER_DELTAS,
                 0, {}),
    "freetier_lowfail": (freetier_grid, {"demeaned": {"audit_weights": "demeaned"}},
                         FREE_TIER_DELTAS, 0,
                         {"profiles": {i: {"miss": LOW_MISS} for i in range(64)}}),
}


def scenario_params(scenario: tuple, **extra) -> Params:
    _, block_days, pre_blocks, _, post_blocks = scenario
    return Params(audit_block_days=block_days, audit_pre_blocks=pre_blocks,
                  audit_post_blocks=post_blocks, **extra)


def simulate(scenario: tuple, replicate: int, panel: dict | None = None):
    tier, _, _, donors, _ = scenario
    params = scenario_params(scenario)
    span = periods(EFFECTIVE, params)
    days = (span["post_end"] - span["pre_start"]).days + 1
    rng = np.random.default_rng(zlib.crc32("|".join(map(str, (*scenario, replicate))).encode()))
    samples = scheduled_panel(donors + 1, span["pre_start"], days, tier, rng, **(panel or {}))
    calls, cells, corridors = audit_inputs(samples, tier, params)
    at_peak = pooled.is_peak(samples["requested_at"], params).to_numpy()
    ok = samples["ok"].to_numpy()
    failures = {"peak_fail": 1 - ok[at_peak].mean(), "other_fail": 1 - ok[~at_peak].mean()}
    return span, calls[pooled.is_peak(calls["requested_at"], params)], cells, corridors, failures


def rank_p(treated: float, placebos) -> float:
    """Permutation p of treated among placebos, largest first, ties against treated."""
    values = np.asarray(placebos, dtype=float)
    values = values[~np.isnan(values)]
    if np.isnan(treated) or not len(values):
        return np.nan
    return (1 + np.sum(values >= treated)) / (1 + len(values))


def draws(a: Audit, corridor_id: str, period: str, params: Params, shared: dict):
    """(pooled BTI, bootstrap draws) resampling calls, as metrics.audit did before its
    interval was removed; same keys, so the same draws. Donors are cached in shared."""
    key = (corridor_id, period)
    if key in shared:
        return shared[key]
    values = a.calls.between(corridor_id, a.span[f"{period}_start"], a.span[f"{period}_end"])
    (sample,) = pooled.draws(values, [pooled.bti_rows], params,
                             ("audit", a.intervention_id, corridor_id, period))
    out = (pooled_bti(values, params), sample)
    if corridor_id != TREATED:
        shared[key] = out
    return out


def treated_estimate(peak: pd.DataFrame, cells: pd.DataFrame, params: Params,
                     candidates: list[str], shared: dict) -> dict:
    """The treated corridor's estimate against fixed donors and, when resamples are set,
    the call-level bootstrap intervals and standard errors the calibration tests."""
    last_day = cells.loc[cells["n_ok"] > 0, "day"].max()
    a = Audit(Calls(peak), {}, "works", TREATED, EFFECTIVE, last_day, params)
    model, residuals, _, _, gaps = a.fit_pool(candidates, list(range(params.audit_pre_blocks)))
    head = a.headline(candidates, model.weights)
    out = {"effect": head["effect"], "equal_effect": head["equal_effect"],
           "post_rmspe": rmspe(gaps)}
    out |= dict.fromkeys(("ci_low", "ci_high", "equal_ci_low", "equal_ci_high", "se",
                          "equal_se"), np.nan)
    if params.bootstrap_resamples:
        tp, tq = draws(a, TREATED, "pre", params, shared)[1], draws(a, TREATED, "post", params,
                                                                   shared)[1]
        dp = np.array([draws(a, c, "pre", params, shared)[1] for c in candidates])
        dq = np.array([draws(a, c, "post", params, shared)[1] for c in candidates])
        synthetic = (tq - model.weights @ dq) - (tp - model.weights @ dp)
        equal = (tq - tp) - (dq.mean(axis=0) - dp.mean(axis=0))
        out["ci_low"], out["ci_high"] = pooled.interval(synthetic, params)
        out["equal_ci_low"], out["equal_ci_high"] = pooled.interval(equal, params)
        out["se"], out["equal_se"] = float(np.nanstd(synthetic, ddof=1)), float(
            np.nanstd(equal, ddof=1))
    return out


def run_audits(task: tuple) -> list[dict]:
    part, scenario, replicate = task
    _, variants, deltas, resamples, panel = PARTS[part]
    span, peak, cells, corridors, failures = simulate(scenario, replicate, panel)
    injected = {d: inject_bti_effect(peak, TREATED, span["post_start"], span["post_end"], d)[0]
                for d in deltas if d > 0}
    records = []
    for variant, options in variants.items():
        params = scenario_params(scenario, bootstrap_resamples=resamples, **options)
        tables = intervention_audits(peak, cells, corridors, INTERVENTIONS, params,
                                     sensitivity=False)
        row = tables["intervention_audit"].iloc[0]
        base = dict(zip(SCENARIO, scenario, strict=True)) | {
            "variant": variant, "replicate": replicate, "status": row.status,
            "n_donors": row.n_donors, "n_placebos": row.n_placebos, **failures,
        }
        if row.status != "ok":
            records += [base | {"delta": d} for d in deltas]
            continue
        donors = tables["audit_donors"]
        candidates = donors.loc[donors["included"].astype(bool), "corridor_id"].tolist()
        placebos = tables["audit_placebos"]
        with np.errstate(divide="ignore", invalid="ignore"):
            placebo_cv = (placebos["post_rmspe"] / placebos["cv_pre_rmspe"]).to_numpy(float)
            placebo_std = (placebos["effect"].abs() / placebos["cv_pre_rmspe"]).to_numpy(float)
        shared: dict = {}
        base |= {"pre_rmspe": row.pre_rmspe, "cv_pre_rmspe": row.cv_pre_rmspe,
                 "n_active_donors": row.n_active_donors}
        for delta in deltas:
            est = treated_estimate(injected.get(delta, peak), cells, params, candidates, shared)
            if delta == 0:
                assert abs(est["effect"] - row.effect) < 1e-9, (scenario, replicate, variant)
            cv_ratio = (est["post_rmspe"] / row.cv_pre_rmspe if row.cv_pre_rmspe > 0 else np.nan)
            records.append(base | est | {
                "delta": delta,
                "p_ratio": rank_p(rmspe_ratio(est["post_rmspe"], row.pre_rmspe),
                                  placebos["rmspe_ratio"]),
                "p_cv_ratio": rank_p(cv_ratio, placebo_cv),
                "p_abs_effect": rank_p(abs(est["effect"]), placebos["effect"].abs()),
                "p_std_effect": rank_p(abs(est["effect"]) / row.cv_pre_rmspe
                                       if row.cv_pre_rmspe > 0 else np.nan, placebo_std),
            })
    return records


def excludes_zero(frame: pd.DataFrame, low: str, high: str) -> np.ndarray:
    positive = frame["delta"] > 0
    return np.where(positive, frame[low] > 0, (frame[low] > 0) | (frame[high] < 0))


def with_detections(frame: pd.DataFrame) -> pd.DataFrame:
    upward = np.where(frame["delta"] > 0, frame["effect"] > 0, True)
    out = frame.copy()
    for rule in RANKS:
        out[rule] = (((out[f"p_{rule}"] <= ALPHA) & upward).astype(float)
                     if f"p_{rule}" in out else np.nan)
    out["cs"] = excludes_zero(out, "cs_low", "cs_high") if "cs_low" in out else np.nan
    if "ci_low" in out and out["ci_low"].notna().any():
        out["interval"] = excludes_zero(out, "ci_low", "ci_high")
        out["equal"] = excludes_zero(out, "equal_ci_low", "equal_ci_high")
    return out


def mde(power: pd.Series) -> str:
    """Smallest delta from which every larger delta reaches POWER."""
    if power.isna().all():
        return "—"
    found = None
    for delta, value in sorted(power.items(), reverse=True):
        if delta == 0:
            break
        if pd.isna(value) or value < POWER:
            break
        found = delta
    return f"{found:.2f}" if found is not None else f"> {max(power.index):.2f}"


def cell(value: float, digits: int = 2) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.{digits}f}"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(r) + " |" for r in rows])


def scenario_cells(key: tuple, group: pd.DataFrame) -> list[str]:
    tier, block_days, pre_blocks, donors, post_blocks = key
    null = group[group["delta"] == 0]
    ok = null[null["status"] == "ok"]
    return [tier, str(block_days), f"{pre_blocks} ({pre_blocks * block_days} d)",
            f"{donors} ({cell(ok['n_donors'].mean(), 1)})", str(post_blocks * block_days),
            cell(1 - len(ok) / len(null))]


def design_report(frame: pd.DataFrame) -> list[str]:
    frame = with_detections(frame)
    lines = ["## 1. Design sweep", ""]

    def summary(variant: str) -> tuple[list[str], list[list[str]]]:
        header = ["tier", "block days", "pre blocks", "donors (used)", "post days", "withheld",
                  "p floor", "exact pre fits", "active donors", "pre / held-out RMSPE",
                  "null effect sd", "false pos. ratio", "false pos. cv ratio",
                  "false pos. |effect|", "false pos. cs", "MDE oracle", "MDE ratio",
                  "MDE cv ratio", "MDE |effect|", "MDE cs"]
        rows = []
        sub = frame[frame["variant"] == variant]
        for key, group in sub.groupby(SCENARIO, sort=True):
            ok = group[group["status"] == "ok"]
            null = ok[ok["delta"] == 0]
            if null.empty:
                rows.append(scenario_cells(key, group) + ["—"] * (len(header) - 6))
                continue
            by_delta = ok.groupby("delta")
            sd = null["effect"].std(ddof=1)
            rows.append(scenario_cells(key, group) + [
                cell((1 / (null["n_placebos"] + 1)).median(), 3),
                cell((null["pre_rmspe"] < EXACT_FIT).mean()),
                cell(null["n_active_donors"].median(), 0),
                cell((null["pre_rmspe"] / null["cv_pre_rmspe"]).median()),
                cell(sd, 3),
                *[cell(null[rule].mean()) for rule in RULES],
                cell(Z * sd),
                *[mde(by_delta[rule].mean()) for rule in RULES],
            ])
        return header, rows

    header, rows = summary("demeaned")
    lines += ["### Demeaned weights (the current estimator)", "", *table(header, rows), ""]
    fit_rows = []
    for key, group in frame[frame["delta"] == 0].groupby(["tier", "block_days", "pre_blocks",
                                                          "variant"]):
        ok = group[group["status"] == "ok"]
        fit_rows.append([key[0], str(key[1]), str(key[2]), key[3],
                         cell((ok["pre_rmspe"] < EXACT_FIT).mean()),
                         cell(ok["n_active_donors"].median(), 0),
                         cell((ok["pre_rmspe"] / ok["cv_pre_rmspe"]).median()),
                         *[cell(ok[rule].mean()) for rule in RULES]])
    lines += ["### Weighting compared, pooled over donor counts and post lengths", "",
              *table(["tier", "block days", "pre blocks", "weights", "exact pre fits",
                      "active donors", "pre / held-out RMSPE", "false pos. ratio",
                      "false pos. cv ratio", "false pos. |effect|", "false pos. cs"], fit_rows),
              ""]
    for variant in ("sparse5", "levels"):
        header, rows = summary(variant)
        lines += [f"### {variant} weights", "", *table(header, rows), ""]
    return lines


def calibration(group: pd.DataFrame, estimate: str, low: str, high: str,
                se: str | None) -> dict[float, dict]:
    """Per true effect: size (interval excludes 0), coverage (interval contains the true
    effect), spread ratio (mean standard error the interval implies over the empirical sd
    of the estimate across panels), bias and median width."""
    out = {}
    for delta, g in group.groupby("delta"):
        g = g[g[low].notna() & g[high].notna()]
        if len(g) < 3:
            continue
        implied = g[se] if se else (g[high] - g[low]) / (2 * 1.959964)
        out[delta] = {
            "n": len(g), "excludes_zero": float(((g[low] > 0) | (g[high] < 0)).mean()),
            "covers": float(((g[low] <= delta) & (g[high] >= delta)).mean()),
            "ratio": float(implied.mean() / g[estimate].std(ddof=1)),
            "bias": float(g[estimate].mean() - delta), "width": float((g[high] - g[low]).median()),
        }
    return out


CALIBRATION_HEADER = ["size (excl. 0 at 0)", "coverage 0.05", "coverage 0.10", "coverage 0.20",
                      "coverage 0.30", "SE/SD at 0", "SE/SD at 0.10", "SE/SD at 0.30",
                      "bias at 0", "median width"]


def calibration_cells(c: dict[float, dict]) -> list[str]:
    def get(delta, key):
        return c.get(delta, {}).get(key)
    return [cell(get(0.0, "excludes_zero")), *[cell(get(d, "covers")) for d in (0.05, 0.10, 0.20,
                                                                              0.30)],
            *[cell(get(d, "ratio")) for d in (0.0, 0.10, 0.30)], cell(get(0.0, "bias"), 3),
            cell(get(0.0, "width"), 3)]


def bootstrap_report(frame: pd.DataFrame) -> list[str]:
    ok = frame[frame["status"] == "ok"]
    variants = sorted(frame["variant"].unique(), key=lambda v: (v.endswith("levels"), v))
    intervals = {"synthetic-control bootstrap interval": ("effect", "ci_low", "ci_high", "se"),
                 "equal-weight bootstrap interval": ("equal_effect", "equal_ci_low",
                                                     "equal_ci_high", "equal_se")}
    lines = ["## 2. Interval calibration", "",
             "Size = share of no-effect panels whose interval excludes zero (nominal 0.05). "
             "Coverage = share of panels whose interval contains the true injected effect "
             "(nominal 0.95). SE/SD = mean standard error the interval reports over the "
             "empirical sd of the point estimate across panels at that effect; 1 means the "
             "spread is estimated correctly, below 1 too narrow. For the confidence sequence "
             "the reported spread is its half-width / 1.96, and a valid always-valid sequence "
             "should sit above 1. The injection moves every estimate by exactly the effect, so "
             "the empirical sd is the same at every effect size; only the reported spread can "
             "change. Real effects that vary week to week would add spread this cannot show.",
             ""]
    pooled_rows = []
    for title, (estimate, low, high, se) in intervals.items():
        for variant in variants:
            sub = ok[ok["variant"] == variant]
            c = [calibration(g, estimate, low, high, se) for _, g in sub.groupby(SCENARIO)]
            size = np.nanmean([x[0.0]["excludes_zero"] for x in c if 0.0 in x])
            cover = np.nanmean([x[d]["covers"] for x in c for d in x if d > 0])
            ratio = np.nanmean([x[d]["ratio"] for x in c for d in x])
            worst = np.nanmin([x[d]["covers"] for x in c for d in x if d > 0])
            pooled_rows.append([title, variant, cell(size), cell(cover), cell(worst), cell(ratio)])
    cs_variants = ({"demeaned": "calls", "levels": "calls-levels"}
                   if "cs_low" in frame and frame["cs_low"].notna().any() else {})
    for weights, variant in cs_variants.items():
        sub = ok[ok["variant"] == variant]
        c = [calibration(g, "cs_mean", "cs_low", "cs_high", None) for _, g in sub.groupby(SCENARIO)]
        pooled_rows.append([f"confidence sequence ({weights} weights)", "—",
                            cell(np.nanmean([x[0.0]["excludes_zero"] for x in c if 0.0 in x])),
                            cell(np.nanmean([x[d]["covers"] for x in c for d in x if d > 0])),
                            cell(np.nanmin([x[d]["covers"] for x in c for d in x if d > 0])),
                            cell(np.nanmean([x[d]["ratio"] for x in c for d in x]))])
    lines += ["### Pooled over every scenario", "",
              *table(["interval", "resampling", "size", "coverage (mean over effects)",
                      "coverage (worst scenario and effect)", "SE/SD (mean)"], pooled_rows), ""]
    for title, (estimate, low, high, se) in intervals.items():
        rows = []
        for key, everything in frame.groupby(SCENARIO, sort=True):
            for variant in variants:
                mine = everything[everything["variant"] == variant]
                sub = mine[mine["status"] == "ok"]
                rows.append(scenario_cells(key, mine)
                            + [variant, *calibration_cells(calibration(sub, estimate, low, high,
                                                                       se))])
        lines += [f"### {title}", "",
                  *table(["tier", "block days", "pre blocks", "donors (used)", "post days",
                          "withheld", "resampling", *CALIBRATION_HEADER], rows), ""]
    if not cs_variants:
        return lines
    rows = []
    for key, everything in frame.groupby(SCENARIO, sort=True):
        for weights, variant in cs_variants.items():
            mine = everything[everything["variant"] == variant]
            sub = mine[mine["status"] == "ok"]
            rows.append(scenario_cells(key, mine)
                        + [weights, *calibration_cells(calibration(sub, "cs_mean", "cs_low",
                                                                   "cs_high", None))])
    lines += ["### Confidence sequence at the last post block", "",
              *table(["tier", "block days", "pre blocks", "donors (used)", "post days",
                      "withheld", "weights", *CALIBRATION_HEADER], rows), ""]
    return lines


def weeks(pre_blocks: float) -> str:
    return f"{pre_blocks} ({pre_blocks * 2} wk)"


def needed(power: pd.Series) -> str:
    """Fewest pre blocks from which every longer pre period reaches POWER."""
    found = None
    for pre, value in sorted(power.items(), reverse=True):
        if pd.isna(value) or value < POWER:
            break
        found = pre
    return weeks(int(found)) if found is not None else f"> {weeks(int(max(power.index)))}"


def preblock_report(frame: pd.DataFrame) -> list[str]:
    frame = with_detections(frame)
    ok = frame[frame["status"] == "ok"]
    pres = sorted(frame["pre_blocks"].unique())
    lines = ["## 3. Minimum detectable effect by pre-period length", "",
             "14-day blocks, 28-day post period, 50 panels per cell. Rows are pre-period "
             "lengths; weeks in brackets. `oracle` is what a test that knew the estimator's "
             "true spread could detect: the ceiling for any rule on this estimator. `needed` "
             f"= fewest pre blocks from which every longer pre period detects the effect in at "
             f"least {POWER:.0%} of panels.", ""]
    summary = []
    detail = []
    for (tier, donors, variant), group in ok.groupby(["tier", "donors", "variant"]):
        powers = {rule: ({}, {}) for rule in ("abs_effect", "std_effect", "ratio", "cv_ratio",
                                              "cs", "oracle")}
        rows = []
        for pre in pres:
            at = group[group["pre_blocks"] == pre]
            null = at[at["delta"] == 0]
            everything = frame[(frame["tier"] == tier) & (frame["donors"] == donors)
                               & (frame["variant"] == variant) & (frame["pre_blocks"] == pre)
                               & (frame["delta"] == 0)]
            if null.empty:
                rows.append([weeks(int(pre)), cell(1.0), *["—"] * 16])
                continue
            sd = null["effect"].std(ddof=1)
            by_delta = at.groupby("delta")
            for rule in powers:
                for i, delta in enumerate((0.10, 0.20)):
                    if rule == "oracle":
                        powers[rule][i][pre] = float(stats.norm.sf(1.959964 - delta / sd))
                    else:
                        powers[rule][i][pre] = by_delta[rule].mean().get(delta, np.nan)
            cs10 = at[np.isclose(at["delta"], 0.10)]
            cs20 = at[np.isclose(at["delta"], 0.20)]
            rows.append([
                weeks(int(pre)), cell(1 - len(null) / len(everything)),
                cell(null["n_donors"].mean(), 1), cell((null["pre_rmspe"] < EXACT_FIT).mean()),
                cell((null["pre_rmspe"] / null["cv_pre_rmspe"]).median()), cell(sd, 3),
                cell(Z * sd), cell(null["abs_effect"].mean()),
                cell(by_delta["abs_effect"].mean().get(0.10)),
                cell(by_delta["abs_effect"].mean().get(0.20)), mde(by_delta["abs_effect"].mean()),
                cell(null["std_effect"].mean()), mde(by_delta["std_effect"].mean()),
                cell(null["ratio"].mean()), mde(by_delta["ratio"].mean()),
                cell(mean_of(null, "cs")),
                cell(((cs10["cs_low"] <= 0.10) & (cs10["cs_high"] >= 0.10)).mean()
                     if "cs_low" in cs10 else np.nan),
                cell(((cs20["cs_low"] <= 0.20) & (cs20["cs_high"] >= 0.20)).mean()
                     if "cs_low" in cs20 else np.nan),
            ])
        for rule, (p10, p20) in powers.items():
            summary.append([tier, str(donors), variant, RULES.get(rule, rule),
                            needed(pd.Series(p10)), needed(pd.Series(p20))])
        detail += [f"### Tier {tier}, {donors} donors, {variant} weights", "",
                   *table(["pre blocks", "withheld", "donors used", "exact pre fits",
                           "pre / held-out RMSPE", "null effect sd", "MDE oracle",
                           "size |effect|", "power 0.10 |effect|", "power 0.20 |effect|",
                           "MDE |effect|", "size std", "MDE std", "size ratio", "MDE ratio",
                           "size cs",
                           "cs coverage 0.10", "cs coverage 0.20"], rows), ""]
    lines += ["### Pre blocks needed", "",
              *table(["tier", "donors", "weights", "rule", "needed for 0.10",
                      "needed for 0.20"], summary), "", *detail]
    return lines


def slots_per_day(tier: str) -> tuple[int, int]:
    """(peak slots, other slots) one corridor owes on a day of the current schedule."""
    day = pd.Series(schedule.day_slots(tier, pd.Timestamp("2026-09-14")))
    peak = int(pooled.is_peak(day, Params()).sum())
    return peak, len(day) - peak


def freetier_report(frame: pd.DataFrame, heading: str, note: str) -> list[str]:
    # a design whose every audit was withheld has no estimate columns at all
    wanted = ("effect", *(f"p_{rule}" for rule in RANKS))
    frame = frame.reindex(columns=[*frame.columns, *(c for c in wanted if c not in frame.columns)])
    frame = with_detections(frame)
    replicates = int(frame["replicate"].max()) + 1
    budget, audits, power = [], [], []
    for (tier, donors), group in frame.groupby(["tier", "donors"], sort=False):
        minutes, ids = schedule.CADENCE_MINUTES[tier], donors + TREATED_IDS
        label = f"{ids} ids @ {minutes} min"
        peak, night = slots_per_day(tier)
        null = group[group["delta"] == 0]
        ran = null[null["status"] == "ok"]
        peak_fail, other_fail = null["peak_fail"].mean(), null["other_fail"].mean()
        for night_slots in (night, 2):
            first = ids * (peak + night_slots)
            retried = ids * (peak * (1 + 2 * peak_fail) + night_slots * (1 + 2 * other_fail))
            month = retried * LONGEST_MONTH + ids * LONGEST_MONTH / 7
            budget.append([label, str(night_slots), str(first), f"{first * LONGEST_MONTH:,}",
                           f"{round(month):,}", f"{month / MONTHLY_ALLOWANCE:.0%}"])
        refused = null["status"].value_counts()
        reasons = ", ".join(f"{status} {n / len(null):.0%}" for status, n in refused.items()
                            if status != "ok")
        audits.append([
            label, str(donors), f"{peak_fail:.1%}", cell(1 - len(ran) / len(null)), reasons or "—",
            cell(ran["n_donors"].mean(), 1) if len(ran) else "—",
            cell(ran["n_donors"].quantile(0.1), 0) if len(ran) else "—",
            cell((ran["n_placebos"] >= 19).sum() / len(null)),
            cell(ran["std_effect"].mean()) if len(ran) else "—",
        ])
        every = group.groupby("delta")["std_effect"].mean()
        run_only = group[group["status"] == "ok"].groupby("delta")["std_effect"].mean()
        power.append([label, *[cell(every.get(d)) for d in FREE_TIER_DELTAS[1:]], mde(every),
                      mde(run_only)])
    return [
        heading, "", note, "",
        f"TomTom's pricing page lists the Routing API at {MONTHLY_ALLOWANCE:,} free calls a "
        f"month (read 2026-09-14), {MONTHLY_ALLOWANCE // LONGEST_MONTH} a day in a "
        f"{LONGEST_MONTH}-day month. Each design audits one of {TREATED_IDS} treated corridors "
        f"against the rest less the {TREATED_IDS} treated ids as declared donors: 14-day "
        f"blocks, 12 pre blocks (24 weeks), 28-day post period, standardised placebo rank, "
        f"{replicates} panels each.", "",
        "### Calls", "",
        "Per corridor a day: every peak slot, plus the night slots that feed the observed "
        "free-flow reference. The current schedule has 8 night slots; the brief's call counts "
        "imply 2. `month` adds, at the panel model's failure rates, two retries for every "
        "call that finally failed and a weekly road refetch per corridor. It leaves out "
        "retries before a call that succeeded, so it is a lower bound; docs/free_tier.md "
        "prices both.", "",
        *table(["design", "night slots", "first attempts a day", f"{LONGEST_MONTH}-day month, no "
                "retries", "month with retries and road checks", "of 20,000"], budget), "",
        "### Audits", "",
        "`withheld`: the audit refused (treated corridor under the block floor, or no donor "
        "left). `donors used`: mean and 10th percentile among audits that ran. `p reachable`: "
        "share of all audits with at least 19 placebos, the fewest at which a placebo p can "
        "reach 0.05. `size`: false-positive rate among audits that ran.", "",
        *table(["design", "donors declared", "peak calls failed", "withheld", "why",
                "donors used", "donors used, p10", "p reachable", "size"], audits), "",
        "### Power", "",
        "Share of all declared audits that detect the effect: a withheld audit counts as not "
        "detected. `MDE, every audit` is what a declared audit can promise; `MDE, audits run` "
        "is the definition the earlier sections use.", "",
        *table(["design", *[f"power {d:.2f}" for d in FREE_TIER_DELTAS[1:]], "MDE, every audit",
                "MDE, audits run"], power), "",
    ]


def mean_of(frame: pd.DataFrame, column: str) -> float:
    return frame[column].mean() if column in frame and frame[column].notna().any() else np.nan


def stress_report(frame: pd.DataFrame, baselines: list[tuple[str, pd.DataFrame, str]],
                  heading: str, description: str) -> list[str]:
    """One stressed part against the same scenarios and seeds from unstressed parts."""
    rules = (*RANKS, "cs", "interval")
    lines = [heading, "", description, ""]
    frame = with_detections(frame)
    ready = [(label, with_detections(b), variant) for label, b, variant in baselines
             if b is not None]
    rows = []
    for key, group in frame.groupby(SCENARIO, sort=True):
        pairs = []
        for label, base, variant in ready:
            match = base[(base[SCENARIO] == pd.Series(key, index=SCENARIO)).all(axis=1)
                         & (base["variant"] == variant)]
            if not match.empty:
                pairs.append((label, match))
        pairs.append(("stressed", group))
        for label, g in pairs:
            ok = g[g["status"] == "ok"]
            null, at = ok[ok["delta"] == 0], ok[np.isclose(ok["delta"], 0.20)]
            covers = (((at["ci_low"] <= 0.20) & (at["ci_high"] >= 0.20)).mean()
                      if "ci_low" in at and at["ci_low"].notna().any() else np.nan)
            rows.append(scenario_cells(key, g) + [label, str(len(null))]
                        + [cell(mean_of(null, r)) for r in rules] + [cell(covers)]
                        + [cell(mean_of(at, r)) for r in RANKS])
    lines += table(["tier", "block days", "pre blocks", "donors (used)", "post days", "withheld",
                    "panels from", "panels", *[f"size {RULES.get(r, r)}" for r in rules],
                    "interval coverage 0.20", *[f"power 0.20 {RULES[r]}" for r in RANKS]], rows)
    return lines + [""]


def sha() -> str:
    found = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
    return found.stdout.strip() or "unknown"


def report(frames: dict[str, pd.DataFrame], replicates: dict[str, int], minutes: float) -> str:
    lines = [
        "# Intervention audit: validity, power and minimum detectable effect",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/dev/audit_power.py` at "
        f"{sha()} (plus uncommitted changes), {minutes:.0f} min for the parts run this time. "
        "Panels per scenario: "
        + ", ".join(f"{part} {int(frame['replicate'].max()) + 1}" for part, frame in frames.items())
        + ".",
        "",
        "Panels: `scripts/dev/panel_model.py`, the fixture generator's travel-time model on the "
        "collector's schedule, with a city-wide daily shock (sd 0.10) and per-corridor weekly "
        "drift (sd 0.08) on the excess over free flow. Those sizes are assumptions, not "
        "Hyderabad estimates. The treated corridor is drawn from the same model as its donors, "
        "so it is exchangeable with them. An effect of known size is injected into its pooled "
        "post-period BTI, which moves the estimate by exactly that much; the audit then runs "
        "unchanged. Settling 9 days throughout.",
        "",
        f"Rules. `ratio`: the published placebo p, post/pre RMSPE ratio ranked, p <= {ALPHA}. "
        "`cv ratio`: the same with the leave-one-block-out pre RMSPE. `|effect|`: treated "
        "|effect| ranked among placebo |effects|. `std |effect|`: treated |effect| over its own "
        "leave-one-block-out pre RMSPE, ranked among the placebos' same ratio. `cs`: the "
        "block confidence sequence at the last post block excludes zero. `interval` / "
        "`equal`: the synthetic-control / equal-weight bootstrap interval excludes zero. "
        "For a positive effect every rule "
        "also needs the estimate's sign right. `oracle`: (1.96 + 0.84) x the sd of the null "
        "effect, what a test that knew the estimator's true spread would need.",
        "",
        f"Columns. `withheld`: share of panels the audit itself refused (insufficient_pre). "
        f"`p floor`: 1/(placebos + 1), the smallest attainable permutation p; above {ALPHA} no "
        f"placebo rule can detect anything. `exact pre fits`: pre RMSPE < {EXACT_FIT:g}. "
        "`pre / held-out RMSPE`: median in-sample over leave-one-block-out pre RMSPE; far "
        "below 1 means the weights fit noise. `false pos.`: detection rate at effect 0; a "
        f"rule is valid only where this is at most about {ALPHA} (with 50 panels its standard "
        f"error is about 0.03). MDE: smallest effect from which every larger injected effect "
        f"is detected in at least {POWER:.0%} of panels; `> x` means never within the sweep.",
        "",
    ]
    if "design" in frames:
        lines += design_report(frames["design"])
    if "bootstrap" in frames:
        lines += bootstrap_report(frames["bootstrap"])
    if "preblocks" in frames:
        lines += preblock_report(frames["preblocks"])
    baselines = [("exchangeable, pre-block sweep", frames.get("preblocks"), "demeaned"),
                 ("exchangeable, bootstrap sweep", frames.get("bootstrap"), "calls")]
    if "stress" in frames:
        lines += stress_report(
            frames["stress"], baselines, "## 4. Exchangeability broken on purpose",
            "The treated corridor is fixed as the most congested and most volatile corridor "
            f"panel_model can draw ({STRESS}). Donors come from the same seeds as the matching "
            "exchangeable panels, so only the treated corridor differs. A rule whose "
            "false-positive rate rises here is exact only when the treated corridor is typical "
            "of its donors, and interventions are not placed on typical roads.")
    if "freetier" in frames:
        lines += freetier_report(
            frames["freetier"], "## 6. Panel designs that fit TomTom's free allowance",
            "Call failure rates as panel_model draws them: most corridors fail up to 12% of "
            "calls, 18% of corridors 16-38%, more at the peaks and on whole dark days.")
    if "freetier_lowfail" in frames:
        lines += freetier_report(
            frames["freetier_lowfail"], "## 7. The same designs at a 3% failure rate",
            f"Every corridor's failure rate fixed at {LOW_MISS:.0%} before the peak and "
            "dark-day multipliers, everything else unchanged. Nobody knows TomTom's failure "
            "rate from Hyderabad yet; this bounds how much of section 6 is the failure "
            "assumption.")
    if "drift" in frames:
        lines += stress_report(
            frames["drift"], baselines, "## 5. Weekly drift 2.5 times larger",
            f"Every corridor's week-to-week drift has sd {DRIFT_WEEK_SD} instead of 0.08; the "
            "treated corridor is exchangeable again. The call-level bootstrap treats calls "
            "within a period as independent, so this is where its interval should break if it "
            "is going to.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=(*PARTS, "both", "all"), default="all")
    parser.add_argument("--replicates", type=int, default=50)
    parser.add_argument("--bootstrap-replicates", type=int, default=100)
    parser.add_argument("--processes", type=int, default=9)
    parser.add_argument("--quick", action="store_true", help="small grid, not written to docs")
    parser.add_argument("--report-only", action="store_true",
                        help="re-render docs/audit_power.md from the saved records")
    args = parser.parse_args()
    parts = {"both": ("design", "bootstrap"), "all": tuple(PARTS)}.get(args.part, (args.part,))
    replicates = {"design": args.replicates, "bootstrap": args.bootstrap_replicates,
                  "preblocks": args.replicates, "stress": args.bootstrap_replicates,
                  "drift": args.bootstrap_replicates, "freetier": args.replicates,
                  "freetier_lowfail": args.replicates}
    if args.quick:
        replicates = {part: 4 for part in replicates}
    started = time.time()
    frames = {}
    for part in parts:
        if args.report_only:
            frames[part] = pd.read_csv(RECORDS[part])
            continue
        grid = PARTS[part][0](args.quick)
        tasks = [(part, s, r) for s in grid for r in range(replicates[part])]
        with Pool(args.processes) as pool:
            records = [r for batch in pool.imap_unordered(run_audits, tasks, chunksize=2)
                       for r in batch]
        frames[part] = pd.DataFrame(records)
        if not args.quick:
            RECORDS[part].parent.mkdir(exist_ok=True)
            frames[part].to_csv(RECORDS[part], index=False)
        print(f"{part}: {len(tasks)} panels in {(time.time() - started) / 60:.1f} min",
              flush=True)
    text = report(frames, replicates, (time.time() - started) / 60)
    print(text)
    if not args.quick:
        if len(parts) < len(PARTS):
            # render every part whose records exist, so one part never drops the others
            for part, path in RECORDS.items():
                if part not in frames and path.exists():
                    frames[part] = pd.read_csv(path)
            text = report(frames, replicates, (time.time() - started) / 60)
        OUT.write_text(text)
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
