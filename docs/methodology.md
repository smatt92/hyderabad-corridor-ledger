# Intervention audit: methodology

What `metrics/audit.py` estimates, what it assumes, and how large an effect it
can detect. Every number in the power section comes from simulated panels
(`scripts/dev/audit_power.py`, full tables in [audit_power.md](audit_power.md)),
not from Hyderabad data. Re-estimate once real data covers a full audit.

## What is estimated

The audit asks whether a corridor's buffer time index (BTI, (p95 − mean) /
mean of peak-hour travel times) changed after a declared intervention, beyond
what comparable untreated corridors did over the same days.

- **Pooling.** BTI describes a distribution, so it is computed once on pooled
  successful peak-hour calls (06:30–10:30 and 16:30–21:00 IST), never
  averaged from cells. A BTI needs 200 pooled calls; below that it is NULL.
- **Periods.** Fixed by the intervention day: `audit_pre_blocks` blocks of
  `audit_block_days` days before it (default 6 × 14 = 84 days), 9 settling
  days excluded, then `audit_post_blocks` blocks (default 2 × 14 = 28 days).
- **Donors.** Corridors no intervention touches, outside the treated
  corridor's pair (diversion onto a paired alternate is a consequence of the
  change, not a control), with every pre block at the floor and a pooled post
  BTI at the floor. Every corridor considered is published with its weight or
  its exclusion reason.
- **Synthetic control.** Weights `w` minimise the squared error between the
  treated corridor's pre-block BTI series and `Σ w_j × donor_j`, subject to
  `w_j ≥ 0` and `Σ w_j = 1`. With the default `audit_weights = "demeaned"`
  both series are demeaned first and the level difference is a fixed shift;
  `"levels"` matches levels with no shift. `audit_max_donors > 0` caps the
  nonzero weights by greedy forward selection. The constraints are enforced
  by non-negative least squares with the sum-to-one condition as a heavily
  weighted extra row, then renormalised; `tests/test_audit.py` checks them on
  random inputs for every option.
- **Headline.**
  `effect = (treated_post − synthetic_post) − (treated_pre − synthetic_pre)`,
  every term a BTI pooled once over its whole period.
- **Cross-check.** The same difference against the equal-weight mean of the
  same donors, published with the gap between the two estimates.

## What it assumes

- **Exchangeability.** A placebo test compares the treated corridor with
  untreated donors run through the same procedure. Its p is exact only if,
  absent the intervention, the treated corridor is no more likely than any
  donor to show a large post-period departure. Interventions are not assigned
  at random: roads get flyovers and signal retiming because they are
  congested and changing. A treated corridor already trending differently
  from the donor pool breaks this assumption, and no statistic computed from
  the same panel can detect that it has.
- **No interference.** Donors are unaffected by the intervention. The
  treated pair's alternate is excluded for this reason; a diversion onto an
  unpaired nearby road is not detected.
- **Donor pool.** Failed calls cluster at peak hours on congested roads, so
  the corridors dropped for a thin pre block are disproportionately the
  congested ones. The donor pool is not a random sample of the network. Each
  audit publishes the excluded corridors' missing rate and BTI beside the
  donors', and the estimate rerun at stricter and looser completeness
  thresholds (`audit_sensitivity`).

## Inference

- **Placebo rank.** The procedure runs with each donor as the treated
  corridor, its own pair excluded from its pool. The treated corridor's
  statistic is ranked among the placebos'. With n placebos, rank r gives
  p = r / (n + 1); ties count against the treated corridor, and no p can be
  below 1 / (n + 1). With fewer than 19 placebos no effect can reach p ≤ 0.05.
  The published p uses the post/pre RMSPE ratio and is always shown with its
  rank, the placebo count and that floor.
- **Bootstrap interval.** `audit_bootstrap = "blocks"` (default) resamples
  whole units of `audit_bootstrap_days` days within each period, the same
  units for every corridor, with weights held fixed. `"calls"` resamples
  single calls independently per corridor.
- **Confidence sequence.** Each completed post block gives a gap between the
  treated block BTI and the synthetic one. An always-valid confidence sequence
  on their running mean may be read after every block.
- **Overfitting diagnostic.** Each audit publishes the in-sample pre RMSPE, a
  leave-one-block-out pre RMSPE (`cv_pre_rmspe`: each pre block predicted by
  weights refitted, donor selection included, on the other blocks),
  `overfit_ratio` = in-sample / held-out, `pre_fit_overfit` when that ratio is
  below `audit_overfit_ratio` (0.5), and `n_active_donors`. Placebos carry
  their own `cv_pre_rmspe`.

<!-- SWEEP RESULTS: validity, MDE, recommendation -->
