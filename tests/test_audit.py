import numpy as np
import pandas as pd
import pytest

from metrics.audit import intervention_audits
from metrics.cells import local_day_hour
from metrics.params import Params

EFFECTIVE = "2026-08-29T00:30:00+05:30"            # local day 2026-08-29
PRE = pd.date_range("2026-08-01", "2026-08-28")    # the 28 days before it
POST = pd.date_range("2026-09-07", "2026-10-04")   # 28 days, after 9 settling days

FLAT = [100.0] * 190 + [200.0] * 10   # mean 105; p95 at position 189.05 = 100 + 0.05 * 100 = 105
TAIL = [100.0] * 180 + [200.0] * 20   # mean 110; p95 = 200; BTI = 90 / 110


def calls(corridor, days, values, minutes=(7 * 60, 10 * 60)):
    """Successful calls carrying values, spread evenly over the days and the minutes."""
    values = np.asarray(values, dtype=float)
    slot, offset = np.divmod(np.arange(len(values)) * len(days), len(values))
    minute = minutes[0] + offset / len(values) * (minutes[1] - minutes[0])
    local = pd.DatetimeIndex(days[slot]) + pd.to_timedelta(minute, unit="min")
    at = local.tz_localize("Asia/Kolkata").tz_convert("UTC")
    frame = pd.DataFrame({"corridor_id": corridor, "requested_at": at, "travel_time_s": values})
    return frame.join(local_day_hour(frame["requested_at"]))


def cells_for(tti):
    counts = tti.groupby(["corridor_id", "day", "hour"]).size().rename("n_ok").reset_index()
    return counts.assign(n_expected=counts["n_ok"])


def audit(*frames, params=Params()):
    tti = pd.concat(frames, ignore_index=True)
    interventions = pd.DataFrame({"id": ["works"], "corridor_id": ["t"],
                                  "effective_at": [EFFECTIVE]})
    (row,) = intervention_audits(tti, cells_for(tti), interventions, params).to_dict("records")
    return row


def test_audit_by_hand():
    row = audit(calls("t", PRE, FLAT), calls("t", POST, TAIL),
                calls("c1", PRE, FLAT), calls("c1", POST, FLAT),
                calls("c2", PRE, FLAT), calls("c2", POST, FLAT))
    assert row["status"] == "ok"
    assert (row["pre_start"], row["pre_end"]) == (PRE[0], PRE[-1])
    assert (row["post_start"], row["post_end"]) == (POST[0], POST[-1])
    assert (row["n_pre"], row["n_post"], row["n_controls"]) == (200, 200, 2)
    assert row["treated_pre"] == pytest.approx(0.0)
    assert row["treated_post"] == pytest.approx(90 / 110)
    assert (row["control_pre"], row["control_post"]) == pytest.approx((0.0, 0.0))
    assert row["effect"] == pytest.approx(90 / 110)
    assert row["weights"] == {"c1": 0.5, "c2": 0.5}
    assert row["ci_low"] < row["ci_high"]
    assert (row["resamples"], row["alpha"]) == (2000, 0.05)
    assert row["missing_rate"] == 0.0 and not row["low_confidence"]


def mean_daily_bti_effect(tti):
    """What averaging daily BTIs would have published for the same calls."""
    def mean_daily_bti(corridor, days):
        by_day = tti[(tti.corridor_id == corridor) & tti.day.isin(days)].groupby("day")
        p95, mean = by_day["travel_time_s"].quantile(0.95), by_day["travel_time_s"].mean()
        return ((p95 - mean) / mean).mean()

    controls = np.mean([mean_daily_bti(c, POST) - mean_daily_bti(c, PRE) for c in ("c1", "c2")])
    return mean_daily_bti("t", POST) - mean_daily_bti("t", PRE) - controls


def test_same_distribution_with_different_sample_counts_is_no_effect():
    """The regression this design exists for. Every corridor draws from one
    distribution throughout; only the treated corridor's call density changes, from
    64 calls a day to 8. Averaging daily BTIs turns that density change into an
    effect; pooling each period does not. One panel's estimate carries sampling
    noise of about +/-0.09, so the claim is checked over 40 replicate panels."""
    rng = np.random.default_rng(20260913)
    params = Params(bootstrap_resamples=200)

    def draw(n):
        return 900 * rng.lognormal(0, 0.35, n)

    pooled_effects, averaged_effects, covered = [], [], 0
    for _ in range(40):
        frames = [calls("t", PRE, draw(28 * 64)), calls("t", POST, draw(28 * 8)),
                  calls("c1", PRE, draw(28 * 32)), calls("c1", POST, draw(28 * 32)),
                  calls("c2", PRE, draw(28 * 32)), calls("c2", POST, draw(28 * 32))]
        row = audit(*frames, params=params)
        assert row["status"] == "ok"
        pooled_effects.append(row["effect"])
        covered += row["ci_low"] <= 0 <= row["ci_high"]
        averaged_effects.append(mean_daily_bti_effect(pd.concat(frames, ignore_index=True)))

    assert abs(np.mean(pooled_effects)) < 0.04    # no effect, within 3 standard errors
    assert np.mean(averaged_effects) < -0.15      # the artifact averaging would publish
    assert covered >= 34                          # the 95% interval covers the true zero


def test_statuses():
    control = [calls("c1", PRE, FLAT), calls("c1", POST, FLAT)]
    assert audit(calls("t", PRE, FLAT[:199]), calls("t", POST, TAIL),
                 *control)["status"] == "insufficient_pre"

    pending = audit(calls("t", PRE, FLAT), calls("t", POST[:10], TAIL[:100]),
                    calls("c1", PRE, FLAT), calls("c1", POST[:10], FLAT[:100]))
    assert pending["status"] == "post_pending" and pending["n_post"] == 100
    assert pending["treated_pre"] == pytest.approx(0.0) and np.isnan(pending["effect"])

    assert audit(calls("t", PRE, FLAT), calls("t", POST, TAIL[:199]),
                 *control)["status"] == "insufficient_post"

    assert audit(calls("t", PRE, FLAT), calls("t", POST, TAIL),
                 calls("c1", PRE, FLAT[:150]), calls("c1", POST, FLAT))["status"] == "no_controls"


def test_off_peak_calls_never_enter_the_audit():
    night = calls("t", POST, [5000.0] * 300, minutes=(60, 180))  # 01:00-03:00
    row = audit(calls("t", PRE, FLAT), calls("t", POST, FLAT), night,
                calls("c1", PRE, FLAT), calls("c1", POST, FLAT))
    assert row["status"] == "ok" and row["n_post"] == 200
    assert row["effect"] == pytest.approx(0.0)
