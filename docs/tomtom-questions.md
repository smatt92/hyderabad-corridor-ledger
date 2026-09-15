# Questions for TomTom

Assembled 2026-09-15 and rewritten the same day, once TomTom's documentation had answered
every technical question it can (`docs/data-sources.md`, "TomTom Traffic Stats: what the
documentation settles"). What remains needs a person at TomTom. Send the questions in one
message, in this order, and track each until it is answered.

## Tracking

| # | Question | Sent | Answered | Answer, in one line |
|---|---|---|---|---|
| 1 | The quote, with publication rights (clauses 11.4 and 11.6.1) | | | |
| 2 | Hyderabad coverage depth, probe density and trial access | | | |
| 3 | A route-level full-traversal count | | | |
| 4 | Corridor identity: GERS ids and the map type, as a quote line item | | | |
| 5 | Two-wheelers in India probe data | | | |

## Settled from the documentation: do not ask

Each is recorded with its source in `docs/data-sources.md`.

- **The product.** Route Analysis, not Batch, and the metrics engine attaches to it.
- **Full traversal.** With `fullTraversal: true`, route statistics come only from vehicles
  that drove the whole route. Full support covers about the last two years.
- **Time zones.** `zoneId: Asia/Kolkata` puts date ranges and time sets in IST.
- **Data lag.** Up to 72 hours, so the most recent report is three days in the past.
- **Sample thresholds.** `averageSampleSizeThreshold` rejects a job at request time.
  `acceptMode: MANUAL` shows sample summaries before a job is accepted.
- **Limits.**
  - Routes: at most 200 km each, 20 per job, 50 via points each.
  - Date ranges: 24 per job, each at most 366 days, 732 unique days in total.
  - Time sets: 24 per job.
- **Pricing mechanism.** Route length multiplied by the number of date ranges.
- **Probe sources.** `probeSource` is PASSENGER (the default), TELEMATICS or ALL, and
  pedestrian data is filtered out.
- **Segment ids.** They change with map versions and hold within a 12-month period. The last
  two years can run on one map version.
- **GERS, as documented.** Only for Traffic Volume, per segment, enabled at the contract
  level, on the Orbis map. Traffic Volume does not cover India.
- **OSM mappings.** Many-to-many, with offsets. We will not use them for identity.
- **The inversions.** They are carried into our design, not asked (CLAUDE.md):
  - p95 travel time = length ÷ p5 speed;
  - free flow = length ÷ p95 speed;
  - mean travel time = length ÷ harmonic mean speed.

## To ask

### 1. The quote, and publication rights with it

A quote for **Route Analysis**, not Batch, covering:
- about 14 road corridors in Greater Hyderabad, both directions (28 directional routes,
  roughly 140 directional miles);
- two or more years of history, plus ongoing access;
- a per-corridor price if possible, so that the panel can grow.

It supersedes the earlier request for "Traffic Stats" in general.

**Publication rights, answered in the quote.** Please state whether the licence permits us to
store Route Analysis results and to publish derived aggregate statistics openly, for anyone
to reuse.
- Your Terms and Conditions prohibit caching or storing Results (clause 11.4).
- They also bar using the products to create a secondary or derived database (clause 11.6.1).

Please say which licence, if any, lifts each restriction for this use, and whether a paid
plan's terms differ from the free tier's on either clause. A price without that answer is
not actionable for us.

**How date ranges are counted.** They multiply the priced road length, so please also say
how they would be counted for our analysis. It pools:
- 14-day blocks: twelve before a road change and one after;
- a trailing 90-day window, refreshed daily;
- 120-day hourly profiles.

And are separate jobs over the same routes and dates priced separately?

### 2. Hyderabad coverage depth, probe density and trial access

How far back does Traffic Stats data for Hyderabad go? What sample sizes should we expect on
Hyderabad arterials, per segment and as full-traversal trips per route, in each of these IST
windows:
- 06:30-10:30;
- 16:30-21:00;
- 00:00-04:00.

Your market coverage page lists India from 2015. It also says coverage in some countries is
limited to selected cities, without saying which. Your Route Analysis page says full archive
support for `fullTraversal` covers only about the last two years: how limited is
full-traversal data for Hyderabad before that?

This decides whether we buy history or collect forward. If Hyderabad history exists at
usable sample sizes, the 24-week baseline before the Miyapur X Road to Allwyn X Road
flyover already exists, and does not need 24 weeks of collection.

The 30-day MOVE Portal trial cannot answer this: Sahil's check found its data limited to the
UK, California, Texas and Melbourne.

**Trial access.** Is Hyderabad data available to 30-day MOVE Portal trial accounts, and to
the API keys issued with them? A test Route Analysis job on a Hyderabad route (job
9885126) returned zero average sample size and zero network length in every time set. We
need to know whether that reflects the trial's regions or Hyderabad's coverage.

### 3. A route-level full-traversal count

With `fullTraversal` enabled, is the number of trips by vehicles that drove the whole route
available, even if undocumented? It could be a field, a report option, or something you
provide on request.

We publish a 95th percentile only from 200 observations, so we need that number to check the
floor. `averageSampleSize` is an average over segments. A segment's `sampleSize` could stand
in for it only if we knew two things:
- **Are partial-route vehicles excluded from `sampleSize` too?** With `fullTraversal`
  enabled, is `sampleSize` limited to vehicles that drove the whole route, or does it count
  every vehicle observed on the segment? Your FAQ says partial-route data is excluded from
  route statistics.
- **Devices or trips?** Does `sampleSize` count devices or trips? A vehicle might drive the
  route on many days in one date range.

### 4. Corridor identity: GERS ids and the map type, as a quote line item

Your Traffic Volume documentation offers `gersIdMapping` per segment in GeoJSON output,
enabled at the contract level, on the Orbis map. Traffic Volume does not list India.
- **Route Analysis.** Does it support GERS ids for Hyderabad routes, per segment or per
  route?
- **Price.** Can GERS be included in the quote, and at what price?
- **Transition mappings.** When a GERS id is replaced after a road is realigned, split or
  merged, are the mappings from old to new ids available to us directly as data, not only
  applied through the Global Entity Matcher?
- **Map type.** A Route Analysis request that the MOVE Portal generated for us used
  `mapType: OPEN_DSEG`, map version `2025.12.1800`. Your Available Maps and Route Analysis
  pages list only GENESIS and ORBIS. What is OPEN_DSEG, and which map type would our
  contract's jobs run on? How do its segment ids behave across map versions: do they
  change yearly, as your Batch schema describes, and do they carry GERS mappings?

We intend to identify each corridor across map versions by its GERS ids. A replaced id
would be an alert for a person to review, never an automatic remap.

### 5. Two-wheelers

Does India probe data include motorised two-wheelers, for example riders using smartphone
navigation? If so, under which probe source: PASSENGER or TELEMATICS? Can they be identified
or excluded?

This decides whether we describe what we publish as mixed-traffic travel time or car travel
time.
