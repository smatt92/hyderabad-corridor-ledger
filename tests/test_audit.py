import numpy as np
import pandas as pd
import pytest

from metrics.audit import (
    Audit,
    Calls,
    estimators_disagree,
    fit,
    held_out_rmspe,
    intervention_audits,
    periods,
    placebo_summary,
    sensitivity_summary,
    simplex_weights,
    sparse_fit,
)
from metrics.cells import local_day_hour
from metrics.params import Params

EFFECTIVE = "2026-08-29T00:30:00+05:30"    # local day 2026-08-29
DAY = pd.Timestamp("2026-08-29")
PARAMS = Params(bootstrap_resamples=200)   # production floors, fewer resamples
SPAN = periods(DAY, PARAMS)
PRE_BLOCKS = [SPAN["pre_start"] + pd.Timedelta(days=14 * k) for k in range(6)]
POST_BLOCKS = [SPAN["post_start"] + pd.Timedelta(days=14 * k) for k in range(2)]
NAN = float("nan")


def calls(corridor, days, values, minutes=(7 * 60, 10 * 60)):
    """Successful calls carrying values, spread evenly over the days and the minutes."""
    values = np.asarray(values, dtype=float)
    slot, offset = np.divmod(np.arange(len(values)) * len(days), len(values))
    minute = minutes[0] + offset / len(values) * (minutes[1] - minutes[0])
    local = pd.DatetimeIndex(days[slot]) + pd.to_timedelta(minute, unit="min")
    at = local.tz_localize("Asia/Kolkata").tz_convert("UTC")
    frame = pd.DataFrame({"corridor_id": corridor, "requested_at": at, "travel_time_s": values})
    return frame.join(local_day_hour(frame["requested_at"]))


def with_bti(bti, n=200):
    """n calls whose pooled BTI is exactly bti: 90% at 100 s and 10% at b.
    mean = 90 + 0.1 b and p95 = b, so BTI = b / (90 + 0.1 b) - 1 and
    b = 90 (1 + bti) / (1 - 0.1 (1 + bti))."""
    b = 90 * (1 + bti) / (1 - 0.1 * (1 + bti))
    return [100.0] * (n * 9 // 10) + [b] * (n - n * 9 // 10)


def series(corridor, pre, post=(), n=200):
    """One block of calls per BTI: pre blocks, then post blocks."""
    frames = [calls(corridor, pd.date_range(start, periods=14), with_bti(b, n))
              for start, b in zip(PRE_BLOCKS, pre, strict=False)]
    frames += [calls(corridor, pd.date_range(start, periods=14), with_bti(b, n))
               for start, b in zip(POST_BLOCKS, post, strict=False)]
    return frames


def cells_for(tti, missing=None):
    """Hourly cells with every call successful, plus `missing` failed calls added to the
    first cell of each (corridor, day)."""
    counts = tti.groupby(["corridor_id", "day", "hour"]).size().rename("n_ok").reset_index()
    cells = counts.assign(n_expected=counts["n_ok"])
    for (corridor, day), extra in (missing or {}).items():
        first = cells.index[(cells["corridor_id"] == corridor) & (cells["day"] == day)][0]
        cells.loc[first, "n_expected"] += extra
    return cells


def audit(frames, pairs=None, params=PARAMS, missing=None):
    tti = pd.concat(frames, ignore_index=True)
    ids = sorted(tti["corridor_id"].unique())
    corridors = pd.DataFrame({"corridor_id": ids,
                              "pair_id": [(pairs or {}).get(c) for c in ids]})
    interventions = pd.DataFrame({"id": ["works"], "corridor_id": ["t"],
                                  "effective_at": [EFFECTIVE]})
    return intervention_audits(tti, cells_for(tti, missing), corridors, interventions, params)


D1_PRE, D1_POST = [0.30, 0.50, 0.40, 0.60, 0.35, 0.55], [0.45, 0.50]
D2_PRE, D2_POST = [0.50, 0.45, 0.60, 0.40, 0.55, 0.50], [0.50, 0.55]
D4_PRE, D4_POST = [0.42, 0.40, 0.47, 0.41, 0.52, 0.44], [0.46, 0.43]
EFFECT = 0.2


def mixture(pre_or_post, shift):
    d1, d2 = (D1_PRE, D2_PRE) if pre_or_post == "pre" else (D1_POST, D2_POST)
    return [0.25 * a + 0.75 * b + shift for a, b in zip(d1, d2, strict=True)]


def by_hand_panel():
    """Treated = 0.25 d1 + 0.75 d2 + 0.1 in every pre block, plus 0.2 after the change.
    t-alt, the treated corridor's paired alternate, matches it exactly but must not be a
    donor. d3 is thin in one pre block. d4 is paired with d1."""
    return [
        *series("t", mixture("pre", 0.1), mixture("post", 0.1 + EFFECT)),
        *series("t-alt", mixture("pre", 0.1), mixture("post", 0.1 + EFFECT)),
        *series("d1", D1_PRE, D1_POST), *series("d2", D2_PRE, D2_POST),
        *series("d4", D4_PRE, D4_POST),
        *series("d3", D2_PRE[:2], D2_POST),
        calls("d3", pd.date_range(PRE_BLOCKS[2], periods=14), with_bti(0.5, 150)),
        *[calls("d3", pd.date_range(start, periods=14), with_bti(0.5))
          for start in PRE_BLOCKS[3:]],
    ]


PAIRS = {"t": "PL-01", "t-alt": "PL-01", "d1": "PL-02", "d4": "PL-02"}
# d3's thin block lost 50 calls to failures: 1150 recorded of 1200 scheduled in the pre period
D3_MISSING = {("d3", PRE_BLOCKS[2]): 50}


def test_simplex_weights_recover_an_exact_mixture():
    a, b = np.array(D1_PRE), np.array(D2_PRE)
    x = np.column_stack([a - a.mean(), b - b.mean()])
    assert simplex_weights(0.25 * x[:, 0] + 0.75 * x[:, 1], x) == pytest.approx([0.25, 0.75],
                                                                               abs=1e-6)


@pytest.mark.parametrize("weights", ["demeaned", "levels"])
@pytest.mark.parametrize("max_donors", [0, 5, 1])
def test_weights_are_non_negative_sum_to_one_and_respect_the_donor_cap(weights, max_donors):
    rng = np.random.default_rng(7)
    for _ in range(20):
        x = rng.normal(0.4, 0.1, size=(6, 12))
        model = fit(rng.normal(0.4, 0.1, 6), x, weights, max_donors)
        assert model.weights.min() >= 0 and model.weights.sum() == pytest.approx(1.0)
        if max_donors:
            assert 1 <= (model.weights > 1e-9).sum() <= max_donors
        if weights == "levels":
            assert model.shift == 0.0


def test_sparse_fit_selects_the_donors_a_mixture_was_built_from():
    rng = np.random.default_rng(3)
    x = rng.normal(0.4, 0.1, size=(12, 8))
    y = 0.6 * x[:, 2] + 0.4 * x[:, 5] + 0.05
    model = sparse_fit(y, x, "demeaned", 5)
    assert np.flatnonzero(model.weights > 1e-6).tolist() == [2, 5]
    assert model.weights[[2, 5]] == pytest.approx([0.6, 0.4], abs=1e-4)
    assert model.shift == pytest.approx(0.05, abs=1e-4)


def test_held_out_rmspe_by_hand():
    """One donor, so the weight is 1 and only the shift is fitted. The treated-minus-donor
    series is d = [0, 0, 3]. In sample the shift is mean(d) = 1 and the residuals are
    [-1, -1, 2]: RMSPE sqrt(2). Leaving each block out, the shift is the mean of the other
    two: residuals 0 - 1.5, 0 - 1.5, 3 - 0, so RMSPE sqrt((2.25 + 2.25 + 9) / 3) = sqrt(4.5)."""
    x = np.array([[0.40], [0.50], [0.30]])
    y = x[:, 0] + np.array([0.0, 0.0, 3.0])
    in_sample = y - fit(y, x).synthetic(x)
    assert np.sqrt(np.mean(in_sample**2)) == pytest.approx(np.sqrt(2))
    assert held_out_rmspe(y, x) == pytest.approx(np.sqrt(4.5))
    assert np.isnan(held_out_rmspe(y[:2], x[:2]))


def test_bootstrap_units_are_whole_days_and_shared_by_every_corridor():
    """t and d carry identical calls. Resampling the same whole units for both, every
    draw of t minus d is exactly zero; resampling calls independently, it is not."""
    frames = [*series("t", D1_PRE, D1_POST), *series("d", D1_PRE, D1_POST)]
    tti = pd.concat(frames, ignore_index=True)
    a = Audit(Calls(tti), {}, "works", "t", DAY, SPAN["post_end"], PARAMS)
    post = a.units("post")
    assert len(post) == 4 and len(a.units("pre")) == 12
    assert post[0] == (SPAN["post_start"], SPAN["post_start"] + pd.Timedelta(days=6))
    assert post[-1][1] == SPAN["post_end"]
    ten = Audit(Calls(tti), {}, "works", "t", DAY, SPAN["post_end"],
                Params(bootstrap_resamples=200, audit_bootstrap_days=10))
    assert [(e - s).days + 1 for s, e in ten.units("post")] == [10, 10, 8]

    for mode, zero_width in (("blocks", True), ("calls", False)):
        (row,) = audit(frames, params=Params(bootstrap_resamples=200, audit_bootstrap=mode))[
            "intervention_audit"].to_dict("records")
        assert row["effect"] == pytest.approx(0.0, abs=1e-12)
        assert (row["ci_high"] - row["ci_low"] < 1e-12) == zero_width
    (row,) = audit(frames, params=Params(bootstrap_resamples=0))["intervention_audit"].to_dict(
        "records")
    assert row["status"] == "ok" and np.isnan(row["ci_low"]) and np.isnan(row["ci_high"])


def test_periods_are_whole_blocks_and_every_boundary_is_recorded():
    assert SPAN == {
        "pre_start": pd.Timestamp("2026-06-06"), "pre_end": pd.Timestamp("2026-08-28"),
        "settle_start": pd.Timestamp("2026-08-29"), "settle_end": pd.Timestamp("2026-09-06"),
        "post_start": pd.Timestamp("2026-09-07"), "post_end": pd.Timestamp("2026-10-04"),
    }


def test_synthetic_control_by_hand():
    tables = audit(by_hand_panel(), PAIRS, missing=D3_MISSING)
    (row,) = tables["intervention_audit"].to_dict("records")
    assert row["status"] == "ok"
    donors = tables["audit_donors"].set_index("corridor_id")
    # the paired alternate is contaminated, not a control, however well it would fit
    assert donors.loc["t-alt", "exclusion"] == "same_pair" and not donors.loc["t-alt", "included"]
    assert donors.loc["d3", "exclusion"] == "incomplete_pre"
    assert donors.loc[["d1", "d2", "d4"], "weight"].tolist() == pytest.approx([0.25, 0.75, 0.0],
                                                                             abs=1e-4)
    assert row["n_donors"] == 3
    assert row["pre_rmspe"] == pytest.approx(0.0, abs=1e-6)
    # an exact mixture stays exact with any one pre block held out
    assert row["cv_pre_rmspe"] == pytest.approx(0.0, abs=1e-4)
    assert row["n_active_donors"] == 2

    blocks = tables["audit_blocks"]
    post = blocks[blocks.period == "post"]
    assert len(blocks[blocks.period == "pre"]) == 6 and post["complete"].all()
    assert post["gap"].tolist() == pytest.approx([EFFECT, EFFECT], abs=1e-4)
    assert row["cs_blocks"] == 2 and row["cs_mean"] == pytest.approx(EFFECT, abs=1e-4)
    assert row["cs_low"] <= row["cs_mean"] <= row["cs_high"]

    # the headline pools each period once: recompute it from the calls directly
    tti = pd.concat(by_hand_panel(), ignore_index=True)

    def period_bti(corridor, period):
        inside = tti.day.between(SPAN[f"{period}_start"], SPAN[f"{period}_end"])
        v = tti.loc[(tti.corridor_id == corridor) & inside, "travel_time_s"]
        return (np.quantile(v, 0.95) - v.mean()) / v.mean()

    w = {"d1": 0.25, "d2": 0.75}
    synthetic = {p: sum(w[c] * period_bti(c, p) for c in w) for p in ("pre", "post")}
    expected = (period_bti("t", "post") - synthetic["post"]) - (period_bti("t", "pre")
                                                                - synthetic["pre"])
    assert row["effect"] == pytest.approx(expected, abs=1e-3)
    assert row["ci_low"] < row["effect"] < row["ci_high"]
    equal = {p: np.mean([period_bti(c, p) for c in ("d1", "d2", "d4")]) for p in ("pre", "post")}
    expected_equal = (period_bti("t", "post") - period_bti("t", "pre")) - (equal["post"]
                                                                            - equal["pre"])
    assert row["equal_effect"] == pytest.approx(expected_equal, abs=1e-6)
    assert row["estimator_gap"] == pytest.approx(row["effect"] - row["equal_effect"])
    assert (row["settle_start"], row["settle_end"]) == (SPAN["settle_start"], SPAN["settle_end"])


def test_excluded_donors_and_their_missingness_are_published():
    tables = audit(by_hand_panel(), PAIRS, missing=D3_MISSING)
    (row,) = tables["intervention_audit"].to_dict("records")
    donors = tables["audit_donors"].set_index("corridor_id")
    assert (donors.loc["d3", "short_pre_blocks"], donors.loc["d3", "min_pre_block_n"]) == (1, 150)
    assert donors.loc["d3", "pre_missing_rate"] == pytest.approx(50 / 1200)
    assert donors.loc["d1", "short_pre_blocks"] == 0
    assert row["n_excluded_incomplete_pre"] == 1
    assert row["included_pre_missing_rate"] == 0.0
    assert row["excluded_pre_missing_rate"] == pytest.approx(50 / 1200)
    assert not np.isnan(row["excluded_pre_bti"]) and not np.isnan(row["included_pre_bti"])


def test_sensitivity_to_the_completeness_threshold():
    tables = audit(by_hand_panel(), PAIRS, missing=D3_MISSING)
    (row,) = tables["intervention_audit"].to_dict("records")
    variants = tables["audit_sensitivity"].set_index("variant")
    # every donor block holds exactly 200 calls, so the strict thresholds admit none
    assert variants["status"].to_dict() == {
        "base": "ok", "strict_125": "no_controls", "strict_150": "no_controls",
        "relaxed_one_block": "ok"}
    assert variants.loc["base", "effect"] == pytest.approx(row["effect"])
    relaxed = variants.loc["relaxed_one_block"]
    # d3 comes back with its one thin block, and every fit skips that block
    assert (relaxed.n_donors, relaxed.n_fit_blocks, relaxed.block_floor) == (4, 5, 200)
    assert relaxed.effect == pytest.approx(row["effect"], abs=0.02)
    assert row["sensitivity_material"] is False or not row["sensitivity_material"]
    assert row["sensitivity_min_effect"] <= row["effect"] <= row["sensitivity_max_effect"]


def test_sensitivity_is_material_when_a_variant_leaves_the_interval_or_flips_sign():
    assert sensitivity_summary(0.20, 0.10, 0.30, [0.20, 0.25, 0.12]) == (0.12, 0.25, False)
    assert sensitivity_summary(0.20, 0.10, 0.30, [0.20, 0.35])[2] is True
    assert sensitivity_summary(0.05, -0.10, 0.20, [0.05, -0.02])[2] is True  # sign flips
    assert sensitivity_summary(0.20, 0.10, 0.30, [NAN])[2] is None


def test_placebos_exclude_their_own_pair_and_report_their_resolution():
    tables = audit(by_hand_panel(), PAIRS)
    (row,) = tables["intervention_audit"].to_dict("records")
    placebos = tables["audit_placebos"].set_index("corridor_id")
    assert set(placebos.index) == {"d1", "d2", "d4"}
    assert "d4" not in placebos.loc["d1", "weights"] and "d1" not in placebos.loc["d4", "weights"]
    # the treated fit is exact before the change, so its ratio outranks every placebo,
    # yet with three placebos no p-value can reach 0.05
    assert (row["n_placebos"], row["placebo_rank"]) == (3, 1)
    assert (row["placebo_p_value"], row["placebo_p_floor"]) == (pytest.approx(0.25),
                                                                pytest.approx(0.25))
    assert not row["placebo_extreme"]
    assert row["placebo_verdict"].startswith("Not extreme: rank 1 of 4 (3 placebo runs")
    assert "smallest attainable p is 1/4 = 0.250" in row["placebo_verdict"]
    assert "no effect could reach p = 0.05" in row["placebo_verdict"]


def test_placebo_summary_by_hand():
    rank, p, floor, extreme, verdict = placebo_summary(2.5, [1.0, 2.0, 3.0, 4.0], 0.05)
    assert (rank, p, floor, extreme) == (3, pytest.approx(3 / 5), pytest.approx(1 / 5), False)
    assert "rank 3 of 5" in verdict and "2 of 4 placebo runs" in verdict
    rank, p, floor, extreme, verdict = placebo_summary(10.0, [1.0] * 19, 0.05)
    assert (rank, p, extreme) == (1, pytest.approx(1 / 20), True)
    assert verdict.startswith("Extreme among placebos: rank 1 of 20")
    rank, p, _, extreme, _ = placebo_summary(NAN, [1.0], 0.05)
    assert rank is None and np.isnan(p) and not extreme
    rank, p, _, extreme, verdict = placebo_summary(1.0, [], 0.05)
    assert rank is None and np.isnan(p) and not extreme and "No placebo" in verdict


def test_estimators_disagree_on_sign_or_interval():
    assert not estimators_disagree(0.20, 0.10, 0.30, 0.18, 0.05, 0.30)
    assert estimators_disagree(0.20, 0.10, 0.30, -0.10, -0.20, 0.00)   # opposite signs
    assert estimators_disagree(0.20, 0.15, 0.25, 0.05, 0.00, 0.10)     # outside each other


def test_statuses():
    donors = [*series("d1", D1_PRE, D1_POST), *series("d2", D2_PRE, D2_POST)]
    treated_pre = series("t", mixture("pre", 0.1))

    thin = [*series("t", mixture("pre", 0.1)[:5], mixture("post", 0.1)),
            calls("t", pd.date_range(PRE_BLOCKS[5], periods=14), with_bti(0.5, 150)), *donors]
    assert audit(thin)["intervention_audit"]["status"].iloc[0] == "insufficient_pre"

    pending = audit([*treated_pre, *series("d1", D1_PRE), *series("d2", D2_PRE),
                     calls("t", pd.date_range(POST_BLOCKS[0], periods=5), with_bti(0.5, 60))])
    assert pending["intervention_audit"]["status"].iloc[0] == "post_pending"

    partial = audit([*treated_pre, *series("t", [], mixture("post", 0.1 + EFFECT)[:1]),
                     *series("d1", D1_PRE, D1_POST[:1]), *series("d2", D2_PRE, D2_POST[:1])])
    (row,) = partial["intervention_audit"].to_dict("records")
    assert row["status"] == "post_partial" and row["post_blocks_complete"] == 1
    assert row["cs_blocks"] == 1 and row["cs_mean"] == pytest.approx(EFFECT, abs=1e-4)
    assert np.isnan(row["effect"]) and np.isnan(row["equal_effect"])  # the headline waits
    assert partial["audit_sensitivity"].empty

    short_post = audit([*treated_pre, *donors,
                        *[calls("t", pd.date_range(s, periods=14), with_bti(0.5, 70))
                          for s in POST_BLOCKS]])
    assert short_post["intervention_audit"]["status"].iloc[0] == "insufficient_post"

    alone = audit([*series("t", mixture("pre", 0.1), mixture("post", 0.1)),
                   *series("t-alt", D1_PRE, D1_POST)], pairs={"t": "PL-01", "t-alt": "PL-01"})
    assert alone["intervention_audit"]["status"].iloc[0] == "no_controls"


def test_same_distribution_with_different_sample_counts_is_no_effect():
    """The Step 2 regression, now for both estimators. Every corridor draws from one
    distribution throughout; only the treated corridor's call density changes, from
    64 calls a day before the change to 16 after. Neither estimator may turn that
    into an effect. Checked over 25 replicate panels, since one panel is noisy."""
    rng = np.random.default_rng(20260913)
    params = Params(bootstrap_resamples=100)
    pre_days = pd.date_range(SPAN["pre_start"], SPAN["pre_end"])
    post_days = pd.date_range(SPAN["post_start"], SPAN["post_end"])

    def draw(corridor, days, per_day):
        return calls(corridor, days, 900 * rng.lognormal(0, 0.35, len(days) * per_day))

    synthetic, equal = [], []
    for _ in range(25):
        frames = [draw("t", pre_days, 64), draw("t", post_days, 16)]
        frames += [draw(d, days, 32) for d in ("d1", "d2", "d3") for days in (pre_days, post_days)]
        (row,) = audit(frames, params=params)["intervention_audit"].to_dict("records")
        assert row["status"] == "ok"
        synthetic.append(row["effect"])
        equal.append(row["equal_effect"])
    assert abs(np.mean(synthetic)) < 0.05
    assert abs(np.mean(equal)) < 0.05
