-- 0012_corridor_route_polyline.sql
--
-- Every sample requests routeRepresentation=summaryOnly and stores no geometry.
-- A corridor's road, though, is fixed by its declared points, so the collector
-- fetches it once, when the corridor is verified: one calculateRoute call with
-- routeRepresentation=polyline, stored here with a simplified copy for drawing.
--
-- The polyline is permanent. It freezes together with the coordinates and
-- via_points, and a corridor holding one can be neither deleted nor redrawn.
-- The collector refetches each stored road weekly and records the comparison in
-- corridor_route_checks. A refetch that differs is never written over the
-- stored road: it means TomTom now routes the corridor down a different road, and
-- the collector run and the daily alarm fail until the corridor is retired.

-- 2 to 20,000 points, each [lat, lon] a little beyond Greater Hyderabad's bounds
-- (config.py's 17.10-17.75, 78.05-78.85), since a road between two points inside
-- them can briefly leave them.
create function public.route_polyline_valid(points jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select case
    when points is null or jsonb_typeof(points) <> 'array' then false
    when jsonb_array_length(points) not between 2 and 20000 then false
    else not exists (
      select 1
        from jsonb_array_elements(points) as p (point)
       where case
               when jsonb_typeof(p.point) <> 'array' or jsonb_array_length(p.point) <> 2 then true
               when jsonb_typeof(p.point -> 0) <> 'number'
                 or jsonb_typeof(p.point -> 1) <> 'number' then true
               else (p.point ->> 0)::numeric not between 17.00 and 17.85
                 or (p.point ->> 1)::numeric not between 77.95 and 78.95
             end
    )
  end
$$;

alter table public.corridors
  add column route_polyline            jsonb,
  add column route_polyline_simplified jsonb,
  add column route_polyline_length_m   integer check (route_polyline_length_m > 0),
  add column route_polyline_fetched_at timestamptz,
  add constraint corridors_route_polyline_complete check (
    (route_polyline is null) = (route_polyline_simplified is null)
    and (route_polyline is null) = (route_polyline_length_m is null)
    and (route_polyline is null) = (route_polyline_fetched_at is null)),
  add constraint corridors_route_polyline_valid check (
    route_polyline is null
    or (public.route_polyline_valid(route_polyline)
        and public.route_polyline_valid(route_polyline_simplified)
        and jsonb_array_length(route_polyline_simplified) <= jsonb_array_length(route_polyline))),
  add constraint corridors_route_polyline_only_when_verified check (
    route_polyline is null or verified);

-- 0006's guard, extended: a stored polyline freezes the coordinates, via_points and
-- the polyline itself, and forbids deleting the corridor.
create or replace function public.corridors_guard()
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
    if old.route_polyline is not null then
      raise exception 'corridor % has a stored road polyline; retire it instead of deleting it',
        old.id using errcode = 'insufficient_privilege';
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
  if (new.origin_lat, new.origin_lon, new.dest_lat, new.dest_lon, new.via_points, new.direction)
     is distinct from
     (old.origin_lat, old.origin_lon, old.dest_lat, old.dest_lon, old.via_points, old.direction)
  then
    if old.activated_at is not null then
      raise exception 'corridor % has been active; its geometry and via_points are permanent',
        old.id using errcode = 'insufficient_privilege';
    end if;
    if old.route_polyline is not null then
      raise exception 'corridor % has a stored road polyline; its geometry and via_points are permanent',
        old.id using errcode = 'insufficient_privilege';
    end if;
  end if;
  if old.route_polyline is not null
     and (new.route_polyline, new.route_polyline_simplified, new.route_polyline_length_m,
          new.route_polyline_fetched_at)
         is distinct from
         (old.route_polyline, old.route_polyline_simplified, old.route_polyline_length_m,
          old.route_polyline_fetched_at)
  then
    raise exception 'corridor % road polyline is permanent: a different road means TomTom has rerouted it; retire the corridor and declare a new one',
      old.id using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;

-- One row per polyline call: the first fetch (initial) and every weekly refetch.
-- Attempts count against the daily call budget (collector/store.py).
create table public.corridor_route_checks (
  id               bigint generated always as identity primary key,
  corridor_id      text not null references public.corridors (id),
  collector_run    text not null references public.collector_runs (id),
  checked_at       timestamptz not null,
  kind             text not null check (kind in ('initial', 'refetch')),
  attempts         smallint not null check (attempts between 1 and 10),
  http_status      smallint check (http_status between 100 and 599),
  error_class      text check (error_class ~ '^[A-Za-z0-9_]{1,40}$'),
  detail           text check (length(detail) <= 500),
  length_m         integer check (length_m > 0),
  points           integer check (points >= 2),
  max_deviation_m  double precision check (max_deviation_m >= 0),
  length_change    double precision,
  matched          boolean,
  -- a polyline came back exactly when there is no error
  check ((error_class is null) = (length_m is not null)),
  check ((error_class is null) = (points is not null)),
  -- only a successful refetch is compared, and it always is
  check ((kind = 'refetch' and error_class is null)
         = (max_deviation_m is not null and length_change is not null and matched is not null))
);

create index corridor_route_checks_corridor on public.corridor_route_checks (corridor_id, checked_at);
create index corridor_route_checks_checked_at on public.corridor_route_checks (checked_at);

-- Row level security: public read, no public write. The checks are the evidence
-- for a rerouting alarm, so the service role cannot rewrite or remove them either.
alter table public.corridor_route_checks enable row level security;
create policy corridor_route_checks_public_read on public.corridor_route_checks
  for select to anon, authenticated using (true);
revoke insert, update, delete, truncate, references, trigger on public.corridor_route_checks
  from anon, authenticated;
revoke update, delete, truncate on public.corridor_route_checks from service_role;
