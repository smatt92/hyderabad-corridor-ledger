# Data sources: no open observed travel times for Hyderabad

A decision record, 2026-09-14. Sahil did the research. Each claim below was checked
against its source on 2026-09-14, and each 2026-09-15 addition to the TomTom Traffic Stats
section on that day. The `checked` column says how: `opened` (the page itself),
`API` (GitHub's or the portal's own API), `search` (a search result's excerpt, page not
opened) or `not re-checked` (the portal refused an automated fetch, so the entry is
Sahil's check alone). Where a check differed from the research notes, the checked value is
recorded here and the difference is listed at the end.

## The finding

**No openly licensed source of observed road travel-time, speed or congestion data exists
for Hyderabad or any Indian city.** That is a negative: it covers the sources below, not
every source that could exist. The closest thing to what this project needs, OpenTraffic's
open speeds from ride-hailing GPS, is defunct and never covered India.

Collecting the data ourselves is not viable either ("Volunteer self-collection: not viable",
below).

## The position: two routes remain

Every route to observed, publishable travel-time data for Hyderabad is closed except two.
Sahil checked both with sources; neither is a guess. The sources re-checked here on
2026-09-14, and what they do not yet establish:

| Route | Evidence | Not yet established | Checked |
|---|---|---|---|
| A negotiated commercial licence | [TomTom Traffic Stats](https://www.tomtom.com/products/traffic-stats/) sells historical speeds, travel times and sample counts for road networks in over 70 countries, through TomTom MOVE, batch delivery or an API, by contacting sales. TomTom's [Traffic Index](https://www.tomtom.com/traffic-index/city/hyderabad/) publishes Hyderabad figures, so TomTom holds Hyderabad trip data. | Whether a licence permits publishing, how full traversal behaves on urban corridors, how far back Hyderabad's data goes, and whether a count of vehicles that drove the whole route exists (put to TomTom, `docs/tomtom-questions.md`). Answered: the metrics engine attaches, with full traversal the route statistics come only from whole-route vehicles, and Hyderabad is covered, densely (job 9886035; "TomTom Traffic Stats: what the documentation settles"). | opened (product page); search (the Hyderabad index page did not render) |
| Institutional access through a university with existing Telangana Government data permissions | IIIT Hyderabad is a named Technology Partner of the Telangana Mobility AI Grand Challenge, with T-AIM and NASSCOM ([IIIT-H Mobility news](https://mobility.iiit.ac.in/news.php)). [TGDeX](https://tgdex.telangana.gov.in/), the state's data exchange built with IISc, links government datasets with research institutions, IIT Hyderabad and IIIT Hyderabad among them ([MediaNama, July 2025](https://www.medianama.com/2025/07/223-telangana-tgdex-india-first-state-led-ai-data-exchange/)). | Whether any such permission covers observed road travel times or speeds, and whether results could be published. | opened (IIIT-H news); search (the TGDeX portal did not render) |

## TomTom Traffic Stats: what the documentation settles

Read on 2026-09-14 from TomTom's [Batch data schema](https://docs.tomtom.com/traffic-stats/documentation/batch/data-schema)
and [Route Analysis API](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)
pages, both opened, and extended on 2026-09-15. That day Sahil put questions to TomTom's
documentation assistant on developer.tomtom.com, and each answer was then checked against
TomTom's pages. In the 2026-09-15 tables, `checked` says how:
- `opened`: the page itself;
- `search`: a search result's excerpt, because TomTom's MOVE Portal guides return 404 to a
  direct fetch;
- `assistant only`: no page was found that says it;
- `product`: a payload the MOVE Portal itself generated, from a job not yet identified
  ("The request shape").

Where an answer and a page differ, this record follows the page, and the differences are
listed at the end of this section.

**CONFIRMED: the metrics engine attaches.** Batch gives `speedPercentiles`, "19 percentiles
(5th–95th, increments of 5)", per segment and hour, with the segment's `length`. Route
Analysis gives route-level `travelTimePercentiles` ("5th, 10th, … 90th, 95th (in
seconds)") as well as `speedPercentiles`. A p95 travel time and a percentile-based
free-flow reference are both derivable.
Route Analysis's `travelTimePercentiles` turned out to be DERIVED from its speed
percentiles, not observed travel times (job 9886035, "What the route statistics are").

**The inversion. Batch percentiles are of speed, not travel time.** On a segment of fixed
length, travel time is length ÷ speed, which reverses the order:

- p95 travel time = length ÷ **p5** speed;
- the free-flow reference (a 5th-percentile travel time) = length ÷ **p95** speed;
- mean travel time = length ÷ **harmonic** mean speed (`harmonicAverageSpeedMetersPerHour`),
  not length ÷ the arithmetic mean speed (`averageSpeedMetersPerHour`), which gives a
  shorter mean travel time than the vehicles took.

Read the other way round, these compute the opposite of unreliability and still look
plausible. This project's observed free-flow reference is the p5 of night-slot travel times
(00:00–04:00 IST); a p95 speed over all hours is a different reference unless the request
is restricted to those hours.

**TomTom's own indices are not this project's.** Route Analysis's `planningTimeIndex`
divides the 95th-percentile travel time by the average travel time of the job's first time
set, and `averageTravelTimeRatio` is also relative to that first time set ([Route
Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). This
project's PTI and TTI divide by a free-flow reference. They share names and are different
numbers, so TomTom's are never published as ours. Route Analysis averages are arithmetic
unless a field says otherwise.

Job 9886035 confirmed both on real output: TomTom's indices divide by the first time set's
average travel time, and its route `travelTimePercentiles` are the speed inversion already
done ("Job 9886035 (R2)").

### Read on 2026-09-14

| Finding | Source text | Consequence |
|---|---|---|
| Batch does not expose sample size | "the number of underlying observations (sample size) is not exposed as a field in the Traffic Stats Batch schema" | The 200 and 30 floors, the shrinkage and the missingness flag all need a count, so Batch cannot feed the metrics engine as built. |
| Route Analysis exposes counts, but no count of full-route vehicles | `sampleSize`: "The sample size visible on the segment. If several measurements are received from the same vehicle on a single segment it is only counted once in the sample size count." `averageSampleSize`: "The total sample size divided by the amount of segments." | A count exists per segment. The route-level figure is an average over segments, not the number of vehicles that drove the whole route, so it does not map onto a 200-observation floor. See "The sample floor" below. |
| Batch is per segment | records keyed by `dsegId`, each with `HourlyStats` | A corridor p95 is not the sum of its segments' p95s: summing assumes the slowest 5% of trips coincide on every segment. |
| Route Analysis can restrict to full traversals | `fullTraversal`: "When you only want vehicles that traversed the full route taken into account, you need to use this parameter." `travelTimeStandardDeviation`: "Only for full traversal routes." Averages are "for the covered part of route". | Route-level statistics from vehicles that drove the whole corridor are obtainable. This page does not say that route `travelTimePercentiles` then use only those vehicles; TomTom's FAQ does (below). |
| Batch hours are UTC | `hour`: "Hour of day (0–23, UTC)" | Batch only. Route Analysis takes a time zone, so its hours are IST (below), and nothing in the design depends on Batch's hours. |
| Segment identity changes every year | "Road segment identifiers and geometries are subject to yearly changes as the road network undergoes updates… For longitudinal studies that span multiple years, it is important to account for potential changes in both identifiers and geometry resulting from annual map updates." | Corridor identity across years is threatened from the supplier's side, the problem the immutability guard solves for our own declarations. It has to be designed in, not discovered later. `osmIds`, recorded here on 2026-09-14 as the mitigation, is not one: see "Corridor identity" below. |
| Empty intervals are omitted | "Empty intervals (no observed traffic) are omitted." | This matches the never-interpolate rule. An omitted interval still has to be counted as missing against the schedule, not skipped. |

**So the product to quote for is Route Analysis, not Batch.** Route Analysis exposes counts,
takes a time zone and can restrict to full traversals. Batch has no counts, UTC hours, and
segment-level percentiles that cannot be combined into a corridor's.

### The request shape: a product payload, not yet canonical

On 2026-09-15 the MOVE Portal returned a Route Analysis request payload, which Sahil
passed on. It came from the product, not from a reading of the documentation. The route
and date-range names and the days list were elided (`...`) when Sahil passed it on; the
days list held all seven days. Its endpoints are not a declared or verified corridor, and
its `via` list is empty, so a job built from it measures whatever road the routing engine
chose, not a pinned corridor.

**Not canonical.** The payload showed one time set, while the job that returned zeros
("First report", below) had three, so they may not be the same request, and the job this
payload belongs to is not identified. The fields below appear in a payload the product
generated. The payload as a whole is not treated as the canonical request shape until a
payload from a job we can identify confirms it (Sahil, 2026-09-15).

```text
{"routes":[{"name":"...","start":{"latitude":17.47273,"longitude":78.41973},
"via":[],"end":{"latitude":17.44875,"longitude":78.37918},
"probeSource":"ALL","fullTraversal":true,"zoneId":"Asia/Kolkata"}],
"dateRanges":[{"name":"...","from":"2026-07-15","to":"2026-07-31",
"exclusions":[],"excludedDaysOfWeek":[]}],
"timeSets":[{"name":"AM peak","timeGroups":[{"days":["MON",...],
"times":["6:30-10:30"]}]}],
"distanceUnit":"KILOMETERS","mapVersion":"2025.12.1800",
"mapType":"OPEN_DSEG","acceptMode":"MANUAL",
"averageSampleSizeThreshold":0,"tags":[],
"configuration":{"dataProviderProfile":"v1"}}
```

| Field | What it shows | Checked |
|---|---|---|
| `routes[].via` | A route field, empty in the test. Declared via points go here, so a corridor is pinned in the request itself, not by a workaround. The Route Analysis page agrees, and warns that without via points the routing engine may not return the road meant. The limit is the collector's: via points fix the points a route passes, not the road between them, so they must be dense enough that no other road fits. | product; opened |
| `probeSource` | `ALL` is accepted. Sahil reports that the product also offers PASSENGER and FLEET. The API page names the fleet value TELEMATICS, and this payload shows neither, so the exact value to send for fleet-only data is not yet confirmed. | product (ALL); Sahil's report (PASSENGER, FLEET) |
| `fullTraversal`, `zoneId` | `true` and `Asia/Kolkata` are accepted. | product |
| `dateRanges[].exclusions`, `dateRanges[].excludedDaysOfWeek` | Both exist; empty in the test. | product |
| `timeSets[].timeGroups` | `days` and `times`. The product writes `6:30-10:30`, without a leading zero. | product |
| `acceptMode` | `MANUAL` is accepted. `AUTO` is the documented default. | product (MANUAL); opened (AUTO) |
| `averageSampleSizeThreshold` | A request field, as documented; 0 in the test. | product |
| `mapType`, `mapVersion` | `OPEN_DSEG` and `2025.12.1800`. The Available Maps and Route Analysis pages read on 2026-09-15 list only GENESIS and ORBIS, with versions such as 2025.12. What OPEN_DSEG is, and how its segment ids behave across versions, is not on those pages. | product; not in the documentation read |
| `tags`, `configuration.dataProviderProfile` | Present, as `[]` and `v1`; neither is described on the pages read. | product |

**Two corrections before production use.** Decided by Sahil on 2026-09-15.

- **Set `averageSampleSizeThreshold`; never send 0.** It is the request-time sample floor,
  and 0 disables it. Its value is not yet chosen.
- **One threshold per job: a request-design constraint.** The threshold is one value per
  job, and the floors differ by time set (`metrics/params.py`): 200 for a p95, 30 for a
  mean or median, 20 for the night p5.
  - So time sets are batched by floor, and peak and night time sets require separate jobs.
    A night time set held to the peak floor could reject the whole job, and a peak time
    set held to the night floor would let thin data through.
  - That turns one job per corridor set into two. About 28 directional corridors, in two
    sets of at most 20 routes, need at least four jobs.
  - The rhythm matrix, if bought, is the third floor group, at 30. Its 168 weekday-hour
    cells, at 24 time sets a job, take at least seven jobs per corridor set: at least 14
    more.
  - Whether separate jobs over the same routes and dates are priced separately is part of
    question 2.
- **AM and PM peak time sets are MON–FRI only; the night time set keeps all seven days.**
  The test used all seven days for its AM peak.
  - Why: weekend peaks on a commuter corridor are a different regime, so a seven-day peak
    pool describes neither weekdays nor weekends.
  - It does not simply flatter the corridor; which way it misleads depends on the
    statistic. In an illustration with assumed lognormal weekday and weekend travel times
    (2,000,000 weekday draws, two weekend draws for every five weekday ones), lighter
    weekends lowered PTI from 2.44 to 2.34–2.42 and TTI from 1.67 to 1.51–1.65. They
    raised BTI from 0.46 to 0.46–0.56, counting the gap between weekdays and weekends as
    unreliability.
  - It also depends on which days are lighter, which is unmeasured for Hyderabad.
    `scripts/dev/panel_model.py` assumes Saturday is the heaviest day (1.13 of an average
    day) and Sunday the lightest (0.72); that is an unsourced model assumption, not a
    measurement.
  - The restriction goes in the time groups' `days`, or in `excludedDaysOfWeek`.

**Open, not decided:**
- **The metrics engine disagrees with the request: an open decision.** As built, the
  engine pools peak-hour calls on all seven days. `peak_minutes` in `metrics/params.py`
  has no day filter, and the ledger, the audit blocks and the floors' timings all assume
  it. The corrected peak time sets are MON–FRI, so bought and collected BTI and PTI would
  be defined differently.
  - Decision rule (Sahil, 2026-09-15): if we buy, the engine follows the purchase; if we
    collect, the engine's definition stands. It cannot be settled until that choice is
    made, and nothing changes until then.
  - The weekend argument above is not specific to bought data: a seven-day pool of
    collected peaks mixes the same two regimes.
- **Holidays.** By the same reasoning, weekday public holidays are a weekend-like regime,
  and `exclusions` can drop them.
- **Profile and rhythm matrix.** The weekday restriction was set for the peak time sets
  only. The 24-hour profile pools every day, and the rhythm matrix keeps each weekday
  separate.

### First report: zero in every time set, and what job R2 settled

The first Route Analysis job, 9885126, returned its sample details file, the counts a job
gives before manual acceptance. Read on 2026-09-15, it covers one route ("KPHB to Hitec
City") and one date range ("Fortnight July"):

| Time set | `averageSampleSize` | `networkLength` (km) | `coveredNetworkLength` (km) |
|---|---|---|---|
| AM peak | 0.0 | 0.0 | 0.0 |
| PM peak | 0.0 | 0.0 | 0.0 |
| Night baseline | 0.0 | 0.0 | 0.0 |

- **The request, as reported.** Sahil reports that the job used `fullTraversal: true` and
  an empty `via`, on a route of 6.89 km.
- **Not known to be the payload above.** That payload showed one time set and this job has
  three, so they may not be the same request. The payload is not treated as this job's
  request, or as the canonical shape.
- **Not a candidate corridor.** The route's endpoints are not the `kphb-circle` or
  `hitec-city-cyber-towers` candidates in `config/junctions.yaml`. Neither the endpoints
  nor those candidates are verified.

**What job 9886035 (R2, below) settled**, 2026-09-15:
- **(b) Hyderabad coverage absent: DISPROVED.** R2 returned dense Hyderabad data for July
  2026.
- **(c) A trial-region restriction: DISPROVED**, provided R2 ran on the same account as
  9885126. Sahil's earlier check, which found the trial's data limited to the UK,
  California, Texas and Melbourne, does not hold for this account. The trial-region
  control designed earlier is not needed, and is not to be run.
- **(a) Full traversal with an empty `via`: the only recorded explanation left, and not
  isolated.** Besides full traversal, R2 changed the route, the length (21.01 km against
  6.89 km), the via points and the time sets. The map type is not known to have changed:
  R2 ran on OPEN_DSEG, the map in the unidentified payload above, and 9885126's map is not
  recorded.
  - The clean test is the ORIGINAL 6.89 km route with only `fullTraversal` flipped off
    (Sahil, 2026-09-15).
  - TomTom's MOVE Portal guides include a page on cloning a report. Cloning job 9885126
    and changing only that flag keeps everything else identical, and the clone's payload
    comes from an identified job.
- **The mechanism is not settled.** At R2's density, "almost nobody drives the whole
  route" is a weak reason for an exact zero in every time set, peaks included. TomTom's
  FAQ names another: a rarely travelled portion of a route, or vehicles skipping its final
  section. R2's routed path ran a fifth of its length on FRC 7 roads, TomTom's class for
  destination roads. A routed path like that on 9885126's route, with no via points to
  hold it to the main road, would have few whole-route vehicles whatever its length. The
  per-segment road classes and sample sizes of the same route with full traversal off
  would show which.

### Job 9886035 (R2): route-level results

Read from the job's results file on 2026-09-15. The results files are not committed: they
are TomTom Results (terms 11.4, CLAUDE.md).

**The job.** A 21.01 km Hyderabad route of 375 segments with one via point,
`fullTraversal: false`, `probeSource: ALL`, `zoneId: Asia/Kolkata`, date range 2026-07-15
to 2026-07-30. The results name the map `India_ind2025.12.1800-23.125-0 OPEN_DSEG`, not
Orbis. Every time set covers all seven days, and 08:00–14:00 is not the project's AM peak
(06:30–10:30).

**The route summary** carries, per date range and time set: `distance`, `coveredDistance`,
`averageSampleSize`, `harmonicAverageSpeed`, `averageTravelTime`, `medianTravelTime`,
`averageTravelTimeRatio`, `planningTimeIndex`, `travelTimePercentiles` (19 values, 5th to
95th in steps of 5) and `speedPercentiles` (19 values). Each segment carries `segmentId`,
`newSegmentId`, `speedLimit`, `frc`, `streetName`, `distance` and `shape`, and per time
set `sampleSize`, `normalizedSampleSize`, speed averages, median and standard deviation,
`travelTimeStandardDeviation`, `averageTravelTime`, `medianTravelTime`, `travelTimeRatio`
and `speedPercentiles`.

**What the route statistics are.** Checked against the file, in all three time sets:
- **Travel-time percentiles are DERIVED, not observed.** Each route
  `travelTimePercentiles` value equals `coveredDistance` divided by the route speed
  percentile at the mirrored rank (the 95th travel time from the 5th speed), within 11 s,
  the rounding of the speeds. TomTom does the inversion; we do not repeat it.
  - The p95 of 224 minutes at 16:30–21:00 is the covered 20.94 km at one uniform speed,
    the route's 5th-percentile speed of 5.6 km/h. It is not a trip anyone is known to have
    taken.
  - Nor is it every segment at its own 5th-percentile speed at once. At 16:30–21:00 a 12 m
    segment with 34 samples has a 5th-percentile speed of 0, which would make that sum
    unbounded.
  - Whether a derived percentile describes trips depends on whose speeds it is drawn from.
    Whole-route vehicles' route speeds would invert back into their trip times; speeds
    from partial passages would not. With full traversal off, that population is not
    documented (question 1).
- **The mean.** `averageTravelTime` equals `coveredDistance` ÷ `harmonicAverageSpeed`, and
  also the sum of the segments' mean travel times, within 3 s.
- **The median.** `medianTravelTime` is the 50th-percentile value of
  `travelTimePercentiles`.
- **TomTom's indices.** `planningTimeIndex` is the time set's p95 travel time ÷ the FIRST
  time set's `averageTravelTime`, and `averageTravelTimeRatio` is its `averageTravelTime`
  ÷ the same base. Here the first time set is 00:00–04:00, so its ratio is 1.0. Reorder
  the time sets and both change.
- **The sample size.** `averageSampleSize` is the sum of segment `sampleSize` over all 375
  segments, zeros included, ÷ 375.
- **Not reproducible from segments.** Pooling the segments' own speed percentiles,
  weighted by sample size, by distance or by both, does not reproduce the route speed
  percentiles. The file does not show how TomTom builds the route distribution.

**Results, flagged for verification: not findings** (Sahil, 2026-09-15). A p95 of 224
minutes and a 55-minute night median on 21 km both look slow, and Sahil is checking them
against his own experience of the road.

Every travel time in the table is derived (above): a median or p95 here is the covered
length at a route speed percentile, not an observed trip.

| Time set (IST, all days) | Covered (km of 21.01) | `averageSampleSize` | Median | p95 | `planningTimeIndex` (TomTom's, ÷ the 00:00–04:00 average) |
|---|---|---|---|---|---|
| 00:00–04:00 | 20.64 | 4,017 | 55.0 min | 121.2 min | 1.97 |
| 08:00–14:00 | 20.94 | 28,855 | 62.2 min | 190.0 min | 3.09 |
| 16:30–21:00 | 20.94 | 19,321 | 70.8 min | 224.2 min | 3.65 |

Sahil's candidate causes: a segment that occasionally stops dead, the route including
something unintended, or genuine Hyderabad conditions. Leads in the file itself, for that
check and not as findings:
- **Construction.** Each value is the covered length at a speed percentile, not an
  observed 21 km trip, so a slow tail of speeds from short passages would scale up to the
  whole route.
- **Road classes.** By distance the route is 19% FRC 2, 29% FRC 3, 33% FRC 4 and 20% FRC 7
  (4.11 km). FRC 7 is TomTom's class for destination roads such as alleys and dead-end
  streets. The first segment is FRC 7 (RBI Officer Quarters Road). Street names along the
  route include Balkampet Road, Sanathnagar Industries Road, Bharat Nagar Colony Main Road
  and Railway Goods Shed Road.
- **Uneven counts.** Segment sample sizes run from 1 or 2 up to 156,220.
  - The median segment holds 2,147 at night, 18,900 at 08:00–14:00 and 10,632 at
    16:30–21:00; the 10th-percentile segment holds 29, 402 and 277.
  - Ten segments (367 m) have no data at night, and two (65 m) have none in the other time
    sets.

**What it changes.**
- **Coverage.** Hyderabad is covered on this account, for July 2026, and densely ("First
  report", above).
- **via, and corridor quality.** A job with a via point returns data, but R2's one via
  point did not pin the corridor (Sahil, 2026-09-15). 4.11 km of its 21 km is FRC 7,
  TomTom's class for destination roads such as alleys and dead-end streets, including
  colony roads.
  - A corridor declares enough via points to hold its intended road, within Route
    Analysis's limit of 50 per route.
  - The road-class distribution along a corridor's route is a quality check worth running
    on every declared corridor. Route Analysis segments carry `frc`; the collector's
    stored road (0012) is points only, with no road class. What share of which class fails
    a corridor is not decided.
- **The inversion warning.** It covers any speed-percentile field: Batch, and Route
  Analysis's route and segment `speedPercentiles`. Route `travelTimePercentiles` are that
  inversion already done by TomTom, so they are derived, not observed, and are never
  presented as observed trip times.
- **TomTom's indices.** Sahil's claim that TomTom computes two of our three headline
  metrics was wrong, and he withdrew it (2026-09-15): TomTom computes neither our PTI nor
  our TTI.
  - `planningTimeIndex` divides the p95 by the average of the job's FIRST time set, so
    reordering time sets changes it. It is not a planning time index in the standard
    sense, which divides by a free-flow travel time. `averageTravelTimeRatio` has the same
    base.
  - Neither is usable as shipped, and neither is published as ours. PTI and TTI stay ours
    to derive, as BTI does, from the route percentiles and averages.
- **The methodology note.** If we buy, all three headline metrics, BTI included, rest on
  TomTom's computation. That computation is its route speed distribution, scaled to the
  covered length, over a population that is undocumented with full traversal off. The note
  says so, says that route travel-time percentiles are derived from speeds and not
  observed, and says that TomTom's indices are not published as ours.
- **Both free-flow bases: a consequence of buying, not decided.** Route Analysis carries
  no no-traffic travel time (`noTrafficTravelTimeInSeconds` comes from the Routing API),
  so bought data cannot supply the `_tomtom` basis.
  - The two-basis design, which the metrics engine never collapses, would collapse to a
    night reference alone.
  - That reference would itself be derived. A night time set's p5 travel time is the
    covered length ÷ its 95th-percentile speed, not the p5 of observed calls that the
    collector's `_p5` basis is.
  - Keeping a second basis would need Routing API calls, which store Results under the
    same licensing question.
- **The sample floors: not retired for the buy branch** (Sahil, 2026-09-15, withdrawing
  his earlier position).
  - The 08:00–14:00 average is 144 times the 200 floor and the 16:30–21:00 average 97
    times; the night average is about 200 times the night p5 floor of 20. Two orders of
    magnitude, not three.
  - The averages hide segments at 1 or 2 samples, and `min(sampleSize)` would have
    withheld every time set.
  - With full traversal off, the population behind a route percentile is undocumented, so
    these counts are not known to be the observations behind it.
  - The floors bind whether we buy or collect.
- **THE CENTRAL PROBLEM** (Sahil, 2026-09-15). Full traversal is what makes a route-level
  percentile meaningful, because only whole-route vehicles count, and on a 7 km urban
  corridor it returned nothing. With it off, the route percentiles are the covered length
  at speed percentiles over an undocumented population. The two are in direct tension, and
  it is now the first question for TomTom. Whether the zero is inherent to corridors of
  that scale, or came from how that route was defined, is not established.

### Confirmed on 2026-09-15, and it attaches

| Finding | Consequence | Checked |
|---|---|---|
| **Full traversal.** With `fullTraversal: true`, route statistics are calculated only from trips by vehicles that drove the entire route; data from vehicles that drove part of it is excluded. The option can reduce the number of probe devices, and TomTom generally does not advise it for longer, more complex or door-to-door routes ([FAQ](https://docs.tomtom.com/traffic-stats/documentation/product-information/faq)). | With full traversal on, route statistics come from whole-corridor vehicles. Route `travelTimePercentiles` are derived from speed percentiles (job 9886035), so they describe those vehicles' trips only if the speeds are the vehicles' own route speeds; that is undocumented (question 1). The warning is about thin counts, which is where the sample floor matters. | opened |
| **Full traversal over older data.** Full archive support for `fullTraversal` covers only about the last two years, a moving window; older periods use limited data ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). | Bought history older than about two years is weaker under full traversal. This bears on whether to buy history (question 3 in `docs/tomtom-questions.md`). | opened |
| **Time zones.** Each Route Analysis route takes a `zoneId`, a tz database name ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)), and every Traffic Stats API uses the time zone given in the request ([FAQ](https://docs.tomtom.com/traffic-stats/documentation/product-information/faq)). | With `Asia/Kolkata`, date ranges and time sets are in IST. The peak windows (06:30–10:30 and 16:30–21:00), the 24-hour profile and the 24×7 rhythm matrix align as designed. | opened |
| **Data lag: up to 72 hours.** Data takes up to 72 hours from arriving at TomTom to being available, so the most recent report is three days in the past ([Data archive process](https://developer.tomtom.com/move-portal/guides/traffic-stats/how-it-works/data-archive-process)). Newly received GPS data is added every day ([FAQ](https://docs.tomtom.com/traffic-stats/documentation/product-information/faq)). The assistant added that reports over the last three days may be incomplete or carry smaller samples. | Purchased figures could run about three days behind: close to current, not an archive only. Request windows end at least 72 hours back, because a hash chain would freeze an incomplete report. | search (72 hours); opened (daily additions); assistant only (incomplete recent reports) |
| **Request-time threshold.** `averageSampleSizeThreshold` defaults to 0. If the average sample size of any one combination of route, date range and time set falls below it, no output is generated, the whole job is moved to REJECTED, and the report is not charged. Without it, output is generated however few samples there are ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). | See "The sample floor" below. | opened |
| **Manual acceptance.** With `acceptMode: MANUAL`, a job waits at NEED_CONFIRMATION with a sample details file giving, per route, date range and time set, the `averageSampleSize`, network length and covered network length. The job is then accepted or rejected ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). | The counts can be read before a report is accepted, so a withheld value can still carry its count. Whether a manually rejected job is charged is not documented. | opened |
| **Omitted data.** Batch omits intervals with no observed traffic ([Batch data schema](https://docs.tomtom.com/traffic-stats/documentation/batch/data-schema)). Route Analysis averages cover the covered part of the route, and each summary gives the route's `distance` and its `coveredDistance` ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). The assistant added that the MOVE Portal offers a manual sample-size filter for map display. | Matches the never-interpolate rule. An omitted interval, or route distance without data, still counts as missing. | opened; assistant only (MOVE filter) |
| **Limits.** Per job: routes of at most 200 km, at most 20 routes, 24 date ranges of at most 366 days each, 732 unique days across them, and 24 time sets ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). At most 50 via points per route ([FAQ](https://docs.tomtom.com/traffic-stats/documentation/product-information/faq)). A job older than two years expires and its data is removed. No limit on segment count or on reports per contract period was found. | Route length does not bind at 4–14 km. About 28 directional corridors need at least two jobs per floor ("One threshold per job"), and the 24×7 rhythm matrix's 168 cells at least seven per corridor set. A corridor's declared via points stay within 50. Results are downloaded and kept, because TomTom deletes them. | opened |
| **Pricing.** The priced length is the total length of a route's segments, multiplied by the number of date ranges: a 20 km route over five date ranges counts as 100 km ([Definitions](https://developer.tomtom.com/move-portal/guides/traffic-stats/how-it-works/definitions)). Access is requested through a local partner or a TomTom account manager ([Introduction](https://docs.tomtom.com/traffic-stats/documentation/product-information/introduction)). | Every date range is paid again. A range is at most 366 days, so history from 2015 takes at least 12 ranges. If each 14-day audit block is its own range, one audit's twelve pre blocks and post period are 13. How ranges are counted belongs in the quote. | search (pricing); opened (access) |
| **Probe sources.** `probeSource` is PASSENGER (the default), TELEMATICS (fleet management vehicles) or ALL ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). Passenger data comes mainly from smartphones, portable navigation devices and some passenger-car makers; fleet data from some truck makers, taxi and delivery services and other fleet companies. Pedestrian data is filtered out of both ([Definitions](https://developer.tomtom.com/move-portal/guides/traffic-stats/how-it-works/definitions)). | The default leaves out taxi and delivery fleets. The source changes what a travel time describes, so it is chosen deliberately and recorded with every request. | opened (parameter); search (categories) |

### Confirmed on 2026-09-15, and it constrains us

| Finding | Consequence | Checked |
|---|---|---|
| **No full-traversal count.** No field returns the number of vehicles that drove the whole route. Route Analysis returns each segment's `sampleSize` and `normalizedSampleSize`, and the route's `averageSampleSize`, the total over segments divided by their number ([Route Analysis](https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis)). A segment's sample size is described as the number of GPS devices observed on it in the date range and time set ([MOVE Portal guides](https://developer.tomtom.com/move-portal/guides/traffic-stats/introduction); the exact page was not identified). | See "The sample floor" below. | opened; search (devices) |
| **Segment ids change with the map.** Batch segment ids and geometries change with yearly map updates and are consistent within a 12-month period ([Batch data schema](https://docs.tomtom.com/traffic-stats/documentation/batch/data-schema)). For the last two years, a moving window, any quarterly map version can be chosen for any date range. Older data is tied to one map version per period: GENESIS 2016.12 for 2008 to January 2019, for example ([Available maps](https://docs.tomtom.com/traffic-stats/documentation/api/available-maps)). | Inside the two-year window a whole series can run on one map version, so segment ids hold across it. History further back crosses map versions, and ids change at each. | opened |
| **GERS ids exist, but not for Route Analysis or India.** TomTom documents `gersIdMapping` only for Traffic Volume: an optional per-segment mapping to an Overture GERS feature, many-to-one, with start and end offsets along the feature, in GeoJSON output only, when enabled at the contract level ([Traffic Volume](https://docs.tomtom.com/traffic-stats/documentation/api/traffic-volume)). Traffic Volume runs on the Orbis map only and covers the United States, Australia, New Zealand, Belgium, the Netherlands, Norway, Sweden and the United Kingdom. No route-level aggregation is documented. | GERS for Hyderabad corridors is not available as documented. It has to be priced into a contract, not switched on later (question 5). | opened |
| **When a GERS id changes.** A GERS id stays the same while a feature is unchanged, and typically through a minor geometry correction. When a road is realigned, split or merged, new ids are assigned with a transition mapping, and TomTom's Global Entity Matcher can update a customer's data automatically ([Understanding GERS IDs](https://docs.tomtom.com/global-entity-matcher/gers-ids)). | See "Corridor identity" below. An automatic update is exactly what this project must not accept. | opened |
| **GERS is Overture's, and its history is public.** Overture describes GERS ids as stable across its releases, and GERS as "a potential standard". It publishes a GERS Registry of every id ever published, with the releases in which each was first seen, last seen and last changed, and a changelog per release marking every id added, removed, changed or unchanged, both as Parquet files in public S3 and Azure buckets ([GERS](https://docs.overturemaps.org/gers/), [Registry](https://docs.overturemaps.org/gers/registry/), [Changelog](https://docs.overturemaps.org/gers/changelog/)). The Overture Maps Foundation is a Joint Development Foundation project, an affiliate of the Linux Foundation ([overturemaps.org](https://overturemaps.org/)). TomTom's own transition mappings have no documented public location. | Anyone can check whether a corridor's GERS ids changed against Overture's public registry and changelog, without TomTom. Transitions made on TomTom's side cannot be checked that way. | opened |
| **OSM ids are unsuitable.** Traffic Volume's `osmIdMapping` is many-to-many: a segment can map to several OSM ways, and one way can appear more than once with different offsets ([Traffic Volume](https://docs.tomtom.com/traffic-stats/documentation/api/traffic-volume)). | An OSM id inherits the ambiguity instead of resolving it. | opened |

### Unresolved

| Question | What is known | Checked |
|---|---|---|
| **Hyderabad's coverage depth** | Coverage exists: job 9886035 returned dense Hyderabad data for 15–30 July 2026 on this account ("Job 9886035 (R2)"). The market coverage page lists India from 2015; its note that coverage is limited to selected cities heads the whole table, so it names no city ([Market coverage](https://docs.tomtom.com/traffic-stats/documentation/product-information/market-coverage)). How far back Hyderabad data goes, and how dense whole-route counts are, is not known. Sahil's earlier check, which found the trial's data limited to the UK, California, Texas and Melbourne, does not hold for this account. Question 3. | opened; product (job 9886035) |
| **Two-wheelers** | Nothing found confirms or excludes motorised two-wheelers from India probe data. Passenger data comes mainly from smartphones, so a rider using phone navigation may count as a passenger probe without being identified as a two-wheeler; that is a reading, not documentation. It decides whether the output is described as mixed-traffic or car travel time, and the methodology note says which, or that it is unknown. Question 6. | search (passenger sources); a reading, not documented |

### The sample floor: two layers, neither an exact count

**Status after job 9886035.** Not retired for the bought branch (Sahil, 2026-09-15): the
floors bind whether we buy or collect ("What it changes", under "Job 9886035 (R2)").

Decided by Sahil on 2026-09-15:
1. **Request time, the primary mechanism:** `averageSampleSizeThreshold`. A combination
   below it produces no data at all, rather than data withheld after the fact.
2. **Publish time, the fallback:** `min(sampleSize)` over the route's segments.

What each layer measures:
- **Neither is the specified floor.** The floor (200 for a p95, 30 for a median) counts
  observations of the corridor, which under full traversal means whole-route trips. No
  documented field gives that number (question 4).
- **The threshold is on an average.** `min(sampleSize)` is never above
  `averageSampleSize`, so the publish-time check is the stricter of the two.
- **`min(sampleSize)` is a lower bound only under a condition.** With full traversal, the
  FAQ says data from partial-route vehicles is excluded, for route statistics. If segment
  counts are filtered the same way, each segment counts only whole-route vehicles, one not
  observed on a segment lowers that segment's count, and `min(sampleSize)` is a lower
  bound, loosest where observations are sparse. The documentation does not say whether
  segment counts are filtered. If they include every vehicle observed on the segment,
  vehicles that drove part of the corridor raise every count, and `min(sampleSize)` can
  exceed the whole-route count and pass a corridor below the floor. On an urban corridor
  that traffic joins and leaves at every junction that would be the expected case, though
  it is unmeasured.
- **Devices, not necessarily trips.** If a segment's sample size counts devices, a vehicle
  that drives the corridor on many days counts once, and the count is below the number of
  trips.
- **The methodology note.** Where the fallback is used, it says the floor was applied
  against a lower bound, not an exact count, and names the condition until TomTom confirms
  it.

The request-time layer is not strictly better than a publish-time floor:
- One thin combination rejects the whole job, including routes and time sets that clear
  the threshold. Jobs are grouped so that thin combinations, such as night time sets or
  low-volume corridors, cannot sink the rest.
- A rejected job returns no count, and this project publishes the count beside every
  withheld value. Manual acceptance returns the counts before a job is accepted.

### Corridor identity: GERS ids, and a change is a signal

Decided by Sahil on 2026-09-15.

- **Prefer GERS ids to TomTom's segment ids, and never use OSM ids.** Why:
  - Segment ids change with map versions. GERS ids are meant to persist through them and
    change only when the road itself changes.
  - GERS ids are Overture's, and Overture publishes every id and every release's changes
    openly. A corridor's identity can be checked without TomTom, and it survives a change
    of provider.
  - OSM mappings are many-to-many, so they inherit the ambiguity.
- **A GERS id change is a signal, not a nuisance.** A realigned, split or merged road is
  what corridor immutability exists to detect. It is raised as an alert. A corridor is
  never remapped silently, and an automatic update of its ids, such as the Global Entity
  Matcher offers, is never accepted.
- **Not yet decided: what the alert leads to.** A realignment is a different road, retired
  and superseded as a rerouting alarm is. A split or merge can also come from a new
  junction on the same carriageway, where the road driven is unchanged. The test the
  project already has for "the same road" is the stored road and its length, within 30 m
  and 2%.
- **Not yet available.** As documented, GERS is for Traffic Volume only and does not cover
  India (question 5).

### Lengths come from the payload

Route Analysis gives each summary's route `distance`, and each segment's `distance`,
`frc`, `speedLimit`, `streetName` and `shape`. Batch's road network gives each segment's
`length`, with `frc`, `speedLimit`, `streetName`, `fow` and `bearing`. A corridor's length
is taken from these, never computed from coordinates.

Checked in the code on 2026-09-15:
- Every corridor length is TomTom's `lengthInMeters`. `collector/tomtom.py` and
  `collector/polyline.py` read it, `metrics/raw.py` and `metrics/readmodel.py` carry it,
  and `web/` shows it as `length_meters`.
- The only computation in metres from coordinates is in `collector/polyline.py`: the 5 m
  simplification tolerance and the 30 m rerouting deviation between two TomTom roads. Both
  are offsets, never a length.
- `collector/registry.py`'s 300 m junction check is a box in degrees, not a distance.

### Where the documentation assistant's answers differed from the pages

Recorded 2026-09-15. In each case this record follows the page.

- **Job rejection.** An average below `averageSampleSizeThreshold` in any one combination
  rejects the whole job, not only that combination. A rejected report is not charged.
- **Full traversal.** The answer left out that full archive support covers only about the
  last two years.
- **India.** The note limiting coverage to selected cities heads every market on the page,
  so it does not establish that India is limited.
- **GERS as a standard.** Overture calls GERS a potential standard, and the Overture Maps
  Foundation is a Joint Development Foundation project affiliated with the Linux
  Foundation. Overture's GERS registry and changelog are public; only TomTom's own
  transition mappings have no documented location.
- **GERS coverage.** Traffic Volume, the only product documented with GERS, does not cover
  India and runs on the Orbis map only.
- **Segment fields.** `fow` and `bearing` are Batch road network fields. Route Analysis
  segments carry `distance`, `frc`, `speedLimit`, `streetName` and `shape`.
- **Not found on any page.** That reports over the last three days are incomplete, and the
  MOVE Portal's manual sample-size filter.
- **Sahil's reasoning, not the assistant's.** `min(sampleSize)` as a lower bound on the
  full-traversal count holds only if full traversal also filters segment counts ("The
  sample floor").

## Catalogues

| Source | What it holds | Checked |
|---|---|---|
| [graphhopper/open-traffic-collection](https://github.com/graphhopper/open-traffic-collection) | A list of open traffic data resources. 455 stars, no licence declared. Entries cover Europe and the US. Outside them there are only Victoria (Australia) and British Columbia (Canada), and no India or Asia entry. Mostly counts, historical data and DATEX II incidents and roadworks; corridor speeds and journey times are rare. Last commit 9 December 2024. | opened, API |

## Formats, not datasets

| Source | What it is | Checked |
|---|---|---|
| [DATEX II](https://datex2.eu/2025/06/11/now-available-datex-ii-version-3-6/) | The European CEN standard data model for exchanging traffic and travel information. Version 3.6 was released on 11 June 2025. It carries data; it is not data. No Indian deployment found. | search |
| [TraFF / TraffXML](https://traffxml.gitlab.io/) | An XML format for distributing traffic messages. A format with no dataset of its own. No Indian deployment found. | search |

## OpenTraffic: the closest match, and defunct

A World Bank-led platform, built by Mapzen, that turned anonymised ride-hailing GPS into
road speeds linked to OpenStreetMap and published them openly.

| Claim | Evidence | Checked |
|---|---|---|
| Piloted in the Philippines (Cebu City and Metro Manila), announced 5 April 2016 | [World Bank press release](https://www.worldbank.org/en/news/press-release/2016/04/05/philippines-real-time-data-can-improve-traffic-management-in); the page now returns 404 | search |
| Open Transport Partnership launched 19 December 2016: Easy Taxi, Grab, Le.Taxi, Mapzen, Miovision, NDrive, World Resources Institute | [World Bank press release](https://www.worldbank.org/en/news/press-release/2016/12/19/the-world-bank-launches-new-open-transport-partnership-to-improve-transportation-through-open-data); the page now returns 404 | search |
| Mapzen's announcement, 19 December 2016, with a Manila demonstration of 11,078,169 ride-share position measurements | [Mapzen blog](https://www.mapzen.com/blog/announcing-open-traffic/) | opened |
| Grab contributed aggregated, anonymised GPS from "over 500,000 drivers" in 34 Southeast Asian cities. India is not mentioned | [Grab blog, 6 December 2016](https://www.grab.com/my/blog/grab-ride-can-improve-traffic-620-million-commuters/) | opened |
| Mapzen shut down; its hosted services turned off on 1 February 2018 | [Mapzen blog, 2 January 2018](https://www.mapzen.com/blog/shutdown/) | opened |
| opentraffic.io is dead: it redirects (HTTP 302) to a domain-sales page at domains.atom.com | opentraffic.io | opened |
| The GitHub organisation is dormant, not archived. None of its 28 repositories is archived; the last push was 7 December 2022, and most are untouched since 2017-2018 | [github.com/opentraffic](https://github.com/opentraffic) | API |
| The code survives under mixed licences: LGPL-3.0 for the pipeline (reporter, datastore, analyst-ui, api, otv2-platform), GPL-3.0 for traffic-engine, MIT or Apache-2.0 for smaller repositories, and osmlr unspecified | [github.com/opentraffic](https://github.com/opentraffic) | API |
| It never covered Hyderabad | No source found showing OpenTraffic data for any Indian city | search |

## Academic data

| Source | What it holds | Checked |
|---|---|---|
| [India Driving Dataset, IIIT Hyderabad](https://insaan.iiit.ac.in/datasets/) | Annotated road-scene images (over 46,000) and LiDAR frames from Hyderabad and Bengaluru, for computer vision. It was described as India's first open, public traffic dataset, but it holds no travel times, speeds or congestion ([FactorDaily](https://archive.factordaily.com/india-driving-dataset-iiit-hyderabad/), [Deccan Chronicle](https://www.deccanchronicle.com/southern-states/telangana/iiit-h-expands-indian-driving-dataset-for-research-on-indias-chaotic-roads-1902670)). | search |

## Indian portals

| Portal | What it holds for this purpose | Checked |
|---|---|---|
| [data.opencity.in](https://data.opencity.in) | The Hyderabad group holds 58 datasets. The transport-related ones are Hyderabad Metro Rail GTFS, Hyderabad Bus Stops and Hyderabad Aviation Traffic Data (airport passengers). No road speeds, travel times or congestion. Its groups are cities, with no transport group. | API |
| [data.telangana.gov.in](https://data.telangana.gov.in) | GTFS, RTA vehicle registrations and airport traffic, no road speeds (Sahil's check). The portal renders in JavaScript and its catalogue API returned 404. A search lists "Hyderabad Domestic Traffic Data 2017". | not re-checked |
| [data.gov.in](https://data.gov.in) | Vehicle registrations and accident counts, no road speeds (Sahil's check). The portal returned 403 to an automated fetch. | not re-checked |
| [Delhi Open Transit Data](https://otd.delhi.gov.in/documentation/) | GTFS bus schedules, and GTFS-Realtime bus vehicle positions for authorised users with a key. Its schedule times assume a constant speed. These are bus positions, not general road speeds: the model Hyderabad does not have. | opened |

## Open observed feeds elsewhere, for reference

Neither covers India.

| Source | What it holds | Checked |
|---|---|---|
| [NDW, Netherlands](https://opendata.ndw.nu/) | Measured `trafficspeed` and `traveltime` feeds, among others. Licence CC0 per Sahil's research; the portal page states no licence and points to a copyright page that was not checked. | opened |
| [National Highways WebTRIS, England](https://findtransportdata.dft.gov.uk/dataset/webtris-traffic-flow-api) | Flow and speed from road sensors (mostly inductive loops), through a free API, under the Open Government Licence v3.0 | opened |
| [DfT road traffic statistics, Great Britain](https://roadtraffic.dft.gov.uk/about) | Open Government Licence v3.0. Counts and annual average daily flow only, not speeds | opened |

## Never use

**Kaggle, "Bangalore's Traffic Pulse"** ([preethamgouda/banglore-city-traffic-dataset](https://www.kaggle.com/datasets/preethamgouda/banglore-city-traffic-dataset),
labelled CC0, last updated 22 August 2024; checked through Kaggle's metadata API). It
claims traffic volume, speed, congestion, environmental impact and signal status for named
Bangalore roads and intersections. Its metadata names no source, instrument, collection
method or period, and does not say whether the data is synthetic. Its provenance cannot be
traced. Never use it in analysis, fixtures, validation or examples.

## Volunteer self-collection: not viable

**Not viable for this project. Do not reopen it.** A volunteer GPS-probe fleet was the only
way to create observed data we could publish ourselves. The numbers in the next section
close it:

- The audit needs about 280 volunteers driving the same corridors every weekday, for 14
  corridors both ways, sustained through a 24-week pre-period and a 28-day post period. That
  is not a recruitment problem; it is a different organisation.
- Even the ledger's weaker requirement, about 44 daily drivers, exceeds what a solo project
  sustains.
- Without a provider's free-flow figure, TTI and PTI rest on the observed night p5, which
  needs 20 night runs per directional corridor every 28 days. Commuters do not drive at 2am,
  so the metric that anchors TTI and PTI is the one volunteers structurally cannot produce.
- Every figure is a lower bound, counting complete corridor runs only.

Do not build any part of the Traccar pipeline. The components that were evaluated are
recorded so the evaluation can be traced:

| Component | Licence | Checked |
|---|---|---|
| [Traccar](https://github.com/traccar/traccar), GPS tracking server for phones and devices | Apache-2.0 | opened |
| [Valhalla Meili](https://valhalla.github.io/valhalla/meili/), map matching of GPS traces to OpenStreetMap | MIT ([LICENSE.md](https://github.com/valhalla/valhalla/blob/master/LICENSE.md)) | API |
| [DPDP Act 2023, section 6](https://indiankanoon.org/doc/15072321/): consent free, specific, informed, unconditional and unambiguous, limited to the data the purpose needs; withdrawable as easily as given; processing stops on withdrawal | statute | search |
| [DPDP Rules 2025](https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Rules,_2025): notified 13 November 2025, in force in phases to 14 May 2027 | rules | search |

## The numbers that closed it

Ledger BTI and PTI need about 2.2 complete peak-window traversals a day, every day, per
directional corridor. The audit needs 14.3 a day.

[FHWA's Travel Time Data Collection Handbook](https://www.fhwa.dot.gov/ohim/handbook/chap3.pdf)
(FHWA-PL-98-035, Tables 3-3 and 3-4) gives 6 to 14 test-vehicle runs per time period to
estimate a **mean** travel time within ±10% at 95% confidence (5 to 10 at 90% confidence),
spread over several weekdays. It notes that agencies typically manage 3 to 6.

This project's tail statistics need far more, because a p95 is a tail. BTI and PTI are
published only from 200 pooled observations, which puts 10 of them above the p95. That is
14 to 33 times FHWA's count for a mean. The floors and windows below are the metrics
engine's (`metrics/params.py`). "Traversal" means one volunteer driving the whole declared
corridor, on its declared road, inside the pooled window, and surviving map matching.

| Statistic | Pool | Floor | Per directional corridor, every day | If volunteers drive weekdays only |
|---|---|---|---|---|
| Ledger BTI, PTI | every peak-hour traversal over 90 days | 200 | 200 / 90 = **2.2 a day** | 200 / 64 weekdays = **3.1 a weekday** |
| Audit block BTI | peak-hour traversals in one 14-day block, for all 12 pre blocks and the post period | 200 | 200 / 14 = **14.3 a day** | 200 / 10 weekdays = **20 a weekday** |
| 24-hour profile, one full peak hour | traversals in that clock hour over 120 days | 200 | 200 / 120 = 1.7 a day in that hour | 200 / 85 weekdays = 2.4 a weekday in that hour |
| Rhythm matrix cell (median) | one weekday and hour over 90 days, 12 occurrences | 30 | 30 / 12 = 2.5 on each occurrence, in that hour | same |
| Observed free-flow reference (p5) | traversals 00:00-04:00 IST over 28 days | 20 | 20 / 28 = 0.7 a night | not possible: needs nights |

What that means for a panel of about 14 corridors, both directions (28 directional
corridors, the size in the TomTom quote request):

- **Traversals.** The ledger needs about 62 complete peak traversals a day across the panel
  (87 a weekday); the audit blocks need 400 a day (560 a weekday).
- **Volunteers.** Suppose a volunteer drives one corridor end to end in the morning peak and
  back in the evening peak, every weekday. Each gives one traversal to each direction, so a
  two-way corridor needs as many such volunteers as it needs traversals per weekday. The
  ledger then needs about 3 on every corridor, about 44 driving every weekday. The audit
  needs 20 on every corridor, 280 every weekday, sustained through the 24-week pre-period
  and the 28-day post period. The audit's minimum panel, the treated corridor and 19 donors
  as 10 two-way corridors, still needs 200 every weekday.
- **Free flow.** Without TomTom there is no `noTrafficTravelTimeInSeconds`, so TTI and PTI
  have only the observed night p5 as a base. That needs 20 night traversals per directional
  corridor every 28 days, which commuting volunteers do not produce. BTI needs no free-flow
  base.

These are lower bounds, for four reasons:

- Volunteers' own trips cover a declared corridor only partly. Stitching partial traversals
  into a corridor travel time is a different estimator, which the metrics engine does not
  have.
- A traversal that leaves the declared road, or falls outside the peak window, does not
  count.
- Map matching rejects some traces.
- A few drivers repeating one road are clustered samples, each driver with a style. The
  floors were set for independent calls, so the same count from a few volunteers is worth
  less.

## Where the checks differed from the research notes

- graphhopper/open-traffic-collection has 455 stars, not 454. It is not actively maintained:
  the last commit was 9 December 2024.
- OpenTraffic's GitHub organisation is dormant, not archived: GitHub marks none of its 28
  repositories as archived. Its code is under mixed licences (LGPL-3.0, GPL-3.0, MIT,
  Apache-2.0), not LGPL-3.0 alone.
- OpenTraffic was piloted in the Philippines in April 2016. December 2016 is when the World
  Bank launched the Open Transport Partnership around it.
- FHWA's 6 to 14 runs are for 95% confidence at ±10% error; at 90% confidence the handbook
  gives 5 to 10.
- DfT road traffic statistics are counts, not speeds. WebTRIS carries speeds.
- NDW's CC0 licence was not confirmed on the pages checked.
- Delhi's real-time bus positions need a requested key.
- Route Analysis's sample size is per segment (`sampleSize`) or an average over segments
  (`averageSampleSize`), not a count of vehicles that drove the whole route.
