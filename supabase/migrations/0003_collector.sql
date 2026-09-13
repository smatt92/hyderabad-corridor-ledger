-- 0003_collector.sql
--
-- P-01 collector schema. Applied before the collector's first run, so every
-- guarantee here covers the first genuine row.
--
--   corridors            declarations, synced from config/corridors.yaml
--   samples              one successful call per corridor per scheduled slot
--   failed_samples       a slot whose attempts all failed; never dropped
--   collector_runs       one row per dispatcher run
--   gap_reports          expected against recorded slots, per corridor per day
--   sample_archives      verified Parquet archives; the only path to pruning
--   chain_verifications  nightly walks of both hash chains
--
-- Chain format v1 from 0001 is unchanged. The columns this migration adds to
-- samples (scheduled_slot, attempts) sit outside that format; UPDATE on
-- samples is impossible, which is what protects them. failed_samples gets a
-- chain of its own, format f1.

-- Corridor declarations -------------------------------------------------------

alter table public.corridors
  add column code             text unique check (code ~ '^[A-Z]{2}-[0-9]{2,4}$'),
  add column class            text check (class in ('core', 'alternate', 'donor')),
  add column tier             text check (tier in ('A', 'B', 'C')),
  add column direction        text check (direction in ('ab', 'ba')),
  add column pair_id          text check (pair_id ~ '^[A-Z]{2}-[0-9]{2,4}$'),
  add column origin_name      text check (length(origin_name) between 1 and 80),
  add column destination_name text check (length(destination_name) between 1 and 80),
  add column via              jsonb check (jsonb_typeof(via) = 'array'),
  add column status           text check (status in ('draft', 'active', 'paused', 'retired')),
  add column supersedes       text references public.corridors (id),
  add column activated_at     timestamptz;  -- set when first non-draft; geometry frozen from then

-- corridors is empty, so these hold for every row that will ever exist.
alter table public.corridors
  alter column class set not null,
  alter column tier set not null,
  alter column direction set not null,
  alter column via set not null,
  alter column status set not null,
  add constraint corridors_active_is_status check (active = (status = 'active')),
  add constraint corridors_alternate_is_pinned
    check (class <> 'alternate' or (pair_id is not null and jsonb_array_length(via) > 0)),
  add constraint corridors_donor_unpaired check (class <> 'donor' or pair_id is null),
  add constraint corridors_not_self_superseding check (supersedes is null or supersedes <> id);

-- One core and at most one alternate per pair and direction. A pair holding
-- one corridor is valid: it means no measured alternate.
create unique index corridors_pair_member
  on public.corridors (pair_id, direction, class) where pair_id is not null;

create function public.corridors_check_pair()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.pair_id is null then
    return new;
  end if;
  if exists (
    select 1 from public.corridors c
     where c.pair_id = new.pair_id and c.id <> new.id and c.direction = new.direction
       and (c.origin_lat, c.origin_lon, c.dest_lat, c.dest_lon)
           is distinct from (new.origin_lat, new.origin_lon, new.dest_lat, new.dest_lon)
  ) then
    raise exception 'corridors in pair % direction % must share origin and destination',
      new.pair_id, new.direction;
  end if;
  if exists (
    select 1 from public.corridors c
     where c.pair_id = new.pair_id and c.id <> new.id and c.direction <> new.direction
       and (c.origin_lat, c.origin_lon, c.dest_lat, c.dest_lon)
           is distinct from (new.dest_lat, new.dest_lon, new.origin_lat, new.origin_lon)
  ) then
    raise exception 'pair % direction % must reverse the other direction', new.pair_id, new.direction;
  end if;
  if new.class = 'alternate' and not exists (
    select 1 from public.corridors c
     where c.pair_id = new.pair_id and c.direction = new.direction and c.class = 'core'
       and c.id <> new.id
  ) then
    raise exception 'alternate % needs the core corridor of pair % declared first', new.id, new.pair_id;
  end if;
  return new;
end;
$$;

create trigger corridors_check_pair
  before insert or update on public.corridors
  for each row execute function public.corridors_check_pair();

-- Once a corridor has been anything but a draft, its geometry is permanent and
-- it cannot be deleted: retire it and declare a new id that supersedes it.
create function public.corridors_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    if old.activated_at is not null then
      raise exception 'corridor % has been active; retire it instead of deleting it', old.id
        using errcode = 'insufficient_privilege';
    end if;
    return old;
  end if;
  if tg_op = 'INSERT' then
    new.activated_at := case when new.status <> 'draft' then now() end;
    return new;
  end if;
  if new.id <> old.id then
    raise exception 'corridor ids are permanent' using errcode = 'insufficient_privilege';
  end if;
  new.activated_at := coalesce(old.activated_at, case when new.status <> 'draft' then now() end);
  if old.activated_at is not null
     and (new.origin_lat, new.origin_lon, new.dest_lat, new.dest_lon, new.via, new.direction)
         is distinct from (old.origin_lat, old.origin_lon, old.dest_lat, old.dest_lon, old.via, old.direction)
  then
    raise exception 'corridor % has been active; its geometry is permanent', old.id
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;

create trigger corridors_guard
  before insert or update or delete on public.corridors
  for each row execute function public.corridors_guard();

-- Append-only guard, shared --------------------------------------------------
--
-- UPDATE and TRUNCATE always raise. DELETE raises unless the transaction is
-- inside public.prune_archived(), which removes only rows a verified archive
-- already holds.

create function public.ledger_append_only()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' and current_setting('ledger.prune', true) = 'on' then
    return old;
  end if;
  raise exception '% is append-only: % is not allowed', tg_table_name, tg_op
    using errcode = 'insufficient_privilege';
end;
$$;

drop trigger samples_no_update_or_delete on public.samples;
drop trigger samples_no_truncate on public.samples;
drop function public.samples_append_only();

create trigger samples_no_update_or_delete
  before update or delete on public.samples
  for each row execute function public.ledger_append_only();

create trigger samples_no_truncate
  before truncate on public.samples
  for each statement execute function public.ledger_append_only();

-- Samples: idempotency and budget accounting ---------------------------------

alter table public.samples
  add column scheduled_slot timestamptz not null,
  add column attempts       smallint not null check (attempts between 1 and 10),
  add constraint samples_measured_at_slot
    check (requested_at >= scheduled_slot - interval '1 minute'
           and requested_at < scheduled_slot + interval '1 hour');

-- A retry after a timeout must never create a second row for the same slot:
-- duplicates would silently corrupt every percentile.
create unique index samples_corridor_slot on public.samples (corridor_id, scheduled_slot);
create index samples_requested_at on public.samples (requested_at);

-- Failed samples -------------------------------------------------------------

create table public.failed_samples (
  seq               bigint primary key,
  corridor_id       text not null references public.corridors (id),
  scheduled_slot    timestamptz not null,
  requested_at      timestamptz not null,  -- first attempt
  attempts          smallint not null check (attempts between 1 and 10),
  error_class       text not null check (error_class ~ '^[A-Za-z0-9_]{1,40}$'),
  http_status       smallint check (http_status between 100 and 599),
  detail_gz         bytea
                    check (detail_gz is null or substring(detail_gz from 1 for 2) = '\x1f8b'::bytea)
                    check (detail_gz is null or octet_length(detail_gz) <= 4096),
  detail_gz_sha256  bytea check (detail_gz_sha256 is null or octet_length(detail_gz_sha256) = 32),
  collector_run     text check (collector_run ~ '^[A-Za-z0-9._/-]{1,64}$'),
  collector_sha     text check (collector_sha ~ '^[0-9a-f]{40}$'),
  inserted_at       timestamptz not null,
  prev_hash         bytea not null check (octet_length(prev_hash) = 32),
  row_hash          bytea not null check (octet_length(row_hash) = 32),
  check (requested_at >= scheduled_slot - interval '1 minute'
         and requested_at < scheduled_slot + interval '1 hour')
);

create unique index failed_samples_corridor_slot on public.failed_samples (corridor_id, scheduled_slot);
create index failed_samples_requested_at on public.failed_samples (requested_at);

-- Canonical text for chain format f1: fields joined by '|', NULL as '',
-- timestamps UTC YYYY-MM-DDTHH:MM:SS.ffffffZ, hashes lowercase hex.
create function public.failed_samples_canonical(f public.failed_samples)
returns text
language sql
stable
set search_path = ''
as $$
  select array_to_string(array[
    'f1',
    f.seq::text,
    f.corridor_id,
    to_char(f.scheduled_slot at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    to_char(f.requested_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    f.attempts::text,
    f.error_class,
    f.http_status::text,
    encode(f.detail_gz_sha256, 'hex'),
    f.collector_run,
    f.collector_sha,
    to_char(f.inserted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  ], '|', '')
$$;

create function public.failed_samples_extend_chain()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  last_seq  bigint;
  last_hash bytea;
begin
  perform pg_advisory_xact_lock(hashtextextended('public.failed_samples chain', 0));
  select f.seq, f.row_hash into last_seq, last_hash
    from public.failed_samples f
   order by f.seq desc
   limit 1;
  new.seq              := coalesce(last_seq, 0) + 1;
  new.prev_hash        := coalesce(last_hash, decode(repeat('00', 32), 'hex'));
  new.inserted_at      := clock_timestamp();
  new.detail_gz_sha256 := case when new.detail_gz is null then null else sha256(new.detail_gz) end;
  new.row_hash         := sha256(new.prev_hash || convert_to(public.failed_samples_canonical(new), 'UTF8'));
  return new;
end;
$$;

create trigger failed_samples_extend_chain
  before insert on public.failed_samples
  for each row execute function public.failed_samples_extend_chain();

create trigger failed_samples_no_update_or_delete
  before update or delete on public.failed_samples
  for each row execute function public.ledger_append_only();

create trigger failed_samples_no_truncate
  before truncate on public.failed_samples
  for each statement execute function public.ledger_append_only();

-- A slot has exactly one outcome: a sample or a failure, never both.
create function public.ledger_one_outcome_per_slot()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(
    'ledger slot ' || new.corridor_id || ' ' || extract(epoch from new.scheduled_slot)::text, 0));
  if tg_table_name = 'samples' and exists (
    select 1 from public.failed_samples f
     where f.corridor_id = new.corridor_id and f.scheduled_slot = new.scheduled_slot
  ) then
    raise exception 'slot % of % is already recorded as failed', new.scheduled_slot, new.corridor_id;
  end if;
  if tg_table_name = 'failed_samples' and exists (
    select 1 from public.samples s
     where s.corridor_id = new.corridor_id and s.scheduled_slot = new.scheduled_slot
  ) then
    raise exception 'slot % of % already has a sample', new.scheduled_slot, new.corridor_id;
  end if;
  return new;
end;
$$;

create trigger samples_one_outcome_per_slot
  before insert on public.samples
  for each row execute function public.ledger_one_outcome_per_slot();

create trigger failed_samples_one_outcome_per_slot
  before insert on public.failed_samples
  for each row execute function public.ledger_one_outcome_per_slot();

-- Runs and gaps ----------------------------------------------------------------

create table public.collector_runs (
  id                text primary key check (id ~ '^[A-Za-z0-9._/-]{1,64}$'),
  collector_sha     text check (collector_sha ~ '^[0-9a-f]{40}$'),
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  outcome           text not null default 'running'
                    check (outcome in ('running', 'ok', 'failed', 'budget_exhausted')),
  slots_due         integer not null default 0 check (slots_due >= 0),
  recorded          integer not null default 0 check (recorded >= 0),
  failed            integer not null default 0 check (failed >= 0),
  skipped_existing  integer not null default 0 check (skipped_existing >= 0),
  skipped_budget    integer not null default 0 check (skipped_budget >= 0),
  attempts          integer not null default 0 check (attempts >= 0),
  detail            text check (length(detail) <= 2000)
);

create index collector_runs_started_at on public.collector_runs (started_at);

create table public.gap_reports (
  day          date not null,  -- IST calendar day
  corridor_id  text not null references public.corridors (id),
  tier         text not null check (tier in ('A', 'B', 'C')),
  expected     integer not null check (expected >= 0),
  recorded     integer not null check (recorded >= 0),
  failed       integer not null check (failed >= 0),
  missing      integer not null check (missing = greatest(expected - recorded - failed, 0)),
  checked_at   timestamptz not null default now(),
  primary key (day, corridor_id)
);

-- Archives and pruning -------------------------------------------------------

create table public.sample_archives (
  id                bigint generated always as identity primary key,
  table_name        text not null check (table_name in ('samples', 'failed_samples')),
  first_seq         bigint not null check (first_seq >= 1),
  last_seq          bigint not null,
  row_count         bigint not null,
  requested_before  timestamptz not null,  -- every archived row was requested before this
  object_path       text not null unique check (object_path ~ '^[a-z0-9][a-z0-9._/-]{1,200}$'),
  n_bytes           bigint not null check (n_bytes > 0),
  sha256            text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  last_row_hash     text not null check (last_row_hash ~ '^[0-9a-f]{64}$'),
  verified_at       timestamptz not null,  -- read back and chain-checked before this row exists
  pruned_at         timestamptz,
  created_at        timestamptz not null default now(),
  check (last_seq >= first_seq),
  check (row_count = last_seq - first_seq + 1),
  unique (table_name, first_seq)
);

-- Archives of a table are contiguous: each starts where the last one ended.
create function public.sample_archives_contiguous()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  next_seq bigint;
begin
  select coalesce(max(a.last_seq), 0) + 1 into next_seq
    from public.sample_archives a
   where a.table_name = new.table_name;
  if new.first_seq <> next_seq then
    raise exception 'an archive of % must start at seq %, not %', new.table_name, next_seq, new.first_seq;
  end if;
  new.pruned_at := null;
  return new;
end;
$$;

create trigger sample_archives_contiguous
  before insert on public.sample_archives
  for each row execute function public.sample_archives_contiguous();

-- The only way a row ever leaves samples or failed_samples.
create function public.prune_archived(archive_id bigint)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  a public.sample_archives;
  retained_min bigint;
  in_range bigint;
  too_recent boolean;
  boundary_hash text;
  deleted bigint;
begin
  select * into a from public.sample_archives where id = archive_id for update;
  if not found then
    raise exception 'no archive %', archive_id;
  end if;
  if a.pruned_at is not null then
    raise exception 'archive % is already pruned', archive_id;
  end if;
  if a.requested_before > now() - interval '90 days' then
    raise exception 'archive % reaches inside the 90-day hot window', archive_id;
  end if;

  -- The newest row always stays in the hot table: the chain trigger finds its
  -- head there, so emptying the table would restart the chain at seq 1.
  if a.last_seq >= (case when a.table_name = 'samples'
                         then (select max(seq) from public.samples)
                         else (select max(seq) from public.failed_samples) end) then
    raise exception 'archive % would remove the newest row; the chain head stays in the table', archive_id;
  end if;

  if a.table_name = 'samples' then
    select min(seq) into retained_min from public.samples;
    select count(*), bool_or(requested_at >= a.requested_before) into in_range, too_recent
      from public.samples where seq between a.first_seq and a.last_seq;
    select encode(row_hash, 'hex') into boundary_hash from public.samples where seq = a.last_seq;
  else
    select min(seq) into retained_min from public.failed_samples;
    select count(*), bool_or(requested_at >= a.requested_before) into in_range, too_recent
      from public.failed_samples where seq between a.first_seq and a.last_seq;
    select encode(row_hash, 'hex') into boundary_hash from public.failed_samples where seq = a.last_seq;
  end if;

  if retained_min is distinct from a.first_seq then
    raise exception 'archive % does not start at the oldest retained row', archive_id;
  end if;
  if in_range <> a.row_count or too_recent then
    raise exception 'archive % does not match the rows it claims to hold', archive_id;
  end if;
  if boundary_hash is distinct from a.last_row_hash then
    raise exception 'archive % last_row_hash does not match the table', archive_id;
  end if;

  perform set_config('ledger.prune', 'on', true);
  if a.table_name = 'samples' then
    delete from public.samples where seq between a.first_seq and a.last_seq;
  else
    delete from public.failed_samples where seq between a.first_seq and a.last_seq;
  end if;
  get diagnostics deleted = row_count;
  perform set_config('ledger.prune', 'off', true);

  update public.sample_archives set pruned_at = now() where id = archive_id;
  return deleted;
end;
$$;

-- Chain verification ---------------------------------------------------------

create function private.failed_samples_chain_breaks()
returns table (seq bigint, problem text)
language sql
stable
set search_path = ''
as $$
  with ordered as (
    select f.seq, f.prev_hash, f.row_hash, f.detail_gz, f.detail_gz_sha256,
           public.failed_samples_canonical(f) as canonical,
           lag(f.seq)      over (order by f.seq) as prev_seq,
           lag(f.row_hash) over (order by f.seq) as prev_row_hash
      from public.failed_samples f
  )
  select o.seq, p.problem
    from ordered o
   cross join lateral (values
     (case when o.row_hash <> sha256(o.prev_hash || convert_to(o.canonical, 'UTF8'))
           then 'row_hash does not match row contents' end),
     (case when o.detail_gz_sha256 is distinct from
                (case when o.detail_gz is null then null else sha256(o.detail_gz) end)
           then 'detail_gz_sha256 does not match detail_gz' end),
     (case when o.prev_seq is not null and o.seq <> o.prev_seq + 1
           then 'seq gap before this row' end),
     (case when o.prev_row_hash is not null and o.prev_hash <> o.prev_row_hash
           then 'prev_hash does not link to the previous row' end),
     (case when o.prev_seq is null and o.seq = 1
                and o.prev_hash <> decode(repeat('00', 32), 'hex')
           then 'genesis prev_hash is not all zeros' end)
   ) as p (problem)
   where p.problem is not null
   order by o.seq
$$;

-- After pruning, the oldest retained row must link to the last archived row.
create function private.archive_boundary_breaks(tbl text)
returns table (seq bigint, problem text)
language plpgsql
stable
set search_path = ''
as $$
declare
  first_retained bigint;
  first_prev bytea;
  archived_hash text;
begin
  if tbl = 'samples' then
    select s.seq, s.prev_hash into first_retained, first_prev from public.samples s order by s.seq limit 1;
  else
    select f.seq, f.prev_hash into first_retained, first_prev from public.failed_samples f order by f.seq limit 1;
  end if;
  if first_retained is null or first_retained = 1 then
    return;
  end if;
  select a.last_row_hash into archived_hash
    from public.sample_archives a
   where a.table_name = tbl and a.last_seq = first_retained - 1 and a.pruned_at is not null;
  if archived_hash is null then
    seq := first_retained;
    problem := 'rows before this one are neither retained nor in a pruned archive';
    return next;
  elsif encode(first_prev, 'hex') <> archived_hash then
    seq := first_retained;
    problem := 'prev_hash does not link to the archived chain';
    return next;
  end if;
end;
$$;

create table public.chain_verifications (
  id                   bigint generated always as identity primary key,
  verified_at          timestamptz not null default now(),
  table_name           text not null check (table_name in ('samples', 'failed_samples')),
  rows_checked         bigint not null,
  first_seq            bigint,
  head_seq             bigint,
  head_row_hash        text check (head_row_hash ~ '^[0-9a-f]{64}$'),
  breaks               integer not null,
  first_break_seq      bigint,
  first_break_problem  text,
  ok                   boolean not null
);

-- Walks both chains, records the head hash and the first break of each.
create function public.record_chain_verification()
returns setof public.chain_verifications
language plpgsql
security definer
set search_path = ''
as $$
declare
  result public.chain_verifications;
begin
  insert into public.chain_verifications
    (table_name, rows_checked, first_seq, head_seq, head_row_hash, breaks, first_break_seq,
     first_break_problem, ok)
  select 'samples', t.n, t.first_seq, t.head_seq,
         (select encode(x.row_hash, 'hex') from public.samples x order by x.seq desc limit 1),
         b.n, b.first_seq, b.first_problem, b.n = 0
    from (select count(*) as n, min(s.seq) as first_seq, max(s.seq) as head_seq
            from public.samples s) t,
         (select count(*)::integer as n, min(z.seq) as first_seq,
                 (array_agg(z.problem order by z.seq))[1] as first_problem
            from (select * from private.samples_chain_breaks()
                  union all
                  select * from private.archive_boundary_breaks('samples')) z) b
  returning * into result;
  return next result;

  insert into public.chain_verifications
    (table_name, rows_checked, first_seq, head_seq, head_row_hash, breaks, first_break_seq,
     first_break_problem, ok)
  select 'failed_samples', t.n, t.first_seq, t.head_seq,
         (select encode(x.row_hash, 'hex') from public.failed_samples x order by x.seq desc limit 1),
         b.n, b.first_seq, b.first_problem, b.n = 0
    from (select count(*) as n, min(f.seq) as first_seq, max(f.seq) as head_seq
            from public.failed_samples f) t,
         (select count(*)::integer as n, min(z.seq) as first_seq,
                 (array_agg(z.problem order by z.seq))[1] as first_problem
            from (select * from private.failed_samples_chain_breaks()
                  union all
                  select * from private.archive_boundary_breaks('failed_samples')) z) b
  returning * into result;
  return next result;
end;
$$;

-- Archive bucket: the archive is the permanent, public record.
insert into storage.buckets (id, name, public, file_size_limit)
values ('archive', 'archive', true, 52428800)
on conflict (id) do nothing;

-- Privileges -------------------------------------------------------------------

revoke update, delete, truncate on public.samples, public.failed_samples from service_role;
revoke update, delete, truncate on public.sample_archives, public.chain_verifications from service_role;
revoke insert on public.chain_verifications from service_role;
revoke truncate on public.collector_runs, public.gap_reports from service_role;

revoke execute on function public.prune_archived(bigint) from public, anon, authenticated;
grant execute on function public.prune_archived(bigint) to service_role;
revoke execute on function public.record_chain_verification() from public, anon, authenticated;
grant execute on function public.record_chain_verification() to service_role;

-- Row level security: public read, no public write, as in 0001.
do $$
declare
  t text;
begin
  foreach t in array array[
    'failed_samples', 'collector_runs', 'gap_reports', 'sample_archives', 'chain_verifications'
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
