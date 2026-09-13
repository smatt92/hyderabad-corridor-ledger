-- 0011_tomtom_responses.sql
--
-- The token bucket is a governor: it counts the calls this project makes and
-- cannot see TomTom's own count. TomTom documents no quota or rate-limit
-- response header, and returns 429 both for too many requests in a given time
-- and for exhausted usage limits (docs.tomtom.com, read 2026-09-14). So the
-- collector keeps every header TomTom sends on the first response of each run
-- and on every 403 and 429. If TomTom reports its own count anywhere, it is in
-- these rows, and the collector's meter can be checked against it.
--
-- Diagnostic, not the ledger: not hash-chained, never archived. About one row
-- per collector run that makes a call, a few dozen a day.

create table public.tomtom_responses (
  id             bigint generated always as identity primary key,
  collector_run  text not null references public.collector_runs (id),
  corridor_id    text not null references public.corridors (id),
  observed_at    timestamptz not null,
  attempt        smallint not null check (attempt between 1 and 10),
  http_status    smallint not null check (http_status between 100 and 599),
  reason         text not null
                 check (reason in ('first_response', 'status_403', 'status_429')),
  -- 429 only: qps when Retry-After asked for a wait of a minute or less,
  -- quota otherwise, including no Retry-After at all
  limit_kind     text check (limit_kind in ('qps', 'quota')),
  headers        jsonb not null
                 check (jsonb_typeof(headers) = 'object' and octet_length(headers::text) <= 8192),
  check (limit_kind is null or http_status = 429),
  check ((reason = 'first_response') = (http_status not in (403, 429)))
);

create index tomtom_responses_observed_at on public.tomtom_responses (observed_at);

-- A 429 that is not a short wait stops collection until 00:00 UTC. Later runs
-- that day measure nothing and say why.
alter table public.collector_runs
  add column skipped_quota integer not null default 0 check (skipped_quota >= 0),
  drop constraint collector_runs_outcome_check,
  add constraint collector_runs_outcome_check
    check (outcome in ('running', 'ok', 'failed', 'budget_exhausted', 'quota_exhausted'));

-- Row level security: public read, no public write, as in 0003.
alter table public.tomtom_responses enable row level security;
create policy tomtom_responses_public_read on public.tomtom_responses
  for select to anon, authenticated using (true);
revoke insert, update, delete, truncate, references, trigger on public.tomtom_responses
  from anon, authenticated;
revoke update, truncate on public.tomtom_responses from service_role;
