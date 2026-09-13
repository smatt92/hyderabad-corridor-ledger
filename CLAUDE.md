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
- Vercel: project `hyderabad-corridor-ledger`, not Git-connected, and
  `vercel.json` sets `git.deploymentEnabled: false`. It hosts `web/` and
  `api/` as Vercel Services (P-04) and nothing else.
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

## Schema discipline

- Every table and schema change is a numbered migration in
  `supabase/migrations/`, named `NNNN_description.sql`, applied with
  `supabase db push`. Never edit a migration that has been pushed.
- RLS is enabled in the migration that creates a table. Public read on
  `corridors`, `samples`, `interventions` and every derived metrics table
  (0003). No write policy for `anon` or `authenticated` anywhere, and their
  write privileges are revoked as well.
- `.mcp.json` configures the Supabase MCP server read-only. Use it to inspect
  schema and spot-check rows. Wanting to mutate through MCP means a migration
  is missing.

## Sample hash chain (format v1)

`samples` is append-only: UPDATE, DELETE and TRUNCATE raise. On insert, a
trigger sets `seq`, `inserted_at`, `raw_gz_sha256`, `prev_hash` and `row_hash`
under an advisory lock, so concurrent writers cannot fork the chain.

    row_hash = sha256(prev_hash || utf8(public.samples_canonical(row)))

- The genesis `prev_hash` is 32 zero bytes.
- Canonical text: fields joined by `|`, NULL as empty, timestamps in UTC as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`, hashes as lowercase hex. Field order is
  defined in `public.samples_canonical` and starts with the literal `v1`.
- Check the chain with `select * from private.samples_chain_breaks();`. An
  empty result means it is intact.
- Pruning for the 90-day window will relax the DELETE guard in its own
  migration, together with the archive job, and only for archived rows.

## Storage budget (500 MB free tier)

At ~2,220 calls/day the panel produces ~810k rows/year.

- Always request `routeRepresentation=summaryOnly`; corridor paths come from
  OSM. `samples.raw_gz` has a 4 KB check constraint, so a response carrying
  geometry fails loudly instead of eating the quota.
- Store raw responses gzipped in `bytea`, never `jsonb`, and read them through
  `metrics.raw.decompress_raw`.
- Monthly archive (not built yet): samples older than 90 days export to
  Parquet in Supabase Storage. The archive is the permanent record and the
  table is a 90-day cache of it. Verify each archive reads back before
  deleting any row.
- `.github/workflows/db-size.yml` logs the database size through
  `public.log_db_size()` weekly and on every push to `main`, and fails at
  400 MB.
- `metrics_daily` is hourly: about 8,800 rows per corridor per year. Derived
  tables are disposable, so they can be truncated and rebuilt if space runs
  short; samples cannot.

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
p5 over a trailing 28 days (`*_p5`), side by side. TomTom's figure is a
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
against scheduled slots (`corridors.cadence_s`), so a collector run that never
started still counts as missing. STL runs only on contiguous segments and
recovery censors at gaps, rather than bridging them. No `fillna`,
interpolation or forward-fill is ever applied to a measurement.

Other definitions worth knowing before changing them:
- Shrinkage: continuous indices use normal-normal empirical Bayes, and
  congested shares use beta-binomial. Raw and shrunk are both published;
  rank 1 is the worst corridor by shrunk value.
- STL runs on the daily mean of hourly TTI with period 7. Trend statements
  use `stl_daily.trend` only, never `observed`.
- CUSUM (k = 0.5, h = 5) and EWMA (lambda = 0.2, L = 3) run on the STL
  residual in robust sigmas. `change_points.magnitude` is in TTI units.
- Before/after uses always-valid confidence sequences on STL-adjusted daily
  TTI, so `before_after` may be read every day. A fixed-horizon p-value may
  not be.

## Read API and frontend (P-04)

Vercel hosts the frontend (`web/`) and the read API (`api/`) and nothing
else. The collector, metrics, chain verification and exports run in GitHub
Actions (`.github/workflows/metrics.yml`).

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

Enforced by `web/src/lib/route.test.ts`, `web/src/lib/rules.test.ts` (no
waypoints, haversine, midpoints, via nodes or great-circle trigonometry
anywhere in `src/`) and `web/scripts/check-bundle.mjs` on the built bundle.
Pairs sharing endpoints is enforced by the `corridors_check_pair` trigger.

### Read API (`api/`)

- It selects precomputed rows and shapes JSON. It never computes a metric and
  never reads `samples`. `api/store.py` allowlists the readable tables, and a
  test asserts `samples` is never queried.
- It needs only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`, and refuses to
  start if `SUPABASE_SERVICE_KEY` is present.
- Every response, errors included, carries `as_of` and `missingness_rate`.
- Data responses are `Cache-Control: public, max-age=0, s-maxage=3600,
  stale-while-revalidate=86400`. `/api/health` and errors are `no-store`.
- `api/pyproject.toml` is FastAPI only, with `default-groups = []`, so a
  deploy build installs no dev tools. numpy and pandas never go in. If cold
  starts or bundle size become a problem, stop and tell Sahil.
- `/api/verify` serves the latest chain walk, which `python -m metrics verify`
  records nightly. Walking the chain reads every sample, so it never runs on
  the read path.
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
