"""Positive control. The replicate test in test_audit.py is a negative control: it
shows a null stays null. This one injects an effect of known size into one simulated
panel and asserts only what the power analysis (docs/audit_power.md) says holds, so
"no effect" can be told apart from "no power".

The panel is the audit's default design: Tier A, 20 donors, twelve 14-day pre blocks
and a 28-day post period. There the standardised placebo rank detected a 0.30 BTI
effect in 50 of 50 simulated panels, and holds its size by construction. The interval
is not asserted here."""

import numpy as np
import pandas as pd
import pytest

from metrics.audit import intervention_audits, periods
from metrics.params import LOCAL_TZ, Params
from scripts.dev.panel_model import audit_inputs, inject_bti_effect, scheduled_panel

EFFECTIVE = pd.Timestamp("2026-07-01")
DELTA = 0.30


def test_the_audit_recovers_an_injected_effect_of_known_size():
    params = Params(bootstrap_resamples=0)
    span = periods(EFFECTIVE, params)
    days = (span["post_end"] - span["pre_start"]).days + 1
    samples = scheduled_panel(21, span["pre_start"], days, "A", np.random.default_rng(11))
    calls, cells, corridors = audit_inputs(samples, "A", params)
    effective_at = (EFFECTIVE + pd.Timedelta(hours=1)).tz_localize(LOCAL_TZ).isoformat()
    interventions = pd.DataFrame({"id": ["works"], "corridor_id": ["c00"],
                                  "effective_at": [effective_at]})

    def audit(frame):
        tables = intervention_audits(frame, cells, corridors, interventions, params,
                                     sensitivity=False)
        return tables["intervention_audit"].iloc[0]

    null = audit(calls)
    injected, before, after = inject_bti_effect(calls, "c00", span["post_start"],
                                                span["post_end"], DELTA, params)
    found = audit(injected)

    assert params.audit_pre_blocks == 12
    assert after - before == pytest.approx(DELTA)
    assert null.status == "ok" and found.status == "ok"
    assert found.n_donors >= 19
    # true of any panel: the injection moves the treated corridor's pooled post BTI by
    # exactly DELTA and nothing else, so the estimate moves by exactly DELTA
    assert found.effect - null.effect == pytest.approx(DELTA, abs=1e-9)
    # true of any panel: no p can fall below 1 / (placebos + 1), here at most 0.05
    assert found.placebo_p_floor == pytest.approx(1 / (found.n_placebos + 1))
    assert found.placebo_p_floor <= 0.05
    # what the sweep says holds at this size: the treated corridor ranks first
    assert found.placebo_rank == 1 and found.placebo_extreme
