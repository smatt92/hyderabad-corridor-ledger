-- 0003_metrics_engine.sql
--
-- Tables for the P-02 metrics engine. Everything here except interventions
-- is derived from raw samples and disposable: backfill deletes and rebuilds
-- it. RLS on, public read, no public write, exactly as in 0001.

-- metrics_daily held no rows and had a per-day grain. P-02 publishes one row
-- per corridor per local hour, so it is rebuilt rather than altered.
drop table public.metrics_daily;

-- Seconds between scheduled calls for a corridor: the missingness
-- denominator. Null means only attempted calls count, which cannot see a
-- collector run that never started.
alter table public.corridors
  add column cadence_s integer check (cadence_s > 0);

-- Input, not derived: before/after comparisons are made around these.
create table public.interventions (
  id            text primary key check (id ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  corridor_id   text not null references public.corridors (id),
  effective_at  timestamptz not null,
  description   text not null check (length(description) between 1 and 500),
  created_at    timestamptz not null default now()
);

-- Per corridor, per local (Asia/Kolkata) hour. Both free-flow bases are kept
-- side by side and never collapsed.
create table public.metrics_daily (
  corridor_id     text not null references public.corridors (id),
  day             date not null,
  hour            smallint not null check (hour between 0 and 23),
  n_expected      integer not null check (n_expected >= 0),
  n_attempted     integer not null check (n_attempted >= 0),
  n_ok            integer not null check (n_ok >= 0),
  missing_rate    double precision,
  low_confidence  boolean not null,
  tt_mean_s       double precision,
  tt_p95_s        double precision,
  ff_tomtom_s     double precision,
  ff_p5_s         double precision,
  tti_tomtom      double precision,
  tti_p5          double precision,
  bti             double precision,
  pti_tomtom      double precision,
  pti_p5          double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, day, hour)
);

create table public.worst15_daily (
  corridor_id     text not null references public.corridors (id),
  day             date not null,
  basis           text not null check (basis in ('tomtom', 'p5')),
  window_start    timestamptz,
  window_end      timestamptz,
  tti             double precision,
  n_samples       integer not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, basis, day)
);

create table public.corridor_rankings (
  window_end      date not null,
  window_days     smallint not null,
  index_name      text not null,
  corridor_id     text not null references public.corridors (id),
  n               integer not null,
  raw             double precision,
  shrunk          double precision,
  city_mean       double precision,
  rank            integer,  -- 1 = worst, ranked on shrunk
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (window_end, index_name, corridor_id)
);

create table public.stl_daily (
  corridor_id     text not null references public.corridors (id),
  basis           text not null check (basis in ('tomtom', 'p5')),
  day             date not null,
  segment_start   date not null,
  observed        double precision not null,
  trend           double precision not null,
  seasonal        double precision not null,
  resid           double precision not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, basis, day)
);

create table public.change_points (
  corridor_id     text not null references public.corridors (id),
  basis           text not null check (basis in ('tomtom', 'p5')),
  chart           text not null check (chart in ('cusum', 'ewma')),
  detected_at     date not null,
  direction       text not null check (direction in ('up', 'down')),
  magnitude       double precision not null,  -- estimated shift, TTI units
  statistic       double precision not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, basis, chart, detected_at, direction)
);

-- One row per corridor, basis and day whose peak TTI reached the threshold.
-- cleared = false is a right-censored duration, never a missing one.
create table public.recovery_events (
  corridor_id     text not null references public.corridors (id),
  basis           text not null check (basis in ('tomtom', 'p5')),
  day             date not null,
  peak_at         timestamptz not null,
  peak_tti        double precision not null,
  duration_min    double precision not null check (duration_min >= 0),
  cleared         boolean not null,
  censor_reason   text check (
                    (cleared and censor_reason is null)
                    or (not cleared and censor_reason in ('window_end', 'data_gap'))),
  is_weekend      boolean not null,
  missing_rate    double precision,
  low_confidence  boolean not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, basis, day)
);

create table public.recovery_km (
  corridor_id     text not null references public.corridors (id),
  basis           text not null check (basis in ('tomtom', 'p5')),
  t_min           double precision not null,
  n_at_risk       integer not null,
  n_events        integer not null,
  n_censored      integer not null,
  survival        double precision not null,
  se              double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (corridor_id, basis, t_min)
);

create table public.recovery_cox (
  basis           text not null check (basis in ('tomtom', 'p5')),
  covariate       text not null,
  n_obs           integer not null,
  n_events        integer not null,
  coef            double precision,
  hazard_ratio    double precision,
  se              double precision,
  p_value         double precision,
  ci_low          double precision,
  ci_high         double precision,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (basis, covariate)
);

create table public.before_after (
  intervention_id text not null references public.interventions (id) on delete cascade,
  basis           text not null check (basis in ('tomtom', 'p5')),
  as_of           date not null,
  n_before        integer not null,
  n_after         integer not null,
  mean_before     double precision,
  mean_after      double precision,
  diff            double precision,
  cs_low          double precision,  -- always-valid: may be read every day
  cs_high         double precision,
  alpha           double precision not null,
  method_version  text not null,
  computed_at     timestamptz not null default now(),
  primary key (intervention_id, basis, as_of)
);

-- Row level security: public read, no public write. Privileges are revoked as
-- well as denied by RLS, as in 0001.
do $$
declare
  t text;
begin
  foreach t in array array[
    'interventions', 'metrics_daily', 'worst15_daily', 'corridor_rankings',
    'stl_daily', 'change_points', 'recovery_events', 'recovery_km',
    'recovery_cox', 'before_after'
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
