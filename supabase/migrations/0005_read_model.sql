-- 0005_read_model.sql
--
-- P-04 read model. The read API selects rows from these tables and from
-- corridors; it never reads samples and never computes. Everything derived
-- below is written by the metrics pipeline in GitHub Actions and replaced
-- wholesale on backfill.
--
-- Corridor declarations (code, class, pair_id, names, the corridors_check_pair
-- trigger) and the chain_verifications history both come from 0003_collector.

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

-- Row level security: public read, no public write, as in 0001 and 0004.
do $$
declare
  t text;
begin
  foreach t in array array[
    'dataset_stats', 'corridor_stats', 'metrics_day', 'profile_hourly',
    'heatmap_weekly', 'network_hourly', 'pair_advantage_hourly',
    'intervention_audit', 'export_manifest'
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
