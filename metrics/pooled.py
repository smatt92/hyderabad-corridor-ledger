"""Pooled distributions: floors, empirical percentiles and bootstrap intervals.

BTI, PTI and every p95 describe a distribution of travel times, not a day. They
are computed once over all successful calls in a pooling window: one hour of
the day across the profile window, the peak hours of the read window, or one
audit period. The empirical p95 of the two to four calls in a single hour is
close to their maximum and biased low by an amount that depends on how many
calls there were, so no tail statistic is ever computed from a cell.

Floors by quantile, not one number:
  central statistics (mean, median, quartiles)   central_min_samples  (30)
  p95 and every statistic built on it            p95_min_samples      (200)
Below its floor a statistic is NaN, published as NULL, and the pooled count is
published beside it.

Percentiles are empirical, linear between order statistics (numpy's default).
Harrell-Davis is deliberately not used: at p95 its weights concentrate on the
top order statistics, so it inherits the sparsity it was meant to fix.

Every published tail statistic carries a percentile bootstrap interval from
bootstrap_resamples resamples of the pooled calls. The generator is seeded from
the parameters and the statistic's key, so the same calls always give the
same interval.
"""

import zlib
from collections.abc import Callable

import numpy as np
import pandas as pd

from metrics.params import LOCAL_TZ, Params

NAN = float("nan")
CHUNK = 250  # resamples drawn at a time, bounding memory on large pools

Statistic = Callable[[np.ndarray], np.ndarray]


def clean(values) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[~np.isnan(array)]


def floor_for(q: float, params: Params) -> int:
    return params.p95_min_samples if q >= 0.95 else params.central_min_samples


def quantile(values, q: float, params: Params = Params()) -> float:
    """Empirical percentile, NaN below the floor for q."""
    v = clean(values)
    return float(np.quantile(v, q)) if len(v) >= floor_for(q, params) else NAN


def mean(values, params: Params = Params()) -> float:
    v = clean(values)
    return float(v.mean()) if len(v) >= params.central_min_samples else NAN


def p95_rows(rows: np.ndarray) -> np.ndarray:
    return np.quantile(rows, 0.95, axis=1)


def bti_rows(rows: np.ndarray) -> np.ndarray:
    """Buffer time index of each row: (p95 - mean) / mean."""
    means = rows.mean(axis=1)
    return (np.quantile(rows, 0.95, axis=1) - means) / means


def generator(params: Params, key) -> np.random.Generator:
    """A generator seeded from the parameters and a key: the same key, the same draws."""
    digest = zlib.crc32("|".join(str(part) for part in key).encode())
    return np.random.default_rng([params.bootstrap_seed, digest])


def draws(values, statistics: list[Statistic], params: Params, key) -> list[np.ndarray]:
    """Each statistic over the same bootstrap_resamples resamples of values."""
    v = clean(values)
    rng = generator(params, key)
    parts: list[list[np.ndarray]] = [[] for _ in statistics]
    remaining = params.bootstrap_resamples
    while remaining:
        k = min(CHUNK, remaining)
        rows = v[rng.integers(0, len(v), size=(k, len(v)))]
        for store, statistic in zip(parts, statistics, strict=True):
            store.append(statistic(rows))
        remaining -= k
    return [np.concatenate(store) for store in parts]


def interval(sample: np.ndarray, params: Params) -> tuple[float, float]:
    """Percentile interval of the finite draws; NaN when there are none."""
    sample = np.asarray(sample, dtype=float)
    sample = sample[~np.isnan(sample)]
    if not len(sample):
        return NAN, NAN
    half = params.bootstrap_alpha / 2
    low, high = np.quantile(sample, [half, 1 - half])
    return float(low), float(high)


def tail(values, statistic: Statistic, params: Params, key) -> tuple[float, float, float]:
    """(value, ci_low, ci_high) of a tail statistic, all NaN below the p95 floor."""
    v = clean(values)
    if len(v) < params.p95_min_samples:
        return NAN, NAN, NAN
    (sample,) = draws(v, [statistic], params, key)
    return float(statistic(v[np.newaxis, :])[0]), *interval(sample, params)


def travel(values, params: Params, key) -> dict:
    """Pooled travel-time statistics. n always; mean and median at the central floor;
    p95 and BTI, each with its interval from the same resamples, at the p95 floor."""
    v = clean(values)
    out = {"n": len(v), "mean": mean(v, params), "p50": quantile(v, 0.5, params)}
    out |= dict.fromkeys(("p95", "p95_ci_low", "p95_ci_high", "bti", "bti_ci_low", "bti_ci_high"),
                         NAN)
    if len(v) >= params.p95_min_samples:
        p95_draws, bti_draws = draws(v, [p95_rows, bti_rows], params, key)
        row = v[np.newaxis, :]
        out["p95"] = float(p95_rows(row)[0])
        out["p95_ci_low"], out["p95_ci_high"] = interval(p95_draws, params)
        out["bti"] = float(bti_rows(row)[0])
        out["bti_ci_low"], out["bti_ci_high"] = interval(bti_draws, params)
    return out


def difference(a, b, statistic: Statistic, params: Params, key) -> tuple[float, float, float]:
    """statistic(a) - statistic(b) for a tail statistic, with an interval from
    independent resamples of each side. NaN unless both sides reach the p95 floor."""
    a, b = clean(a), clean(b)
    if min(len(a), len(b)) < params.p95_min_samples:
        return NAN, NAN, NAN
    (from_a,) = draws(a, [statistic], params, (*key, "a"))
    (from_b,) = draws(b, [statistic], params, (*key, "b"))
    point = float(statistic(a[np.newaxis, :])[0] - statistic(b[np.newaxis, :])[0])
    return point, *interval(from_a - from_b, params)


def is_peak(requested_at: pd.Series, params: Params = Params()) -> pd.Series:
    """True for calls made inside the peak windows, local time."""
    local = requested_at.dt.tz_convert(LOCAL_TZ)
    minute = local.dt.hour * 60 + local.dt.minute
    peak = pd.Series(False, index=requested_at.index)
    for start, end in params.peak_minutes:
        peak |= (minute >= start) & (minute < end)
    return peak
