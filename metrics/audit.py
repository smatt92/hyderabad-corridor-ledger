"""Intervention audit: synthetic control on pooled BTI, with placebos.

BTI is a property of a distribution. Every BTI here pools successful peak-hour
calls over one block of audit_block_days days or over one whole period, and is
used only at the p95 floor. Nothing is averaged from daily values.

Periods are fixed by the intervention date:
  pre     audit_pre_blocks blocks before the change
  settle  audit_settle_days days from the change, excluded
  post    audit_post_blocks blocks after settling

Donors are corridors that no intervention touches and that are not in the
treated corridor's pair: traffic diverting onto a paired alternate is a
consequence of the intervention, so that corridor is contaminated, not a
control. A donor also needs every pre block at the floor and, once the post
period has closed, its pooled post BTI at the floor. Every excluded corridor
is published with its reason.

Synthetic control, the headline. Weights are non-negative, sum to one, and
minimise the squared error between the treated corridor's demeaned pre-block
BTI series and the weighted donors' (Abadie et al.). Demeaning lets an outer
ring road segment and an inner-city arterial match in behaviour without
matching in level; the level difference is absorbed as a fixed shift. Then

    effect = (treated_post - synthetic_post) - (treated_pre - synthetic_pre)

with every BTI pooled once over its whole period and synthetic = sum of
weight x donor BTI. The interval is a percentile bootstrap that resamples
calls within each corridor and period with the weights held fixed. The weights
are published donor by donor.

Placebos. The same procedure runs with each donor in turn as the treated
corridor, its own pair excluded from its pool. The treated corridor's post/pre
RMSPE ratio is ranked among the placebos'; the permutation p-value is
(1 + placebos at least as large) / (1 + placebos). The verdict says plainly
when the treated effect is not extreme, and when there are too few placebos
for any effect to be.

Cross-check. The equal-weight mean of the same donors' pooled BTIs, over the
same periods, with the same bootstrap. Both estimates are published, with the
gap between them and whether they disagree.

Partial post period. The headline waits for the post period to close, so it is
fixed-horizon. Each completed post block gives a gap between the treated
corridor's block BTI and the synthetic one; an always-valid confidence sequence
on the running mean of those gaps (metrics.confseq) may be read after every
block without inflating error.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import nnls

from metrics import pooled
from metrics.cells import local_day_hour
from metrics.confseq import running_cs, running_mean_sd
from metrics.params import Params

NAN = float("nan")
ACTIVE_WEIGHT = 1e-9

AUDIT_COLUMNS = [
    "intervention_id", "corridor_id", "status", "effective_day", "settle_days", "pre_start",
    "pre_end", "settle_start", "settle_end", "post_start", "post_end", "block_days", "pre_blocks",
    "post_blocks", "post_blocks_complete", "n_pre", "n_post", "n_donors", "treated_pre",
    "treated_post", "synthetic_pre", "synthetic_post", "effect", "ci_low", "ci_high", "pre_rmspe",
    "post_rmspe", "rmspe_ratio", "n_placebos", "placebo_p_value", "placebo_extreme",
    "placebo_verdict", "equal_control_pre", "equal_control_post", "equal_effect", "equal_ci_low",
    "equal_ci_high", "estimator_gap", "estimators_disagree", "cs_blocks", "cs_mean", "cs_low",
    "cs_high", "alpha", "resamples", "missing_rate", "low_confidence",
]
DONOR_COLUMNS = [
    "intervention_id", "corridor_id", "included", "weight", "exclusion", "n_pre", "n_post",
    "pre_bti", "post_bti",
]
PLACEBO_COLUMNS = [
    "intervention_id", "corridor_id", "effect", "pre_rmspe", "post_rmspe", "rmspe_ratio",
    "poor_pre_fit", "weights",
]
BLOCK_COLUMNS = [
    "intervention_id", "period", "block", "block_start", "block_end", "complete", "n_treated",
    "treated_bti", "synthetic_bti", "gap", "running_mean", "cs_low", "cs_high",
]
TABLES = {"intervention_audit": AUDIT_COLUMNS, "audit_donors": DONOR_COLUMNS,
          "audit_placebos": PLACEBO_COLUMNS, "audit_blocks": BLOCK_COLUMNS}


def simplex_weights(y: np.ndarray, x: np.ndarray, penalty: float = 1e4) -> np.ndarray:
    """argmin ||y - X w||^2 subject to w >= 0 and sum(w) = 1.

    NNLS with the sum constraint appended as a heavily weighted row, then
    renormalised to remove the residual violation.
    """
    a = np.vstack([x, np.full(x.shape[1], penalty)])
    b = np.append(y, penalty)
    w, _ = nnls(a, b)
    total = w.sum()
    return w / total if total > 0 else np.full(x.shape[1], 1 / x.shape[1])


@dataclass(frozen=True)
class Fit:
    """Donor weights fitted on demeaned pre blocks, and the level shift."""
    weights: np.ndarray
    shift: float

    def synthetic(self, rows: np.ndarray) -> np.ndarray:
        """Synthetic BTI for rows of donor BTIs, one column per donor. Donors with no
        weight do not enter, so a missing value there does not void the row."""
        active = self.weights > ACTIVE_WEIGHT
        return rows[:, active] @ self.weights[active] + self.shift


def fit(y_pre: np.ndarray, x_pre: np.ndarray) -> Fit:
    w = simplex_weights(y_pre - y_pre.mean(), x_pre - x_pre.mean(axis=0))
    return Fit(w, float(y_pre.mean() - x_pre.mean(axis=0) @ w))


def periods(effective_day: pd.Timestamp, params: Params = Params()) -> dict:
    """The fixed periods around a change, as inclusive local days."""
    step = pd.Timedelta(days=params.audit_block_days)
    day = pd.Timedelta(days=1)
    post_start = effective_day + pd.Timedelta(days=params.audit_settle_days)
    return {
        "pre_start": effective_day - params.audit_pre_blocks * step,
        "pre_end": effective_day - day,
        "settle_start": effective_day,
        "settle_end": post_start - day,
        "post_start": post_start,
        "post_end": post_start + params.audit_post_blocks * step - day,
    }


def blocks(span: dict, period: str, params: Params = Params()) -> list[tuple[pd.Timestamp, ...]]:
    """(start, end) of each block of a period, inclusive local days."""
    step = pd.Timedelta(days=params.audit_block_days)
    count = params.audit_pre_blocks if period == "pre" else params.audit_post_blocks
    start = span[f"{period}_start"]
    return [(start + k * step, start + (k + 1) * step - pd.Timedelta(days=1)) for k in range(count)]


def rmspe(gaps) -> float:
    gaps = np.asarray(gaps, dtype=float)
    gaps = gaps[~np.isnan(gaps)]
    return float(np.sqrt(np.mean(gaps**2))) if len(gaps) else NAN


def rmspe_ratio(post: float, pre: float) -> float:
    return post / pre if pre > 0 and not np.isnan(post) else NAN


def placebo_summary(treated_ratio: float, placebo_ratios, alpha: float) -> tuple[float, bool, str]:
    """(permutation p-value, extreme, plain verdict) for the treated post/pre RMSPE ratio."""
    ratios = [r for r in placebo_ratios if not np.isnan(r)]
    n = len(ratios)
    if np.isnan(treated_ratio):
        return NAN, False, ("The treated corridor's post/pre fit ratio could not be computed, "
                            "so it is not ranked against placebos.")
    if n == 0:
        return NAN, False, ("No placebo could be run: no donor had another donor to be matched "
                            "against, so the effect cannot be judged extreme or ordinary.")
    at_least = sum(r >= treated_ratio for r in ratios)
    p = (1 + at_least) / (1 + n)
    if p <= alpha:
        return p, True, (
            f"Extreme among placebos: {at_least} of {n} placebo runs on untreated donors show a "
            f"post/pre fit ratio at least as large as the treated corridor's "
            f"(permutation p = {p:.3f})."
        )
    verdict = (
        f"Not extreme: {at_least} of {n} placebo runs on untreated donors show a post/pre fit "
        f"ratio at least as large as the treated corridor's (permutation p = {p:.2f}). This audit "
        "cannot distinguish the change from ordinary variation among these corridors."
    )
    if 1 / (1 + n) > alpha:
        verdict += (f" With {n} placebos the smallest attainable p is {1 / (1 + n):.2f}, above "
                    f"{alpha:g}, so no effect could be called extreme.")
    return p, False, verdict


def estimators_disagree(effect: float, low: float, high: float,
                        equal: float, equal_low: float, equal_high: float) -> bool:
    """Opposite signs, or either estimate outside the other's interval."""
    if np.isnan([effect, low, high, equal, equal_low, equal_high]).any():
        return False
    opposite = effect * equal < 0
    outside = not (equal_low <= effect <= equal_high) or not (low <= equal <= high)
    return bool(opposite or outside)


class Calls:
    """Each corridor's successful peak-hour calls, sliced by local day."""

    def __init__(self, peak: pd.DataFrame):
        self._by = {
            cid: (group["day"].to_numpy(dtype="datetime64[ns]"),
                  group["travel_time_s"].to_numpy(dtype=float))
            for cid, group in peak.groupby("corridor_id")
        }
        self._cache: dict = {}

    @property
    def corridors(self) -> set[str]:
        return set(self._by)

    def between(self, corridor_id: str, start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray:
        key = (corridor_id, start, end)
        if key not in self._cache:
            days, values = self._by.get(corridor_id, (np.empty(0, "datetime64[ns]"), np.empty(0)))
            inside = (days >= np.datetime64(start)) & (days <= np.datetime64(end))
            self._cache[key] = pooled.clean(values[inside])
        return self._cache[key]


def pooled_bti(values: np.ndarray, params: Params) -> float:
    """BTI of pooled calls, NaN below the p95 floor."""
    if len(values) < params.p95_min_samples:
        return NAN
    return float(pooled.bti_rows(values[np.newaxis, :])[0])


def audit_one(calls: Calls, cells: pd.DataFrame, pairs: dict, intervention_id: str,
              treated: str, treated_all: set[str], effective_day: pd.Timestamp,
              last_day: pd.Timestamp, params: Params) -> dict[str, list[dict]]:
    span = periods(effective_day, params)
    pre_blocks, post_blocks = blocks(span, "pre", params), blocks(span, "post", params)
    floor = params.p95_min_samples

    def block_bti(corridor_id, start, end) -> tuple[int, float]:
        values = calls.between(corridor_id, start, end)
        return len(values), pooled_bti(values, params)

    complete = [end <= last_day for _, end in post_blocks]
    closed = all(complete)
    seen_post_end = min(span["post_end"], last_day)
    t_pre_blocks = [block_bti(treated, s, e) for s, e in pre_blocks]
    t_pre = calls.between(treated, span["pre_start"], span["pre_end"])
    t_post = calls.between(treated, span["post_start"], seen_post_end)

    days = cells["day"]
    involved = cells[(cells["corridor_id"] == treated) & (
        days.between(span["pre_start"], span["pre_end"])
        | days.between(span["post_start"], span["post_end"]))]
    n_expected, n_ok = involved["n_expected"].sum(), involved["n_ok"].sum()
    rate = float((n_expected - n_ok) / n_expected) if n_expected else NAN

    audit = {
        "intervention_id": intervention_id, "corridor_id": treated, "effective_day": effective_day,
        "settle_days": params.audit_settle_days, **span, "block_days": params.audit_block_days,
        "pre_blocks": params.audit_pre_blocks, "post_blocks": params.audit_post_blocks,
        "post_blocks_complete": int(sum(complete)), "n_pre": len(t_pre), "n_post": len(t_post),
        "n_donors": 0, "n_placebos": 0, "placebo_extreme": False,
        "treated_pre": pooled_bti(t_pre, params), "alpha": params.bootstrap_alpha,
        "resamples": params.bootstrap_resamples, "missing_rate": rate,
        "low_confidence": bool(np.isnan(rate) or rate > params.low_confidence_missing_rate),
    }

    treated_pair = pairs.get(treated)
    donors, candidates = {}, []
    for c in sorted((set(cells["corridor_id"]) | calls.corridors) - {treated}):
        pre_values = calls.between(c, span["pre_start"], span["pre_end"])
        post_values = calls.between(c, span["post_start"], seen_post_end)
        if c in treated_all:
            reason = "treated"
        elif treated_pair is not None and pairs.get(c) == treated_pair:
            reason = "same_pair"
        elif any(block_bti(c, s, e)[0] < floor for s, e in pre_blocks):
            reason = "incomplete_pre"
        elif closed and len(post_values) < floor:
            reason = "insufficient_post"
        else:
            reason = None
            candidates.append(c)
        donors[c] = {
            "intervention_id": intervention_id, "corridor_id": c, "included": reason is None,
            "weight": NAN, "exclusion": reason, "n_pre": len(pre_values),
            "n_post": len(post_values), "pre_bti": pooled_bti(pre_values, params),
            "post_bti": pooled_bti(post_values, params) if closed else NAN,
        }

    out = {"intervention_audit": [audit], "audit_donors": [], "audit_placebos": [],
           "audit_blocks": []}

    def block_row(period, k, start, end, done, n, treated_bti, synthetic=NAN) -> dict:
        return {"intervention_id": intervention_id, "period": period, "block": k,
                "block_start": start, "block_end": end, "complete": done, "n_treated": n,
                "treated_bti": treated_bti, "synthetic_bti": synthetic,
                "gap": treated_bti - synthetic, "running_mean": NAN, "cs_low": NAN, "cs_high": NAN}

    def finish(status: str) -> dict[str, list[dict]]:
        audit["status"] = status
        out["audit_donors"] = [donors[c] for c in sorted(donors)]
        return out

    if last_day < span["pre_end"] or any(n < floor for n, _ in t_pre_blocks):
        out["audit_blocks"] = [block_row("pre", k, s, e, e <= last_day, n, b)
                               for k, ((s, e), (n, b)) in enumerate(zip(pre_blocks, t_pre_blocks,
                                                                        strict=True))]
        return finish("insufficient_pre")
    if closed and len(t_post) < floor:
        return finish("insufficient_post")
    if not candidates:
        return finish("no_controls")

    audit["n_donors"] = len(candidates)
    y_pre = np.array([b for _, b in t_pre_blocks])
    x_pre = np.array([[block_bti(c, s, e)[1] for c in candidates] for s, e in pre_blocks])
    model = fit(y_pre, x_pre)
    for c, w in zip(candidates, model.weights, strict=True):
        donors[c]["weight"] = round(float(w), 6)
    pre_synthetic = model.synthetic(x_pre)
    pre_residuals = y_pre - pre_synthetic
    audit["pre_rmspe"] = rmspe(pre_residuals)
    rows = [block_row("pre", k, s, e, True, n, b, float(synthetic))
            for k, ((s, e), (n, b), synthetic)
            in enumerate(zip(pre_blocks, t_pre_blocks, pre_synthetic, strict=True))]

    gaps = []
    for k, ((s, e), done) in enumerate(zip(post_blocks, complete, strict=True)):
        if not done:
            rows.append(block_row("post", k, s, e, False,
                                  len(calls.between(treated, s, min(e, last_day))), NAN))
            continue
        n, b = block_bti(treated, s, e)
        donor_row = np.array([[block_bti(c, s, e)[1] for c in candidates]])
        synthetic = float(model.synthetic(donor_row)[0])
        rows.append(block_row("post", k, s, e, True, n, b, synthetic))
        if not np.isnan(rows[-1]["gap"]):
            gaps.append((len(rows) - 1, rows[-1]["gap"]))

    if gaps:
        values = np.array([g for _, g in gaps])
        half = params.cs_alpha / 2
        m = len(pre_residuals)
        pre_sd = float(np.std(pre_residuals, ddof=1)) if m > 1 else 0.0
        intercept = float(stats.t.ppf(1 - half / 2, m - 1) * pre_sd / np.sqrt(m)) if m > 1 else 0.0
        _, running_sd = running_mean_sd(values)
        mean, low, high = running_cs(values, half, params.audit_post_blocks,
                                     sd=np.fmax(running_sd, pre_sd))
        for (index, _), mu, lo, hi in zip(gaps, mean, low, high, strict=True):
            rows[index] |= {"running_mean": float(mu), "cs_low": float(lo - intercept),
                            "cs_high": float(hi + intercept)}
        audit |= {"cs_blocks": len(values), "cs_mean": float(mean[-1]),
                  "cs_low": float(low[-1] - intercept), "cs_high": float(high[-1] + intercept)}
    out["audit_blocks"] = rows

    if not any(complete):
        return finish("post_pending")
    if not closed:
        return finish("post_partial")

    key = ("audit", intervention_id)

    def with_draws(corridor_id: str, period: str) -> tuple[float, np.ndarray]:
        values = calls.between(corridor_id, span[f"{period}_start"], span[f"{period}_end"])
        (sample,) = pooled.draws(values, [pooled.bti_rows], params, (*key, corridor_id, period))
        return pooled_bti(values, params), sample

    tp, tp_draws = with_draws(treated, "pre")
    tq, tq_draws = with_draws(treated, "post")
    dp, dp_draws = (np.array(v) for v in zip(*(with_draws(c, "pre") for c in candidates),
                                             strict=True))
    dq, dq_draws = (np.array(v) for v in zip(*(with_draws(c, "post") for c in candidates),
                                             strict=True))
    w = model.weights
    synthetic_pre, synthetic_post = float(w @ dp), float(w @ dq)
    effect = (tq - synthetic_post) - (tp - synthetic_pre)
    low, high = pooled.interval((tq_draws - w @ dq_draws) - (tp_draws - w @ dp_draws), params)
    equal_pre, equal_post = float(dp.mean()), float(dq.mean())
    equal = (tq - tp) - (equal_post - equal_pre)
    equal_low, equal_high = pooled.interval(
        (tq_draws - tp_draws) - (dq_draws.mean(axis=0) - dp_draws.mean(axis=0)), params)
    audit["post_rmspe"] = rmspe([g for _, g in gaps])
    treated_ratio = rmspe_ratio(audit["post_rmspe"], audit["pre_rmspe"])

    ratios = []
    for p_index, p in enumerate(candidates):
        pool = [i for i, c in enumerate(candidates)
                if c != p and not (pairs.get(p) is not None and pairs.get(c) == pairs.get(p))]
        if not pool:
            continue
        placebo = fit(x_pre[:, p_index], x_pre[:, pool])
        placebo_pre = rmspe(x_pre[:, p_index] - placebo.synthetic(x_pre[:, pool]))
        placebo_gaps = []
        for s, e in post_blocks:
            row = np.array([[block_bti(candidates[i], s, e)[1] for i in pool]])
            placebo_gaps.append(block_bti(p, s, e)[1] - float(placebo.synthetic(row)[0]))
        placebo_post = rmspe(placebo_gaps)
        ratio = rmspe_ratio(placebo_post, placebo_pre)
        ratios.append(ratio)
        out["audit_placebos"].append({
            "intervention_id": intervention_id, "corridor_id": p,
            "effect": float((dq[p_index] - placebo.weights @ dq[pool])
                            - (dp[p_index] - placebo.weights @ dp[pool])),
            "pre_rmspe": placebo_pre, "post_rmspe": placebo_post, "rmspe_ratio": ratio,
            "poor_pre_fit": bool(placebo_pre > params.audit_poor_fit_ratio * audit["pre_rmspe"]),
            "weights": {candidates[i]: round(float(v), 6)
                        for i, v in zip(pool, placebo.weights, strict=True) if v > ACTIVE_WEIGHT},
        })
    p_value, extreme, verdict = placebo_summary(treated_ratio, ratios, params.bootstrap_alpha)

    audit |= {
        "treated_pre": tp, "treated_post": tq, "synthetic_pre": synthetic_pre,
        "synthetic_post": synthetic_post, "effect": effect, "ci_low": low, "ci_high": high,
        "rmspe_ratio": treated_ratio, "n_placebos": sum(not np.isnan(r) for r in ratios),
        "placebo_p_value": p_value, "placebo_extreme": extreme, "placebo_verdict": verdict,
        "equal_control_pre": equal_pre, "equal_control_post": equal_post,
        "equal_effect": equal, "equal_ci_low": equal_low, "equal_ci_high": equal_high,
        "estimator_gap": effect - equal,
        "estimators_disagree": estimators_disagree(effect, low, high, equal, equal_low, equal_high),
    }
    return finish("ok")


def intervention_audits(
    tti: pd.DataFrame, cells: pd.DataFrame, corridors: pd.DataFrame,
    interventions: pd.DataFrame, params: Params = Params(),
) -> dict[str, pd.DataFrame]:
    """The audit tables. tti: successful calls (corridor_id, requested_at, day,
    travel_time_s); cells: hourly cells, for missingness and the last day with data;
    corridors: pair_id per corridor, for the donor exclusions."""
    rows: dict[str, list[dict]] = {name: [] for name in TABLES}
    if not interventions.empty and not tti.empty:
        calls = Calls(tti[pooled.is_peak(tti["requested_at"], params)])
        declared = corridors.reindex(columns=["corridor_id", "pair_id"])
        pairs = {r.corridor_id: (None if pd.isna(r.pair_id) else r.pair_id)
                 for r in declared.itertuples(index=False)}
        last_day = cells.loc[cells["n_ok"] > 0, "day"].max()
        treated_all = set(interventions["corridor_id"])
        for iv in interventions.itertuples(index=False):
            effective = local_day_hour(pd.to_datetime(pd.Series([iv.effective_at]), utc=True))
            result = audit_one(calls, cells, pairs, iv.id, iv.corridor_id, treated_all,
                               effective["day"].iloc[0], last_day, params)
            for name, found in result.items():
                rows[name].extend(found)
    return {name: pd.DataFrame(rows[name]).reindex(columns=columns)
            for name, columns in TABLES.items()}
