-- 0014_audit_donor_floor.sql
--
-- An audit, and each of its sensitivity variants, is withheld below a published
-- floor of usable donors: status too_few_donors. With n placebos the smallest
-- attainable p is 1/(n+1), so 19 donors is the fewest at which a p of 0.05 can
-- exist. docs/donor_floor.md found, in simulation, that the rank also holds its
-- nominal 5% size from 19 usable donors up. min_donors records the floor each
-- audit was held to, so a reader never has to infer it.
--
-- Both tables are derived, replaced wholesale on every backfill, and hold no
-- rows, so min_donors can be not null.

alter table public.intervention_audit
  drop constraint intervention_audit_status_check,
  add constraint intervention_audit_status_check check (status in (
    'ok', 'insufficient_pre', 'post_pending', 'post_partial', 'insufficient_post',
    'no_controls', 'too_few_donors')),
  add column min_donors smallint not null;

alter table public.audit_sensitivity
  drop constraint audit_sensitivity_status_check,
  add constraint audit_sensitivity_status_check check (status in (
    'ok', 'no_controls', 'too_few_donors', 'too_few_blocks'));
