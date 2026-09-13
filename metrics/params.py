"""Metric definitions that are parameters rather than code.

Changing any value here changes what the numbers mean, so bump
METHOD_VERSION with it. metrics_* tables are disposable: a backfill
recomputes them from raw under the new version.
"""

from dataclasses import dataclass

METHOD_VERSION = "p02.5"
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

    # Pooled distributions (metrics.pooled). BTI, PTI and every p95 are properties
    # of a distribution, not of a day: they are computed over pooled calls and
    # published only at or above their floor. Percentiles are empirical.
    p95_min_samples: int = 200
    central_min_samples: int = 30
    bootstrap_resamples: int = 2000
    bootstrap_alpha: float = 0.05
    bootstrap_seed: int = 20260913
    # Peak hours pooled for the ledger and the audit, local minutes after
    # midnight, [start, end): 06:30-10:30 and 16:30-21:00.
    peak_minutes: tuple[tuple[int, int], ...] = ((390, 630), (990, 1260))

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

    # Read model served by the P-04 API. The read window pools the ledger's
    # peak-hour statistics; the profile window pools each hour of the day, and is
    # longer because an hour holds at most four calls a day.
    read_window_days: int = 90
    profile_window_days: int = 120
    network_baseline_weeks: int = 8
    network_baseline_min: int = 3
    network_state_band_pct: float = 7.0

    # Intervention audit (metrics.audit). Periods are whole blocks of
    # audit_block_days; each block's BTI pools its peak-hour calls and needs the
    # p95 floor, which Tier B/C reach in 14 days (about 238 calls). Synthetic
    # control weights are fitted on the pre blocks. A placebo whose pre-period
    # RMSPE exceeds audit_poor_fit_ratio times the treated one is flagged.
    audit_block_days: int = 14
    audit_pre_blocks: int = 6
    audit_settle_days: int = 9
    audit_post_blocks: int = 2
    audit_poor_fit_ratio: float = 5.0

    def __post_init__(self) -> None:
        if self.p95_min_samples < self.central_min_samples:
            raise ValueError("p95_min_samples must be at least central_min_samples")
