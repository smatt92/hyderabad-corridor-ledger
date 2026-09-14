# Hyderabad Corridor Ledger

An independent record of how long it takes to drive fixed corridors in
Hyderabad. The corridors are measured through TomTom's Routing API every 15 or
30 minutes across the morning and evening peaks, and every 30 minutes at
night. Each result is kept in a hash-chained, append-only log that anyone can
re-walk. It exists because a single trip time says little. Commuters feel how
much a corridor varies from one day to the next, and a city needs to know
whether a flyover actually changed that. Google tells you the fastest route
right now. This ledger is meant to tell you the most reliable route at 8:40 on
a Tuesday, from months of measurements rather than one.

**The database holds zero real samples, and the site is not deployed.**
Everything described below has run only on synthetic data.

## What it cannot do

Read this before anything it can do.

- **It detects flyover-scale changes, not a signal retiming.** The audit needs
  24 weeks of pre-period, 20 Tier A donor corridors and a 28-day post period.
  Under those conditions, in simulation, it reliably detects a change of about
  0.20 in the buffer time index (BTI), roughly a third of a typical corridor's
  value. A signal retiming, an enforcement drive or a turning restriction is
  usually smaller than that. **A "not extreme" verdict for a small
  intervention says nothing about whether it worked.**
- **Tier B corridors cannot be audited.** Their 14-day blocks miss the
  200-call floor too often. In simulation 30–62% of Tier B audits were
  withheld, and 9–12 usable donors remained out of 20, too few for any placebo
  p to reach 0.05.
- **A 56-day post period is untested.** Every detection figure here assumes 28
  days.
- **A single extreme verdict is not a finding.** With no effect at all, about
  one audit in 22 reads "extreme" by chance when there are 21 placebos.
- **It is not live.** Indices are recomputed once a night, at 03:11 IST. It
  knows nothing about the accident ten minutes ago.
- **It holds no road geometry yet.** A corridor's road is fetched from TomTom
  once, when the corridor is verified, and no corridor is verified. Until then
  every line on the map is a straight connector between measured endpoints,
  labelled as one, and not the road.
- **Every power figure comes from simulated panels.** Their noise sizes are
  assumptions: a city-wide daily shock with sd 0.10 and a weekly corridor drift
  with sd 0.08. They have to be re-estimated once a real corridor has a full
  audit window.

### Minimum detectable effect

This is the smallest BTI change the audit's placebo rank detected in at least
80% of 50 simulated panels, with Tier A corridors and a 28-day post period. The
percentages are of 0.54, the median pooled peak BTI of a simulated corridor.
Real Hyderabad values are unknown until data arrives.

| pre-period | MDE, 20 donors | MDE, 40 donors |
|---|---|---|
| 12 weeks | 0.30 (56%) | 0.20 (37%) |
| 18 weeks | 0.30 (56%) | 0.20 (37%) |
| 24 weeks | 0.20 (37%) | 0.20 (37%) |
| 30 weeks | 0.15 (28%) | 0.15 (28%) |
| 36 weeks | 0.15 (28%) | 0.15 (28%) |
| 48 weeks | 0.15 (28%) | 0.15 (28%) |
| 60 weeks | 0.15 (28%) | 0.15 (28%) |

- A change of 0.10 was not reliably detected at any pre-period up to 60 weeks.
  Power peaked at 0.72 with 20 donors and 0.74 with 40.
- With 10 donors, no placebo p can reach 0.05 at all.
- Samples are never backfilled. A corridor must start collecting at least 24
  weeks before its intervention opens, so works that are announced but not yet
  begun are seeded first.

Full tables are in [docs/methodology.md](docs/methodology.md) and
[docs/audit_power.md](docs/audit_power.md).

### Why no confidence interval is shown

Every interval this project tried was a bootstrap that resampled individual
calls. That treats calls from the same day and the same week as independent,
and traffic is not: a city-wide shock moves every corridor on the same day,
and each corridor drifts from week to week.

The results in simulation:
- **Ledger p95 and PTI intervals** covered the true value in 68–84% of panels
  at the model's default correlation, and 41–58% with stronger weekly drift,
  against a nominal 95%.
- **Two identical corridors** showed a "lead" in 10–20% of hours.
- **The audit's interval** held its size (6%) when drift was small, and failed
  (20%) when drift was 2.5 times larger. Resampling whole weeks or whole
  blocks failed even at low drift (11% and 26%).

Nothing observable told the two drift regimes apart, so no rule could decide
when an interval was safe to show. Every value is therefore published as a
point estimate beside the number of calls it pools and its window. The audit
relies on its placebo rank instead. An interval may come back only after a
calibration run on measured Hyderabad drift holds coverage.

Two derived tables still carry interval columns, and nothing serves them:
`before_after` holds a confidence sequence on daily TTI, and `recovery_cox`
holds hazard-ratio intervals. See [docs/ledger_intervals.md](docs/ledger_intervals.md).

## Unresolved: TomTom's terms and allowance

This could stop the project, so it is written here and not in a footnote.

- **Keeping and publishing the data.** The project chose TomTom believing its
  terms allowed keeping the results. TomTom's public Terms and Conditions,
  read on 14 September 2026, say otherwise on a plain reading:
  - clause 11.4 prohibits caching or storing Results, except caching in
    clients within the response's cache headers;
  - clause 11.6.1 bars building a secondary or derived database;
  - no clause found permits publishing results as an open dataset.

  The sample log, the Parquet archive and the exports all store Results. So
  would each corridor road the collector stores at verification (0012), which
  the database also makes publicly readable.
- **Allowance.** TomTom's pricing page lists the Routing API at 20,000 free
  calls a month, and does not say when the count resets. The collector's
  budget was designed around 2,400 calls a day, which uses 20,000 in under
  nine days.
- **Caveats.** These are public pages, which may not be this account's
  contract, and this is not legal advice. Until it is settled with TomTom, no
  licence has been chosen, and nothing in this repository describes the data
  as licensed for reuse.

## Current status

As of 14 September 2026.

| Part | State |
|---|---|
| Database (Supabase, Mumbai) | Migrations 0001–0012 applied; 0011 (TomTom response headers) and 0012 (corridor roads and their weekly checks) on 14 September. 0013 (probe calls) written and not applied. 12 MB. |
| Probe mode | Built and off. It would measure how often TomTom calls fail, keeping only each attempt's corridor, time, attempt number, HTTP status and latency, never the response. It needs 0013 and Sahil's decision to run. |
| Corridors | 10 declared, all draft placeholders. None verified, none active. |
| Measurements | 0 samples, 0 failed samples, 0 collector runs recorded. |
| Collector | Scheduled every 5 minutes across the collection windows in GitHub Actions. It exits at once while no corridor is active. |
| Hash chains | Both chains walked once, on 13 September. One Rekor anchor, covering two empty chains. |
| Metrics engine | Built and tested on synthetic panels. Every derived table is empty. The nightly job has not run yet. |
| Read API and dashboard | Built and tested against fixture data. **Not deployed**: no Vercel project, no `VERCEL_TOKEN`, no browser tile key. |
| Intervention audit (P-07) | Estimator and view built. No audit is possible until a corridor has 205 days of data. |
| System View (P-05 design, P-06 build) | **Not built.** The design has not been delivered. |
| Junction register | 16 candidates. None verified on satellite imagery. |
| Works register | 12 works: 4 announced, 2 under construction, 6 treated. 6 have a source that supports their status. 18 control candidates, none screened. |

Waiting on Sahil:
- verifying junction coordinates;
- declaring real corridors to replace the placeholders;
- the TomTom question above;
- `VERCEL_TOKEN` and the tile key for deployment.

## Using the dashboard

> **This section describes a site that is not deployed.** The Vercel phase is
> blocked with no token, and the database holds zero real samples. Everything
> below was checked against synthetic fixture data, which the dashboard marks
> with a SAMPLE DATA banner. No screenshots are included. Remove this note when
> the first real deploy lands.

This is a measurement instrument, not a navigation app. It shows how each
measured corridor has behaved at a given hour across months of calls, so you
can see which route is predictable and when. It does not know about the
accident that happened ten minutes ago. For that, use Google Maps.

The views are tabs across the top. A date scrubber and an hour scrubber sit
beside them. "Live" and "historical" are the same views at different scrubber
positions.

### 1. Corridor ledger (landing view)

**Answers:** which corridors are worst, and how that has moved.
**Does not answer:** why a corridor is bad, or whether it will be bad today.

- **TTI (travel time index) is severity:** travel time divided by free-flow
  time. A TTI of 2.4 means a trip that takes 20 minutes with no traffic takes
  48.
- **Two free-flow references.** Every index is shown against both:
  - TomTom's modelled no-traffic time;
  - the observed 5th percentile of night calls (00:00–04:00 IST) over the
    trailing 28 days.

  They are never averaged. Where they disagree is itself a finding.
- **BTI (buffer time index) is unreliability**, usually what commuters actually
  feel. It is (p95 − mean) ÷ mean over pooled peak-hour calls. A BTI of 0.5
  means the bad trip takes half again as long as the average one.
- **PTI (planning time index) is the practical one:** p95 travel time divided
  by free-flow time. Allow PTI times the free-flow time, and 95% of the
  peak-hour calls in the window arrived within it. That is 95% of calls, not 19
  days in 20: bad calls cluster on bad days.
- **Ranking.** The table is sorted worst first on shrunk TTI. Shrinkage pulls
  a corridor-hour with few calls toward the city mean, so a corridor with
  three bad calls does not top the table. Raw and shrunk values are both
  published.
- **Pooling.** BTI and PTI pool every peak-hour call (06:30–10:30 and
  16:30–21:00 IST) over the trailing 90 days. Each is shown beside the count
  of calls pooled, and the scrubbers do not move them. Because they pool
  every peak hour, they clear their floor early: around day 6–7 of collection
  for a corridor measured every 15 minutes, and day 12–14 for one measured
  every 30 minutes. Not day 90. See [When numbers first appear, and which never
  do](#when-numbers-first-appear-and-which-never-do).
- **No interval.** An interval that resampled calls treated calls from the
  same day and week as independent. In simulation it covered the true value
  in 68–84% of panels, not 95%
  ([docs/ledger_intervals.md](docs/ledger_intervals.md)).
- **An em dash means below the sample floor, never zero.** The floor is 200
  pooled calls for anything derived from a p95, and 30 for a mean or median.
  The count is shown beside the dash. Some dashes are permanent by design,
  not a fault: see [When numbers first appear, and which never
  do](#when-numbers-first-appear-and-which-never-do).

### 2. Network pulse

**Answers:** which corridors have been running worse than their own normal,
day after day, across the 90-day window.
**Does not answer:** how bad a corridor is in absolute terms. It fits no trend
line.

How to read it:
- Each row is a corridor and each column a day. The colour is travel time at
  the selected hour against that corridor's own median at that hour.
- A horizon chart folds a large deviation into darker, stacked bands (three
  each way), so a thin row can still show it. Warm means slower than usual,
  cool means faster, and a day with no value is blank.

Because each row is measured against its own median, a chronically congested
corridor behaving normally looks quiet. The view shows change, not severity.

### 3. Weekly rhythm

**Answers:** when a corridor breaks down, not just that it does.
**Does not answer:** what causes the pattern.

- One corridor as a 7 × 24 grid: median TTI for each weekday and hour, over
  the window stated on the view.
- A selector picks the free-flow reference, and the view names the one it
  shows.
- Cells below the floor stay empty, and low-confidence cells are hatched. The
  worst and best cells are called out.
- For a corridor measured every 30 minutes, every cell stays empty. It gets at
  most 26 calls per weekday and hour in the 90-day window, under the floor of 30.
  The citywide matrix pools every corridor and does fill.

It helps with choosing a departure time, and with arguments about signal
timing or enforcement staffing.

### 4. Route comparison

This is the view that does something Google does not: it shows how two
measured routes have behaved over months, not what one route looks like now.

**Answers:** for two separately declared and measured corridors between the
same endpoints, how each has behaved at the selected hour.
**Does not answer:** which road is faster now, or which one to take. It
declares no winner.

- **Median and p95.** Both are shown for each side, each with its pooled
  count, pooled over the trailing 120 days. The median describes a normal day.
  The p95 describes the day that makes you late. A p95 at a single hour needs
  months of collection, and some hours never get one: see [When numbers first
  appear, and which never do](#when-numbers-first-appear-and-which-never-do).
- **Both routes are measured.** Each must be declared and measured in its own
  right. We never compute an alternative. A corridor with no measured pair
  shows an empty state that says so. It never builds a second route.
- **No winner.** The difference between the two p95s is shown with both
  counts, never as a lead. With no interval, a difference can be noise: in
  simulation, two identical corridors showed a "lead" in 10–20% of hours.
- **The Google Maps button** passes the origin and destination only, with no
  waypoints. Its label reads "Open in Google Maps · endpoints only, Google
  chooses the road".
  - It is deliberately not labelled "most reliable at this hour". The page
    names no corridor as more reliable, and with endpoints only Google picks
    the road, so the link cannot send anyone down the more reliable corridor.
  - It is never labelled "fastest now" either.

### 5. Intervention audit

**What the audit can see.**
- It detects flyover-scale changes.
- It does not detect a signal retiming.
- Tier B corridors cannot be audited.
- A 56-day post period is untested.

The view opens with this statement for every audit, whatever its status.

**Answers:** whether a named infrastructure change moved a corridor's BTI by
more than untreated corridors moved.
**Does not answer:** whether a small intervention worked, or why a change
happened.

How the verdict works:
- **The comparison.** The audit builds a synthetic version of the treated
  corridor: a weighted blend of untreated donor corridors, matched over 24
  weeks before the change. It then compares the real corridor with that blend
  afterwards.
- **Placebo runs.** It repeats the whole procedure with each donor treated in
  turn, and ranks the treated corridor's standardised effect among those
  runs. "Extreme" means it ranked at the top: p is its rank divided by one
  more than the number of placebos, and extreme means p ≤ 0.05.
- **The floor.** With 21 placebos the smallest possible p is 1 in 22. Even
  with no effect at all, about one audit in 22 reads extreme by chance, and
  every verdict says so. A single extreme verdict is not a finding.
- **"Not extreme" for a small intervention means this panel cannot resolve
  it. It does not mean the intervention failed.** This is the most likely
  misreading of the view.

Everything behind the counterfactual is published, because a counterfactual
nobody can inspect is not evidence:
- the weight of every donor;
- every excluded corridor with its reason: paired alternate, treated, under
  construction, incomplete pre-period, or too little post-period data;
- the missing rate and BTI of the excluded corridors beside the donors';
- an equal-weight cross-check;
- reruns at stricter and looser completeness thresholds.

An audit is withheld, with its reason, until it has 168 pre days, 9 settling
days and 28 post days. No corridor has data yet, so no audit can report until
about seven months after the first real corridor goes active.

### 6. Map

**Answers:** where the corridors are. It is for spatial orientation only.

- **Stored roads and straight connectors.** A corridor whose road has been
  stored is drawn as that road: the route TomTom returned through the
  corridor's declared points, fetched once when the corridor was verified. Any
  other corridor is a straight connector between its measured endpoints, not
  the road driven. A list under the map says which corridor is drawn which
  way. No corridor has a stored road yet.
- **Basemaps.** Minimal (the default), street or satellite, remembered in your
  browser. All three are TomTom raster tiles loaded by your browser from
  TomTom. Minimal is TomTom's street map desaturated, and satellite is
  TomTom's imagery. Until the browser tile key exists, no mode shows a
  basemap.
- **Satellite imagery never shows a straight connector.** A straight line over
  imagery reads as a claim about the road, crossing Hussain Sagar or cutting
  through buildings. So satellite mode is offered only once some corridor has
  a stored road, and over it only those corridors are drawn; the rest are
  listed as not drawn.
- **Tiles.** The traffic-flow layer refreshes every 2 minutes while the tab is
  visible, and is not drawn over imagery. If a layer's tiles fail to load (for
  example once the tile allowance runs out), the whole layer is hidden and the
  corridors draw on a plain ground.
- **Freshness.** Line colours are TTI at the scrubber position. The indices
  behind them are recomputed nightly, not every 15 minutes, and the timestamp
  above the map says when. The traffic tiles are live; the lines are not.

### 7. Wall mode (`?mode=wall`)

**For:** a large display read from across a room, with no interaction. The
design target is a 65-inch screen at 3–5 m.

- **Panels.** Four rotate every 25 seconds (`?rotate=` accepts 6–60): network
  state, worst five corridors, city rhythm and biggest movers.
- **No map.** It has no map, so it loads no tiles on any rotation.
- **Timers.** It checks API health every 60 seconds and reloads data every 15
  minutes (the indices themselves change nightly). It reloads the page daily
  at 04:00 IST.
- **Degraded state.** If the API is unreachable or a refresh fails, an amber
  DEGRADED banner appears over the last good data, dimmed, saying when the
  failure started. The screen never goes blank.

### When numbers first appear, and which never do

A new corridor shows em dashes for a while, and some hours show them forever.
Each pooled statistic appears only once enough calls clear its floor, so how
soon depends on how often the corridor is measured at the peaks.

| Statistic | Floor | Every 15 minutes | Every 30 minutes |
|---|---|---|---|
| Ledger BTI and PTI (every peak-hour call, 90 days) | 200 calls | day 6–7 | day 12–14 |
| Profile and route comparison, a full peak hour (120 days) | 200 calls | day 50–58 | day 100–115 |
| Profile and route comparison at 06:00, 10:00 and 16:00 (120 days) | 200 calls | day 100–115 | **never** |
| Weekly rhythm, one corridor, a full peak hour (90 days) | 30 calls | week 8–9 | **never** |
| Weekly rhythm, one corridor, 06:00, 10:00 and 16:00 (90 days) | 30 calls | **never** | **never** |

Ranges run from no failed calls to 12.5% failed.

**Why "never" is by design.**
- 06:00, 10:00 and 16:00 lie only partly inside the peak windows (06:30–10:30,
  16:30–21:00), so they get half the calls of a full hour.
- Every 30 minutes that is one call a day, at most 120 in the profile's 120-day
  window, so the p95 floor of 200 is never reached.
- The rhythm matrix's median needs 30 calls per weekday and hour, and a 90-day
  window holds each weekday only 12 or 13 times.

A permanent em dash in those places means the corridor was never sampled densely
enough there. It is not a fault. The arithmetic is in
[docs/free_tier.md](docs/free_tier.md), section 5.

### Data export

- **Routes.** `/api/export.csv` (gzipped) and `/api/export.parquet` redirect to
  files in the public `exports` bucket. Each file's sha256 is in
  `export_manifest` and in the response headers.
- **Contents.** Every published corridor-hour from `metrics_daily`, with the
  declared corridor and its measured length. These are derived hourly metrics,
  not raw responses. The raw record is the monthly Parquet archive in the
  public `archive` bucket.
- **Nothing has been exported yet.**
- **Licence: none has been chosen.**
- **Permission.** Whether this data may be published at all is unresolved.
  See [Unresolved: TomTom's terms and allowance](#unresolved-tomtoms-terms-and-allowance).

### Verify it yourself

Every sample and every failed call is a row in a SHA-256 hash chain. Each
row's hash covers the row and the previous row's hash, so changing or deleting
any row breaks every hash after it. `/api/verify` reports the latest walk of
both chains and when it ran.

A walk recorded inside the database it checks proves little on its own. So
every night CI signs both chain heads with keyless cosign: GitHub's OIDC token
names the workflow, and the signature is entered in Sigstore's Rekor, a public
append-only log that nobody, the author included, can edit or backdate. The
signed head files and their signature bundles are public.

Check the signature on an anchor:

```bash
BASE=https://duejdeswzjepliqfkjyf.supabase.co/storage/v1/object/public/archive
curl -s "$BASE/heads/index.json"
curl -sO "$BASE/heads/20260913T193709Z.json"
curl -sO "$BASE/heads/20260913T193709Z.sigstore.json"
cosign verify-blob \
  --bundle 20260913T193709Z.sigstore.json \
  --certificate-identity https://github.com/smatt92/hyderabad-corridor-ledger/.github/workflows/daily.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  20260913T193709Z.json
```

Then walk both chains from their first row: archive files first, then the
live tables, recomputing every hash. The check confirms every anchored head is
still in place:

```bash
cd collector && uv sync
SUPABASE_URL=https://duejdeswzjepliqfkjyf.supabase.co SUPABASE_KEY=<publishable key> uv run python anchor.py check
```

The limits, plainly:
- **What it proves.** It proves what CI published, and when. It does not prove
  a measurement was right when TomTom returned it.
- **Before the first anchor.** Rows rewritten before the first anchored head
  would be invisible. The only anchor so far (13 September 2026) covers two
  empty chains, so it anchors nothing yet.
- **Deleted anchor files.** Deleting anchor files from the bucket hides those
  anchors from the checker, though their Rekor entries stay in the public log.
- **The key.** The full walk reads the live tables with the project's
  publishable key, which is not published anywhere yet. Until it is, a reader
  can check signatures and download the archive, but cannot run `anchor.py
  check` against the live tables.
- **Where it has run.** The `cosign` command above is the one `anchor.py` runs
  in CI, where it passed on 13 September. It has not been run from outside
  CI.

### Reading the gaps

- **A gap means we did not measure, not that traffic was fine.** Missing data
  renders as a gap. It is never interpolated, carried forward or modelled.
- **Missingness tracks congestion.** API failures (timeouts, rate limits)
  cluster at peak congestion, so missingness rises with the very thing being
  measured. Filling a gap would understate congestion exactly where it is
  worst.
- **Flags.** Every metric carries its missing rate against the collector's
  schedule. A cell missing more than 15% is flagged low-confidence and drawn
  hatched and dimmed. Metrics older than 30 hours show as STALE.

### What to do if a number looks wrong

1. Check the pooled count and the window printed beside it. A value derived
   from a p95 just above 200 calls is thin.
2. Check the low-confidence and STALE markers.
3. Then open an issue at
   <https://github.com/smatt92/hyderabad-corridor-ledger/issues>. Give the
   corridor ID, the date and hour (IST), and the view.

## Quick start

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js with
npm. The repository holds four projects, each with its own lockfile.

```bash
git clone https://github.com/smatt92/hyderabad-corridor-ledger.git
cd hyderabad-corridor-ledger
uv sync                                  # metrics engine, at the repo root
(cd collector && uv sync --group dev)
(cd api && uv sync --group dev)
(cd web && npm ci)
```

Run the checks the way CI runs them:

```bash
uv run pytest && uv run ruff check metrics tests scripts
(cd collector && uv run pytest && uv run ruff check . && uv run python config.py && uv run python immutability.py)
(cd api && uv run pytest && uv run ruff check .)
(cd web && npm test && npm run build)
```

### Environment variables

| Variable | Used by | Where it lives |
|---|---|---|
| `SUPABASE_URL` | collector, metrics jobs, API | GitHub Actions, Vercel |
| `SUPABASE_SERVICE_KEY` | collector, metrics jobs | GitHub Actions only. Never Vercel, never a file. |
| `TOMTOM_API_KEY` | collector | GitHub Actions only |
| `SUPABASE_PUBLISHABLE_KEY` | read API | Vercel only |
| `TOMTOM_TILE_KEY` | dashboard build | Vercel only; a separate, domain-restricted key |
| `LEDGER_FIXTURE_DIR` | read API, locally | your shell. The API refuses it when `VERCEL` is set. |
| `SUPABASE_KEY` | `anchor.py check` | anyone; a key that can read the public tables |

Tokens are never written to files, `.env` included.

### Running the collector

There is no local or staging database.
- **Don't run `fetch.py` with real keys.** It writes to the production ledger,
  whose rows are append-only and hash-chained, and it spends TomTom calls.
- **The tests** exercise the collector through a fake ledger and a fake
  transport.
- **Checks that need no key:** `uv run python config.py` validates the corridor
  declarations and the daily budget, and `uv run python registry.py` validates
  the junction and works registers.

### The dashboard on fixture data

```bash
.venv/bin/python scripts/dev/build_fixtures.py
LEDGER_FIXTURE_DIR="$PWD/.fixtures/tables" api/.venv/bin/uvicorn app:app --app-dir api --host 127.0.0.1 --port 8000
npm --prefix web run dev
```

- **Fixtures.** `build_fixtures.py` runs synthetic samples through the real
  pipeline into `.fixtures/tables/`, which is gitignored.
- **Local site.** The dashboard serves on <http://localhost:5173>, and proxies
  `/api` to port 8000. Wall mode is <http://localhost:5173/?mode=wall>.
- **Marking.** Every fixture response carries `sample: true`, and the
  dashboard shows its SAMPLE DATA banner.

## Repository layout

| Path | Holds |
|---|---|
| `collector/` | The only code that calls TomTom or writes samples. Runs in GitHub Actions. |
| `metrics/` | The metrics engine: pure functions from raw samples to derived tables. `io.py` is its only I/O. |
| `tests/` | Metrics engine tests. |
| `api/` | The read-only FastAPI app meant for Vercel. |
| `web/` | Dashboard and wall mode: Vite, TypeScript, Preact, uPlot. |
| `config/` | `corridors.yaml` (the only corridor declarations), `junctions.yaml` (junction candidates), `interventions.yaml` (works register). |
| `supabase/migrations/` | Numbered schema migrations. |
| `scripts/ci/` | The authorship check and the forbidden commit text. |
| `scripts/dev/` | Fixture builder, and the simulations behind the methodology. |
| `docs/` | Architecture, methodology and calibration records. |
| `.github/workflows/` | Collector, nightly, metrics, archive, test and guard workflows. |
| `.githooks/` | The commit-msg hook. |
| `CLAUDE.md` | Working rules and the reasoning behind each. |

## Rules a contributor must not break

| Rule | Enforced by |
|---|---|
| A verified or measured corridor's geometry never changes. To change a road, retire the corridor and declare a new id that supersedes it. | `collector/immutability.py` in `tests.yml` and `corridors.yml`; database trigger `corridors_guard` once a road is stored or the corridor has been active |
| A corridor's stored road is fetched once and never overwritten. A refetch that differs is a rerouting alarm. | Database trigger `corridors_guard` (0012); `collector/fetch.py` fails the run; `collector/gaps.py` fails nightly until the corridor is retired |
| Satellite imagery never shows a straight connector. | `web/src/lib/mapmode.ts` with `mapmode.test.ts`; `web/src/lib/rules.test.ts` |
| An unverified corridor stays a draft. | `collector/config.py` in CI; database constraint `corridors_measured_only_when_verified` (0010) |
| Raw responses are kept, gzipped, and never with route geometry. | The collector refuses a response with route points or over 4 KB gzipped; check constraint on `samples.raw_gz`; `archive.py` re-verifies each file's sha256 and chain before `prune_archived()` may delete |
| `samples` and `failed_samples` are insert-only. | Database triggers raise on UPDATE and TRUNCATE, and on DELETE outside `prune_archived()`; the service role's UPDATE, DELETE and TRUNCATE privileges are revoked; the hash chain, walked nightly and anchored in Rekor |
| The frontend never constructs a route. The Maps link carries origin and destination only, and distance comes only from `length_meters`. | `web/src/lib/route.test.ts`, `web/src/lib/rules.test.ts`, `web/scripts/check-bundle.mjs` on the built bundle |
| No banned package in the bundle: the `d3` meta-package, `d3-selection`, `d3-transition`, `d3-zoom`, `d3-brush`, deck.gl, MapLibre, Mapbox, Leaflet, three.js. | Vite plugin `forbidPackages` in `web/vite.config.ts`; `web/src/lib/rules.test.ts` |
| The service key never reaches Vercel, and the collector's TomTom key never reaches a browser. | The API refuses to start with `SUPABASE_SERVICE_KEY` set; the Vite build refuses `TOMTOM_API_KEY`; `check-bundle.mjs`; `collector/tests/test_workflows.py` allows only `collector.yml` to hold the key |
| Schema changes only through numbered migrations, immutable once applied. | **Not enforced in code.** Nothing compares an applied migration with its file. Review and `CLAUDE.md` only. |
| Every commit is authored and signed by Sahil Mathew. | `scripts/ci/check-authorship.sh` over the full history (`authorship.yml`); `.githooks/commit-msg`; rulesets `main-signed-history` and `main-ci` |
| No agent pushes. | **Not enforced in code.** An instruction in `CLAUDE.md`. The signing agent on Sahil's machine signs whatever commits are made there. |

## Further reading

- [docs/architecture.md](docs/architecture.md): how the system fits
  together, in diagrams, and the decisions behind it with the evidence that
  settled each one.
- [docs/methodology.md](docs/methodology.md): what the intervention audit
  estimates, what it assumes, and what it can detect.
- [docs/ledger_intervals.md](docs/ledger_intervals.md) and
  [docs/audit_power.md](docs/audit_power.md): the simulation runs that removed
  every interval and set the audit's design.
- [CLAUDE.md](CLAUDE.md): the working rules, each with its reason.
