-- 0009_no_ledger_intervals.sql
--
-- The ledger, profile and route-comparison intervals are withdrawn. Each was a
-- percentile bootstrap that resampled single calls, as if calls from the same
-- day and the same week were independent. They are not: a city-wide shock moves
-- every corridor on the same day, and each corridor drifts from week to week. In
-- simulation (docs/ledger_intervals.md, 400 panels per scenario and tier) the
-- ledger's p95 travel time and PTI intervals covered their true value in 68-84%
-- of panels at the model's default correlation and 41-58% with weekly drift of
-- 0.20, and the pair advantage interval excluded zero on 10-20% of panels whose
-- two corridors were identical. The same construction failed for the
-- intervention audit (0008). Point values stay, each beside its pooled count,
-- and no interval replaces them; no gate is attempted.
--
-- 0005 is applied and is not edited. These tables are derived and are replaced
-- wholesale on every backfill.

alter table public.corridor_stats
  drop column tt_p95_peak_ci_low,
  drop column tt_p95_peak_ci_high,
  drop column bti_peak_ci_low,
  drop column bti_peak_ci_high,
  drop column pti_tomtom_peak_ci_low,
  drop column pti_tomtom_peak_ci_high,
  drop column pti_p5_peak_ci_low,
  drop column pti_p5_peak_ci_high;

alter table public.profile_hourly
  drop column tt_p95_ci_low,
  drop column tt_p95_ci_high,
  drop column bti_ci_low,
  drop column bti_ci_high,
  drop column tti_tomtom_p95_ci_low,
  drop column tti_tomtom_p95_ci_high,
  drop column tti_p5_p95_ci_low,
  drop column tti_p5_p95_ci_high;

alter table public.pair_advantage_hourly
  drop column advantage_ci_low,
  drop column advantage_ci_high;

-- the resample count described intervals that no longer exist
alter table public.dataset_stats
  drop column bootstrap_resamples;
