# Data sources: no open observed travel times for Hyderabad

A decision record, 2026-09-14. Sahil did the research. Each claim below was checked
against its source on 2026-09-14. The `checked` column says how: `opened` (the page itself),
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
| A negotiated commercial licence | [TomTom Traffic Stats](https://www.tomtom.com/products/traffic-stats/) sells historical speeds, travel times and sample counts for road networks in over 70 countries, through TomTom MOVE, batch delivery or an API, by contacting sales. TomTom's [Traffic Index](https://www.tomtom.com/traffic-index/city/hyderabad/) publishes Hyderabad figures, so TomTom holds Hyderabad trip data. | Whether a licence permits publishing, and whether it delivers individual travel times or only percentiles per time bin. Both are put to TomTom (CLAUDE.md). | opened (product page); search (the Hyderabad index page did not render) |
| Institutional access through a university with existing Telangana Government data permissions | IIIT Hyderabad is a named Technology Partner of the Telangana Mobility AI Grand Challenge, with T-AIM and NASSCOM ([IIIT-H Mobility news](https://mobility.iiit.ac.in/news.php)). [TGDeX](https://tgdex.telangana.gov.in/), the state's data exchange built with IISc, links government datasets with research institutions, IIT Hyderabad and IIIT Hyderabad among them ([MediaNama, July 2025](https://www.medianama.com/2025/07/223-telangana-tgdex-india-first-state-led-ai-data-exchange/)). | Whether any such permission covers observed road travel times or speeds, and whether results could be published. | opened (IIIT-H news); search (the TGDeX portal did not render) |

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
