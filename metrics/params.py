"""Metric definitions that are parameters rather than code.

Changing any value here changes what the numbers mean, so bump
METHOD_VERSION with it. metrics_* tables are disposable: a backfill
recomputes them from raw under the new version.
"""

from dataclasses import dataclass

METHOD_VERSION = "p02.3"
LOCAL_TZ = "Asia/Kolkata"
BASES = ("tomtom", "p5")


@dataclass(frozen=True)
class Params:
    # Informative missingness: flag, never impute.
    low_confidence_missing_rate: float = 0.15

    # Observed free flow: p5 of successful night-slot travel times over a trailing
    # window. Night slots are local hours [start, end), sampled every 30 minutes.
    ff_p5_night_hours: tuple[int, int] = (0, 4)
    ff_p5_window_days: int = 28
    ff_p5_min_samples: int = 20

    worst_window: str = "15min"

    # Recovery: time from the day's peak TTI until TTI drops below threshold.
    recovery_threshold: float = 1.3
    recovery_max_gap_min: float = 45.0

    # Rankings and shrinkage.
    ranking_window_days: int = 28
    congested_tti: float = 1.3

    # STL on the daily series.
    stl_period: int = 7
    stl_min_segment_days: int = 21

    # Control charts on the STL residual, in robust standard deviations.
    cusum_k: float = 0.5
    cusum_h: float = 5.0
    ewma_lambda: float = 0.2
    ewma_limit_l: float = 3.0

    # Confidence sequences.
    cs_alpha: float = 0.05
    cs_before_days: int = 28
    cs_rho_target_days: int = 28

    # Read model served by the P-04 API.
    read_window_days: int = 90
    heatmap_min_days: int = 2
    network_baseline_weeks: int = 8
    network_baseline_min: int = 3
    network_state_band_pct: float = 7.0

    # Intervention audit (synthetic control).
    audit_settle_days: int = 9
    audit_min_pre_days: int = 14
