-- 0002_db_size_log.sql
--
-- Database size log for the 500 MB free tier. The db-size workflow calls
-- public.log_db_size() with the service key and fails the build at 400 MB.

create table private.db_size_log (
  id           bigint generated always as identity primary key,
  measured_at  timestamptz not null default now(),
  bytes        bigint not null check (bytes >= 0)
);

alter table private.db_size_log enable row level security;

create function public.log_db_size()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  size_bytes bigint := pg_database_size(current_database());
begin
  insert into private.db_size_log (bytes) values (size_bytes);
  return size_bytes;
end;
$$;

revoke execute on function public.log_db_size() from public, anon, authenticated;
grant execute on function public.log_db_size() to service_role;
