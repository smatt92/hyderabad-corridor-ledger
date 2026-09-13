-- 0010_corridor_verification_and_treatment.sql
--
-- Verified. Public sources give neighbourhood centroids, bus stops and metro
-- stations, not junction centres, and a corridor's coordinates are immutable
-- once it is measured (corridors_guard). A corridor may therefore leave draft
-- only once a person has verified its coordinates on satellite imagery.
-- collector/config.py refuses an unverified non-draft corridor in CI; this
-- constraint refuses it again in the database.
--
-- Treatment. Every corridor records whether its road is untreated, will be
-- treated, is under construction or has been treated. Anything but untreated
-- cites a work in config/interventions.yaml, whose sources CI checks. A donor
-- is a control and is always untreated. The intervention audit excludes a
-- corridor under construction (under_works) or treated from every donor pool.

alter table public.corridors
  add column verified boolean not null default false,
  add column treatment_status text not null default 'untreated'
    check (treatment_status in ('untreated', 'will_be_treated', 'under_construction', 'treated')),
  add column treatment_work text
    check (treatment_work ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  add constraint corridors_measured_only_when_verified
    check (verified or (status = 'draft' and not active)),
  add constraint corridors_treatment_cites_a_work
    check ((treatment_status = 'untreated') = (treatment_work is null)),
  add constraint corridors_donor_is_untreated
    check (class <> 'donor' or treatment_status = 'untreated');

alter table public.audit_donors
  drop constraint audit_donors_exclusion_check,
  add constraint audit_donors_exclusion_check
    check (exclusion in ('treated', 'under_works', 'same_pair', 'incomplete_pre',
                         'insufficient_post'));
