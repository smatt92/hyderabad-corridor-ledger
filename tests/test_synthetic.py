import numpy as np
import pandas as pd
import pytest

from metrics.params import Params
from metrics.synthetic import intervention_audits, simplex_weights

DAYS = pd.date_range("2026-08-01", "2026-08-30", freq="D")
T = np.arange(len(DAYS))
A = 0.30 + 0.05 * np.sin(T)
B = 0.50 + 0.04 * np.cos(1.7 * T)
POST = DAYS >= pd.Timestamp("2026-08-24")  # effective 08-21, 3 settling days
TREATED = 0.5 * A + 0.5 * B + 0.02 - 0.10 * POST


def day_frame(series: dict[str, np.ndarray]) -> pd.DataFrame:
    parts = [pd.DataFrame({"corridor_id": c, "day": DAYS, "bti": v, "n_expected": 4, "n_ok": 4})
             for c, v in series.items()]
    return pd.concat(parts, ignore_index=True)


PARAMS = Params(audit_settle_days=3, audit_min_pre_days=14)


def test_simplex_weights_recover_an_exact_mixture():
    x = np.column_stack([A - A.mean(), B - B.mean()])
    y = 0.25 * x[:, 0] + 0.75 * x[:, 1]
    assert simplex_weights(y, x) == pytest.approx([0.25, 0.75], abs=1e-6)


def test_audit_by_hand():
    decoy = 0.5 * A + 0.5 * B + 0.02  # a perfect match, but missing one pre-period day
    decoy[5] = np.nan
    day = day_frame({"treated": TREATED, "a": A, "b": B, "decoy": decoy, "other": A * 1.1})
    interventions = pd.DataFrame({
        "id": ["retime", "other-works"], "corridor_id": ["treated", "other"],
        "effective_at": ["2026-08-21T00:30:00+05:30", "2026-08-10T00:00:00+05:30"],
    })
    out = intervention_audits(day, interventions, PARAMS).set_index("intervention_id")
    row = out.loc["retime"]

    assert row.status == "ok"
    # decoy dropped for its missing pre day (never filled); "other" is itself treated
    assert row.weights == pytest.approx({"a": 0.5, "b": 0.5}, abs=1e-5)
    assert (row.n_pre, row.n_post, row.n_controls) == (20, 7, 2)
    assert (row.pre_start, row.pre_end) == (pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-20"))
    post = (pd.Timestamp("2026-08-24"), pd.Timestamp("2026-08-30"))
    assert (row.post_start, row.post_end) == post
    assert row.synthetic_pre == pytest.approx(row.treated_pre)  # shared by construction
    assert row.pre_rmse == pytest.approx(0.0, abs=1e-6)
    assert row.effect == pytest.approx(-0.10, abs=1e-6)
    assert row.treated_post - row.synthetic_post == pytest.approx(-0.10, abs=1e-6)
    assert row.cs_low <= row.effect <= row.cs_high
    assert row.missing_rate == 0.0 and not row.low_confidence


def test_audit_statuses():
    day = day_frame({"treated": TREATED, "a": A})
    early = pd.DataFrame({"id": ["early"], "corridor_id": ["treated"],
                          "effective_at": ["2026-08-05T00:00:00+05:30"]})
    assert intervention_audits(day, early, PARAMS)["status"].iloc[0] == "insufficient_pre"

    late = pd.DataFrame({"id": ["late"], "corridor_id": ["treated"],
                         "effective_at": ["2026-08-29T00:00:00+05:30"]})
    assert intervention_audits(day, late, PARAMS)["status"].iloc[0] == "no_post"

    alone = day_frame({"treated": TREATED})
    retime = pd.DataFrame({"id": ["retime"], "corridor_id": ["treated"],
                           "effective_at": ["2026-08-21T00:30:00+05:30"]})
    assert intervention_audits(alone, retime, PARAMS)["status"].iloc[0] == "no_controls"
