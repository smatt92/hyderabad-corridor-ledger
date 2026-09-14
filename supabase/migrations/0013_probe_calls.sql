-- 0013_probe_calls.sql
--
-- Probe mode (collector/probe.py) measures how often TomTom calls fail at the
-- collector's real cadence, because every panel-sizing table in
-- docs/free_tier.md turns on that rate and nobody has measured it. It keeps only
-- what each attempt was: which corridor, when, the attempt number, the HTTP status
-- and the latency to the response headers. The response body is never read, so
-- no travel time, distance or geometry is stored. That a status code is not a
-- Result under clause 11.4 of TomTom's Terms is Sahil's reading, not legal advice,
-- and is being put to TomTom.

create table public.probe_calls (
  id            bigint generated always as identity primary key,
  corridor_id   text not null references public.corridors (id),
  requested_at  timestamptz not null,
  attempt       smallint not null check (attempt between 1 and 3),
  -- null: no response arrived (a timeout or a connection failure)
  http_status   smallint check (http_status between 100 and 599),
  latency_ms    integer not null check (latency_ms between 0 and 600000),
  unique (corridor_id, requested_at)
);

create index probe_calls_requested_at on public.probe_calls (requested_at);

-- Row level security: public read, no public write. The rows are the evidence for a
-- failure rate, so the service role cannot rewrite or remove them either.
alter table public.probe_calls enable row level security;
create policy probe_calls_public_read on public.probe_calls
  for select to anon, authenticated using (true);
revoke insert, update, delete, truncate, references, trigger on public.probe_calls
  from anon, authenticated;
revoke update, delete, truncate on public.probe_calls from service_role;
