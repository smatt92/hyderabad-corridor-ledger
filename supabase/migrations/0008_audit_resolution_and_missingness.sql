-- 0008_audit_resolution_and_missingness.sql
--
-- What the intervention audit must publish beside its estimate so the
-- estimate is not read as more precise, or more representative, than it is.
--
-- Placebo resolution. With n placebos the smallest attainable permutation p is
-- 1 / (n + 1), so a p-value is published with the treated corridor's rank and
-- that floor, never bare.
--
-- Overfitting. With few pre blocks and many donors the weights can reproduce the
-- treated pre series exactly. The in-sample pre RMSPE is published beside a
-- leave-one-block-out RMSPE and the number of active donors.
--
-- Informative missingness in donor selection. Failed calls cluster at peak
-- hours on congested roads, so the corridors dropped for a thin pre block are
-- disproportionately the congested ones and the donor pool is not a random
-- sample of the network. Each audit publishes the excluded corridors' missing
-- rate and BTI beside the donors', and reruns the estimate under stricter and
-- looser completeness thresholds (audit_sensitivity).
--
-- No sequential test. The block confidence sequence from 0007 excluded zero on
-- 12-18% of no-effect panels at six pre blocks against a nominal 5%
-- (docs/audit_power.md). Its columns are dropped rather than left for a reader
-- to quote. The audit reports once, after the post period closes.
--
-- 0007 is applied and is not edited. The audit tables are derived and are
-- replaced wholesale on every backfill.

alter table public.intervention_audit
  add column cv_pre_rmspe               double precision,  -- leave-one-block-out
  add column overfit_ratio              double precision,  -- pre_rmspe / cv_pre_rmspe
  add column pre_fit_overfit            boolean,           -- overfit_ratio below audit_overfit_ratio
  add column n_active_donors            integer,           -- nonzero weights
  add column placebo_rank               integer,           -- 1 = largest post/pre RMSPE ratio
  add column placebo_p_floor            double precision,  -- 1 / (n_placebos + 1)
  add column n_excluded_incomplete_pre  integer not null default 0,
  add column included_pre_missing_rate  double precision,  -- mean over donors, peak hours
  add column excluded_pre_missing_rate  double precision,  -- mean over incomplete_pre exclusions
  add column included_pre_bti           double precision,
  add column excluded_pre_bti           double precision,
  add column sensitivity_min_effect     double precision,
  add column sensitivity_max_effect     double precision,
  add column sensitivity_material       boolean;           -- a variant outside the interval or of opposite sign

alter table public.intervention_audit
  drop column cs_blocks,
  drop column cs_mean,
  drop column cs_low,
  drop column cs_high;

alter table public.audit_blocks
  drop column running_mean,
  drop column cs_low,
  drop column cs_high;

alter table public.audit_placebos
  add column cv_pre_rmspe  double precision;

alter table public.audit_donors
  add column pre_missing_rate  double precision,          -- peak hours of the pre period
  add column short_pre_blocks  smallint not null default 0,
  add column min_pre_block_n   integer;

-- The estimate under each donor completeness threshold.
create table public.audit_sensitivity (
  intervention_id   text not null references public.interventions (id) on delete cascade,
  variant           text not null check (variant in (
                      'base', 'strict_125', 'strict_150', 'relaxed_one_block')),
  block_floor       integer not null,   -- calls every donor pre block must reach
  max_short_blocks  smallint not null,  -- pre blocks a donor may have below that
  status            text not null check (status in ('ok', 'no_controls', 'too_few_blocks')),
  n_donors          integer not null,
  n_fit_blocks      smallint not null,
  effect            double precision,
  ci_low            double precision,
  ci_high           double precision,
  equal_effect      double precision,
  placebo_rank      integer,
  n_placebos        integer,
  placebo_p_value   double precision,
  placebo_p_floor   double precision,
  method_version    text not null,
  computed_at       timestamptz not null default now(),
  primary key (intervention_id, variant)
);

alter table public.audit_sensitivity enable row level security;
create policy audit_sensitivity_public_read
  on public.audit_sensitivity for select to anon, authenticated using (true);
revoke insert, update, delete, truncate, references, trigger
  on public.audit_sensitivity from anon, authenticated;
