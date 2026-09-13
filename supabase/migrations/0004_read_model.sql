-- 0004_read_model.sql
--
-- P-04 read model. The read API selects rows from these tables and from
-- corridors; it never reads samples and never computes. Everything derived
-- below is written by the metrics pipeline in GitHub Actions and replaced
-- wholesale on backfill. chain_verifications is the exception: an
-- append-only history of chain walks.

-- Corridor declarations ------------------------------------------------------
--
-- A pair is one primary corridor and at most one declared alternate. Both
-- share origin and destination and are measured in their own right. A pair
-- that declares one corridor is valid; nothing downstream derives a second.

alter table public.corridors
  add column code             text unique check (code ~ '^[A-Z]{2}-[0-9]{2,4}$'),
  add column pair_id          text check (pair_id ~ '^[A-Z]{2}-[0-9]{2,4}$'),
  add column role             text check (role in ('primary', 'alternate')),
  add column origin_name      text check (length(origin_name) between 1 and 80),
  add column destination_name text check (length(destination_name) between 1 and 80),
  add constraint corridors_pair_role check ((pair_id is null) = (role is null));

create unique index corridors_pair_role_unique on public.corridors (pair_id, role);

create function public.corridors_check_pair()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.pair_id is null then
    return new;
  end if;
  if exists (
    select 1 from public.corridors c
     where c.pair_id = new.pair_id and c.id <> new.id
       and (c.origin_lat, c.origin_lon, c.dest_lat, c.dest_lon)
           is distinct from (new.origin_lat, new.origin_lon, new.dest_lat, new.dest_lon)
  ) then
    raise exception 'corridors in pair % must share origin and destination', new.pair_id;
  end if;
  if new.role = 'alternate' and not exists (
    select 1 from public.corridors c
     where c.pair_id = new.pair_id and c.role = 'primary' and c.id <> new.id
  ) then
    raise exception 'pair % declares an alternate before its primary', new.pair_id;
  end if;
  return new;
end;
$$;

create trigger corridors_check_pair
  before insert or update on public.corridors
  for each row execute function public.corridors_check_pair();

-- Derived columns on metrics_daily -------------------------------------------

alter table public.metrics_daily
  add column tti_tomtom_delta_wk  double precision,  -- vs same hour 7 days earlier
  add column tti_p5_delta_wk      double precision,
  add column tt_ratio_own_median  double precision;  -- tt_mean_s / own median at this hour

-- Derived read-model tables --------------------------------------------------

create table public.dataset_stats (
  id              text primary key check (id = 'window'),
  window_start    date not null,
  window_end      date not null,
  n_corridors     integer not null,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now()
);

create table public.corridor_stats (
  corridor_id     text primary key references public.corridors (id),
  window_start    date not null,
  window_end      date not null,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  length_meters   integer check (length_meters > 0),  -- measured by TomTom; null if none
  ff_tomtom_s     double precision,
  ff_p5_s         double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now()
);

create table public.metrics_day (
  corridor_id     text not null references public.corridors (id),
  day             date not null,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  tt_mean_s       double precision,
  tti_tomtom      double precision,
  tti_p5          double precision,
  bti             double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, day)
);

create table public.profile_hourly (
  corridor_id     text not null references public.corridors (id),
  hour            smallint not null check (hour between 0 and 23),
  window_start    date not null,
  window_end      date not null,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  tt_mean_s       double precision,
  tt_p50_s        double precision,
  tt_p95_s        double precision,
  bti             double precision,
  tti_tomtom_p25  double precision,
  tti_tomtom_p50  double precision,
  tti_tomtom_p75  double precision,
  tti_tomtom_p95  double precision,
  tti_p5_p25      double precision,
  tti_p5_p50      double precision,
  tti_p5_p75      double precision,
  tti_p5_p95      double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, hour)
);

create table public.heatmap_weekly (
  scope           text not null check (scope in ('corridor', 'network')),
  corridor_id     text references public.corridors (id),
  dow             smallint not null check (dow between 0 and 6),  -- 0 = Sunday
  hour            smallint not null check (hour between 0 and 23),
  window_start    date not null,
  window_end      date not null,
  n_days          integer not null,
  tti_tomtom_p50  double precision,  -- null below the minimum day count
  tti_p5_p50      double precision,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  check ((scope = 'network') = (corridor_id is null))
);

create unique index heatmap_weekly_key
  on public.heatmap_weekly (scope, coalesce(corridor_id, ''), dow, hour);

create table public.network_hourly (
  day             date not null,
  hour            smallint not null check (hour between 0 and 23),
  n_corridors     integer not null,  -- corridors with a baseline at this hour
  tt_ratio_p50    double precision,
  pct_vs_normal   double precision,
  state           text check (state in ('worse', 'normal', 'better')),
  tti_tomtom_p50  double precision,
  tti_p5_p50      double precision,
  n_expected      integer not null,
  n_ok            integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (day, hour)
);

-- Only pairs that declare an alternate have rows: a one-corridor pair has
-- nothing to compare and that is not an error.
create table public.pair_advantage_hourly (
  pair_id            text not null,
  hour               smallint not null check (hour between 0 and 23),
  primary_id         text not null references public.corridors (id),
  alternate_id       text not null references public.corridors (id),
  primary_tt_p95_s   double precision,
  alternate_tt_p95_s double precision,
  advantage_p95_s    double precision,  -- primary minus alternate; > 0 favours the alternate
  low_confidence     boolean not null,
  method_version     text not null,
  computed_at        timestamptz not null default now(),
  primary key (pair_id, hour)
);

create table public.intervention_audit (
  intervention_id text primary key references public.interventions (id) on delete cascade,
  corridor_id     text not null references public.corridors (id),
  status          text not null check (status in ('ok', 'insufficient_pre', 'no_controls', 'no_post')),
  effective_day   date not null,
  settle_days     smallint not null,
  pre_start       date,
  pre_end         date,
  post_start      date,
  post_end        date,
  n_pre           integer not null,
  n_post          integer not null,
  n_controls      integer not null,
  treated_pre     double precision,
  treated_post    double precision,
  synthetic_pre   double precision,
  synthetic_post  double precision,
  effect          double precision,  -- treated_post - synthetic_post, BTI units
  cs_low          double precision,  -- always-valid confidence sequence on the effect
  cs_high         double precision,
  alpha           double precision not null,
  pre_rmse        double precision,
  weights         jsonb not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now()
);

-- Chain verification history -------------------------------------------------
--
-- Walking the chain reads every sample, so it never runs on the read path.
-- A scheduled job calls record_chain_verification() with the service key;
-- /verify serves the latest row.

create table public.chain_verifications (
  id               bigint generated always as identity primary key,
  verified_at      timestamptz not null default now(),
  rows_checked     bigint not null,
  first_seq        bigint,
  head_seq         bigint,
  head_row_hash    text check (head_row_hash ~ '^[0-9a-f]{64}$'),
  breaks           integer not null,
  first_break_seq  bigint,
  ok               boolean not null
);

create function public.record_chain_verification()
returns public.chain_verifications
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.chain_verifications;
begin
  insert into public.chain_verifications
    (rows_checked, first_seq, head_seq, head_row_hash, breaks, first_break_seq, ok)
  select s.n, s.first_seq, s.head_seq,
         (select encode(x.row_hash, 'hex') from public.samples x order by x.seq desc limit 1),
         b.n, b.first_break, b.n = 0
    from (select count(*) as n, min(seq) as first_seq, max(seq) as head_seq
            from public.samples) s,
         (select count(*)::integer as n, min(seq) as first_break
            from private.samples_chain_breaks()) b
  returning * into result;
  return result;
end;
$$;

revoke execute on function public.record_chain_verification() from public, anon, authenticated;
grant execute on function public.record_chain_verification() to service_role;

-- Open dataset exports -------------------------------------------------------
--
-- Files are written to the public exports bucket by the metrics workflow.
-- The manifest records what each file is, so /export.* can redirect to it
-- with its as_of, missingness and checksum.

insert into storage.buckets (id, name, public, file_size_limit)
values ('exports', 'exports', true, 52428800)
on conflict (id) do nothing;

create table public.export_manifest (
  format          text primary key check (format in ('csv', 'parquet')),
  object_path     text not null check (object_path ~ '^[a-z0-9][a-z0-9._/-]{1,200}$'),
  window_start    date not null,
  window_end      date not null,
  n_rows          bigint not null,
  n_bytes         bigint not null,
  sha256          text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  missing_rate    double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now()
);

-- Row level security: public read, no public write, as in 0001 and 0003.
do $$
declare
  t text;
begin
  foreach t in array array[
    'dataset_stats', 'corridor_stats', 'metrics_day', 'profile_hourly',
    'heatmap_weekly', 'network_hourly', 'pair_advantage_hourly',
    'intervention_audit', 'chain_verifications', 'export_manifest'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy %I on public.%I for select to anon, authenticated using (true)',
      t || '_public_read', t);
    execute format(
      'revoke insert, update, delete, truncate, references, trigger on public.%I '
      'from anon, authenticated', t);
  end loop;
end;
$$;
