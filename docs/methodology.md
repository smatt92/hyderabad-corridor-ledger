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
  `audit_block_days` days before it (default 12 × 14 = 168 days), 9 settling
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
  same donors, published with the gap between the two estimates and whether
  they point in opposite directions.

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
  The published p is always shown with its rank, the placebo count and that
  floor.
- **The ranked statistic is the standardised effect**, |effect| divided by the
  corridor's own leave-one-block-out pre RMSPE. Three candidates were tested
  (audit_power.md sections 3 and 4):
  - raw |effect| holds size only when the treated corridor is typical of its
    donors. With the treated corridor made the most congested and volatile the
    model can draw, it excluded zero on 11% and 12% of no-effect panels at 40
    donors. Real corridors are not exchangeable: an outer ring road segment and
    an inner-city arterial differ in volatility, and raw |effect| ranks the
    volatile one as significant.
  - the post/pre RMSPE ratio (Abadie's statistic) normalises for fit, but its
    in-sample denominator goes to zero when the weights reproduce the pre
    series exactly. It held size under stress (2–4%) and had little power: 0.10
    to 0.64 at a 0.20 BTI effect.
  - the standardised effect normalises like the ratio with an error the fit
    cannot shrink. Under stress it held size (3–7%) with power 0.71–0.89 at
    0.20 BTI. On exchangeable panels its size was 0–12% per cell (50 panels
    each), consistent with the exact value, at most 1/(n + 1) below 5%.

  A corridor whose held-out pre error is zero has no scale; it is left unranked
  and the verdict says why.
- **No interval.** No confidence interval is published for the effect. A
  percentile bootstrap resampling calls within each corridor and period was
  tested in [audit_power.md](audit_power.md) sections 2 and 5:
  - with the simulated weekly corridor drift (sd 0.08), across 10 scenarios
    (Tiers A and B; 6–18 pre blocks; 20–40 donors; 28–56 post days; 80
    panels each), it excluded zero on 6% of no-effect panels and covered the
    true effect in 97% on average, 91% at worst;
  - with weekly drift 2.5 times larger (sd 0.20; 4 scenarios, 100 panels
    each), it excluded zero on 20% of no-effect panels (16–26% per scenario)
    and covered the true effect in 80–86%, with a standard error 0.65–0.80 of
    the estimate's actual spread. The equal-weight interval covered 76–85%;
  - resampling whole weeks or whole 14-day blocks failed even at low drift
    (11% and 26% size): a 28-day post period holds four weeks or two blocks.

  How much Hyderabad corridors drift from week to week is unknown until data
  arrives. An interval that holds in only one regime needs a gate that
  withholds it in the other, and none was found. Publishing only when the
  bootstrap standard error was at least the spread implied by the held-out pre
  blocks still left 17% size and 83–86% coverage among the intervals published
  under high drift, because that ratio barely tracks the actual error
  (correlation −0.08 and −0.17). So there is no interval. The placebo rank
  needs no variance estimate and held its size under both drift levels (2–8%)
  and under a noisy treated corridor (3–7%). An interval may return only after
  a calibration run on measured Hyderabad drift holds size and coverage.
- **No sequential test.** An earlier version published an always-valid
  confidence sequence on the gaps between treated and synthetic block BTIs,
  meant to be read after each post block. At the default six pre blocks and
  28 post days it excluded zero on 12–18% of no-effect panels (20 and 40
  donors, in both sweeps) against a nominal 5%. Its scale came from the
  pre-period residuals, which an overfitted synthetic control drives toward
  zero. Where it did hold size, at 12 or more pre blocks, it was 0.20–0.46
  BTI wide, too wide to say anything. It was removed. The audit reports once,
  after the post period closes, and nothing may be read off a partial post
  period.
- **Overfitting diagnostic.** Each audit publishes the in-sample pre RMSPE, a
  leave-one-block-out pre RMSPE (`cv_pre_rmspe`: each pre block predicted by
  weights refitted, donor selection included, on the other blocks),
  `overfit_ratio` = in-sample / held-out, `pre_fit_overfit` when that ratio is
  below `audit_overfit_ratio` (0.5), and `n_active_donors`. Placebos carry
  their own `cv_pre_rmspe`.

## Weighting: demeaned, levels, or a donor cap

With six pre blocks and many donors, simplex weights can reproduce the
treated corridor's pre series exactly, and an exact fit predicts nothing.
Levels weights cut the share of exact fits at six pre blocks from 6–43% of
panels to 2–20%, and a five-donor cap to 0%. Neither restored the placebo
ranking: at six pre blocks the RMSPE-ratio rank detected nothing up to 0.45
BTI under any of the three. Neither changed the estimate's spread (null-effect
sd 0.049–0.055 at 20 and 40 donors). Exact fits disappear at twelve pre blocks
with demeaned weights and nine with levels. With the standardised rank, levels
reached 0.20 BTI at 9 blocks and demeaned at 12 with 20 donors, and the order
reversed at 40 donors (6 against 9): no consistent advantage. Demeaned weights
stay the default, and the pre-period length, not the weighting, is what fixes
the hull problem.

## What the audit can detect

Minimum detectable effect (MDE): the smallest BTI change the standardised
placebo rank detects in at least 80% of simulated panels, Tier A, 28-day post
period, 50 panels per cell. Percentages are of 0.54, the median pooled peak BTI
of a simulated corridor (interquartile range 0.49–0.59); real Hyderabad values
are unknown until data arrives.

**By pre-period length first.**

| pre blocks | weeks | MDE, 20 donors | MDE, 40 donors |
|---|---|---|---|
| 6 | 12 | 0.30 (56%) | 0.20 (37%) |
| 9 | 18 | 0.30 (56%) | 0.20 (37%) |
| 12 | 24 | 0.20 (37%) | 0.20 (37%) |
| 15 | 30 | 0.15 (28%) | 0.15 (28%) |
| 18 | 36 | 0.15 (28%) | 0.15 (28%) |
| 24 | 48 | 0.15 (28%) | 0.15 (28%) |
| 30 | 60 | 0.15 (28%) | 0.15 (28%) |

- A 0.20 change needs 24 weeks of pre-period at 20 donors, 12 at 40.
- A 0.15 change needs 30 weeks at either.
- A 0.10 change (18%) is not reached at any length up to 60 weeks: power
  peaked at 0.72 (20 donors) and 0.74 (40). Beyond about 15 blocks more
  pre-period buys nothing, because the estimate's spread is then set by the
  28-day post period.

**Then donors.** Doubling from 20 to 40 donors helps only with a short pre
period (0.30 to 0.20 at 6–9 blocks). With 10 donors no placebo p can reach
0.05 at all. Tier B corridors lose so many donors and treated blocks to the
200-call floor that nothing was detectable (30–62% of audits withheld, 9–12
usable donors from 20).

**Then post-period length.** A 56-day post period is the lever for smaller
effects. It was tested only for the other rank statistics (audit_power.md
section 1): there the smallest detected effect fell to 0.10 BTI only with 40
donors, 18 pre blocks and 56 post days. The standardised rank at 56 days is
untested.

**The capability statement.** With 24 weeks of pre-period, 20 Tier A donors
and a 28-day post period, this audit reliably detects a change of about 0.20
BTI, a third of a typical corridor's buffer. That is the scale of removing a
corridor's recurring breakdown: a flyover or grade separation at the junction
where its queues form, or a new link that takes a large share of its through
traffic. A signal retiming, an enforcement drive or a turning restriction
usually trims delay without removing the breakdown. If one moves BTI by 10–15%,
this audit will most likely report "not extreme", and that says nothing about
whether it worked. Which intervention produces which BTI change is a judgement,
not a measurement from this project. BTI is (p95 − mean) / mean, so a change
that shortens every trip by the same proportion leaves it unchanged: an
intervention can cut travel times without moving BTI at all.

## Limits of this evidence

- Every number above comes from `scripts/dev/panel_model.py`, whose noise
  sizes (a city-wide daily shock with sd 0.10, weekly corridor drift with sd
  0.08, per-call volatility and failure rates) are assumptions. Re-run the
  sweep on real data once a corridor has a full audit window.
- The injected effect stretches peak-hour travel times about their mean, so it
  moves the pooled BTI by exactly the amount injected and nothing else. A real
  intervention also shifts the mean, varies from week to week and may take
  longer than 9 days to settle.
- Exchangeability is assumed, not tested: the stress panel makes the treated
  corridor noisier than its donors, not trending differently.
