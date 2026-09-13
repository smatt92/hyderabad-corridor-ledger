import numpy as np
import pandas as pd
import pytest

from metrics.recovery import cox_model, kaplan_meier, recovery_duration, recovery_events
from tests.helpers import local

GAP = pd.Timedelta(minutes=45)


def at(*wall_times):
    return [local(f"2026-09-01 {t}") for t in wall_times]


def test_recovery_cleared():
    result = recovery_duration(at("08:00", "08:15", "08:30", "08:45"),
                               np.array([1.1, 1.8, 1.5, 1.25]), 1.3, GAP)
    assert result == (1, pd.Timedelta(minutes=30), True, None)


def test_recovery_right_censored_at_window_end():
    result = recovery_duration(at("08:00", "08:15", "08:30"), np.array([1.1, 1.8, 1.6]), 1.3, GAP)
    assert result == (1, pd.Timedelta(minutes=15), False, "window_end")


def test_recovery_right_censored_at_data_gap_not_imputed_across_it():
    # 08:30 -> 09:30 is a 60-minute gap: whatever happened inside it is unknown
    result = recovery_duration(at("08:15", "08:30", "09:30"), np.array([1.8, 1.6, 1.0]), 1.3, GAP)
    assert result == (0, pd.Timedelta(minutes=15), False, "data_gap")


def test_day_that_never_congests_is_not_at_risk():
    assert recovery_duration(at("08:00", "08:15"), np.array([1.2, 1.29]), 1.3, GAP) is None


def test_recovery_events_keep_censored_days():
    tti = pd.DataFrame({
        "corridor_id": "a",
        "day": [pd.Timestamp("2026-09-01")] * 3 + [pd.Timestamp("2026-09-05")] * 2,
        "requested_at": at("08:00", "08:15", "08:30")
        + [local("2026-09-05 08:00"), local("2026-09-05 08:15")],
        "tti_tomtom": [1.8, 1.4, 1.2, 1.9, 1.7],
        "tti_p5": np.nan,
    })
    daily = pd.DataFrame({"corridor_id": "a",
                          "day": [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-05")],
                          "missing_rate": [0.0, 0.5], "low_confidence": [False, True]})
    out = recovery_events(tti, daily).set_index("day")

    assert len(out) == 2
    tue, sat = out.loc[pd.Timestamp("2026-09-01")], out.loc[pd.Timestamp("2026-09-05")]
    assert (tue.cleared, tue.duration_min, tue.is_weekend) == (True, 30.0, False)
    assert (sat.cleared, sat.censor_reason, sat.duration_min) == (False, "window_end", 15.0)
    assert bool(sat.is_weekend) and bool(sat.low_confidence)


def test_kaplan_meier_with_greenwood():
    km = kaplan_meier([10, 20, 20, 30, 40], [True, True, False, True, False])
    assert km["t_min"].tolist() == [10, 20, 30, 40]
    assert km["n_at_risk"].tolist() == [5, 4, 2, 1]
    assert km["n_events"].tolist() == [1, 1, 1, 0]
    assert km["n_censored"].tolist() == [0, 1, 0, 1]
    # S: 4/5; *3/4; *1/2
    assert km["survival"].tolist() == pytest.approx([0.8, 0.6, 0.3, 0.3])
    # Greenwood: 1/20; +1/12; +1/2
    assert km["se"].tolist() == pytest.approx([
        0.8 * np.sqrt(1 / 20),
        0.6 * np.sqrt(1 / 20 + 1 / 12),
        0.3 * np.sqrt(1 / 20 + 1 / 12 + 1 / 2),
        0.3 * np.sqrt(1 / 20 + 1 / 12 + 1 / 2),
    ])


def test_dropping_censored_durations_understates_recovery_time():
    def median(km):
        return km.loc[km["survival"] <= 0.5, "t_min"].iloc[0]

    kept = kaplan_meier([10, 20, 20, 30, 40], [True, True, False, True, False])
    dropped = kaplan_meier([10, 20, 30], [True, True, True])  # 1/3 and 0 after 20, 30
    assert median(kept) == 30
    assert median(dropped) == 20


def test_cox_longer_recovery_after_higher_peaks():
    n = 40
    peak = np.linspace(1.3, 3.25, n)
    events = pd.DataFrame({
        "basis": "tomtom",
        "peak_tti": peak,
        "duration_min": 10 * peak + [(i * 7) % 11 for i in range(n)],
        "cleared": True,
        "is_weekend": [i % 2 == 0 for i in range(n)],
        "peak_at": local("2026-09-01 09:00"),
        "missing_rate": 0.0,
    })
    out = cox_model(events).set_index("covariate")

    assert set(out.index) == {"peak_tti", "is_weekend"}  # constant covariates dropped
    assert out.loc["peak_tti", "coef"] < 0                # higher peak, slower to clear
    assert out.loc["peak_tti", "hazard_ratio"] < 1


def test_cox_not_fitted_on_too_few_events():
    events = pd.DataFrame({
        "basis": "tomtom", "peak_tti": [1.5, 2.0, 2.5], "duration_min": [10.0, 20.0, 30.0],
        "cleared": True, "is_weekend": [True, False, True],
        "peak_at": local("2026-09-01 09:00"), "missing_rate": 0.0,
    })
    assert cox_model(events).empty
