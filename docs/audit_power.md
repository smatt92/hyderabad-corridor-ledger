# Intervention audit: power and minimum detectable effect

Generated 2026-09-13 15:56 UTC by `scripts/dev/audit_power.py` at a9abfeb, 40 simulated panels per scenario, 9 min.

Panels come from `scripts/dev/panel_model.py`: the fixture generator's travel-time model on the collector's schedule, with a city-wide daily shock (sd 0.10) and per-corridor weekly drift (sd 0.08) on the excess over free flow. Those sizes are assumptions, not Hyderabad estimates. An effect of known size is injected into the treated corridor's pooled post-period BTI; the real audit then runs unchanged. Pre period 84 days in six 14-day blocks, settling 9 days.

Detection rules: `interval` = synthetic-control 95% bootstrap interval excludes zero; `placebo ratio` = published permutation p (post/pre RMSPE ratio) <= 0.05; `placebo |effect|` = treated |effect| ranked among placebo |effects|, p <= 0.05; `equal` = equal-weight interval excludes zero. A rule is usable only where its false-positive rate (effect 0) is near 0.05. MDE = smallest injected BTI effect detected in at least 80% of panels. `exact pre fits` = share of panels whose synthetic control reproduces all six pre blocks (pre RMSPE < 1e-06). `donors used` is after exclusions for incomplete pre blocks.

| tier | donors | donors used | post days | exact pre fits | false pos. interval | false pos. placebo ratio | false pos. placebo |effect| | false pos. equal | power 0.03 (interval) | power 0.06 (interval) | power 0.10 (interval) | power 0.15 (interval) | power 0.25 (interval) | MDE interval | MDE placebo ratio | MDE placebo |effect| | MDE equal | bias at 0.15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 10 | 10.0 | 28 | 0.03 | 0.10 | 0.00 | 0.00 | 0.05 | 0.12 | 0.35 | 0.57 | 0.85 | 0.97 | 0.15 | > 0.25 | > 0.25 | 0.15 | +0.008 |
| A | 10 | 10.0 | 56 | 0.00 | 0.05 | 0.00 | 0.00 | 0.10 | 0.10 | 0.47 | 0.70 | 0.85 | 1.00 | 0.15 | > 0.25 | > 0.25 | 0.15 | -0.007 |
| A | 20 | 20.0 | 28 | 0.10 | 0.05 | 0.05 | 0.05 | 0.05 | 0.05 | 0.17 | 0.60 | 0.85 | 1.00 | 0.15 | > 0.25 | 0.25 | 0.15 | +0.006 |
| A | 20 | 20.0 | 56 | 0.15 | 0.10 | 0.03 | 0.05 | 0.05 | 0.10 | 0.30 | 0.65 | 0.93 | 1.00 | 0.15 | > 0.25 | 0.15 | 0.10 | +0.005 |
| A | 40 | 40.0 | 28 | 0.23 | 0.07 | 0.00 | 0.07 | 0.07 | 0.17 | 0.38 | 0.65 | 0.82 | 1.00 | 0.15 | > 0.25 | 0.15 | 0.15 | +0.003 |
| A | 40 | 39.9 | 56 | 0.20 | 0.05 | 0.00 | 0.10 | 0.05 | 0.07 | 0.33 | 0.60 | 0.90 | 1.00 | 0.15 | > 0.25 | 0.15 | 0.15 | -0.005 |
| B | 10 | 6.3 | 28 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.04 | 0.12 | 0.29 | 0.58 | 0.92 | 0.25 | > 0.25 | > 0.25 | 0.25 | +0.003 |
| B | 10 | 6.2 | 56 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.15 | 0.50 | 0.70 | 1.00 | 0.25 | > 0.25 | > 0.25 | 0.25 | -0.000 |
| B | 20 | 12.5 | 28 | 0.04 | 0.00 | 0.00 | 0.00 | 0.00 | 0.09 | 0.26 | 0.48 | 0.57 | 0.96 | 0.25 | > 0.25 | > 0.25 | 0.15 | +0.022 |
| B | 20 | 12.2 | 56 | 0.00 | 0.05 | 0.00 | 0.00 | 0.05 | 0.05 | 0.19 | 0.52 | 0.76 | 0.95 | 0.25 | > 0.25 | > 0.25 | 0.15 | -0.005 |
| B | 40 | 25.3 | 28 | 0.35 | 0.09 | 0.00 | 0.13 | 0.09 | 0.04 | 0.04 | 0.17 | 0.57 | 0.91 | 0.25 | > 0.25 | > 0.25 | 0.25 | -0.016 |
| B | 40 | 24.9 | 56 | 0.09 | 0.09 | 0.00 | 0.05 | 0.00 | 0.09 | 0.23 | 0.50 | 0.82 | 0.95 | 0.15 | > 0.25 | 0.25 | 0.15 | -0.011 |

Panels withheld by the audit itself: 642 of 2880 ({'insufficient_pre': 642}).
