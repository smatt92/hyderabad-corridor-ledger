-- 0001_init.sql
--
-- Baseline schema: corridors, samples (hash-chained, append-only) and
-- metrics_daily.
--
-- Two properties are set here on purpose and must never be retrofitted:
--   1. RLS is enabled on every table before any row exists.
--   2. The samples hash chain is installed in the same migration that creates
--      samples, so it covers the first row ever written.
-- Later changes are new numbered migrations, never edits to this file.

-- Not exposed through the Data API. Holds functions and tables that anonymous
-- API callers have no business reaching.
create schema private;
revoke all on schema private from public;

-- corridors ------------------------------------------------------------------

create table public.corridors (
  id          text primary key check (id ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  name        text not null check (length(name) between 1 and 200),
  origin_lat  double precision not null check (origin_lat between -90 and 90),
  origin_lon  double precision not null check (origin_lon between -180 and 180),
  dest_lat    double precision not null check (dest_lat between -90 and 90),
  dest_lon    double precision not null check (dest_lon between -180 and 180),
  -- Corridor geometry comes from OSM as a GeoJSON LineString. TomTom route
  -- geometry is never requested or stored.
  osm_path    jsonb check (osm_path is null or osm_path ->> 'type' = 'LineString'),
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);

-- samples --------------------------------------------------------------------
--
-- One row per TomTom calculateRoute call (routeRepresentation=summaryOnly).
-- seq, inserted_at, raw_gz_sha256, prev_hash and row_hash are always set by the
-- chain trigger; values supplied by the client are overwritten.

create table public.samples (
  seq                       bigint primary key,
  corridor_id               text not null references public.corridors (id),
  requested_at              timestamptz not null,
  -- null when no HTTP response was received
  http_status               smallint check (http_status between 100 and 599),
  length_m                  integer,
  travel_time_s             integer,
  traffic_delay_s           integer,
  no_traffic_travel_time_s  integer,
  historic_travel_time_s    integer,
  -- Response body, gzip-compressed. The size cap is the storage budget's
  -- tripwire: a response that carries route geometry will not fit.
  raw_gz                    bytea not null
                            check (substring(raw_gz from 1 for 2) = '\x1f8b'::bytea)
                            check (octet_length(raw_gz) <= 4096),
  raw_gz_sha256             bytea not null check (octet_length(raw_gz_sha256) = 32),
  collector_run             text check (collector_run ~ '^[A-Za-z0-9._/-]{1,64}$'),
  collector_sha             text check (collector_sha ~ '^[0-9a-f]{40}$'),
  inserted_at               timestamptz not null,
  prev_hash                 bytea not null check (octet_length(prev_hash) = 32),
  row_hash                  bytea not null check (octet_length(row_hash) = 32)
);

create index samples_corridor_requested_at on public.samples (corridor_id, requested_at);

-- Canonical text of a row, hashed into the chain. Format v1:
--   fields joined by '|', NULL rendered as '', timestamps in UTC as
--   YYYY-MM-DDTHH:MM:SS.ffffffZ, raw_gz_sha256 as lowercase hex.
-- No field can contain '|' (see the column checks), so the encoding is
-- unambiguous. Any change to this function is a new format version.
create function public.samples_canonical(s public.samples)
returns text
language sql
stable
set search_path = ''
as $$
  select array_to_string(array[
    'v1',
    s.seq::text,
    s.corridor_id,
    to_char(s.requested_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    s.http_status::text,
    s.length_m::text,
    s.travel_time_s::text,
    s.traffic_delay_s::text,
    s.no_traffic_travel_time_s::text,
    s.historic_travel_time_s::text,
    encode(s.raw_gz_sha256, 'hex'),
    s.collector_run,
    s.collector_sha,
    to_char(s.inserted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ], '|', '')
$$;

create function public.samples_extend_chain()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  last_seq  bigint;
  last_hash bytea;
begin
  -- Serialise writers. The lock is held until commit, so the next writer's
  -- query below runs only once this row is visible to it.
  perform pg_advisory_xact_lock(hashtextextended('public.samples chain', 0));

  select s.seq, s.row_hash into last_seq, last_hash
    from public.samples s
   order by s.seq desc
   limit 1;

  new.seq           := coalesce(last_seq, 0) + 1;
  new.prev_hash     := coalesce(last_hash, decode(repeat('00', 32), 'hex'));
  new.inserted_at   := clock_timestamp();
  new.raw_gz_sha256 := sha256(new.raw_gz);
  new.row_hash      := sha256(new.prev_hash || convert_to(public.samples_canonical(new), 'UTF8'));
  return new;
end;
$$;

create trigger samples_extend_chain
  before insert on public.samples
  for each row execute function public.samples_extend_chain();

create function public.samples_append_only()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'samples is append-only: % is not allowed', tg_op
    using errcode = 'insufficient_privilege';
end;
$$;

create trigger samples_no_update_or_delete
  before update or delete on public.samples
  for each row execute function public.samples_append_only();

create trigger samples_no_truncate
  before truncate on public.samples
  for each statement execute function public.samples_append_only();

-- Every break in the chain, one row per problem. Empty result: chain intact.
-- In the private schema because it scans the whole table.
create function private.samples_chain_breaks()
returns table (seq bigint, problem text)
language sql
stable
set search_path = ''
as $$
  with ordered as (
    select s.seq, s.prev_hash, s.row_hash, s.raw_gz, s.raw_gz_sha256,
           public.samples_canonical(s) as canonical,
           lag(s.seq)      over (order by s.seq) as prev_seq,
           lag(s.row_hash) over (order by s.seq) as prev_row_hash
      from public.samples s
  )
  select o.seq, p.problem
    from ordered o
   cross join lateral (values
     (case when o.row_hash <> sha256(o.prev_hash || convert_to(o.canonical, 'UTF8'))
           then 'row_hash does not match row contents' end),
     (case when o.raw_gz_sha256 <> sha256(o.raw_gz)
           then 'raw_gz_sha256 does not match raw_gz' end),
     (case when o.prev_seq is not null and o.seq <> o.prev_seq + 1
           then 'seq gap before this row' end),
     (case when o.prev_row_hash is not null and o.prev_hash <> o.prev_row_hash
           then 'prev_hash does not link to the previous row' end),
     (case when o.prev_seq is null and o.seq = 1
                and o.prev_hash <> decode(repeat('00', 32), 'hex')
           then 'genesis prev_hash is not all zeros' end)
   ) as p (problem)
   where p.problem is not null
   order by o.seq
$$;

-- metrics_daily --------------------------------------------------------------

create table public.metrics_daily (
  corridor_id                   text not null references public.corridors (id),
  day                           date not null,  -- calendar day in Asia/Kolkata
  samples_total                 integer not null check (samples_total >= 0),
  samples_ok                    integer not null check (samples_ok between 0 and samples_total),
  travel_time_p50_s             integer,
  travel_time_p85_s             integer,
  no_traffic_travel_time_p50_s  integer,
  traffic_delay_p50_s           integer,
  method_version                text not null,
  computed_at                   timestamptz not null default now(),
  primary key (corridor_id, day)
);

-- Row level security ---------------------------------------------------------

alter table public.corridors     enable row level security;
alter table public.samples       enable row level security;
alter table public.metrics_daily enable row level security;

create policy corridors_public_read
  on public.corridors for select to anon, authenticated using (true);
create policy samples_public_read
  on public.samples for select to anon, authenticated using (true);
create policy metrics_daily_public_read
  on public.metrics_daily for select to anon, authenticated using (true);

-- RLS already denies writes: there is no write policy. Revoking the privileges
-- too means a policy added by mistake still grants nothing, and closes
-- TRUNCATE, which RLS does not cover. Writes come only from the service role.
revoke insert, update, delete, truncate, references, trigger
  on public.corridors, public.samples, public.metrics_daily
  from anon, authenticated;
