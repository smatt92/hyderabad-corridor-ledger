-- 0007_audit_synthetic_control.sql
--
-- The intervention audit's headline is a synthetic control again, on pooled
-- BTI, with published donor weights, placebo runs, the equal-weight estimator
-- as a cross-check, and an always-valid confidence sequence over completed
-- post-period blocks. metrics/audit.py describes the method.
--
-- intervention_audit from 0005 is derived and has never held a row, so it is
-- dropped and rebuilt rather than altered column by column. 0005 is applied
-- and is not edited. Derived tables are replaced wholesale on every backfill.

drop table public.intervention_audit;

create table public.intervention_audit (
  intervention_id       text primary key references public.interventions (id) on delete cascade,
  corridor_id           text not null references public.corridors (id),
  status                text not null check (status in (
                          'ok', 'insufficient_pre', 'post_pending', 'post_partial',
                          'insufficient_post', 'no_controls')),
  effective_day         date not null,
  settle_days           smallint not null,
  -- Every period boundary is recorded, settling included: none is inferred.
  pre_start             date not null,
  pre_end               date not null,
  settle_start          date not null,
  settle_end            date not null,
  post_start            date not null,
  post_end              date not null,
  block_days            smallint not null,
  pre_blocks            smallint not null,
  post_blocks           smallint not null,
  post_blocks_complete  smallint not null,
  n_pre                 integer not null,  -- pooled peak-hour calls, treated corridor
  n_post                integer not null,
  n_donors              integer not null,
  -- Synthetic control, the headline. Each BTI pooled once over its period.
  treated_pre           double precision,
  treated_post          double precision,
  synthetic_pre         double precision,
  synthetic_post        double precision,
  effect                double precision,  -- BTI units
  ci_low                double precision,  -- percentile bootstrap, weights fixed
  ci_high               double precision,
  pre_rmspe             double precision,  -- fit on the pre blocks
  post_rmspe            double precision,
  rmspe_ratio           double precision,
  -- Placebo runs on the donors.
  n_placebos            integer not null,
  placebo_p_value       double precision,
  placebo_extreme       boolean not null,
  placebo_verdict       text,
  -- Equal-weight cross-check over the same donors and periods.
  equal_control_pre     double precision,
  equal_control_post    double precision,
  equal_effect          double precision,
  equal_ci_low          double precision,
  equal_ci_high         double precision,
  estimator_gap         double precision,  -- effect - equal_effect
  estimators_disagree   boolean,
  -- Always-valid confidence sequence over completed post blocks, latest block.
  cs_blocks             integer,
  cs_mean               double precision,
  cs_low                double precision,
  cs_high               double precision,
  alpha                 double precision not null,
  resamples             integer not null,
  missing_rate          double precision,
  low_confidence        boolean not null,
  method_version        text not null,
  computed_at           timestamptz not null default now()
);

-- Every corridor considered as a donor: its weight, or why it was excluded.
create table public.audit_donors (
  intervention_id  text not null references public.interventions (id) on delete cascade,
  corridor_id      text not null references public.corridors (id),
  included         boolean not null,
  weight           double precision check (weight between 0 and 1),
  exclusion        text check (exclusion in (
                     'treated', 'same_pair', 'incomplete_pre', 'insufficient_post')),
  n_pre            integer not null,
  n_post           integer not null,
  pre_bti          double precision,
  post_bti         double precision,
  method_version   text not null,
  computed_at      timestamptz not null default now(),
  primary key (intervention_id, corridor_id),
  check (included = (exclusion is null)),
  check (included or weight is null)
);

-- The procedure rerun with each donor as the treated corridor.
create table public.audit_placebos (
  intervention_id  text not null references public.interventions (id) on delete cascade,
  corridor_id      text not null references public.corridors (id),
  effect           double precision,
  pre_rmspe        double precision,
  post_rmspe       double precision,
  rmspe_ratio      double precision,
  poor_pre_fit     boolean not null,
  weights          jsonb not null,
  method_version   text not null,
  computed_at      timestamptz not null default now(),
  primary key (intervention_id, corridor_id)
);

-- Treated and synthetic BTI per block, and the confidence sequence after each
-- completed post block.
create table public.audit_blocks (
  intervention_id  text not null references public.interventions (id) on delete cascade,
  period           text not null check (period in ('pre', 'post')),
  block            smallint not null,
  block_start      date not null,
  block_end        date not null,
  complete         boolean not null,
  n_treated        integer not null,
  treated_bti      double precision,
  synthetic_bti    double precision,
  gap              double precision,
  running_mean     double precision,
  cs_low           double precision,
  cs_high          double precision,
  method_version   text not null,
  computed_at      timestamptz not null default now(),
  primary key (intervention_id, period, block)
);

-- Row level security: public read, no public write, as in 0001.
do $$
declare
  t text;
begin
  foreach t in array array[
    'intervention_audit', 'audit_donors', 'audit_placebos', 'audit_blocks'
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
