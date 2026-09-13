import numpy as np
import pandas as pd
import pytest

from metrics.worst15 import worst_15
from tests.helpers import local

DAY = pd.Timestamp("2026-09-01")


def test_worst_15_minute_window_and_its_timing():
    times = ["08:00", "08:05", "08:10", "08:15", "08:20", "08:25"]
    tti = pd.DataFrame({
        "corridor_id": "a",
        "day": DAY,
        "requested_at": [local(f"2026-09-01 {t}") for t in times],
        "tti_tomtom": [1.2, 1.8, 2.4, 3.0, 1.2, 1.0],
        "tti_p5": np.nan,
    })
    daily = pd.DataFrame({"corridor_id": ["a"], "day": [DAY], "missing_rate": [0.1],
                          "low_confidence": [False]})
    out = worst_15(tti, daily).set_index("basis")

    # Windows are (t - 15 min, t]. Means ending at each call:
    #   08:00 1.2 | 08:05 1.5 | 08:10 1.8 | 08:15 (1.8+2.4+3.0)/3 = 2.4
    #   08:20 (2.4+3.0+1.2)/3 = 2.2 | 08:25 (3.0+1.2+1.0)/3 = 1.7333
    tomtom = out.loc["tomtom"]
    assert tomtom.tti == pytest.approx(2.4)
    assert tomtom.window_end == local("2026-09-01 08:15")
    assert tomtom.window_start == local("2026-09-01 08:00")
    assert tomtom.n_samples == 3
    assert tomtom.missing_rate == pytest.approx(0.1)

    # no p5 reference that day: reported as absent, not estimated
    p5 = out.loc["p5"]
    assert np.isnan(p5.tti) and p5.n_samples == 0 and pd.isna(p5.window_end)
