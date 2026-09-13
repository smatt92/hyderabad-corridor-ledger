-- 0006_via_points.sql
--
-- Every measured corridor is pinned to its road by declared via points.
--
-- calculateRoute returns TomTom's choice of road between the points it is
-- given. With only an origin and a destination, a corridor measures whatever
-- road TomTom picks on that call, which can change between runs, so the
-- series would not measure a fixed corridor. Two corridors sharing endpoints
-- would measure the same road twice. So every corridor, core, alternate or
-- donor, declares an ordered list of via points, passed to calculateRoute as
-- waypoints, and
--   * via_points are geometry: frozen with the endpoints once a corridor has
--     been anything but a draft (corridors_guard);
--   * the members of a pair share endpoints and must differ in via_points
--     (corridors_check_pair).
--
-- 0003 created the column as `via` and required it only of alternates. This
-- renames it and requires it of every corridor. corridors holds no rows.
-- 0003 is applied and is not edited.

alter table public.corridors rename column via to via_points;

-- An ordered list of 1 to 25 points, each exactly {lat, lon} inside Greater
-- Hyderabad: the same bounds collector/config.py enforces.
create function public.via_points_valid(points jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select case
    when points is null or jsonb_typeof(points) <> 'array' then false
    when jsonb_array_length(points) not between 1 and 25 then false
    else not exists (
      select 1
        from jsonb_array_elements(points) as p (point)
       where case
               when jsonb_typeof(p.point) <> 'object' then true
               when not (p.point ?& array['lat', 'lon'])
                 or (select count(*) from jsonb_object_keys(p.point)) <> 2 then true
               when jsonb_typeof(p.point -> 'lat') <> 'number'
                 or jsonb_typeof(p.point -> 'lon') <> 'number' then true
               else (p.point ->> 'lat')::numeric not between 17.10 and 17.75
                 or (p.point ->> 'lon')::numeric not between 78.05 and 78.85
             end
    )
  end
$$;

alter table public.corridors
  drop constraint corridors_alternate_is_pinned,
  add constraint corridors_alternate_is_paired check (class <> 'alternate' or pair_id is not null),
  add constraint corridors_via_points_valid check (public.via_points_valid(via_points));

create or replace function public.corridors_check_pair()
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
     where c.pair_id = new.pair_id and c.id <> new.id and c.direction = new.direction
       and c.via_points = new.via_points
  ) then
    raise exception 'corridors in pair % direction % declare identical via_points: they would measure the same road',
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

-- Unchanged from 0003 except that via_points is named in the frozen geometry.
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
     and (new.origin_lat, new.origin_lon, new.dest_lat, new.dest_lon, new.via_points, new.direction)
         is distinct from
         (old.origin_lat, old.origin_lon, old.dest_lat, old.dest_lon, old.via_points, old.direction)
  then
    raise exception 'corridor % has been active; its geometry and via_points are permanent', old.id
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;
