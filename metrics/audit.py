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
period has closed, its pooled post BTI at the floor. Every corridor considered
is published with its weight or the reason it was excluded.

Donor selection is not neutral. Failed calls cluster at peak hours on the
most congested roads, so the corridors dropped for a thin pre block are
disproportionately the congested ones and the donor pool leans toward
well-behaved roads. Each audit therefore publishes the excluded corridors'
missing rate and BTI beside the donors', and reruns the estimate under stricter
and looser completeness thresholds (VARIANTS). sensitivity_material says
whether the effect moves outside its interval as the threshold moves.

Synthetic control, the headline. Weights are non-negative, sum to one, and
minimise the squared error between the treated corridor's demeaned pre-block
BTI series and the weighted donors' (Abadie et al.). Demeaning lets an outer
ring road segment and an inner-city arterial match in behaviour without
matching in level; the level difference is absorbed as a fixed shift. Then

    effect = (treated_post - synthetic_post) - (treated_pre - synthetic_pre)

with every BTI pooled once over its whole period and synthetic = sum of
weight x donor BTI. The interval is a percentile bootstrap over whole units of
audit_bootstrap_days days: each resample draws units of a period with
replacement, the same units for every corridor, so week-to-week drift and
city-wide shocks move the interval as they move the estimate. Consecutive days
on one corridor are not independent, and resampling single calls (still
available as audit_bootstrap = "calls") gives intervals that are too narrow.
Weights are held fixed across resamples.

Overfitting. With few pre blocks and many donors the weights can reproduce the
treated pre series exactly, and an exact fit predicts nothing. Each audit
publishes the in-sample pre RMSPE beside a leave-one-block-out RMSPE (each pre
block predicted by weights fitted on the others), the number of active donors,
and pre_fit_overfit when the in-sample fit is tighter than audit_overfit_ratio
of the held-out one. audit_max_donors caps the active donors.

Placebos. The same procedure runs with each donor in turn as the treated
corridor, its own pair excluded from its pool. The treated corridor's post/pre
RMSPE ratio is ranked among the placebos'. With n placebos, rank r of n + 1
gives permutation p = r / (n + 1), and no p can be smaller than 1 / (n + 1).
The rank, the placebo count and that floor are published with every p, and the
verdict says plainly when the effect is not extreme.

Cross-check. The equal-weight mean of the same donors' pooled BTIs, over the
same periods, with the same bootstrap. Both estimates are published, with the
gap between them and whether they disagree.

Partial post period. The headline waits for the post period to close, so it is
fixed-horizon. Each completed post block gives a gap between the treated
corridor's block BTI and the synthetic one; an always-valid confidence sequence
on the running mean of those gaps (metrics.confseq) may be read after every
block without inflating error.
"""

import math
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
MIN_FIT_BLOCKS = 3
# (name, multiple of the p95 floor every donor pre block must reach, short blocks allowed).
# A short block has no BTI, so a donor admitted with one is fitted only on the blocks
# every donor in the pool has; nothing is filled in.
VARIANTS = (
    ("base", 1.0, 0),
    ("strict_125", 1.25, 0),
    ("strict_150", 1.5, 0),
    ("relaxed_one_block", 1.0, 1),
)

AUDIT_COLUMNS = [
    "intervention_id", "corridor_id", "status", "effective_day", "settle_days", "pre_start",
    "pre_end", "settle_start", "settle_end", "post_start", "post_end", "block_days", "pre_blocks",
    "post_blocks", "post_blocks_complete", "n_pre", "n_post", "n_donors", "treated_pre",
    "treated_post", "synthetic_pre", "synthetic_post", "effect", "ci_low", "ci_high", "pre_rmspe",
    "post_rmspe", "rmspe_ratio", "cv_pre_rmspe", "overfit_ratio", "pre_fit_overfit",
    "n_active_donors", "n_placebos", "placebo_rank", "placebo_p_value",
    "placebo_p_floor", "placebo_extreme", "placebo_verdict", "equal_control_pre",
    "equal_control_post", "equal_effect", "equal_ci_low", "equal_ci_high", "estimator_gap",
    "estimators_disagree", "cs_blocks", "cs_mean", "cs_low", "cs_high",
    "n_excluded_incomplete_pre", "included_pre_missing_rate", "excluded_pre_missing_rate",
    "included_pre_bti", "excluded_pre_bti", "sensitivity_min_effect", "sensitivity_max_effect",
    "sensitivity_material", "alpha", "resamples", "missing_rate", "low_confidence",
]
DONOR_COLUMNS = [
    "intervention_id", "corridor_id", "included", "weight", "exclusion", "n_pre", "n_post",
    "pre_bti", "post_bti", "pre_missing_rate", "short_pre_blocks", "min_pre_block_n",
]
PLACEBO_COLUMNS = [
    "intervention_id", "corridor_id", "effect", "pre_rmspe", "cv_pre_rmspe", "post_rmspe",
    "rmspe_ratio", "poor_pre_fit", "weights",
]
BLOCK_COLUMNS = [
    "intervention_id", "period", "block", "block_start", "block_end", "complete", "n_treated",
    "treated_bti", "synthetic_bti", "gap", "running_mean", "cs_low", "cs_high",
]
SENSITIVITY_COLUMNS = [
    "intervention_id", "variant", "block_floor", "max_short_blocks", "status", "n_donors",
    "n_fit_blocks", "effect", "ci_low", "ci_high", "equal_effect", "placebo_rank", "n_placebos",
    "placebo_p_value", "placebo_p_floor",
]
TABLES = {"intervention_audit": AUDIT_COLUMNS, "audit_donors": DONOR_COLUMNS,
          "audit_placebos": PLACEBO_COLUMNS, "audit_blocks": BLOCK_COLUMNS,
          "audit_sensitivity": SENSITIVITY_COLUMNS}
HEADLINE = (
    "treated_pre", "treated_post", "synthetic_pre", "synthetic_post", "effect", "ci_low",
    "ci_high", "equal_control_pre", "equal_control_post", "equal_effect", "equal_ci_low",
    "equal_ci_high",
)
PLACEBO_SUMMARY = (
    "pre_rmspe", "post_rmspe", "rmspe_ratio", "n_placebos", "placebo_rank", "placebo_p_value",
    "placebo_p_floor", "placebo_extreme", "placebo_verdict",
)


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


def fit(y_pre: np.ndarray, x_pre: np.ndarray, weights: str = "demeaned",
        max_donors: int = 0) -> Fit:
    """Simplex weights on the pre blocks: non-negative and summing to one, so the
    synthetic corridor never extrapolates beyond its donors. max_donors > 0 caps the
    nonzero weights."""
    if max_donors and x_pre.shape[1] > max_donors:
        return sparse_fit(y_pre, x_pre, weights, max_donors)
    if weights == "levels":
        return Fit(simplex_weights(y_pre, x_pre), 0.0)
    w = simplex_weights(y_pre - y_pre.mean(), x_pre - x_pre.mean(axis=0))
    return Fit(w, float(y_pre.mean() - x_pre.mean(axis=0) @ w))


def sparse_fit(y_pre: np.ndarray, x_pre: np.ndarray, weights: str, max_donors: int) -> Fit:
    """Greedy forward selection: add the donor that most reduces pre-period squared
    error, refit on the chosen donors, stop at max_donors or when nothing improves."""
    chosen: list[int] = []
    remaining = list(range(x_pre.shape[1]))
    best = np.inf
    while remaining and len(chosen) < max_donors:
        trials = []
        for j in remaining:
            columns = [*chosen, j]
            candidate = fit(y_pre, x_pre[:, columns], weights)
            error = y_pre - candidate.synthetic(x_pre[:, columns])
            trials.append((float(np.sum(error**2)), j))
        error_sum, j = min(trials)
        if error_sum >= best:
            break
        chosen.append(j)
        remaining.remove(j)
        best = error_sum
    chosen_fit = fit(y_pre, x_pre[:, chosen], weights)
    full = np.zeros(x_pre.shape[1])
    full[chosen] = chosen_fit.weights
    return Fit(full, chosen_fit.shift)


def held_out_rmspe(y_pre: np.ndarray, x_pre: np.ndarray, weights: str = "demeaned",
                   max_donors: int = 0) -> float:
    """Leave-one-block-out RMSPE: each pre block predicted by weights fitted, donors
    selected included, on the other blocks."""
    if len(y_pre) < 3:
        return NAN
    residuals = []
    for k in range(len(y_pre)):
        keep = np.arange(len(y_pre)) != k
        held = fit(y_pre[keep], x_pre[keep], weights, max_donors)
        residuals.append(float(y_pre[k] - held.synthetic(x_pre[[k]])[0]))
    return rmspe(residuals)


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


def peak_hours(params: Params = Params()) -> set[int]:
    """Local hours that overlap a peak window."""
    return {h for h in range(24) for start, end in params.peak_minutes
            if h * 60 < end and h * 60 + 60 > start}


def rmspe(gaps) -> float:
    gaps = np.asarray(gaps, dtype=float)
    gaps = gaps[~np.isnan(gaps)]
    return float(np.sqrt(np.mean(gaps**2))) if len(gaps) else NAN


def rmspe_ratio(post: float, pre: float) -> float:
    return post / pre if pre > 0 and not np.isnan(post) else NAN


def placebo_summary(treated_ratio: float, placebo_ratios,
                    alpha: float) -> tuple[int | None, float, float, bool, str]:
    """(rank, permutation p, smallest attainable p, extreme, plain verdict) for the
    treated post/pre RMSPE ratio among the placebo ratios. Rank 1 is the largest;
    ties count against the treated corridor."""
    ratios = [r for r in placebo_ratios if not np.isnan(r)]
    n = len(ratios)
    if np.isnan(treated_ratio):
        return None, NAN, NAN, False, ("The treated corridor's post/pre fit ratio could not be "
                                       "computed, so it is not ranked against placebos.")
    if n == 0:
        return None, NAN, NAN, False, (
            "No placebo could be run: no donor had another donor to be matched against, so the "
            "effect cannot be judged extreme or ordinary.")
    at_least = sum(r >= treated_ratio for r in ratios)
    rank, total = 1 + at_least, n + 1
    p, floor = rank / total, 1 / total
    resolution = (f"rank {rank} of {total} ({n} placebo runs on untreated donors; the smallest "
                  f"attainable p is 1/{total} = {floor:.3f}), permutation p = {rank}/{total} = "
                  f"{p:.3f}")
    if p <= alpha:
        return rank, p, floor, True, f"Extreme among placebos: {resolution}."
    verdict = (f"Not extreme: {resolution}. {at_least} of {n} placebo runs show a post/pre fit "
               "ratio at least as large as the treated corridor's, so this audit cannot "
               "distinguish the change from ordinary variation among these corridors.")
    if floor > alpha:
        verdict += f" With {n} placebos no effect could reach p = {alpha:g}."
    return rank, p, floor, False, verdict


def block_cs(gaps: np.ndarray, residuals: np.ndarray,
             params: Params) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(running mean, low, high) of the post-block gaps: an always-valid confidence
    sequence, its scale at least the pre residuals' sd, widened by a t interval for the
    pre-period level the gaps are measured from."""
    half = params.cs_alpha / 2
    m = len(residuals)
    pre_sd = float(np.std(residuals, ddof=1)) if m > 1 else 0.0
    intercept = float(stats.t.ppf(1 - half / 2, m - 1) * pre_sd / np.sqrt(m)) if m > 1 else 0.0
    _, running_sd = running_mean_sd(gaps)
    mean, low, high = running_cs(gaps, half, params.audit_post_blocks,
                                 sd=np.fmax(running_sd, pre_sd))
    return mean, low - intercept, high + intercept


def estimators_disagree(effect: float, low: float, high: float,
                        equal: float, equal_low: float, equal_high: float) -> bool:
    """Opposite signs, or either estimate outside the other's interval."""
    if np.isnan([effect, low, high, equal, equal_low, equal_high]).any():
        return False
    opposite = effect * equal < 0
    outside = not (equal_low <= effect <= equal_high) or not (low <= equal <= high)
    return bool(opposite or outside)


def sensitivity_summary(effect: float, low: float, high: float,
                        variant_effects) -> tuple[float, float, bool | None]:
    """(smallest, largest effect across threshold variants, material). Material means a
    variant's effect has the opposite sign or falls outside the headline interval."""
    values = [e for e in variant_effects if not np.isnan(e)]
    if not values or np.isnan([effect, low, high]).any():
        return NAN, NAN, None
    material = any(e * effect < 0 or not (low <= e <= high) for e in values)
    return min(values), max(values), bool(material)


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


class Audit:
    """One intervention's periods and blocks, with cached pooled BTIs and draws."""

    def __init__(self, calls: Calls, pairs: dict, intervention_id: str, treated: str,
                 effective_day: pd.Timestamp, last_day: pd.Timestamp, params: Params):
        self.calls, self.pairs, self.params = calls, pairs, params
        self.intervention_id, self.treated = intervention_id, treated
        self.span = periods(effective_day, params)
        self.pre_blocks = blocks(self.span, "pre", params)
        self.post_blocks = blocks(self.span, "post", params)
        self.complete = [end <= last_day for _, end in self.post_blocks]
        self.closed = all(self.complete)
        self._pooled: dict = {}
        self._units: dict = {}

    def block(self, corridor_id: str, period: str, k: int) -> tuple[int, float]:
        start, end = (self.pre_blocks if period == "pre" else self.post_blocks)[k]
        values = self.calls.between(corridor_id, start, end)
        return len(values), pooled_bti(values, self.params)

    def units(self, period: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """The whole-day units a period is resampled in, audit_bootstrap_days long."""
        step = pd.Timedelta(days=self.params.audit_bootstrap_days)
        start, end = self.span[f"{period}_start"], self.span[f"{period}_end"]
        out = []
        while start <= end:
            out.append((start, min(start + step - pd.Timedelta(days=1), end)))
            start += step
        return out

    def unit_draws(self, period: str) -> np.ndarray:
        """The units each resample takes, shared by every corridor so city-wide shocks
        move the donors and the treated corridor together."""
        if period not in self._units:
            rng = pooled.generator(self.params, ("audit-units", self.intervention_id, period))
            n = len(self.units(period))
            self._units[period] = rng.integers(0, n, size=(self.params.bootstrap_resamples, n))
        return self._units[period]

    def pooled(self, corridor_id: str, period: str) -> tuple[float, np.ndarray]:
        """A corridor's BTI pooled over a whole period, and its bootstrap draws."""
        key = (corridor_id, period)
        if key not in self._pooled:
            values = self.calls.between(corridor_id, self.span[f"{period}_start"],
                                        self.span[f"{period}_end"])
            if self.params.bootstrap_resamples == 0:
                sample = np.empty(0)
            elif self.params.audit_bootstrap == "calls":
                (sample,) = pooled.draws(values, [pooled.bti_rows], self.params,
                                         ("audit", self.intervention_id, corridor_id, period))
            else:
                parts = [self.calls.between(corridor_id, s, e) for s, e in self.units(period)]
                sample = np.array([pooled_bti(np.concatenate([parts[i] for i in row]),
                                              self.params)
                                   for row in self.unit_draws(period)])
            self._pooled[key] = (pooled_bti(values, self.params), sample)
        return self._pooled[key]

    def fitter(self, y: np.ndarray, x: np.ndarray) -> Fit:
        return fit(y, x, self.params.audit_weights, self.params.audit_max_donors)

    def held_out(self, y: np.ndarray, x: np.ndarray) -> float:
        return held_out_rmspe(y, x, self.params.audit_weights, self.params.audit_max_donors)

    def same_pair(self, a: str, b: str) -> bool:
        pair = self.pairs.get(a)
        return pair is not None and self.pairs.get(b) == pair

    def pre_series(self, donors: list[str], fit_blocks: list[int]) -> tuple[np.ndarray, ...]:
        y = np.array([self.block(self.treated, "pre", k)[1] for k in fit_blocks])
        x = np.array([[self.block(c, "pre", k)[1] for c in donors] for k in fit_blocks])
        return y, x

    def post_row(self, donors: list[str], k: int) -> np.ndarray:
        return np.array([[self.block(c, "post", k)[1] for c in donors]])

    def fit_pool(self, donors: list[str], fit_blocks: list[int]):
        """(fit, pre residuals, pre synthetic, post synthetic per block, post gaps)."""
        y, x = self.pre_series(donors, fit_blocks)
        model = self.fitter(y, x)
        pre_synthetic = model.synthetic(x)
        post_synthetic = [float(model.synthetic(self.post_row(donors, k))[0]) if done else NAN
                          for k, done in enumerate(self.complete)]
        gaps = [self.block(self.treated, "post", k)[1] - synthetic
                for k, (synthetic, done) in enumerate(zip(post_synthetic, self.complete,
                                                          strict=True)) if done]
        return model, y - pre_synthetic, pre_synthetic, post_synthetic, gaps

    def headline(self, donors: list[str], weights: np.ndarray) -> dict:
        tp, tp_draws = self.pooled(self.treated, "pre")
        tq, tq_draws = self.pooled(self.treated, "post")
        dp = np.array([self.pooled(c, "pre")[0] for c in donors])
        dq = np.array([self.pooled(c, "post")[0] for c in donors])
        dp_draws = np.array([self.pooled(c, "pre")[1] for c in donors])
        dq_draws = np.array([self.pooled(c, "post")[1] for c in donors])
        synthetic_pre, synthetic_post = float(weights @ dp), float(weights @ dq)
        low, high = pooled.interval((tq_draws - weights @ dq_draws)
                                    - (tp_draws - weights @ dp_draws), self.params)
        equal_pre, equal_post = float(dp.mean()), float(dq.mean())
        equal_low, equal_high = pooled.interval(
            (tq_draws - tp_draws) - (dq_draws.mean(axis=0) - dp_draws.mean(axis=0)), self.params)
        return {
            "treated_pre": tp, "treated_post": tq, "synthetic_pre": synthetic_pre,
            "synthetic_post": synthetic_post,
            "effect": (tq - synthetic_post) - (tp - synthetic_pre), "ci_low": low, "ci_high": high,
            "equal_control_pre": equal_pre, "equal_control_post": equal_post,
            "equal_effect": (tq - tp) - (equal_post - equal_pre), "equal_ci_low": equal_low,
            "equal_ci_high": equal_high,
        }

    def placebo_runs(self, donors: list[str], fit_blocks: list[int],
                     treated_pre_rmspe: float) -> tuple[list[dict], list[float]]:
        x = np.array([[self.block(c, "pre", k)[1] for c in donors] for k in fit_blocks])
        dp = np.array([self.pooled(c, "pre")[0] for c in donors])
        dq = np.array([self.pooled(c, "post")[0] for c in donors])
        rows, ratios = [], []
        for i, placebo_id in enumerate(donors):
            pool = [j for j, c in enumerate(donors) if j != i and not self.same_pair(placebo_id, c)]
            if not pool:
                continue
            others = [donors[j] for j in pool]
            model = self.fitter(x[:, i], x[:, pool])
            pre = rmspe(x[:, i] - model.synthetic(x[:, pool]))
            post = rmspe([self.block(placebo_id, "post", k)[1]
                          - float(model.synthetic(self.post_row(others, k))[0])
                          for k in range(len(self.post_blocks))])
            ratio = rmspe_ratio(post, pre)
            ratios.append(ratio)
            rows.append({
                "intervention_id": self.intervention_id, "corridor_id": placebo_id,
                "effect": float((dq[i] - model.weights @ dq[pool])
                                - (dp[i] - model.weights @ dp[pool])),
                "pre_rmspe": pre, "cv_pre_rmspe": self.held_out(x[:, i], x[:, pool]),
                "post_rmspe": post, "rmspe_ratio": ratio,
                "poor_pre_fit": bool(pre > self.params.audit_poor_fit_ratio * treated_pre_rmspe),
                "weights": {c: round(float(v), 6) for c, v in zip(others, model.weights,
                                                                   strict=True)
                            if v > ACTIVE_WEIGHT},
            })
        return rows, ratios

    def estimate(self, donors: list[str], fit_blocks: list[int]) -> dict:
        """The full estimate for one donor pool: headline, cross-check and placebos."""
        model, residuals, _, _, gaps = self.fit_pool(donors, fit_blocks)
        pre, post = rmspe(residuals), rmspe(gaps)
        ratio = rmspe_ratio(post, pre)
        placebo_rows, ratios = self.placebo_runs(donors, fit_blocks, pre)
        rank, p, floor, extreme, verdict = placebo_summary(ratio, ratios,
                                                           self.params.bootstrap_alpha)
        return self.headline(donors, model.weights) | {
            "weights": model.weights, "placebos": placebo_rows, "pre_rmspe": pre,
            "post_rmspe": post, "rmspe_ratio": ratio,
            "n_placebos": sum(not np.isnan(r) for r in ratios), "placebo_rank": rank,
            "placebo_p_value": p, "placebo_p_floor": floor, "placebo_extreme": extreme,
            "placebo_verdict": verdict,
        }


def audit_one(calls: Calls, cells: pd.DataFrame, pairs: dict, intervention_id: str,
              treated: str, treated_all: set[str], effective_day: pd.Timestamp,
              last_day: pd.Timestamp, params: Params,
              sensitivity: bool = True) -> dict[str, list[dict]]:
    a = Audit(calls, pairs, intervention_id, treated, effective_day, last_day, params)
    span, floor = a.span, params.p95_min_samples
    all_blocks = list(range(params.audit_pre_blocks))
    seen_post_end = min(span["post_end"], last_day)
    t_pre_blocks = [a.block(treated, "pre", k) for k in all_blocks]
    t_pre = calls.between(treated, span["pre_start"], span["pre_end"])
    t_post = calls.between(treated, span["post_start"], seen_post_end)

    days = cells["day"]
    in_pre = days.between(span["pre_start"], span["pre_end"])
    involved = cells[(cells["corridor_id"] == treated)
                     & (in_pre | days.between(span["post_start"], span["post_end"]))]
    n_expected, n_ok = involved["n_expected"].sum(), involved["n_ok"].sum()
    rate = float((n_expected - n_ok) / n_expected) if n_expected else NAN
    peak = cells[in_pre & cells["hour"].isin(peak_hours(params))]
    peak = peak.groupby("corridor_id")[["n_expected", "n_ok"]].sum()
    pre_missing = (peak["n_expected"] - peak["n_ok"]) / peak["n_expected"]

    audit = {
        "intervention_id": intervention_id, "corridor_id": treated, "effective_day": effective_day,
        "settle_days": params.audit_settle_days, **span, "block_days": params.audit_block_days,
        "pre_blocks": params.audit_pre_blocks, "post_blocks": params.audit_post_blocks,
        "post_blocks_complete": int(sum(a.complete)), "n_pre": len(t_pre), "n_post": len(t_post),
        "n_donors": 0, "n_placebos": 0, "placebo_extreme": False,
        "treated_pre": pooled_bti(t_pre, params), "alpha": params.bootstrap_alpha,
        "resamples": params.bootstrap_resamples, "missing_rate": rate,
        "low_confidence": bool(np.isnan(rate) or rate > params.low_confidence_missing_rate),
    }

    donors, candidates, pre_counts, post_ok = {}, [], {}, {}
    for c in sorted((set(cells["corridor_id"]) | calls.corridors) - {treated}):
        counts = [a.block(c, "pre", k)[0] for k in all_blocks]
        pre_values = calls.between(c, span["pre_start"], span["pre_end"])
        post_values = calls.between(c, span["post_start"], seen_post_end)
        pre_counts[c] = counts
        post_ok[c] = not a.closed or len(post_values) >= floor
        short = sum(n < floor for n in counts)
        if c in treated_all:
            reason = "treated"
        elif a.same_pair(treated, c):
            reason = "same_pair"
        elif short:
            reason = "incomplete_pre"
        elif not post_ok[c]:
            reason = "insufficient_post"
        else:
            reason = None
            candidates.append(c)
        donors[c] = {
            "intervention_id": intervention_id, "corridor_id": c, "included": reason is None,
            "weight": NAN, "exclusion": reason, "n_pre": len(pre_values),
            "n_post": len(post_values), "pre_bti": pooled_bti(pre_values, params),
            "post_bti": pooled_bti(post_values, params) if a.closed else NAN,
            "pre_missing_rate": float(pre_missing.get(c, NAN)), "short_pre_blocks": short,
            "min_pre_block_n": min(counts),
        }

    def mean_of(ids: list[str], field: str) -> float:
        values = [donors[c][field] for c in ids if not np.isnan(donors[c][field])]
        return float(np.mean(values)) if values else NAN

    excluded = [c for c in donors if donors[c]["exclusion"] == "incomplete_pre"]
    audit |= {
        "n_excluded_incomplete_pre": len(excluded),
        "included_pre_missing_rate": mean_of(candidates, "pre_missing_rate"),
        "excluded_pre_missing_rate": mean_of(excluded, "pre_missing_rate"),
        "included_pre_bti": mean_of(candidates, "pre_bti"),
        "excluded_pre_bti": mean_of(excluded, "pre_bti"),
    }

    out = {name: [] for name in TABLES}
    out["intervention_audit"] = [audit]

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
                               for k, ((s, e), (n, b)) in enumerate(zip(a.pre_blocks, t_pre_blocks,
                                                                        strict=True))]
        return finish("insufficient_pre")
    if a.closed and len(t_post) < floor:
        return finish("insufficient_post")
    if not candidates:
        return finish("no_controls")

    audit["n_donors"] = len(candidates)
    model, residuals, pre_synthetic, post_synthetic, _ = a.fit_pool(candidates, all_blocks)
    for c, w in zip(candidates, model.weights, strict=True):
        donors[c]["weight"] = round(float(w), 6)
    audit["pre_rmspe"] = rmspe(residuals)
    cv = a.held_out(*a.pre_series(candidates, all_blocks))
    overfit = audit["pre_rmspe"] / cv if cv > 0 else NAN
    audit |= {
        "cv_pre_rmspe": cv, "overfit_ratio": overfit,
        "pre_fit_overfit": (None if np.isnan(overfit)
                            else bool(overfit < params.audit_overfit_ratio)),
        "n_active_donors": int((model.weights > ACTIVE_WEIGHT).sum()),
    }
    rows = [block_row("pre", k, s, e, True, n, b, float(synthetic))
            for k, ((s, e), (n, b), synthetic)
            in enumerate(zip(a.pre_blocks, t_pre_blocks, pre_synthetic, strict=True))]
    gaps = []
    for k, ((s, e), done) in enumerate(zip(a.post_blocks, a.complete, strict=True)):
        if not done:
            rows.append(block_row("post", k, s, e, False,
                                  len(calls.between(treated, s, min(e, last_day))), NAN))
            continue
        n, b = a.block(treated, "post", k)
        rows.append(block_row("post", k, s, e, True, n, b, post_synthetic[k]))
        if not np.isnan(rows[-1]["gap"]):
            gaps.append((len(rows) - 1, rows[-1]["gap"]))

    if gaps:
        values = np.array([g for _, g in gaps])
        mean, low, high = block_cs(values, residuals, params)
        for (index, _), mu, lo, hi in zip(gaps, mean, low, high, strict=True):
            rows[index] |= {"running_mean": float(mu), "cs_low": float(lo), "cs_high": float(hi)}
        audit |= {"cs_blocks": len(values), "cs_mean": float(mean[-1]),
                  "cs_low": float(low[-1]), "cs_high": float(high[-1])}
    out["audit_blocks"] = rows

    if not any(a.complete):
        return finish("post_pending")
    if not a.closed:
        return finish("post_partial")

    base = a.estimate(candidates, all_blocks)
    audit |= {k: base[k] for k in HEADLINE + PLACEBO_SUMMARY}
    audit |= {
        "estimator_gap": base["effect"] - base["equal_effect"],
        "estimators_disagree": estimators_disagree(base["effect"], base["ci_low"], base["ci_high"],
                                                   base["equal_effect"], base["equal_ci_low"],
                                                   base["equal_ci_high"]),
    }
    out["audit_placebos"] = base["placebos"]

    if sensitivity:
        eligible = [c for c in donors
                    if donors[c]["exclusion"] not in ("treated", "same_pair") and post_ok[c]]
        for name, multiple, max_short in VARIANTS:
            block_floor = math.ceil(multiple * floor)
            pool = [c for c in eligible if sum(n < block_floor for n in pre_counts[c]) <= max_short]
            fit_blocks = [k for k in all_blocks
                          if all(not np.isnan(a.block(c, "pre", k)[1]) for c in pool)]
            row = {"intervention_id": intervention_id, "variant": name,
                   "block_floor": block_floor, "max_short_blocks": max_short,
                   "n_donors": len(pool), "n_fit_blocks": len(fit_blocks)}
            if not pool:
                row["status"] = "no_controls"
            elif len(fit_blocks) < MIN_FIT_BLOCKS:
                row["status"] = "too_few_blocks"
            else:
                same = pool == candidates and fit_blocks == all_blocks
                result = base if same else a.estimate(pool, fit_blocks)
                row |= {"status": "ok"} | {k: result[k] for k in (
                    "effect", "ci_low", "ci_high", "equal_effect", "placebo_rank", "n_placebos",
                    "placebo_p_value", "placebo_p_floor")}
            out["audit_sensitivity"].append(row)
        low_effect, high_effect, material = sensitivity_summary(
            base["effect"], base["ci_low"], base["ci_high"],
            [r["effect"] for r in out["audit_sensitivity"] if r["status"] == "ok"])
        audit |= {"sensitivity_min_effect": low_effect, "sensitivity_max_effect": high_effect,
                  "sensitivity_material": material}
    return finish("ok")


def intervention_audits(
    tti: pd.DataFrame, cells: pd.DataFrame, corridors: pd.DataFrame,
    interventions: pd.DataFrame, params: Params = Params(), sensitivity: bool = True,
) -> dict[str, pd.DataFrame]:
    """The audit tables. tti: successful calls (corridor_id, requested_at, day,
    travel_time_s); cells: hourly cells, for missingness and the last day with data;
    corridors: pair_id per corridor, for the donor exclusions. sensitivity=False skips
    the threshold variants (the power analysis does not need them)."""
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
                               effective["day"].iloc[0], last_day, params, sensitivity)
            for name, found in result.items():
                rows[name].extend(found)
    return {name: pd.DataFrame(rows[name]).reindex(columns=columns)
            for name, columns in TABLES.items()}
