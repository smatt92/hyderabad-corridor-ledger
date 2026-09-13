"""EWMA and CUSUM control charts on the STL residual.

CUSUM accumulates small persistent deviations, so it detects slow drift that
eyeballing a sparkline never will. Residuals are standardised by a robust
sigma (1.4826 x MAD) of their segment. Magnitudes are reported in TTI units.
"""

import numpy as np
import pandas as pd

from metrics.params import Params

COLUMNS = ["corridor_id", "basis", "chart", "detected_at", "direction", "magnitude", "statistic"]


def robust_sigma(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def cusum(z: np.ndarray, k: float, h: float) -> list[tuple[int, str, float, float]]:
    """Two-sided tabular CUSUM. Returns (index, direction, statistic, shift).

    shift is the estimated mean shift in sigma units, k + S / N, where N counts
    periods since the signalling sum last left zero. Both sums reset after a
    signal.
    """
    signals = []
    hi = lo = 0.0
    n_hi = n_lo = 0
    for i, value in enumerate(z):
        hi = max(0.0, hi + value - k)
        lo = max(0.0, lo - value - k)
        n_hi = n_hi + 1 if hi > 0 else 0
        n_lo = n_lo + 1 if lo > 0 else 0
        if hi > h:
            signals.append((i, "up", hi, k + hi / n_hi))
        elif lo > h:
            signals.append((i, "down", lo, k + lo / n_lo))
        else:
            continue
        hi = lo = 0.0
        n_hi = n_lo = 0
    return signals


def ewma(z: np.ndarray, lam: float, limit_l: float) -> list[tuple[int, str, float, float]]:
    """EWMA chart. Signals when the statistic first crosses its time-varying limit
    L * sqrt(lam / (2 - lam) * (1 - (1 - lam)^(2t))). Returns (index, direction,
    statistic, shift) with shift = |statistic| in sigma units."""
    signals = []
    stat = 0.0
    was_out = False
    for i, value in enumerate(z):
        stat = lam * value + (1 - lam) * stat
        t = i + 1
        limit = limit_l * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * t)))
        out = abs(stat) > limit
        if out and not was_out:
            signals.append((i, "up" if stat > 0 else "down", stat, abs(stat)))
        was_out = out
    return signals


def change_points(stl: pd.DataFrame, params: Params = Params()) -> pd.DataFrame:
    rows = []
    for (corridor_id, basis, _), seg in stl.groupby(["corridor_id", "basis", "segment_start"]):
        seg = seg.sort_values("day")
        resid = seg["resid"].to_numpy(dtype=float)
        sigma = robust_sigma(resid)
        if not np.isfinite(sigma) or sigma <= 0:
            continue
        z = resid / sigma
        days = seg["day"].to_numpy()
        charts = {
            "cusum": cusum(z, params.cusum_k, params.cusum_h),
            "ewma": ewma(z, params.ewma_lambda, params.ewma_limit_l),
        }
        for chart, signals in charts.items():
            for i, direction, statistic, shift in signals:
                rows.append(
                    (corridor_id, basis, chart, days[i], direction, shift * sigma, statistic)
                )
    return pd.DataFrame(rows, columns=COLUMNS)
