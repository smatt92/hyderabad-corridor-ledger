"""What TomTom's free Routing allowance can support.

    .venv/bin/python scripts/dev/free_tier.py [--replicates N] [--processes N] [--quick]

TomTom lists the Routing API at 20,000 free calls a month. This works out, for
panel designs of four treated corridors plus donors:
  - calls in a 31-day month, retries and road checks included, by peak cadence,
    night slots, call failure rate and panel width;
  - the call failure rate at which the intervention audit breaks: the share of
    audits withheld crosses 20%, or fewer than 80% of audits keep 19 usable
    donors, the fewest at which a placebo p can reach 0.05;
  - the widest panel that fits the allowance and stays auditable, at each
    failure rate;
  - what cutting night slots costs the observed free-flow reference;
  - when each pooled statistic first clears its floor.

Whether an audit is withheld, and how many donors it can use, is settled by
metrics.audit's completeness rules before any synthetic control is fitted: the
treated corridor needs every pre block and the post period at the p95 floor, and
so does every donor it uses. So this counts successful peak-hour calls per block
on panel_model panels instead of running the audit, and checks that shortcut
against the full audits saved by scripts/dev/audit_power.py. Failure rates are
swept by fixing every corridor's panel_model failure parameter; one panel per
replicate is reused across the sweep, so a higher rate only ever adds failures.
The failure structure (more at the peaks, and whole dark days) is panel_model's
assumption, and nobody has measured TomTom's rate from Hyderabad.

Writes docs/free_tier.md and the per-panel records to .fixtures/.
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

from metrics import pooled, schedule  # noqa: E402
from metrics.audit import periods  # noqa: E402
from metrics.cells import local_day_hour  # noqa: E402
from metrics.params import LOCAL_TZ, Params  # noqa: E402
from scripts.dev.panel_model import scheduled_panel  # noqa: E402

MONTHLY_ALLOWANCE, MONTH_DAYS = 20_000, 31
ROAD_CHECKS_PER_MONTH = MONTH_DAYS / 7          # one road refetch a week per corridor
TREATED_IDS, MIN_PLACEBOS = 4, 19
WITHHELD_LIMIT, AUDITABLE_SHARE = 0.20, 0.80
CADENCES = {30: "B", 20: "M20", 15: "A"}
# metrics.schedule has no 20-minute cadence; this adds one to this script's processes only.
schedule.CADENCE_MINUTES.setdefault("M20", 20)
NIGHT_SLOTS = (8, 4, 2)                         # 00:00-04:00 IST every 30, 60 or 120 minutes
TRANSIENT = (0.0, 0.05)
MISS = (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10)
MAX_DONORS = 29
DONORS_SHOWN = (19, 21, 23, 25, 27, 29)
EFFECTIVE = pd.Timestamp("2026-07-01")
OUT = ROOT / "docs" / "free_tier.md"
RECORDS = ROOT / ".fixtures" / "free_tier_panels.csv"
FULL_AUDITS = {"model failure rates": (ROOT / ".fixtures" / "audit_power_freetier.csv", None),
               "3% failure": (ROOT / ".fixtures" / "audit_power_freetier_lowfail.csv", 0.03)}


def slots_per_day(minutes: int) -> tuple[int, int, dict[int, int]]:
    """(peak slots, night slots, peak slots by local hour) one corridor owes a day."""
    day = pd.Series(schedule.day_slots(CADENCES[minutes], pd.Timestamp("2026-09-14")))
    peak = pooled.is_peak(day, Params()).to_numpy()
    hours = day[peak].dt.tz_convert(LOCAL_TZ).dt.hour.value_counts().sort_index()
    return int(peak.sum()), int((~peak).sum()), hours.to_dict()


def attempts_per_slot(failure: float, transient: float) -> float:
    """A slot that finally fails spent all three attempts (a quota refusal spends one, so
    this is the costlier case). A slot that succeeds spent a retry for every transient
    failure first: 1 + q + q^2 for a per-attempt transient failure chance q."""
    return (1 - failure) * (1 + transient + transient**2) + 3 * failure


def month_per_corridor(minutes: int, night: int, failure: float, transient: float) -> float:
    peak, _, _ = slots_per_day(minutes)
    return (MONTH_DAYS * (peak + night) * attempts_per_slot(failure, transient)
            + ROAD_CHECKS_PER_MONTH)


def widest(minutes: int, night: int, failure: float, transient: float) -> int:
    return math.floor(MONTHLY_ALLOWANCE / month_per_corridor(minutes, night, failure, transient))


def usable_corridors(samples: pd.DataFrame, params: Params) -> tuple[np.ndarray, float, float]:
    """(usable flag per corridor in id order, peak failure share, other failure share).
    Usable: every pre block and the post period hold the p95 floor of successful
    peak-hour calls, metrics.audit.audit_one's test for the treated corridor and for a
    donor alike."""
    span, floor = periods(EFFECTIVE, params), params.p95_min_samples
    at_peak = pooled.is_peak(samples["requested_at"], params).to_numpy()
    ok = samples["ok"].to_numpy()
    calls = samples.loc[ok & at_peak, ["corridor_id", "requested_at"]]
    day = local_day_hour(calls["requested_at"])["day"]
    ids = sorted(samples["corridor_id"].unique())
    pre = day.between(span["pre_start"], span["pre_end"])
    post = day.between(span["post_start"], span["post_end"])
    block = (day[pre] - span["pre_start"]).dt.days // params.audit_block_days
    pre_counts = (pd.DataFrame({"c": calls.loc[pre, "corridor_id"], "b": block})
                  .groupby(["c", "b"]).size().unstack(fill_value=0)
                  .reindex(index=ids, columns=range(params.audit_pre_blocks), fill_value=0))
    post_counts = calls.loc[post, "corridor_id"].value_counts().reindex(ids, fill_value=0)
    usable = ((pre_counts >= floor).all(axis=1) & (post_counts >= floor)).to_numpy()
    return usable, float(1 - ok[at_peak].mean()), float(1 - ok[~at_peak].mean())


def run_panel(task: tuple) -> dict:
    minutes, miss, replicate, n, seed_key = task
    params = Params()
    span = periods(EFFECTIVE, params)
    days = (span["post_end"] - span["pre_start"]).days + 1
    rng = np.random.default_rng(zlib.crc32(seed_key.encode()))
    profiles = None if miss is None else {i: {"miss": miss} for i in range(64)}
    samples = scheduled_panel(n, span["pre_start"], days, CADENCES[minutes], rng,
                              profiles=profiles)
    usable, peak_fail, other_fail = usable_corridors(samples, params)
    row = {"seed": seed_key, "minutes": minutes, "miss": miss, "replicate": replicate,
           "peak_fail": peak_fail, "other_fail": other_fail, "treated_ok": bool(usable[0])}
    running = np.cumsum(usable[1:])
    return row | {f"usable_{d}": int(running[d - 1]) for d in range(1, n)}


def sweep_tasks(replicates: int) -> list[tuple]:
    tasks = []
    for minutes in CADENCES:
        n = MAX_DONORS + 1 if minutes == 30 else 1   # only 30 minutes fits 19 donors
        tasks += [(minutes, miss, r, n, f"free-tier|{minutes}|{r}")
                  for miss in MISS for r in range(replicates)]
    return tasks


def validation_tasks() -> list[tuple]:
    """The seeds audit_power.py used for the full audits it saved."""
    tasks = []
    for path, miss in FULL_AUDITS.values():
        if not path.exists():
            continue
        full = pd.read_csv(path)
        for (tier, donors, replicate), _ in full[full["delta"] == 0].groupby(
                ["tier", "donors", "replicate"]):
            minutes = next(m for m, t in CADENCES.items() if t == tier)
            key = "|".join(map(str, (tier, 14, 12, donors, 2, replicate)))
            tasks.append((minutes, miss, replicate, donors + 1, key))
    return tasks


def crossing(xs, ys, threshold: float, rising: bool) -> tuple[float, str]:
    """(x, label) where y first crosses threshold, linear between grid points."""
    previous = None
    for x, y in sorted(zip(xs, ys, strict=True)):
        if (y >= threshold) if rising else (y < threshold):
            if previous is None:
                return x, f"≤ {x:.1%}"
            x0, y0 = previous
            at = x if y == y0 else x0 + (threshold - y0) * (x - x0) / (y - y0)
            return at, f"{at:.1%}"
        previous = (x, y)
    last = max(xs)
    return math.inf, f"> {last:.1%}"


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def first_day(floor: int, calls_a_day: float, window_days: int) -> str:
    days = math.ceil(floor / calls_a_day)
    return f"day {days}" if days <= window_days else "never"


def first_week(floor: int, calls_a_week: float, weeks: int) -> str:
    needed = math.ceil(floor / calls_a_week)
    return f"week {needed}" if needed <= weeks else "never"


def partly_covered(by_hour: dict[int, int], verdict) -> str:
    """Hours with fewer peak slots than a full hour, grouped by what verdict says of them."""
    full = max(by_hour.values())
    groups: dict[str, list[str]] = {}
    for hour, slots in sorted(by_hour.items()):
        if slots < full:
            groups.setdefault(verdict(slots), []).append(f"{hour:02d}:00")
    return "; ".join(f"{', '.join(hours)}: {v}" for v, hours in groups.items())


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(r) + " |" for r in rows])


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    """Per cadence and failure parameter: failure shares, withheld rate, and for each donor
    count the share of audits keeping 19 usable donors, and of audits that are both run and
    able to reach p 0.05."""
    rows = []
    for (minutes, miss), g in frame.groupby(["minutes", "miss"]):
        row = {"minutes": minutes, "miss": miss, "peak_fail": g["peak_fail"].mean(),
               "other_fail": g["other_fail"].mean(), "withheld": 1 - g["treated_ok"].mean()}
        for d in range(MIN_PLACEBOS, MAX_DONORS + 1):
            if f"usable_{d}" in g and g[f"usable_{d}"].notna().all():
                reach = g[f"usable_{d}"] >= MIN_PLACEBOS
                row[f"reach_{d}"] = reach.mean()
                row[f"auditable_{d}"] = (reach & g["treated_ok"]).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def validation_report(records: pd.DataFrame) -> list[str]:
    lines = ["## 6. Check: the shortcut against full audits", "",
             "The same panels (the seeds `scripts/dev/audit_power.py` used) run through this "
             "script's call counting and through `metrics.audit`. Withheld or not, and the "
             "number of usable donors when the audit ran, must agree.", ""]
    rows = []
    for label, (path, miss) in FULL_AUDITS.items():
        if not path.exists():
            continue
        full = pd.read_csv(path)
        full = full[full["delta"] == 0]
        mine = records[records["miss"].isna()] if miss is None else records[records["miss"] == miss]
        for (tier, donors), g in full.groupby(["tier", "donors"]):
            keys = ["|".join(map(str, (tier, 14, 12, donors, 2, r))) for r in g["replicate"]]
            short = mine.set_index("seed").reindex(keys)
            withheld_full = (g["status"] != "ok").to_numpy()
            withheld_mine = ~short["treated_ok"].astype(bool).to_numpy()
            ran = ~withheld_full
            donors_full = g["n_donors"].to_numpy()[ran]
            donors_mine = short[f"usable_{donors}"].to_numpy()[ran]
            rows.append([label, f"{donors + TREATED_IDS} ids @ "
                         f"{next(m for m, t in CADENCES.items() if t == tier)} min",
                         str(len(g)), f"{(withheld_full == withheld_mine).mean():.0%}",
                         f"{(donors_full == donors_mine).mean():.0%}" if ran.any() else "—"])
    return lines + table(["failure rates", "design", "panels", "withheld agrees",
                          "usable donors agree"], rows) + [""]


def budget_report() -> list[str]:
    lines = ["## 1. Calls in a 31-day month", "",
             f"Per corridor: every peak slot and night slot for {MONTH_DAYS} days, with "
             "retries, plus a weekly road refetch. `f` is the share of slots that still fail "
             "after all attempts, each of which spent three; `q` is the chance an attempt "
             "fails and is retried on a slot that then succeeds. Neither has been measured: "
             "`q` is shown at 0 and 5%. Widest panel = most corridor ids whose month fits "
             f"{MONTHLY_ALLOWANCE:,}; donors = ids − {TREATED_IDS} treated. A panel with fewer "
             f"than {MIN_PLACEBOS} donors is ruled out: no audit of it can produce a p of 0.05, "
             "whatever its budget.", ""]
    rows = []
    for minutes in CADENCES:
        peak, _, _ = slots_per_day(minutes)
        for night in NIGHT_SLOTS:
            for transient in TRANSIENT:
                cells = []
                for failure in (0.0, 0.02, 0.04, 0.06, 0.08, 0.10):
                    ids = widest(minutes, night, failure, transient)
                    donors = ids - TREATED_IDS
                    cells.append(f"{ids} ({donors})" + ("" if donors >= MIN_PLACEBOS else " ✗"))
                per = month_per_corridor(minutes, night, 0.0, transient)
                rows.append([f"{minutes} min", str(night), str(peak + night), f"{transient:.0%}",
                             f"{per:,.0f}", *cells])
    lines += table(["peak cadence", "night slots", "calls a day", "q",
                    "calls a month per id at f 0", *[f"widest ids (donors) at f {f:.0%}"
                                                     for f in (0.0, 0.02, 0.04, 0.06, 0.08,
                                                               0.10)]], rows)
    lines += ["", "✗: fewer than 19 donors, ruled out. Every 20- and 15-minute design is ruled "
              "out at every failure rate: the allowance cannot hold 23 ids at those cadences.", ""]
    return lines


def breaking_report(summary: pd.DataFrame) -> list[str]:
    lines = ["## 2. Where the audit breaks", "",
             "Withheld: the treated corridor misses the floor in a pre block or the post "
             "period. Its breaking point does not depend on the panel's width. Usable donors "
             "depend on how many are declared. `auditable` = run and holding at least 19 "
             "usable donors. Failure rates are the share of peak-hour calls failed, as the "
             "collector would measure it.", ""]
    rows = []
    for minutes in CADENCES:
        s = summary[summary["minutes"] == minutes]
        _, withheld = crossing(s["peak_fail"], s["withheld"], WITHHELD_LIMIT, rising=True)
        if minutes != 30:
            rows.append([f"{minutes} min", "—", withheld, "—", "—", "ruled out by budget"])
            continue
        for d in DONORS_SHOWN:
            _, reach = crossing(s["peak_fail"], s[f"reach_{d}"], AUDITABLE_SHARE, rising=False)
            _, audit = crossing(s["peak_fail"], s[f"auditable_{d}"], AUDITABLE_SHARE,
                                rising=False)
            rows.append([f"{minutes} min", f"{d + TREATED_IDS} ids ({d} donors)", withheld, reach,
                         audit, ""])
    lines += table(["peak cadence", "design", "withheld crosses 20%",
                    "under 80% keep 19 donors", "under 80% auditable", ""], rows)
    s = summary[summary["minutes"] == 30].sort_values("peak_fail")
    lines += ["", "The curves at 30 minutes:", ""]
    lines += table(["peak calls failed", "withheld", *[f"auditable, {d} donors"
                                                       for d in DONORS_SHOWN]],
                   [[f"{r.peak_fail:.1%}", f"{r.withheld:.0%}",
                     *[f"{getattr(r, f'auditable_{d}'):.0%}" for d in DONORS_SHOWN]]
                    for r in s.itertuples()])
    return lines + [""]


def widest_report(summary: pd.DataFrame) -> tuple[list[str], list[str]]:
    lines = ["## 3. The widest auditable panel that fits", "",
             f"At each failure rate, 30-minute peaks: the most ids whose month fits "
             f"{MONTHLY_ALLOWANCE:,} with that failure rate's retries, and whether that panel "
             f"is auditable ({AUDITABLE_SHARE:.0%} of audits run with at least 19 usable "
             f"donors, and no more than {WITHHELD_LIMIT:.0%} withheld). Panels wider than "
             f"{MAX_DONORS + TREATED_IDS} ids are scored as {MAX_DONORS + TREATED_IDS}, which "
             "understates them.", ""]
    verdicts = []
    s = summary[summary["minutes"] == 30].sort_values("peak_fail")
    for transient in TRANSIENT:
        rows = []
        for r in s.itertuples():
            cells, best = [], None
            for night in NIGHT_SLOTS:
                ids = widest(30, night, r.peak_fail, transient)
                donors = min(ids - TREATED_IDS, MAX_DONORS)
                if ids - TREATED_IDS < MIN_PLACEBOS:
                    cells.append(f"{ids} ✗")
                    continue
                auditable = getattr(r, f"auditable_{donors}")
                good = auditable >= AUDITABLE_SHARE and r.withheld <= WITHHELD_LIMIT
                cells.append(f"{ids} ({auditable:.0%})" + ("" if good else " ✗"))
                if good and (best is None or ids > best[0]):
                    best = (ids, night)
            rows.append([f"{r.peak_fail:.1%}", f"{r.withheld:.0%}", *cells,
                         f"{best[0]} ids, {best[1]} night slots" if best else "none"])
            verdicts.append((transient, r.peak_fail, best))
        lines += [f"q = {transient:.0%}:", "",
                  *table(["peak calls failed", "withheld", *[f"{n} night slots: widest ids "
                                                             "(auditable)" for n in NIGHT_SLOTS],
                         "widest that satisfies all three"], rows), ""]
    return lines, verdicts


def night_report() -> list[str]:
    params = Params()
    window, floor = params.ff_p5_window_days, params.ff_p5_min_samples
    rows = []
    for night in NIGHT_SLOTS:
        n = night * window
        rank = math.floor(0.05 * (n - 1)) + 1   # linear interpolation between these two
        sd = math.sqrt(0.05 * 0.95 / n)
        low, high = max(0.0, 0.05 - 2 * sd), 0.05 + 2 * sd
        rows.append([str(night), f"every {240 // night} min", str(n),
                     f"between the {ordinal(rank)} and {ordinal(rank + 1)} fastest",
                     f"{low:.1%} to {high:.1%}",
                     f"day {math.ceil(floor / night)}", str(MONTH_DAYS * night)])
    gained = widest(30, 2, 0.0, 0.0) - widest(30, 8, 0.0, 0.0)
    return ["## 4. What cutting night slots costs", "",
            f"The observed free-flow reference is the p5 of successful night-slot travel times "
            f"(00:00-04:00 IST) over a trailing {window} days, published at {floor} calls or "
            "more. TTI and PTI against it, and every table and ranking column on that basis, "
            "move with it. A panel_model panel cannot price the cut: its night travel times "
            "sit at the free-flow floor, so its p5 hardly moves with the slot count. So this "
            "is the sampling arithmetic, before failures, which only make it worse.", "",
            *table(["night slots", "spacing", f"calls in {window} days", "p5 sits",
                    "percentile it lands on, ±2 sd", "first published",
                    "night calls a month per id"], rows),
            "", "- At 2 slots the reference sits between the 3rd and 4th fastest of 56 calls: "
            "one unusually fast night moves it, and it can land anywhere from about the 0th to "
            "the 11th percentile of night travel times. At 8 slots it sits between the 12th and "
            "13th of 224, within about the 2nd to 8th. In seconds that depends on how spread "
            "night travel times are near their fastest, which nobody knows until night calls "
            "exist.",
            "- Fewer slots also sample fewer night hours: 2 slots are 00:00 and 02:00, missing "
            "whichever hour is emptiest if it is another.",
            "- A longer window buys calls back at the cost of reacting slower: 2 slots over 56 "
            "days pool 112 calls, as 4 slots do over 28, but a monsoon month's drift then takes "
            "twice as long to leave the reference.",
            f"- The budget side: each night slot a corridor drops saves {MONTH_DAYS} calls a "
            f"month, so 8 → 2 frees {6 * MONTH_DAYS} per corridor: {gained} more corridors in "
            f"{MONTHLY_ALLOWANCE:,} at 30-minute peaks with no failures "
            f"({widest(30, 8, 0.0, 0.0)} ids at 8 night slots, {widest(30, 2, 0.0, 0.0)} at 2).",
            ""]


def pooling_report() -> list[str]:
    params = Params()
    rows = []
    for minutes in CADENCES:
        peak, _, by_hour = slots_per_day(minutes)
        full = max(by_hour.values())
        weeks = params.read_window_days // 7   # every weekday occurs at least this often
        for failure in (0.0, 0.05, 0.125):
            ok = 1 - failure
            profile = {slots: first_day(params.p95_min_samples, slots * ok,
                                        params.profile_window_days) for slots in by_hour.values()}
            rhythm = {slots: first_week(params.central_min_samples, slots * ok, weeks)
                      for slots in by_hour.values()}
            rows.append([
                f"{minutes} min", f"{failure:.1%}".replace(".0%", "%"),
                f"day {math.ceil(params.p95_min_samples / (peak * ok))}",
                profile[full], partly_covered(by_hour, profile.get), rhythm[full],
                partly_covered(by_hour, rhythm.get),
                f"{1 - params.p95_min_samples / (peak * params.audit_block_days):.0%}",
            ])
    return ["## 5. When pooled statistics first appear", "",
            f"Days of collection before each statistic clears its floor, at 0%, 5% and 12.5% of "
            f"calls failed (12.5% is panel_model's rate). Ledger BTI and PTI pool every "
            f"peak-hour call over {params.read_window_days} days (floor "
            f"{params.p95_min_samples}). The 24-hour profile and the route "
            f"comparison pool one clock hour over {params.profile_window_days} days (floor "
            f"{params.p95_min_samples}); hours the peak windows only partly cover get fewer "
            f"slots. The weekly rhythm matrix takes a median per weekday and hour over "
            f"{params.read_window_days} days (floor {params.central_min_samples}). `block "
            "slack`: the share of a 14-day block's peak calls that can fail before the block "
            "misses the audit's floor.", "",
            *table(["peak cadence", "failed", "ledger BTI, PTI", "profile, full peak hours",
                    "profile, partly covered hours", "rhythm, full hours",
                    "rhythm, partly covered hours", "block slack"], rows),
            "", "`never`: not within the window, however long the corridor runs.", ""]


def verdict_lines(verdicts, summary: pd.DataFrame) -> list[str]:
    s = summary[summary["minutes"] == 30]
    lines = ["## Verdict", ""]
    for transient in TRANSIENT:
        ok = [(f, best) for q, f, best in verdicts if q == transient and best]
        last_ok = max(ok, key=lambda item: item[0]) if ok else None
        first_bad = min((f for q, f, best in verdicts if q == transient and not best),
                        default=None)
        if not ok:
            lines.append(f"- q = {transient:.0%}: no 30-minute panel satisfies all three at any "
                         "failure rate swept.")
            continue
        widest_at_low = max(ok, key=lambda item: item[1][0])
        lines.append(
            f"- q = {transient:.0%}: the widest panel satisfying all three is "
            f"{widest_at_low[1][0]} ids ({widest_at_low[1][0] - TREATED_IDS} donors, "
            f"{widest_at_low[1][1]} night slots), at {widest_at_low[0]:.1%} of peak calls failed. "
            f"Some panel still qualifies up to {last_ok[0]:.1%} "
            f"({last_ok[1][0]} ids, {last_ok[1][1]} night slots)"
            + (f"; from {first_bad:.1%} none does." if first_bad is not None else "."))
    _, withheld = crossing(s["peak_fail"], s["withheld"], WITHHELD_LIMIT, rising=True)
    lines += ["", f"At 30-minute peaks the treated corridor alone withholds more than 20% of "
              f"audits once about {withheld} of peak calls fail, whatever the panel's width, "
              "because a 14-day block has 238 peak slots against a floor of 200.", ""]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--processes", type=int, default=9)
    parser.add_argument("--quick", action="store_true", help="4 replicates, not written")
    args = parser.parse_args()
    replicates = 4 if args.quick else args.replicates
    started = time.time()
    tasks = sweep_tasks(replicates) + ([] if args.quick else validation_tasks())
    with Pool(args.processes) as pool:
        records = pd.DataFrame(list(pool.imap_unordered(run_panel, tasks, chunksize=4)))
    if not args.quick:
        RECORDS.parent.mkdir(exist_ok=True)
        records.to_csv(RECORDS, index=False)
    sweep = records[records["seed"].str.startswith("free-tier|")]
    summary = summarise(sweep)
    widest_lines, verdicts = widest_report(summary)
    minutes = (time.time() - started) / 60
    text = "\n".join([
        "# What TomTom's free Routing allowance can support", "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `scripts/dev/free_tier.py`, "
        f"{replicates} panels per cadence and failure rate, {minutes:.0f} min. TomTom's "
        f"pricing page lists the Routing API at {MONTHLY_ALLOWANCE:,} free calls a month (read "
        "2026-09-14). Every design audits one of 4 treated corridors (the Miyapur-Allwyn "
        "package, both directions) with 14-day blocks, 12 pre blocks and a 28-day post period. "
        "Panels are `scripts/dev/panel_model.py`'s, whose failure structure is an assumption; "
        "nobody has measured TomTom's failure rate from Hyderabad.", "",
        *verdict_lines(verdicts, summary),
        *budget_report(), *breaking_report(summary), *widest_lines, *night_report(),
        *pooling_report(),
        *([] if args.quick else validation_report(records)),
    ]) + "\n"
    print(text)
    if not args.quick:
        OUT.write_text(text)
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
