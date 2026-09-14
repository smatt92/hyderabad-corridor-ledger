# The donor floor: where the placebo rank holds its size

Generated 2026-09-14 11:05 UTC by `scripts/dev/donor_floor.py` at 1596620 (plus uncommitted changes), 800 panels per cell at 30-minute peaks, rendered from the saved records.

19 usable donors is where a placebo p first can reach 0.05, since with n placebos the smallest p is 1/(n+1). This asks where the rank rule's false-positive rate is actually at its nominal 5%. Every audit is the full `metrics.audit` run on panel_model panels with no effect (size) or a known BTI effect injected into the treated corridor's post period (power), failure parameter 1% so that every declared donor is usable, 14-day blocks, 12 pre blocks, 28-day post period.

- `size`: share of no-effect audits reading extreme, with its Wilson 95% interval. `by rank alone`: floor(0.05 x (n + 1)) / (n + 1), what an exactly exchangeable placebo rank would give.
- `floor`: the fewest donors from which, at every larger count swept, the interval reaches 5%. A count whose interval sits wholly above 5% has a size distinguishably above nominal.

## What it found

- The rank held its nominal size at every count swept, from 19 donors up, under both placebo designs. The fewest donors at which a p of 0.05 exists is also, in this model, where the rule holds its size, so the floor is 19.
- Putting the treated corridor in every placebo pool moved no count's size outside the other design's interval (both designs ran on the same panels).
- docs/audit_power.md section 4 read a size of 10% at 20 Tier A donors: 5 of 50 panels, whose Wilson 95% interval runs 4.3% to 21.4%. Tier A at 20 donors here, every donor usable, reads 6.0% on 400 panels.

## Placebos: current

Floor: **19 donors**.

| donors | panels | withheld | placebos | size (95% interval) | by rank alone | power 0.20 | power 0.30 |
|---|---|---|---|---|---|---|---|
| 19 | 800 | 0% | 19.0 | 5.8% (4.3% to 7.6%) | 5.0% | 0.75 | 0.93 |
| 20 | 800 | 0% | 20.0 | 4.3% (3.1% to 5.9%) | 4.8% | 0.77 | 0.92 |
| 23 | 800 | 0% | 23.0 | 4.3% (3.1% to 5.9%) | 4.2% | 0.74 | 0.91 |
| 26 | 800 | 0% | 26.0 | 5.2% (3.9% to 7.0%) | 3.7% | 0.77 | 0.93 |
| 29 | 800 | 0% | 29.0 | 4.4% (3.2% to 6.0%) | 3.3% | 0.72 | 0.92 |
| 35 | 800 | 0% | 35.0 | 2.4% (1.5% to 3.7%) | 2.8% | 0.67 | 0.89 |
| 40 | 800 | 0% | 40.0 | 4.6% (3.4% to 6.3%) | 4.9% | 0.81 | 0.96 |
| 50 | 800 | 0% | 50.0 | 4.9% (3.6% to 6.6%) | 3.9% | 0.76 | 0.94 |

## Placebos: treated in pool

Floor: **19 donors**.

| donors | panels | withheld | placebos | size (95% interval) | by rank alone | power 0.20 | power 0.30 |
|---|---|---|---|---|---|---|---|
| 19 | 800 | 0% | 19.0 | 5.0% (3.7% to 6.7%) | 5.0% | 0.73 | 0.90 |
| 20 | 800 | 0% | 20.0 | 3.9% (2.7% to 5.5%) | 4.8% | 0.73 | 0.88 |
| 23 | 800 | 0% | 23.0 | 4.0% (2.9% to 5.6%) | 4.2% | 0.71 | 0.88 |
| 26 | 800 | 0% | 26.0 | 4.2% (3.1% to 5.9%) | 3.7% | 0.73 | 0.90 |
| 29 | 800 | 0% | 29.0 | 4.1% (3.0% to 5.7%) | 3.3% | 0.69 | 0.89 |
| 35 | 800 | 0% | 35.0 | 2.1% (1.3% to 3.4%) | 2.8% | 0.64 | 0.84 |
| 40 | 800 | 0% | 40.0 | 4.2% (3.1% to 5.9%) | 4.9% | 0.80 | 0.95 |
| 50 | 800 | 0% | 50.0 | 4.9% (3.6% to 6.6%) | 3.9% | 0.76 | 0.94 |

## Cross-check at 15-minute peaks (Tier A)

| tier | donors | placebos | panels | size (95% interval) |
|---|---|---|---|---|
| A | 20 | current | 400 | 6.0% (4.1% to 8.8%) |
| A | 20 | treated in pool | 400 | 5.0% (3.3% to 7.6%) |
| A | 40 | current | 400 | 3.5% (2.1% to 5.8%) |
| A | 40 | treated in pool | 400 | 3.2% (1.9% to 5.5%) |

## Limits

- The panels are panel_model's. Its noise sizes are assumptions, and size depends on how alike the treated corridor and its donors are; real corridors differ more than these.
- Every donor here is usable. On a real panel failures exclude some, and the floor applies to the donors that remain.

