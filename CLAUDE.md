# Hyderabad Corridor Ledger

An independent, auditable record of road travel times on Hyderabad corridors,
collected from the TomTom Routing API into a hash-chained sample log.

## Authorship and signing

Every commit in this repository is authored and signed by Sahil Mathew
(`sahil.matt@gmail.com`, GitHub `smatt92`). Repo-local git config sets the
identity and SSH signing (`commit.gpgsign=true`, `gpg.format=ssh`).

Rules for Claude, without exception:

- NEVER add a Co-Authored-By trailer, a generated-with footer, or a session
  link to any commit message.
- NEVER configure a bot identity, a noreply address, or a second author.
- NEVER create, request, or store signing keys. The private key stays on
  Sahil's machine and the signing agent is Sahil's.
- One branch: `main`. Never create a feature branch.
- Stage and commit. Do NOT push. End every unit of work by printing this
  command for Sahil to run, then stop:

      git push origin main

  Do not run it yourself, do not run it because Sahil said "continue", and do
  not run it inside a script or a chained command.
- If a commit fails because signing is unavailable, STOP and say so. Never
  fall back to `--no-gpg-sign`. An unsigned commit in this repo is a defect,
  not a minor variance.
- The message check is a case-insensitive substring match, so never quote the
  forbidden strings in a commit message, not even to describe the check.

Enforced in code, not by this file:

| Guard | Where |
|---|---|
| Author and committer identity, forbidden message text, signature present | `scripts/ci/check-authorship.sh`, run over the full history by `.github/workflows/authorship.yml` on every push and PR |
| Signature valid and made by smatt92's key, not GitHub's | same script, through the GitHub GraphQL API in CI |
| Forbidden message text, before the commit exists | `.githooks/commit-msg` (`core.hooksPath=.githooks`) |
| Unsigned commits rejected at the remote | ruleset `main-signed-history`: required signatures, no force push, no deletion, no bypass |
| CI status on `main` | ruleset `main-ci`: requires `authorship`; admin bypass so direct pushes stay allowed |

The forbidden strings live in one place: `scripts/ci/forbidden-commit-text.txt`.

**Why.** This project's entire value is being an independent, auditable
record. A verifiable commit history is the same argument as the hash-chained
sample log, applied to the code that produced the data. If the collector's
logic cannot be attributed, the dataset it produced cannot be trusted either.

## Infrastructure

- Supabase: project `hyderabad-corridor-ledger`, ref `duejdeswzjepliqfkjyf`,
  region `ap-south-1` (Mumbai), org `sutytlpyraimbvdqdicf`.
- Vercel: not created or linked yet. When it is: project
  `hyderabad-corridor-ledger`, not Git-connected, and `vercel.json` sets
  `git.deploymentEnabled: false`. It hosts `web/` and `api/` as Vercel
  Services (P-04) and nothing else.
- GitHub: `smatt92/hyderabad-corridor-ledger`, public, with secret scanning
  and push protection on.

## Secrets

| Secret | GitHub Actions | Vercel | Any file |
|---|---|---|---|
| `SUPABASE_SERVICE_KEY` | yes | **never** | **never** |
| `TOMTOM_API_KEY` (server-side) | yes | **never** | **never** |
| `SUPABASE_URL` | yes | yes | no |
| `SUPABASE_PUBLISHABLE_KEY` | no | yes | no |
| `TOMTOM_TILE_KEY` (separate, domain-restricted) | no | yes, before P2 | no |

- The collector runs in GitHub Actions with the service key. Nothing else
  holds it: not a Vercel env var, not a client bundle, not a committed file.
- If a step appears to need the service key on Vercel, stop and tell Sahil:
  something is running in the wrong place.
- Tokens are never written to files, `.env` included.
- PostgREST needs `apikey` AND `Authorization`. With a legacy JWT key,
  `apikey` alone silently resolves to the `anon` role: a service call fails
  with 401 (`db-size.yml` did), or reads only what anon may read and looks as
  if it worked. Every hand-rolled REST call sends both. `db-size.yml` sends
  both headers and reports the key's style, never the key.
  `collector/store.py` and `metrics/io.py` add `Authorization` for JWT-style
  keys. New-style `sb_` keys authenticate through `apikey`: on 2026-09-13 the
  publishable key worked with `apikey` alone and with an identical Bearer.
  Whether the `sb_secret_` key accepts a Bearer header is not yet verified.
  The project has both a legacy `service_role` JWT and an `sb_secret_` key.

## Schema discipline

- Every table and schema change is a numbered migration in
  `supabase/migrations/`, named `NNNN_description.sql`, applied with
  `supabase db push`. A migration is immutable once applied to the linked
  project, and freely editable before that.
- RLS is enabled in the migration that creates a table. Public read on
  `corridors`, `samples`, `failed_samples`, the collector's run, gap,
  archive and verification tables (0003), `interventions` and every derived
  metrics table (0004, 0005). No write policy for `anon` or `authenticated` anywhere, and their
  write privileges are revoked as well.
- `.mcp.json` configures the Supabase MCP server read-only. Use it to inspect
  schema and spot-check rows. Wanting to mutate through MCP means a migration
  is missing.

## Hash chains (samples v1, failed_samples f1)

`samples` and `failed_samples` are append-only. UPDATE and TRUNCATE always
raise; DELETE raises everywhere except inside `public.prune_archived()`, and
the service role's UPDATE, DELETE and TRUNCATE privileges are revoked too. On
insert, a trigger sets `seq`, `inserted_at`, the payload digest, `prev_hash`
and `row_hash` under an advisory lock, so concurrent writers cannot fork a
chain.

    row_hash = sha256(prev_hash || utf8(canonical(row)))

- The genesis `prev_hash` is 32 zero bytes.
- Canonical text: fields joined by `|`, NULL as empty, timestamps in UTC as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`, hashes as lowercase hex. Field order is
  defined in `public.samples_canonical` (starts with `v1`) and
  `public.failed_samples_canonical` (starts with `f1`). `collector/chain.py`
  ports both; its tests hold vectors hashed by the database.
- Format v1 was applied in 0001 and does not cover `samples.scheduled_slot`
  or `samples.attempts`, which 0003 added. The append-only guard protects
  those two, not the hash.
- `public.record_chain_verification()` (service role) walks both chains,
  records each head hash and first break in `chain_verifications`, and
  returns them. `daily.yml` runs it nightly and copies the heads into the job
  summary, outside the database.
- Any change to a canonical function is a new format version.

## Storage budget (500 MB free tier)

The daily budget is 2,400 TomTom calls. At that ceiling the ledger gains about
876k rows a year, and the 90-day hot window holds at most about 216k.

- Always request `routeRepresentation=summaryOnly`; corridor paths come from
  OSM. The collector refuses a response over 4 KB gzipped and
  `samples.raw_gz` has a 4 KB check constraint, so a response carrying
  geometry fails loudly instead of eating the quota.
- Store raw responses gzipped in `bytea`, never `jsonb`, and read them through
  `metrics.raw.decompress_raw`.
- Monthly archive (`collector/archive.py`, `.github/workflows/archive.yml`):
  rows requested more than 90 days ago go to Parquet in the public `archive`
  bucket, at most 20,000 rows a file. Each file is downloaded again and its
  sha256 and hash chain re-checked before `sample_archives` records it. Only
  then does `public.prune_archived()` delete, after checking the row count and
  boundary hash itself. The archive is the permanent record and the tables are
  a 90-day cache of it. The newest row of each table never leaves: it holds
  the chain head.
- `.github/workflows/db-size.yml` logs the database size through
  `public.log_db_size()` weekly and on every push to `main`, and fails at
  400 MB.
- `metrics_daily` is hourly: about 8,800 rows per corridor per year. Derived
  tables are disposable, so they can be truncated and rebuilt if space runs
  short; samples cannot.

## Collector (P-01)

`collector/` is its own uv project and runs only in GitHub Actions, never on
Vercel. It is the only code holding the service key and the server-side
TomTom key.

### Corridor declarations

`config/corridors.yaml` is the only place a corridor is defined, validated by
`collector/config.py`: `id`, `code`, `name`, `class` (core, alternate or
donor), `tier` (A, B or C), `direction` (ab or ba), `pair_id`, origin and
destination names and coordinates, `via_points`, `status` (draft, active, paused or
retired) and `supersedes`.

- Alternates are declared, never derived. A pair holds one core and at most
  one alternate per direction, all sharing endpoints, and `ba` reverses `ab`.
  A one-corridor pair is valid: it means no measured alternate. Donors are
  never paired.
- Every corridor, core, alternate or donor, declares `via_points`: an ordered
  list of lat/lon that the collector sends to calculateRoute as waypoints on
  every call. Without them TomTom chooses the road and can silently choose a
  different one between runs, so the series would not measure a fixed
  corridor, and two corridors sharing endpoints would measure the same road
  twice. A pair's members share endpoints and must differ in `via_points`:
  identical `via_points` within a pair is an error in `collector/config.py`
  and in the `corridors_check_pair` trigger (0006). `via_points` never reach
  a user.
- Geometry (endpoints, `via_points`, direction) freezes the first time a corridor is
  anything but a draft. To change a measured road, retire the corridor and
  declare a new id that `supersedes` it. `collector/immutability.py` compares
  every committed version in CI, and the `corridors_guard` trigger refuses the
  change again in the database.
- `.github/workflows/corridors.yml` syncs the file into `corridors` on pushes
  to `main`, after the same checks.
- `placeholder-01` to `placeholder-10` are drafts. Nothing is measured until
  real corridors replace them and are set `active`. Tests read the frozen
  copy in `collector/tests/fixtures/`, never the live file.

### Schedule, budget and retries

- Slots, IST: 06:30-10:30 and 16:30-21:00, every 15 minutes for Tier A and
  every 30 minutes for Tiers B and C; night slots every 30 minutes from 00:00
  to 04:00 for every tier. Tier A owes 42 slots a day, Tiers B and C 25.
- `.github/workflows/collector.yml` dispatches every 5 minutes across those
  windows. Each run measures every active corridor whose latest slot is due,
  meaning less than one slot spacing old, and has no outcome yet. GitHub
  delays and drops scheduled runs. A slot no run reaches in time is missing,
  and is never backfilled.
- Idempotency: (corridor_id, scheduled_slot) is unique in `samples` and in
  `failed_samples`, and a trigger allows one outcome per slot across the two.
- Budget: a token bucket of 2,400 calls per IST day, released as slots come
  due, with 15% held back for retries. Every HTTP attempt spends a token.
  `python collector/config.py` fails in CI when the active panel cannot fit.
- Retries: timeouts, connection errors, 429 and 5xx, three attempts with full
  jitter backoff. When they run out, the slot goes to `failed_samples` with
  its error class. A failure is never dropped.
- `length_m` from the response is the only distance anywhere in the system.
- A response with route points, or over 4 KB gzipped, is recorded as a
  `geometry_leak` failure and fails the run.
- The collector refuses to start if `samples` or `failed_samples` hold rows but
  no collector run was ever recorded.

### Checks that fail loudly

| Check | Where |
|---|---|
| Slots missing from yesterday (IST) | `collector/gaps.py` in `daily.yml`; writes `gap_reports` |
| Head hash and first break of both chains | `collector/chain.py` in `daily.yml` |
| Database at or over 400 MB | `db-size.yml` |
| A measured corridor's geometry changed | `immutability.py` in `tests.yml` and `corridors.yml` |
| Scheduled workflows disabled after 60 idle days | `keepalive.yml` re-enables them through the API weekly |

**Done** means seven unbroken days of real samples with a valid chain: the gap
report prints the count of unbroken days, and both chains verify.

## Metrics engine (P-02)

`metrics/` turns raw responses into `metrics_daily` (per corridor, per local
hour), `worst15_daily`, `corridor_rankings`, `stl_daily`, `change_points`,
`recovery_events`, `recovery_km`, `recovery_cox` and `before_after`.

- Raw is the source of truth; every derived table is disposable. `python -m
  metrics backfill` recomputes all of them from the Parquet archive plus the
  hot table and replaces them wholesale. It refuses to run if any seq between
  1 and the latest is missing, since that would silently rewrite history.
- Changing a definition: edit `metrics/params.py` or the pure function, bump
  `METHOD_VERSION`, run a backfill. Never patch derived rows by hand.
- `uv run pytest` and `uv run ruff check .` before every commit; CI runs both.
- `--dry-run DIR` writes Parquet locally using the publishable key. Writing
  to the database needs the service key and happens only in GitHub Actions.

**Why metric functions are pure.** Every module except `metrics/io.py` takes
dataframes and returns dataframes, with no database or network access.
A published number has to be reproducible from raw by anyone holding the
archive. A function with no hidden inputs can be checked against a fixture
whose expected values were worked out by hand, re-run over all of history
when a definition changes, and audited by reading it. I/O inside a metric
makes its output depend on when and where it ran, which is the opposite of an
auditable record. New metrics get a pure function and a hand-computed test;
only `metrics/io.py` reads or writes.

**Why both free-flow series survive.** TTI and PTI are published against
TomTom's `noTrafficTravelTimeInSeconds` (`*_tomtom`) and against the observed
p5 of night-slot samples (00:00-04:00 IST) over a trailing 28 days
(`*_p5`), side by side. TomTom's figure is a
modelled estimate nobody outside TomTom can audit. The p5 is observed but
drifts up during long disruptions such as a monsoon month, which flatters
TTI. Where the two disagree is itself a finding. Averaging them, reconciling
them or keeping one hides that disagreement and makes the index depend on a
choice the reader cannot see. Never collapse them into one column, and never
drop one from a table or a ranking.

**Why censored observations are never dropped.** Recovery time runs from the
day's peak TTI until TTI falls below 1.3. A corridor that has not cleared by
the end of the sampling window, or whose readings stop mid-congestion, is
right-censored at its last reading (`recovery_events.cleared = false`) and
stays in the Kaplan-Meier and Cox fits. The corridors that fail to clear are
the worst ones. Dropping them keeps only the recoveries that happened, so
recovery looks fastest exactly where it is slowest.
`tests/test_recovery.py` shows the median moving from 30 to 20 minutes when
censored rows are dropped.

**Why nothing is imputed.** API failures (429s, upstream timeouts) cluster
during peak congestion, so missingness correlates with the thing being
measured. Any fill-in value, whether interpolated, carried forward or
modelled, is drawn from the calmer readings around the gap. It understates
congestion exactly when congestion is worst, and it looks like data. So a
cell with no successful call has NULL metrics, every metric row carries
`missing_rate`, and `low_confidence` is true above 15%. Missingness is counted
against the collector's schedule for each corridor's tier
(`metrics/schedule.py`, checked against `collector/schedule.py`), so a
collector run that never started still counts as missing. STL runs only on contiguous segments and
recovery censors at gaps, rather than bridging them. No `fillna`,
interpolation or forward-fill is ever applied to a measurement.

**BTI is a property of a distribution, not of a day.** BTI, PTI and every
p95 are computed once over pooled successful calls (`metrics/pooled.py`),
never per corridor-hour-day cell and never as an average of daily values. A
cell holds two to four calls. The empirical p95 of three draws is effectively
their maximum and biased low by an amount that depends on the count, so cell
BTIs of 0.01-0.09 were wrong, not merely low. Averaging them is wrong twice:
the mean of ratios is not the ratio of means, and a change in sample density
between two periods manufactures an effect out of the estimator.
`tests/test_audit.py` draws both periods from one distribution with different
densities and requires no effect.

- Pooling units: the 24-hour profile pools every call at each local hour over
  the profile window (120 days). The ledger pools peak-hour calls
  (06:30-10:30, 16:30-21:00 IST) over the trailing 90 days, one distribution
  per corridor. The audit pools peak-hour calls over each fixed 28-day period
  and computes BTI once per period.
- Floors by quantile: p95-derived statistics need 200 pooled calls; mean and
  median need 30. Below a floor the value is NULL and the pooled count is
  published beside it. The frontend renders an em dash, an insufficient-samples
  state and the count, never a number.
- Percentiles are empirical, linear between order statistics. Do not use
  Harrell-Davis: at p95 its weights concentrate on the top order statistics,
  so it inherits the sparsity it was meant to fix and overshoots.
- Every published p95, and every value built on one, carries a percentile
  bootstrap interval from 2,000 resamples, seeded from the statistic's key so
  it reproduces. The ledger shows the point value; the expanded row shows
  "0.42 [0.31, 0.58]".
- Any view showing a p95-derived metric states its pooling window in visible
  text: the dates, what was pooled, and the count.
- Tier A pooling yields ~360 calls per corridor-hour at 90 days. Tiers B and C
  yield ~180 and cross the p95 floor at roughly 100 days, so their tail
  metrics legitimately show insufficient samples for about three months. The
  profile window is 120 days so that they do cross it; a 90-day window never
  would.
- The hourly and daily series carry TTI and mean travel time with their counts
  (`n_ok`), and no tail statistic.

Other definitions worth knowing before changing them:
- Shrinkage: TTI uses normal-normal empirical Bayes over hourly cells, and
  congested shares use beta-binomial. BTI and PTI are never ranked from cells. Raw and shrunk are both published;
  rank 1 is the worst corridor by shrunk value.
- STL runs on the daily mean of hourly TTI with period 7. Trend statements
  use `stl_daily.trend` only, never `observed`.
- CUSUM (k = 0.5, h = 5) and EWMA (lambda = 0.2, L = 3) run on the STL
  residual in robust sigmas. `change_points.magnitude` is in TTI units.
- Before/after uses always-valid confidence sequences on STL-adjusted daily
  TTI, so `before_after` may be read every day. A fixed-horizon p-value may
  not be.
- The intervention audit (`metrics/audit.py`) is a different estimator. It
  pools BTI once per fixed 28-day period, takes a difference in differences
  against the equal-weight mean of untreated corridors, and reports a
  bootstrap interval. It publishes no effect until the post period has
  closed, so re-reading it cannot change the answer.

## Read API and frontend (P-04)

Vercel hosts the frontend (`web/`) and the read API (`api/`) and nothing
else. The collector, chain verification, archive, metrics and exports run in
GitHub Actions.

### Route construction: hard rule

A route we have not measured must never reach a user. Someone may drive it.

- The frontend never constructs, derives, infers or suggests a route. No
  midpoints, no nearest-node heuristics, no via nodes.
- Alternates come only from `pair_id` in the payload. A pair that declares
  one corridor is a valid API response (`alternate: null`), and the
  comparison view renders its empty state. It never builds a second route.
- The Google Maps handoff carries origin and destination only:
  `google.com/maps/dir/?api=1&origin=LAT,LON&destination=LAT,LON&travelmode=driving`.
  No waypoints parameter, ever. Only `web/src/lib/route.ts` builds that URL.
- Distance is `length_meters` from the payload, measured by TomTom. Never
  compute it from coordinates. When it is absent, show an em dash.
- The map draws each pair as a straight connector between measured endpoints,
  captioned as such. We store `routeRepresentation=summaryOnly` and hold no
  route geometry. Real geometry would be separate, scoped work against OSM.
- `via_points` do not change this. A person declares them in
  `config/corridors.yaml`, and they are measured on every cycle for months.
  Declared and measured is the opposite of derived at render time. The API
  does not serve them, the frontend never constructs a route from them or
  from anything else, and the Maps handoff still carries origin and
  destination only. The route-construction ban is unchanged.

Enforced by `web/src/lib/route.test.ts`, `web/src/lib/rules.test.ts` (no
waypoints, haversine, midpoints, via nodes or great-circle trigonometry
anywhere in `src/`) and `web/scripts/check-bundle.mjs` on the built bundle.
Pairs sharing endpoints is enforced by `collector/config.py` and the
`corridors_check_pair` trigger. Payloads name a pair's sides `primary` and
`alternate`: the primary is the pair's `class: core` corridor, mapped in
`api/app.py` and `metrics/io.py`. Donor corridors have no role.

### Read API (`api/`)

- It selects precomputed rows and shapes JSON. It never computes a metric and
  never reads `samples`. `api/store.py` allowlists the readable tables, and a
  test asserts `samples` is never queried.
- It needs only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`, and refuses to
  start if `SUPABASE_SERVICE_KEY` is present.
- Every response, errors included, carries `as_of` and `missingness_rate`.
- Tail statistics (p95, BTI, PTI) come only from the pooled tables:
  `corridor_stats` (the ledger), `profile_hourly`, `pair_advantage_hourly`
  and `intervention_audit`, each with its window, count and interval. Hourly
  and daily series never carry them. A payload that includes one also
  carries `floors` from `dataset_stats`.
- Data responses are `Cache-Control: public, max-age=0, s-maxage=3600,
  stale-while-revalidate=86400`. `/api/health` and errors are `no-store`.
- `api/pyproject.toml` is FastAPI only, with `default-groups = []`, so a
  deploy build installs no dev tools. numpy and pandas never go in. If cold
  starts or bundle size become a problem, stop and tell Sahil.
- `/api/verify` serves the latest walk of each chain, `samples` and
  `failed_samples`. `daily.yml` records one nightly, and `python -m metrics
  verify` records another before each backfill. Walking a chain reads every
  row, so it never runs on the read path.
- `/api/export.csv` and `/api/export.parquet` redirect to the files in the
  public `exports` bucket. `export_manifest` records each file's sha256. The
  CSV is gzipped (`.csv.gz`) to stay under the bucket's 50 MB file limit.
- Endpoints beyond the P-04 list, added for the design: `/api/network/heatmap`
  (wall city rhythm), `/api/interventions` (audit picker), `/api/health`.

### Frontend (`web/`)

- Vite + TypeScript + Preact. uPlot draws the solved chart types
  (sparklines, profile band, trend, slope chart, spread band, wall bars).
  `d3-scale`, `d3-array`, `d3-shape` and `d3-time-format` are math and format
  helpers only.
- Built by hand because they are the product: the horizon grid
  (`encodings/Horizon.tsx`), the 24x7 rhythm matrix
  (`encodings/RhythmMatrix.tsx`) and the reliability-advantage strip
  (`encodings/AdvantageStrip.tsx`).
- Never install or import: the `d3` meta-package, `d3-selection`,
  `d3-transition`, `d3-zoom`, `d3-brush`, deck.gl, MapLibre, Mapbox, Leaflet,
  or three.js. three.js belongs only to the P-06 showcase route. The build
  plugin in `web/vite.config.ts` fails on any of them by module id.
- Map tiles are plain `<img>` elements in a static slippy-tile grid over
  Greater Hyderabad (`lib/tiles.ts`): no pan, no zoom, no map library.
- The browser uses `TOMTOM_TILE_KEY`, a separate key restricted to the
  deployed origin. The build fails if `TOMTOM_API_KEY` is in its environment.
- Both free-flow bases appear in every table and ranking. A chart that can show
  one basis at a time (rhythm matrix, map) has a basis selector and labels the
  basis it shows. Network pulse and the wall's network state use travel time
  against each corridor's own normal, which needs no basis.
- A p95-derived number appears only as the API publishes it: the point value
  in compact views, its interval in expanded ones, and its pooling window
  stated in visible text. Below its floor it is an em dash with the
  insufficient-samples state and the count, never a number.
- Staleness and low confidence are rendered, never hidden. Metrics older than
  30 hours show as STALE, low-confidence cells are hatched and dimmed, and an
  unreachable API shows a degraded notice rather than an empty page.
- The time scrubber moves in whole hours because `metrics_daily` is hourly.
  Nothing is shown at a resolution the pipeline does not publish.

### Wall mode (`?mode=wall`)

- Same bundle, separate layout tree (`web/src/wall/`), dark register.
- Every timer and request belongs to one `Scheduler` (`lib/scheduler.ts`):
  `setTimeout` chains, never `setInterval`, all stopped on unmount. The
  scheduler test runs a simulated week with a flat timer count.
- The page reloads itself daily at 04:00 IST. Health is checked every 60 s and
  data refreshed every 15 min.
- When the API is unreachable or a refresh fails, a DEGRADED banner appears
  over the last good data, dimmed. The screen is never blank.

### Local preview with fixture data

`.venv/bin/python scripts/dev/build_fixtures.py` runs synthetic samples
through the real pipeline into `.fixtures/tables/` (gitignored, excluded from
Vercel). The API serves them when `LEDGER_FIXTURE_DIR` is set, marks every
response `sample: true`, and refuses to do so when `VERCEL` is set. The
frontend shows the design's sample-data banner only when the API says
`sample`. Fixture code never enters the frontend bundle.
