-- 0015_audit_ranked_placebo_floor.sql
--
-- An audit, and each of its sensitivity variants, is withheld when fewer placebos
-- are ranked than the donor floor (min_donors): status too_few_placebos, distinct
-- from too_few_donors so the two causes stay separable in the record. Donors are
-- what is available; ranked placebos are what the placebo rank uses. A placebo is
-- unranked when its leave-one-block-out pre-period error is zero, so its effect has
-- no scale, and with fewer than 19 ranked placebos a "not extreme" verdict would be
-- guaranteed by the design (docs/unranked_placebos.md).
--
-- n_donors and n_placebos already sit on every audit row; the comments say what each
-- counts, so a reader can see when they diverge.

alter table public.intervention_audit
  drop constraint intervention_audit_status_check,
  add constraint intervention_audit_status_check check (status in (
    'ok', 'insufficient_pre', 'post_pending', 'post_partial', 'insufficient_post',
    'no_controls', 'too_few_donors', 'too_few_placebos'));

alter table public.audit_sensitivity
  drop constraint audit_sensitivity_status_check,
  add constraint audit_sensitivity_status_check check (status in (
    'ok', 'no_controls', 'too_few_donors', 'too_few_placebos', 'too_few_blocks'));

comment on column public.intervention_audit.n_donors is
  'Usable donors: candidate corridors left after every exclusion.';
comment on column public.intervention_audit.n_placebos is
  'Ranked placebos: placebo runs whose standardised effect could be computed. 0 when no placebo was run; the status says why.';
comment on column public.audit_sensitivity.n_donors is
  'Usable donors in this variant''s pool.';
comment on column public.audit_sensitivity.n_placebos is
  'Ranked placebos in this variant; null when the variant was not estimated.';
