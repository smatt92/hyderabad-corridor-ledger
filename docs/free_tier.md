# What TomTom's free Routing allowance can support

Generated 2026-09-14 11:02 UTC by `scripts/dev/free_tier.py`, 200 panels per cadence and failure rate, 1 min. TomTom's pricing page lists the Routing API at 20,000 free calls a month (read 2026-09-14). Every design audits one of 4 treated corridors (the Miyapur-Allwyn package, both directions) with 14-day blocks, 12 pre blocks and a 28-day post period. Panels are `scripts/dev/panel_model.py`'s, whose failure structure is an assumption; nobody has measured TomTom's failure rate from Hyderabad.

## Verdict

- q = 0%: the widest panel satisfying all three is 33 ids (29 donors, 2 night slots), at 0.6% of peak calls failed. Some panel still qualifies up to 6.4% (29 ids, 2 night slots); from 7.7% none does.
- q = 5%: the widest panel satisfying all three is 31 ids (27 donors, 2 night slots), at 0.6% of peak calls failed. Some panel still qualifies up to 6.4% (28 ids, 2 night slots); from 7.7% none does.

At 30-minute peaks the treated corridor alone withholds more than 20% of audits once about 8.0% of peak calls fail, whatever the panel's width, because a 14-day block has 238 peak slots against a floor of 200.

## 1. Calls in a 31-day month

Per corridor: every peak slot and night slot for 31 days, with retries, plus a weekly road refetch. `f` is the share of slots that still fail after all attempts, each of which spent three; `q` is the chance an attempt fails and is retried on a slot that then succeeds. Neither has been measured: `q` is shown at 0 and 5%. Widest panel = most corridor ids whose month fits 20,000; donors = ids − 4 treated. A panel with fewer than 19 donors, the donor floor, is ruled out: the audit withholds its verdict below the floor (docs/donor_floor.md), whatever the budget.

| peak cadence | night slots | calls a day | q | calls a month per id at f 0 | widest ids (donors) at f 0% | widest ids (donors) at f 2% | widest ids (donors) at f 4% | widest ids (donors) at f 6% | widest ids (donors) at f 8% | widest ids (donors) at f 10% |
|---|---|---|---|---|---|---|---|---|---|---|
| 30 min | 8 | 25 | 0% | 779 | 25 (21) | 24 (20) | 23 (19) | 22 (18) ✗ | 22 (18) ✗ | 21 (17) ✗ |
| 30 min | 8 | 25 | 5% | 820 | 24 (20) | 23 (19) | 22 (18) ✗ | 21 (17) ✗ | 21 (17) ✗ | 20 (16) ✗ |
| 30 min | 4 | 21 | 0% | 655 | 30 (26) | 29 (25) | 28 (24) | 27 (23) | 26 (22) | 25 (21) |
| 30 min | 4 | 21 | 5% | 690 | 29 (25) | 27 (23) | 27 (23) | 26 (22) | 25 (21) | 24 (20) |
| 30 min | 2 | 19 | 0% | 593 | 33 (29) | 32 (28) | 31 (27) | 30 (26) | 29 (25) | 28 (24) |
| 30 min | 2 | 19 | 5% | 624 | 32 (28) | 30 (26) | 29 (25) | 28 (24) | 27 (23) | 27 (23) |
| 20 min | 8 | 34 | 0% | 1,058 | 18 (14) ✗ | 18 (14) ✗ | 17 (13) ✗ | 16 (12) ✗ | 16 (12) ✗ | 15 (11) ✗ |
| 20 min | 8 | 34 | 5% | 1,114 | 17 (13) ✗ | 17 (13) ✗ | 16 (12) ✗ | 16 (12) ✗ | 15 (11) ✗ | 15 (11) ✗ |
| 20 min | 4 | 30 | 0% | 934 | 21 (17) ✗ | 20 (16) ✗ | 19 (15) ✗ | 19 (15) ✗ | 18 (14) ✗ | 17 (13) ✗ |
| 20 min | 4 | 30 | 5% | 983 | 20 (16) ✗ | 19 (15) ✗ | 18 (14) ✗ | 18 (14) ✗ | 17 (13) ✗ | 17 (13) ✗ |
| 20 min | 2 | 28 | 0% | 872 | 22 (18) ✗ | 22 (18) ✗ | 21 (17) ✗ | 20 (16) ✗ | 19 (15) ✗ | 19 (15) ✗ |
| 20 min | 2 | 28 | 5% | 918 | 21 (17) ✗ | 21 (17) ✗ | 20 (16) ✗ | 19 (15) ✗ | 18 (14) ✗ | 18 (14) ✗ |
| 15 min | 8 | 42 | 0% | 1,306 | 15 (11) ✗ | 14 (10) ✗ | 14 (10) ✗ | 13 (9) ✗ | 13 (9) ✗ | 12 (8) ✗ |
| 15 min | 8 | 42 | 5% | 1,375 | 14 (10) ✗ | 14 (10) ✗ | 13 (9) ✗ | 13 (9) ✗ | 12 (8) ✗ | 12 (8) ✗ |
| 15 min | 4 | 38 | 0% | 1,182 | 16 (12) ✗ | 16 (12) ✗ | 15 (11) ✗ | 15 (11) ✗ | 14 (10) ✗ | 14 (10) ✗ |
| 15 min | 4 | 38 | 5% | 1,244 | 16 (12) ✗ | 15 (11) ✗ | 14 (10) ✗ | 14 (10) ✗ | 14 (10) ✗ | 13 (9) ✗ |
| 15 min | 2 | 36 | 0% | 1,120 | 17 (13) ✗ | 17 (13) ✗ | 16 (12) ✗ | 15 (11) ✗ | 15 (11) ✗ | 14 (10) ✗ |
| 15 min | 2 | 36 | 5% | 1,179 | 16 (12) ✗ | 16 (12) ✗ | 15 (11) ✗ | 15 (11) ✗ | 14 (10) ✗ | 14 (10) ✗ |

✗: fewer than 19 donors, ruled out. Every 20- and 15-minute design is ruled out at every failure rate: the allowance cannot hold 23 ids at those cadences.

## 2. Where the audit breaks

Withheld: the treated corridor misses the floor in a pre block or the post period. Its breaking point does not depend on the panel's width. Usable donors depend on how many are declared. `auditable` = run and holding at least 19 usable donors. Failure rates are the share of peak-hour calls failed, as the collector would measure it.

| peak cadence | design | withheld crosses 20% | under 80% keep 19 donors | under 80% auditable |  |
|---|---|---|---|---|---|
| 30 min | 23 ids (19 donors) | 8.0% | 3.1% | 3.1% |  |
| 30 min | 25 ids (21 donors) | 8.0% | 6.4% | 5.8% |  |
| 30 min | 27 ids (23 donors) | 8.0% | 7.2% | 6.7% |  |
| 30 min | 29 ids (25 donors) | 8.0% | 7.8% | 7.1% |  |
| 30 min | 31 ids (27 donors) | 8.0% | 8.1% | 7.7% |  |
| 30 min | 33 ids (29 donors) | 8.0% | 8.4% | 7.8% |  |
| 20 min | — | > 12.7% | — | — | ruled out by budget |
| 15 min | — | > 12.8% | — | — | ruled out by budget |

The curves at 30 minutes:

| peak calls failed | withheld | auditable, 19 donors | auditable, 21 donors | auditable, 23 donors | auditable, 25 donors | auditable, 27 donors | auditable, 29 donors |
|---|---|---|---|---|---|---|---|
| 0.6% | 0% | 100% | 100% | 100% | 100% | 100% | 100% |
| 1.3% | 0% | 100% | 100% | 100% | 100% | 100% | 100% |
| 1.9% | 0% | 96% | 100% | 100% | 100% | 100% | 100% |
| 2.6% | 2% | 88% | 98% | 98% | 98% | 98% | 98% |
| 3.2% | 2% | 78% | 98% | 98% | 98% | 98% | 98% |
| 3.8% | 4% | 66% | 96% | 96% | 96% | 96% | 96% |
| 4.5% | 5% | 53% | 92% | 94% | 95% | 95% | 95% |
| 5.1% | 6% | 39% | 88% | 94% | 94% | 94% | 94% |
| 6.4% | 9% | 18% | 72% | 88% | 91% | 91% | 91% |
| 7.7% | 17% | 2% | 28% | 59% | 72% | 81% | 83% |
| 8.9% | 29% | 0% | 0% | 5% | 16% | 34% | 47% |
| 10.2% | 55% | 0% | 0% | 0% | 0% | 0% | 0% |
| 12.7% | 90% | 0% | 0% | 0% | 0% | 0% | 0% |

## 3. The widest auditable panel that fits

At each failure rate, 30-minute peaks: the most ids whose month fits 20,000 with that failure rate's retries, and whether that panel is auditable (80% of audits run with at least 19 usable donors, and no more than 20% withheld). Panels wider than 33 ids are scored as 33, which understates them.

q = 0%:

| peak calls failed | withheld | 8 night slots: widest ids (auditable) | 4 night slots: widest ids (auditable) | 2 night slots: widest ids (auditable) | widest that satisfies all three |
|---|---|---|---|---|---|
| 0.6% | 0% | 25 (100%) | 30 (100%) | 33 (100%) | 33 ids, 2 night slots |
| 1.3% | 0% | 25 (100%) | 29 (100%) | 32 (100%) | 32 ids, 2 night slots |
| 1.9% | 0% | 24 (100%) | 29 (100%) | 32 (100%) | 32 ids, 2 night slots |
| 2.6% | 2% | 24 (98%) | 29 (98%) | 32 (98%) | 32 ids, 2 night slots |
| 3.2% | 2% | 24 (94%) | 28 (98%) | 31 (98%) | 31 ids, 2 night slots |
| 3.8% | 4% | 23 (66%) ✗ | 28 (96%) | 31 (96%) | 31 ids, 2 night slots |
| 4.5% | 5% | 23 (53%) ✗ | 28 (95%) | 30 (95%) | 30 ids, 2 night slots |
| 5.1% | 6% | 23 (39%) ✗ | 27 (94%) | 30 (94%) | 30 ids, 2 night slots |
| 6.4% | 9% | 22 ✗ | 27 (88%) | 29 (91%) | 29 ids, 2 night slots |
| 7.7% | 17% | 22 ✗ | 26 (46%) ✗ | 29 (72%) ✗ | none |
| 8.9% | 29% | 21 ✗ | 25 (0%) ✗ | 28 (10%) ✗ | none |
| 10.2% | 55% | 21 ✗ | 25 (0%) ✗ | 28 (0%) ✗ | none |
| 12.7% | 90% | 20 ✗ | 24 (0%) ✗ | 26 (0%) ✗ | none |

q = 5%:

| peak calls failed | withheld | 8 night slots: widest ids (auditable) | 4 night slots: widest ids (auditable) | 2 night slots: widest ids (auditable) | widest that satisfies all three |
|---|---|---|---|---|---|
| 0.6% | 0% | 24 (100%) | 28 (100%) | 31 (100%) | 31 ids, 2 night slots |
| 1.3% | 0% | 23 (100%) | 28 (100%) | 31 (100%) | 31 ids, 2 night slots |
| 1.9% | 0% | 23 (96%) | 28 (100%) | 30 (100%) | 30 ids, 2 night slots |
| 2.6% | 2% | 23 (88%) | 27 (98%) | 30 (98%) | 30 ids, 2 night slots |
| 3.2% | 2% | 23 (78%) ✗ | 27 (98%) | 30 (98%) | 30 ids, 2 night slots |
| 3.8% | 4% | 22 ✗ | 27 (96%) | 29 (96%) | 29 ids, 2 night slots |
| 4.5% | 5% | 22 ✗ | 26 (94%) | 29 (95%) | 29 ids, 2 night slots |
| 5.1% | 6% | 22 ✗ | 26 (94%) | 29 (94%) | 29 ids, 2 night slots |
| 6.4% | 9% | 21 ✗ | 25 (72%) ✗ | 28 (90%) | 28 ids, 2 night slots |
| 7.7% | 17% | 21 ✗ | 25 (28%) ✗ | 28 (66%) ✗ | none |
| 8.9% | 29% | 20 ✗ | 24 (0%) ✗ | 27 (5%) ✗ | none |
| 10.2% | 55% | 20 ✗ | 24 (0%) ✗ | 26 (0%) ✗ | none |
| 12.7% | 90% | 19 ✗ | 23 (0%) ✗ | 25 (0%) ✗ | none |

## 4. What cutting night slots costs

The observed free-flow reference is the p5 of successful night-slot travel times (00:00-04:00 IST) over a trailing 28 days, published at 20 calls or more. TTI and PTI against it, and every table and ranking column on that basis, move with it. A panel_model panel cannot price the cut: its night travel times sit at the free-flow floor, so its p5 hardly moves with the slot count. So this is the sampling arithmetic, before failures, which only make it worse.

| night slots | spacing | calls in 28 days | p5 sits | percentile it lands on, ±2 sd | first published | night calls a month per id |
|---|---|---|---|---|---|---|
| 8 | every 30 min | 224 | between the 12th and 13th fastest | 2.1% to 7.9% | day 3 | 248 |
| 4 | every 60 min | 112 | between the 6th and 7th fastest | 0.9% to 9.1% | day 5 | 124 |
| 2 | every 120 min | 56 | between the 3rd and 4th fastest | 0.0% to 10.8% | day 10 | 62 |

- At 2 slots the reference sits between the 3rd and 4th fastest of 56 calls: one unusually fast night moves it, and it can land anywhere from about the 0th to the 11th percentile of night travel times. At 8 slots it sits between the 12th and 13th of 224, within about the 2nd to 8th. In seconds that depends on how spread night travel times are near their fastest, which nobody knows until night calls exist.
- Fewer slots also sample fewer night hours: 2 slots are 00:00 and 02:00, missing whichever hour is emptiest if it is another.
- A longer window buys calls back at the cost of reacting slower: 2 slots over 56 days pool 112 calls, as 4 slots do over 28, but a monsoon month's drift then takes twice as long to leave the reference.
- The budget side: each night slot a corridor drops saves 31 calls a month, so 8 → 2 frees 186 per corridor: 8 more corridors in 20,000 at 30-minute peaks with no failures (25 ids at 8 night slots, 33 at 2).

## 5. When pooled statistics first appear

Days of collection before each statistic clears its floor, at 0%, 5% and 12.5% of calls failed (12.5% is panel_model's rate). Ledger BTI and PTI pool every peak-hour call over 90 days (floor 200). The 24-hour profile and the route comparison pool one clock hour over 120 days (floor 200); hours the peak windows only partly cover get fewer slots. The weekly rhythm matrix takes a median per weekday and hour over 90 days (floor 30). `block slack`: the share of a 14-day block's peak calls that can fail before the block misses the audit's floor.

| peak cadence | failed | ledger BTI, PTI | profile, full peak hours | profile, partly covered hours | rhythm, full hours | rhythm, partly covered hours | block slack |
|---|---|---|---|---|---|---|---|
| 30 min | 0% | day 12 | day 100 | 06:00, 10:00, 16:00: never | never | 06:00, 10:00, 16:00: never | 16% |
| 30 min | 5% | day 13 | day 106 | 06:00, 10:00, 16:00: never | never | 06:00, 10:00, 16:00: never | 16% |
| 30 min | 12.5% | day 14 | day 115 | 06:00, 10:00, 16:00: never | never | 06:00, 10:00, 16:00: never | 16% |
| 20 min | 0% | day 8 | day 67 | 06:00, 16:00: day 100; 10:00: never | week 10 | 06:00, 10:00, 16:00: never | 45% |
| 20 min | 5% | day 9 | day 71 | 06:00, 16:00: day 106; 10:00: never | week 11 | 06:00, 10:00, 16:00: never | 45% |
| 20 min | 12.5% | day 9 | day 77 | 06:00, 16:00: day 115; 10:00: never | week 12 | 06:00, 10:00, 16:00: never | 45% |
| 15 min | 0% | day 6 | day 50 | 06:00, 10:00, 16:00: day 100 | week 8 | 06:00, 10:00, 16:00: never | 58% |
| 15 min | 5% | day 7 | day 53 | 06:00, 10:00, 16:00: day 106 | week 8 | 06:00, 10:00, 16:00: never | 58% |
| 15 min | 12.5% | day 7 | day 58 | 06:00, 10:00, 16:00: day 115 | week 9 | 06:00, 10:00, 16:00: never | 58% |

`never`: not within the window, however long the corridor runs.

## 6. Check: the shortcut against full audits

The same panels (the seeds `scripts/dev/audit_power.py` used) run through this script's call counting and through `metrics.audit`. Withheld or not, and the number of usable donors when the audit ran, must agree.

| failure rates | design | panels | withheld agrees | usable donors agree |
|---|---|---|---|---|
| model failure rates | 20 ids @ 15 min | 100 | 100% | 100% |
| model failure rates | 30 ids @ 30 min | 100 | 100% | 100% |
| model failure rates | 34 ids @ 30 min | 100 | 100% | 100% |
| model failure rates | 24 ids @ 20 min | 100 | 100% | 100% |
| 3% failure | 20 ids @ 15 min | 100 | 100% | 100% |
| 3% failure | 30 ids @ 30 min | 100 | 100% | 100% |
| 3% failure | 34 ids @ 30 min | 100 | 100% | 100% |
| 3% failure | 24 ids @ 20 min | 100 | 100% | 100% |

