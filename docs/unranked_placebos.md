# Unranked placebos

Generated 2026-09-14 13:27 UTC by `scripts/dev/unranked_placebos.py`, 800 panels per pre-block count, 16 min. panel_model panels at 30-minute peaks, failure parameter 1%, 20 declared donors, demeaned weights, 14-day blocks, 28-day post period, no effect.

A placebo is unranked when its leave-one-block-out pre-period error is zero: every pre block is predicted exactly by weights fitted on the others, so its effect has no scale. An audit left with fewer ranked placebos than the donor floor is withheld as `too_few_placebos`. The last column is a different condition, the treated corridor's exact in-sample fit, which docs/methodology.md measured when comparing weightings; it does not imply the first.

| pre blocks | panels | audits run | audits with an unranked placebo (95% interval) | unranked of placebo runs | treated fit exact in sample (95% interval) |
|---|---|---|---|---|---|
| 6 | 800 | 800 | 0 of 800 (0.0%; 0.0% to 0.5%) | 0 of 16000 | 120 of 800 (15.0%; 12.7% to 17.6%) |
| 12 | 800 | 799 | 0 of 799 (0.0%; 0.0% to 0.5%) | 0 of 15978 | 0 of 799 (0.0%; 0.0% to 0.5%) |

- Every panel here has near-complete data; a real panel loses donors to failures, which leaves fewer placebo runs but does not by itself unrank one.
- panel_model's corridors are more alike than real ones. Re-measure on real data.
