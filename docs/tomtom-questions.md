# Questions for TomTom

Assembled 2026-09-15, to send in one message and track until each is answered. Every
technical question TomTom's public documentation can answer has been answered from it
(`docs/data-sources.md`, "TomTom Traffic Stats: what the documentation settles"). What
remains is licensing, the quote, and four specifics.

## Tracking

| # | Question | Sent | Answered | Answer, in one line |
|---|---|---|---|---|
| 1 | Publication rights (clauses 11.4 and 11.6.1) | | | |
| 2 | Full-traversal statistics and their count | | | |
| 3 | Route identity across annual map updates | | | |
| 4 | Probe density on Hyderabad arterials | | | |
| Q | The Route Analysis quote | | | |

## Settled from the documentation: do not ask

| Finding | Source, read 2026-09-14 |
|---|---|
| **Confirmed: the metrics engine attaches.** `speedPercentiles` gives 19 percentiles, 5th to 95th in steps of 5, so a p95 travel time and an observed free-flow reference are both derivable. Route Analysis also returns route-level `travelTimePercentiles`. | [Batch data schema](https://docs.tomtom.com/traffic-stats/documentation/batch/data-schema), [Route Analysis API](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis) |
| **Confirmed: Route Analysis, not Batch, is the product.** Batch is per segment, exposes no sample size, and is bucketed in UTC hours that do not align to IST. Route Analysis takes a time zone (`zoneId`) and can restrict to vehicles that drove the whole route (`fullTraversal`). | same pages |
| **Data grain.** Traffic Stats delivers percentiles per segment and hour (Batch) or per route (Route Analysis), not individual trips. The question "individual travel times or percentiles" is answered and no longer needs asking. | same pages |
| **India is covered** by Traffic Stats, since 2015. The coverage page also says coverage in some countries is limited to selected cities, without naming them. | [Market coverage](https://docs.tomtom.com/traffic-stats/documentation/product-information/market-coverage) |

Two inversions follow from these and are carried into our design, not asked (CLAUDE.md,
"TomTom's terms and allowance"): speed percentiles invert into travel time (p95 travel
time = length ÷ p5 speed, free-flow = length ÷ p95 speed), and mean travel time is
length ÷ harmonic mean speed, not ÷ the arithmetic mean speed.

## To ask

### 1. Publication rights

Does any licence (research, non-commercial or paid commercial) permit us to store Route
Analysis responses and to publish derived aggregate statistics openly, for anyone to reuse?

Your Terms and Conditions prohibit "the caching or storing of any Results" (clause 11.4)
and bar using the products to create "any secondary or derived database" (clause 11.6.1).
Please state which licence, if any, lifts each restriction for this use, and whether a paid
plan carries different terms from the free tier on either clause. Please answer this
together with the quote: a quote that does not settle both clauses is not actionable for
us.

### 2. Full traversal

With `fullTraversal` enabled, are the route-level `travelTimePercentiles` computed only from
vehicles that drove the whole route? Is the number of those vehicles returned?

We publish a 95th percentile only from 200 pooled observations and need a count to check
that floor. `averageSampleSize` is documented as "the total sample size divided by the
amount of segments", an average over segments, not a count of vehicles on the route.

### 3. Route identity across annual map updates

Your schema documentation says segment identifiers and geometries change with yearly map
updates, and that longitudinal studies spanning several years must account for it. For a
multi-year series on a fixed set of routes, how is route identity maintained across those
updates? Do `osmIds` stay stable, and is there a mapping from retired segment ids to their
replacements?

### 4. Probe density in Hyderabad

What sample sizes should we expect on Hyderabad arterials: per segment, and as
full-traversal counts per route, in 06:30-10:30 and 16:30-21:00 IST, and in 00:00-04:00
IST? Is Hyderabad inside India's coverage, or among the cities where coverage is limited?

The free trial cannot answer this: Sahil's check found its data limited to the UK,
California, Texas and Melbourne. (The FAQ and market coverage pages checked here describe
a 30-day trial but do not name its regions.)

### The quote

A quote for **Route Analysis**, not Batch, for about 14 road corridors in Greater
Hyderabad, both directions (roughly 140 directional miles), two years of history plus
ongoing access, priced per corridor so that the panel can grow. It supersedes the earlier
request for "Traffic Stats" in general.
