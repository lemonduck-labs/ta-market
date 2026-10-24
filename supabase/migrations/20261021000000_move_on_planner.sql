-- The move-on planner's shared store on Supabase Postgres (London region).
--
-- Synthetic records only: every household id is SYN-0001 to SYN-9999, checked on every table.
-- Plans are suggestions for an officer to approve, never decisions. Each statutory decision
-- (an offer, a referral, ending a duty) is made and recorded outside the planner.
--
-- What the database makes true, whatever a page or a script sends:
--   * Who and when: every author, actor and timestamp is set here, from auth.uid() and now().
--   * Roles (public.members): every active member reads; Contributors and up save versions,
--     move the status pointer, work the checks and record progress; only Editors and the owner
--     record decisions and change the four-eyes setting; only the owner manages members.
--   * Four-eyes: an approval is refused when four-eyes is on and the approver saved the version,
--     or when the SHA-256 it names is not the version's.
--   * Fingerprints: a version is refused unless its SHA-256 is the SHA-256 of its plan written
--     as the page's canonical JSON (keys sorted at every level).
--   * Reviewer notes: a version lists the reviewer notes it was drafted against (at most five,
--     each {id, kind, text}), and its plan answers each of them once and no other. Which notes
--     are current is worked out by the page and the draft-plan function from the decisions.
--   * Workflow: a decision needs the version that is submitted, once per submission; a decided
--     plan is locked until an Editor reopens it; progress needs an approved plan.
--   * Insert-only: nobody, the dashboard included, changes or deletes versions, decisions,
--     drafts, page events or the audit log, and no audited table can be truncated.
--   * The audit log is written here, by triggers, for every insert, update or delete of the
--     other tables. The page never writes it.
--
-- The page's records (app/README.md) map to these tables; app/src/hosted.js does the mapping:
--   members/{id}                  public.members
--   versions/{id}/v/{version}     public.versions (author = id)
--   decisions/{id}/d/{decision}   public.decisions (author = id)
--   audit/{id}/e/{event}          public.audit (actor = id), written by triggers; the page's
--                                 own events (exports) go to public.events
--   files/{household}             public.files
--   checks/{household}            public.checks, one row per check
--   moves/{household}             public.moves
--   config/workflow               public.config
--   data/users/{id}/draft_{hh}    public.private_drafts, readable by that person only
-- Two tables the page never sees: public.drafts (each Claude draft, written by the draft-plan
-- function) and public.deny_terms (the private deny list, read by that function only).
--
-- Needs Supabase's auth schema (auth.users, auth.uid()) and roles (anon, authenticated,
-- service_role). tests/test_hosted_db.py runs this file on a local Postgres with a stand-in for
-- both (tests/hosted_supabase_stub.sql).

create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated, service_role;

-- ============================================================== tables

create table public.members (
  user_id uuid primary key references auth.users (id) on delete restrict,
  role text not null check (role in ('viewer', 'contributor', 'editor', 'owner')),
  display_name text not null default '' check (char_length(display_name) <= 80),
  active boolean not null default true,
  invited_at timestamptz not null default now(),
  invited_by uuid,
  updated_at timestamptz not null default now(),
  updated_by uuid
);
comment on table public.members is 'Who may use the planner, at which role. Set active to false to remove access; records keep their author.';

create table public.versions (
  id text primary key check (id ~ '^[A-Za-z0-9~_.-]{1,80}$'),
  author uuid not null references public.members (user_id),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  version integer not null,
  source text not null check (source in ('claude', 'template', 'edited')),
  from_source text check (from_source in ('claude', 'template', 'edited')),
  plan jsonb not null check (jsonb_typeof(plan) = 'object' and octet_length(plan::text) <= 65536),
  screen jsonb not null check (jsonb_typeof(screen) = 'object'),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  prompt_sha256 text check (prompt_sha256 ~ '^[0-9a-f]{64}$'),
  review jsonb not null default '[]'::jsonb
    check (case when jsonb_typeof(review) = 'array' then jsonb_array_length(review) <= 5 and octet_length(review::text) <= 8192 else false end),
  created_at timestamptz not null default now(),
  key text generated always as (author::text || '/' || id) stored unique
);
comment on table public.versions is 'Each plan version, screened by the page. Insert-only. key is the page''s version id (author/id). review is the reviewer notes the plan answers.';
create index versions_author on public.versions (author, created_at);
create index versions_household on public.versions (household_id, version);

create table public.decisions (
  id text primary key check (id ~ '^[A-Za-z0-9~_.-]{1,80}$'),
  author uuid not null references public.members (user_id),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  decision text not null check (decision in ('approved', 'returned', 'rejected', 'reopened')),
  version_id text references public.versions (key),
  plan_sha256 text check (plan_sha256 ~ '^[0-9a-f]{64}$'),
  four_eyes boolean not null default true,
  note text not null default '' check (char_length(note) <= 1000),
  reason text check (reason in ('changed', 'duplicate', 'not_needed', 'other')),
  decided_at timestamptz not null default now(),
  check (decision <> 'rejected' or reason is not null),
  check (decision <> 'returned' or note <> '')
);
comment on table public.decisions is 'Each decision on a plan: approved, returned, rejected or reopened. Insert-only.';
create index decisions_author on public.decisions (author, decided_at);
create index decisions_household on public.decisions (household_id, decided_at desc, id desc);

create table public.files (
  household_id text primary key check (household_id ~ '^SYN-[0-9]{4}$'),
  status text check (status in ('drafting', 'submitted')),
  version_id text references public.versions (key),
  updated_at timestamptz,
  updated_by uuid,
  assignee uuid references public.members (user_id),
  assigned_at timestamptz,
  check (status is null or version_id is not null)
);
comment on table public.files is 'The status pointer (drafting or submitted, and which version) and who has the household. updated_at moves only with the pointer.';

create table public.checks (
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  check_id text not null check (check_id ~ '^[a-z0-9][a-z0-9._-]{0,80}$'),
  state text not null check (state in ('open', 'done', 'na')),
  updated_by uuid,
  updated_at timestamptz not null default now(),
  primary key (household_id, check_id)
);
comment on table public.checks is 'Each check''s state for a household: open, done (checked) or na (not applicable), with who and when.';

create table public.moves (
  household_id text primary key check (household_id ~ '^SYN-[0-9]{4}$'),
  stage text not null check (stage in ('none', 'referral', 'offer', 'accepted', 'moved', 'fell_through')),
  pathway_id text check (pathway_id ~ '^[a-z][a-z0-9-]{0,40}$'),
  note text not null default '' check (char_length(note) <= 1000),
  plan_version text references public.versions (id),
  updated_by uuid,
  updated_at timestamptz not null default now()
);
comment on table public.moves is 'Progress on an approved plan: the stage, the pathway and a screened note.';

create table public.config (
  key text primary key check (key = 'workflow'),
  four_eyes boolean not null default true,
  updated_at timestamptz not null default now(),
  updated_by uuid
);
comment on table public.config is 'The approval setting. Four-eyes is on unless an Editor turns it off.';

create table public.events (
  id bigint generated always as identity primary key,
  actor uuid not null references public.members (user_id),
  household_id text check (household_id ~ '^SYN-[0-9]{4}$'),
  action text not null check (action in ('pack_exported', 'audit_exported')),
  detail text not null default '' check (char_length(detail) <= 200),
  spec_version text check (char_length(spec_version) <= 40),
  at timestamptz not null default now()
);
comment on table public.events is 'What the page did that changes no table (an export). The database sets who and when; the page says what. Insert-only.';

create table public.drafts (
  id bigint generated always as identity primary key,
  requested_by uuid not null references public.members (user_id),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  passed boolean not null,
  rules text[] not null default '{}',
  problem_count integer not null default 0 check (problem_count >= 0),
  prompt_sha256 text check (prompt_sha256 ~ '^[0-9a-f]{64}$'),
  plan_sha256 text check (plan_sha256 ~ '^[0-9a-f]{64}$'),
  model text check (char_length(model) <= 80),
  stop_reason text check (char_length(stop_reason) <= 40),
  input_tokens integer,
  output_tokens integer,
  spec_version text check (char_length(spec_version) <= 40),
  at timestamptz not null default now()
);
comment on table public.drafts is 'Each draft the draft-plan function asked Claude for: who, which household, whether it passed the screen and which rules it broke. Never the text. Insert-only.';
create index drafts_requested_by on public.drafts (requested_by, at);

create table public.private_drafts (
  user_id uuid not null default auth.uid() references public.members (user_id),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  working jsonb check (working is null or (jsonb_typeof(working) = 'object' and octet_length(working::text) <= 131072)),
  at timestamptz not null default now(),
  primary key (user_id, household_id)
);
comment on table public.private_drafts is 'A person''s unsaved, screened draft. Only that person can read it. Not audited, so the shared log never holds it.';

create table public.deny_terms (
  term text primary key check (char_length(term) between 2 and 120)
);
comment on table public.deny_terms is 'The private deny list. Only the draft-plan function reads it (the service role). Not audited, so the shared log never holds a name.';

create table public.audit (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid,
  actor_role text not null,
  table_name text not null,
  op text not null check (op in ('INSERT', 'UPDATE', 'DELETE')),
  row_key text not null,
  household_id text,
  action text not null,
  detail text not null default '',
  spec_version text,
  change jsonb not null
);
comment on table public.audit is 'Written by triggers only. actor is null for a change made from the dashboard or a migration; actor_role says which database role made it. Insert-only.';
create index audit_actor on public.audit (actor, at desc, id desc);
create index audit_household on public.audit (household_id, at);

-- ============================================================== helpers

create function private.role_rank(r text) returns integer
language sql immutable set search_path = '' as $$
  select case r when 'viewer' then 1 when 'contributor' then 2 when 'editor' then 3 when 'owner' then 4 else 0 end
$$;

-- The caller's role, or null when they are not an active member.
create function private.my_role() returns text
language sql stable security definer set search_path = '' as $$
  select m.role from public.members m where m.user_id = auth.uid() and m.active
$$;

create function private.at_least(r text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce(private.role_rank(private.my_role()) >= private.role_rank(r), false)
$$;

-- The page's canonical JSON (app/src/page.js, canon): keys sorted at every level, no spaces,
-- strings escaped as JSON.stringify does. The same text as the page for strings, booleans, null,
-- arrays, objects with ASCII keys and plain decimal numbers; the plan schema has no numbers.
create function private.canon_json(v jsonb) returns text
language plpgsql immutable strict set search_path = '' as $$
declare
  t text := jsonb_typeof(v);
  out_text text;
begin
  if t = 'object' then
    select '{' || coalesce(string_agg(to_json(e.key)::text || ':' || private.canon_json(e.value), ',' order by e.key collate "C"), '') || '}'
      into out_text from jsonb_each(v) as e;
    return out_text;
  elsif t = 'array' then
    select '[' || coalesce(string_agg(private.canon_json(e.value), ',' order by e.ord), '') || ']'
      into out_text from jsonb_array_elements(v) with ordinality as e(value, ord);
    return out_text;
  elsif t = 'string' then
    return to_json(v #>> '{}')::text;
  end if;
  return v::text;
end $$;

create function private.plan_sha256(p jsonb) returns text
language sql immutable strict set search_path = '' as $$
  select encode(sha256(convert_to(private.canon_json(p), 'UTF8')), 'hex')
$$;

-- Serialises changes to one household's workflow (versions, the pointer, decisions, checks,
-- progress), so two people acting at once cannot both pass a check that each would fail.
create function private.lock_household(hid text) returns void
language plpgsql volatile set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('ta-move-on-planner:' || hid, 0));
end $$;

create function private.last_decision(hid text) returns text
language sql stable security definer set search_path = '' as $$
  select d.decision from public.decisions d where d.household_id = hid order by d.decided_at desc, d.id desc limit 1
$$;

create function private.refuse(msg text, code text default '23514') returns void
language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = code, message = msg;
end $$;

-- ============================================================== before triggers: who, when, rules

create function private.members_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
begin
  if tg_op = 'INSERT' then
    new.invited_at := now();
    new.invited_by := uid;
  else
    if new.user_id <> old.user_id then perform private.refuse('a member''s id cannot change'); end if;
    new.invited_at := old.invited_at;
    new.invited_by := old.invited_by;
    if uid is not null and new.user_id = uid and (new.role <> old.role or new.active <> old.active) then
      perform private.refuse('you cannot change your own role or access', '42501');
    end if;
    if old.role = 'owner' and old.active and (new.role <> 'owner' or not new.active)
       and not exists (select 1 from public.members m where m.role = 'owner' and m.active and m.user_id <> new.user_id) then
      perform private.refuse('the planner needs an active owner');
    end if;
    if (new.role, new.display_name, new.active) is not distinct from (old.role, old.display_name, old.active) then
      new.updated_at := old.updated_at;   -- nothing changed, so nothing happened
      new.updated_by := old.updated_by;
      return new;
    end if;
  end if;
  new.updated_at := now();
  new.updated_by := uid;
  return new;
end $$;

create function private.versions_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null or not private.at_least('contributor') then
    perform private.refuse('saving a version needs a signed-in Contributor, Editor or owner', '42501');
  end if;
  new.author := uid;
  perform private.lock_household(new.household_id);
  if private.last_decision(new.household_id) in ('approved', 'rejected') then
    perform private.refuse('the plan is decided; an Editor must reopen it first');
  end if;
  new.created_at := now();
  new.version := coalesce((select max(v.version) from public.versions v where v.household_id = new.household_id), 0) + 1;
  if new.plan -> 'household_id' is distinct from to_jsonb(new.household_id) or new.plan -> 'record_is_synthetic' is distinct from 'true'::jsonb then
    perform private.refuse('the plan is not for this synthetic household');
  end if;
  if new.sha256 is distinct from private.plan_sha256(new.plan) then
    perform private.refuse('the SHA-256 does not match the plan');
  end if;
  if jsonb_typeof(new.review) is distinct from 'array' then
    perform private.refuse('a version''s reviewer notes must be a list');
  end if;
  if jsonb_array_length(new.review) > 5 then
    perform private.refuse('a version answers at most five reviewer notes');
  end if;
  if exists (select 1 from jsonb_array_elements(new.review) e
             where jsonb_typeof(e) <> 'object' or coalesce(e ->> 'id', '') !~ '^review-[1-5]$'
                or coalesce(e ->> 'kind', '') not in ('returned', 'rejected') or jsonb_typeof(e -> 'text') is distinct from 'string')
     or (select count(distinct e ->> 'id') from jsonb_array_elements(new.review) e) <> jsonb_array_length(new.review) then
    perform private.refuse('each reviewer note needs its own id, review-1 to review-5, a kind and a text');
  end if;
  if (select coalesce(array_agg(e ->> 'id' order by e ->> 'id'), '{}') from jsonb_array_elements(new.review) e)
     is distinct from (select coalesce(array_agg(a ->> 'note' order by a ->> 'note'), '{}')
                       from jsonb_array_elements(case when jsonb_typeof(new.plan -> 'responds_to_review') = 'array'
                                                      then new.plan -> 'responds_to_review' else '[]'::jsonb end) a) then
    perform private.refuse('the plan must answer each reviewer note the version lists, once, and no other');
  end if;
  if new.screen -> 'passed' is distinct from 'true'::jsonb or jsonb_typeof(new.screen -> 'spec_version') is distinct from 'string'
     or char_length(new.screen ->> 'spec_version') > 40 then
    perform private.refuse('a version must have passed the screen');
  end if;
  new.screen := jsonb_build_object('passed', true, 'spec_version', new.screen -> 'spec_version', 'checked_at', to_jsonb(now()));
  return new;
end $$;

create function private.decisions_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  v_row public.versions;
  f_row public.files;
  last_decision text;
  last_at timestamptz;
begin
  if uid is null or not private.at_least('editor') then
    perform private.refuse('only an Editor or the owner can record a decision', '42501');
  end if;
  new.author := uid;
  perform private.lock_household(new.household_id);
  new.decided_at := now();
  new.four_eyes := coalesce((select c.four_eyes from public.config c where c.key = 'workflow'), true);
  if new.version_id is not null then
    select * into v_row from public.versions v where v.key = new.version_id;
    if not found or v_row.household_id <> new.household_id then
      perform private.refuse('the decision names a version of another household');
    end if;
    if new.plan_sha256 is distinct from v_row.sha256 then
      perform private.refuse('the SHA-256 does not match the version''s');
    end if;
  end if;
  select d.decision, d.decided_at into last_decision, last_at
    from public.decisions d where d.household_id = new.household_id order by d.decided_at desc, d.id desc limit 1;
  if new.decision = 'reopened' then
    if last_decision is null or last_decision not in ('approved', 'rejected') then
      perform private.refuse('only an approved or rejected plan can be reopened');
    end if;
    return new;
  end if;
  if new.version_id is null then
    perform private.refuse('the decision must name the version it is about');
  end if;
  if new.decision = 'approved' and new.four_eyes and v_row.author = uid then
    perform private.refuse('four-eyes is on: the person who saved this version cannot approve it');
  end if;
  select * into f_row from public.files f where f.household_id = new.household_id;
  if not found or f_row.status is distinct from 'submitted' or f_row.version_id is distinct from new.version_id then
    perform private.refuse('this version is not the one submitted for approval');
  end if;
  if last_decision in ('approved', 'rejected') or (last_at is not null and f_row.updated_at <= last_at) then
    perform private.refuse('the plan has not been submitted again since the last decision');
  end if;
  return new;
end $$;

-- updated_at and updated_by belong to the status pointer: they move when a request sets the
-- status or the version (files_pointer below), even to the same values, as a resubmission after a
-- return does, and never when someone only takes or releases the household. The page works out a
-- returned plan by comparing the pointer's time with the last decision's.
create function private.files_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  hh text;
begin
  if tg_op = 'UPDATE' and new.household_id <> old.household_id then perform private.refuse('a file''s household cannot change'); end if;
  perform private.lock_household(new.household_id);
  if new.version_id is not null then
    select v.household_id into hh from public.versions v where v.key = new.version_id;
    if hh is distinct from new.household_id then perform private.refuse('the pointer names a version of another household'); end if;
  end if;
  if tg_op = 'UPDATE' then
    new.updated_at := old.updated_at;
    new.updated_by := old.updated_by;
  elsif new.status is not null or new.version_id is not null then
    if private.last_decision(new.household_id) in ('approved', 'rejected') then
      perform private.refuse('the plan is decided; an Editor must reopen it first');
    end if;
    new.updated_at := now();
    new.updated_by := uid;
  else
    new.updated_at := null;
    new.updated_by := null;
  end if;
  if (tg_op = 'INSERT' and new.assignee is not null) or (tg_op = 'UPDATE' and new.assignee is distinct from old.assignee) then
    if new.assignee is not null and uid is not null and new.assignee <> uid then
      perform private.refuse('a person can take a household only for themselves', '42501');
    end if;
    new.assigned_at := case when new.assignee is not null then now() end;
  elsif tg_op = 'UPDATE' then
    new.assigned_at := old.assigned_at;
  else
    new.assigned_at := null;
  end if;
  return new;
end $$;

-- Runs after files_before (triggers of one kind fire in name order), only when the request sets
-- the status or the version.
create function private.files_pointer() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if private.last_decision(new.household_id) in ('approved', 'rejected') then
    perform private.refuse('the plan is decided; an Editor must reopen it first');
  end if;
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;

create function private.checks_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' and (new.household_id <> old.household_id or new.check_id <> old.check_id) then
    perform private.refuse('a check''s household and id cannot change');
  end if;
  perform private.lock_household(new.household_id);
  if private.last_decision(new.household_id) = 'rejected' then
    perform private.refuse('the plan was rejected; an Editor must reopen it before the checks change');
  end if;
  if tg_op = 'UPDATE' and new.state = old.state then
    new.updated_by := old.updated_by;   -- nothing changed, so nothing happened
    new.updated_at := old.updated_at;
    return new;
  end if;
  new.updated_by := auth.uid();
  new.updated_at := now();
  return new;
end $$;

create function private.moves_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  hh text;
begin
  if tg_op = 'UPDATE' and new.household_id <> old.household_id then perform private.refuse('a progress record''s household cannot change'); end if;
  perform private.lock_household(new.household_id);
  if private.last_decision(new.household_id) is distinct from 'approved' then
    perform private.refuse('progress is recorded against an approved plan');
  end if;
  if new.plan_version is not null then
    select v.household_id into hh from public.versions v where v.id = new.plan_version;
    if hh is distinct from new.household_id then perform private.refuse('the progress names a version of another household'); end if;
  end if;
  if tg_op = 'UPDATE' and (new.stage, new.pathway_id, new.note, new.plan_version) is not distinct from (old.stage, old.pathway_id, old.note, old.plan_version) then
    new.updated_by := old.updated_by;   -- nothing changed, so nothing happened
    new.updated_at := old.updated_at;
    return new;
  end if;
  new.updated_by := auth.uid();
  new.updated_at := now();
  return new;
end $$;

create function private.config_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' and new.key <> old.key then perform private.refuse('a setting''s key cannot change'); end if;
  if tg_op = 'UPDATE' and new.four_eyes = old.four_eyes then
    new.updated_at := old.updated_at;   -- nothing changed, so nothing happened
    new.updated_by := old.updated_by;
    return new;
  end if;
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;

create function private.events_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null or private.my_role() is null then perform private.refuse('an event needs a signed-in member', '42501'); end if;
  new.actor := uid;
  new.at := now();
  return new;
end $$;

create function private.drafts_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is not null then new.requested_by := auth.uid(); end if;
  new.at := now();
  return new;
end $$;

create function private.private_drafts_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null then perform private.refuse('a private draft needs a signed-in member', '42501'); end if;
  if tg_op = 'UPDATE' and new.household_id <> old.household_id then perform private.refuse('a draft''s household cannot change'); end if;
  new.user_id := uid;
  new.at := now();
  return new;
end $$;

create trigger members_before before insert or update on public.members for each row execute function private.members_before();
create trigger versions_before before insert on public.versions for each row execute function private.versions_before();
create trigger decisions_before before insert on public.decisions for each row execute function private.decisions_before();
create trigger files_a_before before insert or update on public.files for each row execute function private.files_before();
create trigger files_b_pointer before update of status, version_id on public.files for each row execute function private.files_pointer();
create trigger checks_before before insert or update on public.checks for each row execute function private.checks_before();
create trigger moves_before before insert or update on public.moves for each row execute function private.moves_before();
create trigger config_before before insert or update on public.config for each row execute function private.config_before();
create trigger events_before before insert on public.events for each row execute function private.events_before();
create trigger drafts_before before insert on public.drafts for each row execute function private.drafts_before();
create trigger private_drafts_before before insert or update on public.private_drafts for each row execute function private.private_drafts_before();

-- ============================================================== insert-only and no truncate

create function private.refuse_change() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '42501', message = format('%s is insert-only: %s is refused', tg_table_name, lower(tg_op));
end $$;

create trigger versions_insert_only before update or delete on public.versions for each row execute function private.refuse_change();
create trigger decisions_insert_only before update or delete on public.decisions for each row execute function private.refuse_change();
create trigger events_insert_only before update or delete on public.events for each row execute function private.refuse_change();
create trigger drafts_insert_only before update or delete on public.drafts for each row execute function private.refuse_change();
create trigger audit_insert_only before update or delete on public.audit for each row execute function private.refuse_change();

create function private.refuse_truncate() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '42501', message = format('%s cannot be truncated: the audit log would lose track of it', tg_table_name);
end $$;

create trigger members_no_truncate before truncate on public.members for each statement execute function private.refuse_truncate();
create trigger versions_no_truncate before truncate on public.versions for each statement execute function private.refuse_truncate();
create trigger decisions_no_truncate before truncate on public.decisions for each statement execute function private.refuse_truncate();
create trigger files_no_truncate before truncate on public.files for each statement execute function private.refuse_truncate();
create trigger checks_no_truncate before truncate on public.checks for each statement execute function private.refuse_truncate();
create trigger moves_no_truncate before truncate on public.moves for each statement execute function private.refuse_truncate();
create trigger config_no_truncate before truncate on public.config for each statement execute function private.refuse_truncate();
create trigger events_no_truncate before truncate on public.events for each statement execute function private.refuse_truncate();
create trigger drafts_no_truncate before truncate on public.drafts for each statement execute function private.refuse_truncate();
create trigger audit_no_truncate before truncate on public.audit for each statement execute function private.refuse_truncate();

-- ============================================================== the audit log

-- Words the page uses for these, so an entry reads the same in the hosted log as in the pilot's.
create function private.source_label(s text) returns text
language sql immutable set search_path = '' as $$
  select case s when 'claude' then 'drafted by Claude' when 'template' then 'from the template' when 'edited' then 'edited' else coalesce(s, '') end
$$;

create function private.version_no(version_key text) returns text
language sql stable security definer set search_path = '' as $$
  select coalesce((select v.version::text from public.versions v where v.key = version_key), '?')
$$;

create function private.audit_row() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  n jsonb := case when tg_op <> 'DELETE' then to_jsonb(new) end;
  o jsonb := case when tg_op <> 'INSERT' then to_jsonb(old) end;
  r jsonb;
  diff_new jsonb := '{}'::jsonb;
  diff_old jsonb := '{}'::jsonb;
  act text;
  det text := '';
  hid text;
  who uuid := auth.uid();
  rk text;
  spec text;
  claims jsonb;
  bits text[] := '{}';
begin
  r := coalesce(n, o);
  hid := r ->> 'household_id';
  if tg_op = 'UPDATE' then
    select coalesce(jsonb_object_agg(k, n -> k), '{}'::jsonb), coalesce(jsonb_object_agg(k, o -> k), '{}'::jsonb)
      into diff_new, diff_old
      from jsonb_object_keys(n) as k where n -> k is distinct from o -> k;
    if diff_new = '{}'::jsonb then return null; end if;   -- nothing changed, so nothing happened
  end if;
  begin
    claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    claims := null;
  end;

  if tg_op = 'DELETE' then
    act := 'row_deleted';
    det := tg_table_name;
  end if;

  case tg_table_name
  when 'members' then
    rk := r ->> 'user_id';
    hid := null;
    if tg_op = 'INSERT' then act := 'member_added'; det := r ->> 'role';
    elsif tg_op = 'UPDATE' then
      act := 'member_changed';
      if diff_new ? 'role' then bits := bits || format('role %s to %s', o ->> 'role', n ->> 'role'); end if;
      if diff_new ? 'active' then bits := bits || (case when (n ->> 'active')::boolean then 'access restored' else 'access removed' end); end if;
      if diff_new ? 'display_name' then bits := bits || 'name changed'::text; end if;
      det := array_to_string(bits, ', ');
    end if;
  when 'versions' then
    rk := r ->> 'key';
    spec := r -> 'screen' ->> 'spec_version';
    act := 'plan_saved';
    det := format('version %s, %s', r ->> 'version', private.source_label(r ->> 'source'))
      || case when r ->> 'source' = 'edited' and r ->> 'from_source' is not null then ' from ' || private.source_label(r ->> 'from_source') else '' end;
  when 'decisions' then
    rk := (r ->> 'author') || '/' || (r ->> 'id');
    act := case r ->> 'decision' when 'approved' then 'plan_approved' when 'returned' then 'plan_returned'
                                 when 'rejected' then 'plan_rejected' else 'reopened' end;
    det := case r ->> 'decision'
      when 'approved' then format('version %s, four-eyes %s', private.version_no(r ->> 'version_id'), case when (r ->> 'four_eyes')::boolean then 'on' else 'off' end)
      when 'rejected' then case r ->> 'reason' when 'changed' then 'The record or the circumstances have changed'
        when 'duplicate' then 'Another plan covers this household' when 'not_needed' then 'No move-on plan is needed now'
        else 'Other (see the note)' end
      when 'returned' then 'with a note'
      else '' end;
  when 'files' then
    rk := r ->> 'household_id';
    if tg_op <> 'DELETE' then
      -- The pointer was set when its time moved (files_pointer), so a resubmission counts.
      if (tg_op = 'INSERT' and (n ->> 'status' is not null or n ->> 'version_id' is not null))
         or diff_new ? 'updated_at' or diff_new ? 'status' or diff_new ? 'version_id' then
        if n ->> 'status' = 'submitted' then
          act := 'plan_submitted';
          det := format('version %s', private.version_no(n ->> 'version_id'));
        else
          act := 'plan_pointer_set';
          det := format('%s, version %s', coalesce(n ->> 'status', 'no status'), private.version_no(n ->> 'version_id'));
        end if;
        if (tg_op = 'INSERT' and n ->> 'assignee' is not null) or diff_new ? 'assignee' then det := det || '; assignee changed'; end if;
      elsif (tg_op = 'INSERT' and n ->> 'assignee' is not null) or diff_new ? 'assignee' then
        act := case when n ->> 'assignee' is not null then 'assigned' else 'unassigned' end;
      else
        act := 'file_updated';
      end if;
    end if;
  when 'checks' then
    rk := (r ->> 'household_id') || '/' || (r ->> 'check_id');
    if tg_op <> 'DELETE' then
      act := 'check_updated';
      det := format('%s: %s', n ->> 'check_id', case n ->> 'state' when 'done' then 'checked' when 'na' then 'not applicable' else 'open' end);
    end if;
  when 'moves' then
    rk := r ->> 'household_id';
    if tg_op <> 'DELETE' then
      act := 'progress_updated';
      det := case n ->> 'stage' when 'none' then 'Not started' when 'referral' then 'Referral or application made'
               when 'offer' then 'Offer made' when 'accepted' then 'Offer accepted' when 'moved' then 'Moved on'
               when 'fell_through' then 'Fell through' else n ->> 'stage' end
        || case when n ->> 'pathway_id' is null then '' else ', ' || case n ->> 'pathway_id' when 'social-housing' then 'Social housing'
               when 'prs-offer' then 'PRS offer' when 'supported-housing' then 'Supported housing' else n ->> 'pathway_id' end end;
    end if;
  when 'config' then
    rk := r ->> 'key';
    if tg_op <> 'DELETE' then
      act := 'workflow_changed';
      det := case when (n ->> 'four_eyes')::boolean then 'four-eyes on' else 'four-eyes off' end;
    end if;
  when 'events' then
    rk := r ->> 'id';
    act := r ->> 'action';
    det := r ->> 'detail';
    who := (r ->> 'actor')::uuid;
    spec := r ->> 'spec_version';
  when 'drafts' then
    rk := r ->> 'id';
    who := (r ->> 'requested_by')::uuid;
    spec := r ->> 'spec_version';
    if (r ->> 'passed')::boolean then
      act := 'draft_created';
      det := 'passed the screen';
    else
      act := 'draft_failed_screen';
      det := format('%s %s: %s', r ->> 'problem_count', case when (r ->> 'problem_count')::int = 1 then 'problem' else 'problems' end,
                    array_to_string(array(select jsonb_array_elements_text(r -> 'rules')), ', '));
    end if;
  else
    rk := coalesce(r ->> 'id', '');
    act := coalesce(act, 'row_changed');
  end case;

  if tg_op = 'DELETE' then
    act := 'row_deleted';
    det := tg_table_name;
  end if;

  insert into public.audit (at, actor, actor_role, table_name, op, row_key, household_id, action, detail, spec_version, change)
  values (now(), who, coalesce(claims ->> 'role', 'database'), tg_table_name, tg_op, coalesce(rk, ''), hid, act, coalesce(det, ''), spec,
          case tg_op when 'INSERT' then jsonb_build_object('new', n) when 'DELETE' then jsonb_build_object('old', o)
                     else jsonb_build_object('old', diff_old, 'new', diff_new) end);
  return null;
end $$;

create trigger members_audit after insert or update or delete on public.members for each row execute function private.audit_row();
create trigger versions_audit after insert on public.versions for each row execute function private.audit_row();
create trigger decisions_audit after insert on public.decisions for each row execute function private.audit_row();
create trigger files_audit after insert or update or delete on public.files for each row execute function private.audit_row();
create trigger checks_audit after insert or update or delete on public.checks for each row execute function private.audit_row();
create trigger moves_audit after insert or update or delete on public.moves for each row execute function private.audit_row();
create trigger config_audit after insert or update or delete on public.config for each row execute function private.audit_row();
create trigger events_audit after insert on public.events for each row execute function private.audit_row();
create trigger drafts_audit after insert on public.drafts for each row execute function private.audit_row();

-- ============================================================== privileges and row-level security

-- Supabase grants every new table in public to anon, authenticated and service_role. Take that
-- back and grant only what each role needs. TRUNCATE in particular is not covered by row-level
-- security, so nobody outside the database owner keeps it.
revoke all on public.members, public.versions, public.decisions, public.files, public.checks, public.moves,
  public.config, public.events, public.drafts, public.private_drafts, public.deny_terms, public.audit
  from public, anon, authenticated, service_role;

grant select on public.members, public.versions, public.decisions, public.files, public.checks, public.moves,
  public.config, public.events, public.drafts, public.audit to authenticated;
grant insert (user_id, role, display_name, active), update (role, display_name, active) on public.members to authenticated;
grant insert on public.versions, public.decisions, public.events to authenticated;
grant insert, update on public.files, public.checks, public.moves, public.config to authenticated;
grant select, insert, update on public.private_drafts to authenticated;

-- The draft-plan function: who may draft, how many drafts they asked for, the deny list, and
-- each draft's record. Nothing else.
grant select on public.members, public.drafts, public.deny_terms to service_role;
grant insert on public.drafts to service_role;

revoke all on all functions in schema private from public;
grant execute on function private.my_role(), private.at_least(text), private.role_rank(text) to authenticated, service_role;

alter table public.members enable row level security;
alter table public.versions enable row level security;
alter table public.decisions enable row level security;
alter table public.files enable row level security;
alter table public.checks enable row level security;
alter table public.moves enable row level security;
alter table public.config enable row level security;
alter table public.events enable row level security;
alter table public.drafts enable row level security;
alter table public.private_drafts enable row level security;
alter table public.deny_terms enable row level security;
alter table public.audit enable row level security;

-- Every active member reads the shared records. Someone signed in who is not a member reads nothing.
-- The helpers are wrapped in (select ...) so Postgres works them out once per query, not per row.
create policy members_read on public.members for select to authenticated using ((select private.my_role()) is not null);
create policy versions_read on public.versions for select to authenticated using ((select private.my_role()) is not null);
create policy decisions_read on public.decisions for select to authenticated using ((select private.my_role()) is not null);
create policy files_read on public.files for select to authenticated using ((select private.my_role()) is not null);
create policy checks_read on public.checks for select to authenticated using ((select private.my_role()) is not null);
create policy moves_read on public.moves for select to authenticated using ((select private.my_role()) is not null);
create policy config_read on public.config for select to authenticated using ((select private.my_role()) is not null);
create policy events_read on public.events for select to authenticated using ((select private.my_role()) is not null);
create policy drafts_read on public.drafts for select to authenticated using ((select private.my_role()) is not null);
create policy audit_read on public.audit for select to authenticated using ((select private.my_role()) is not null);

create policy members_owner_insert on public.members for insert to authenticated with check ((select private.at_least('owner')));
create policy members_owner_update on public.members for update to authenticated using ((select private.at_least('owner'))) with check ((select private.at_least('owner')));
create policy versions_insert on public.versions for insert to authenticated with check ((select private.at_least('contributor')));
create policy decisions_insert on public.decisions for insert to authenticated with check ((select private.at_least('editor')));
create policy files_insert on public.files for insert to authenticated with check ((select private.at_least('contributor')));
create policy files_update on public.files for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));
create policy checks_insert on public.checks for insert to authenticated with check ((select private.at_least('contributor')));
create policy checks_update on public.checks for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));
create policy moves_insert on public.moves for insert to authenticated with check ((select private.at_least('contributor')));
create policy moves_update on public.moves for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));
create policy config_insert on public.config for insert to authenticated with check ((select private.at_least('editor')));
create policy config_update on public.config for update to authenticated using ((select private.at_least('editor'))) with check ((select private.at_least('editor')));
create policy events_insert on public.events for insert to authenticated with check ((select private.my_role()) is not null);

create policy private_drafts_own on public.private_drafts for all to authenticated
  using (user_id = (select auth.uid()) and (select private.my_role()) is not null)
  with check (user_id = (select auth.uid()) and (select private.my_role()) is not null);

-- public.deny_terms has row-level security on and no policy: only the service role reads it.

-- ============================================================== seed and live updates

insert into public.config (key, four_eyes) values ('workflow', true);

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.members, public.versions, public.decisions, public.files,
      public.checks, public.moves, public.config, public.audit;
  end if;
end $$;
