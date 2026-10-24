-- A stand-in for the parts of Supabase that supabase/migrations/*.sql needs, so the tests can run
-- the migration on a plain local Postgres. On Supabase all of this already exists.
--
-- auth.uid() reads the caller's id from request.jwt.claims, as PostgREST sets it for each request
-- and as Supabase's own auth.uid() reads it. The tests act as a person by opening a transaction,
-- switching to the authenticated role and setting request.jwt.claims, as PostgREST does.

create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;

create schema auth;
create table auth.users (id uuid primary key, email text unique);

create function auth.uid() returns uuid
language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create function auth.role() returns text
language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;

grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema public to anon, authenticated, service_role;

-- Supabase grants every new table, sequence and function in public to these three roles. The
-- migration has to take back what it does not want them to have, so the stand-in does the same.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
