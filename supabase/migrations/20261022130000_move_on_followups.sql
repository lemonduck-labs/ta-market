-- Follow-ups (phase 6): small jobs on a file, each with an owner and a due date.
--
-- The page's tasks/<id> record (app/src/page.js, addTask and setTask; app/src/hosted.js maps it
-- here). Any Contributor adds one, ticks it off or back, and changes its date or its owner; nobody
-- deletes one. The database sets who added and who finished each one and when, refuses an owner
-- who is not an active member, and writes the audit log itself. A follow-up is a step in working a
-- plan, never part of the plan and never a decision; synthetic records only. Unlike the checks,
-- follow-ups stay open to change once a plan is approved: the move itself comes after.

create table public.tasks (
  id text primary key check (id ~ '^task~[0-9a-z]{1,12}~[0-9a-z]{1,8}$'),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  text text not null check (length(btrim(text)) between 1 and 240),
  kind text not null default 'custom' check (kind ~ '^[a-z][a-z0-9-]{0,30}$'),
  due date,
  assignee uuid,
  done boolean not null default false,
  done_by uuid,
  done_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_by uuid,
  updated_at timestamptz not null default now()
);
comment on table public.tasks is 'Follow-ups on a file: text, due date, owner, and whether done, with who added and who finished each. No deletes.';
create index tasks_household on public.tasks (household_id);
create index tasks_assignee on public.tasks (assignee) where not done;

create function private.tasks_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  -- A new owner must be an active member. A follow-up whose owner has since left can still be
  -- ticked off or moved to another date.
  if new.assignee is not null and (tg_op = 'INSERT' or new.assignee is distinct from old.assignee)
     and not exists (select 1 from public.members m where m.user_id = new.assignee and m.active) then
    perform private.refuse('a follow-up''s owner must be an active member');
  end if;
  if tg_op = 'INSERT' then
    new.created_by := auth.uid();
    new.created_at := now();
    new.updated_by := auth.uid();
    new.updated_at := now();
    new.done_by := case when new.done then auth.uid() end;
    new.done_at := case when new.done then now() end;
    return new;
  end if;
  if new.id <> old.id or new.household_id <> old.household_id then
    perform private.refuse('a follow-up''s id and household cannot change');
  end if;
  new.kind := old.kind;
  new.created_by := old.created_by; new.created_at := old.created_at;
  if new.done is distinct from old.done then
    new.done_by := case when new.done then auth.uid() end;
    new.done_at := case when new.done then now() end;
  else
    new.done_by := old.done_by; new.done_at := old.done_at;
  end if;
  if (new.text, new.due, new.assignee, new.done) is not distinct from (old.text, old.due, old.assignee, old.done) then
    new.updated_by := old.updated_by;   -- nothing changed, so nothing happened
    new.updated_at := old.updated_at;
  else
    new.updated_by := auth.uid();
    new.updated_at := now();
  end if;
  return new;
end $$;
create trigger tasks_before before insert or update on public.tasks for each row execute function private.tasks_before();

create function private.audit_task() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  claims jsonb;
  act text;
  bits text[] := '{}';
begin
  if tg_op = 'UPDATE' and (new.text, new.due, new.assignee, new.done) is not distinct from (old.text, old.due, old.assignee, old.done) then
    return null;
  end if;
  begin
    claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    claims := null;
  end;
  if tg_op = 'INSERT' then act := 'task_added';
  elsif new.done is distinct from old.done then act := case when new.done then 'task_done' else 'task_reopened' end;
  else
    act := 'task_changed';
    if new.due is distinct from old.due then bits := array_append(bits, 'due date'); end if;
    if new.assignee is distinct from old.assignee then bits := array_append(bits, 'owner'); end if;
    if new.text is distinct from old.text then bits := array_append(bits, 'text'); end if;
  end if;
  insert into public.audit (at, actor, actor_role, table_name, op, row_key, household_id, action, detail, spec_version, change)
  values (now(), auth.uid(), coalesce(claims ->> 'role', 'database'), 'tasks', tg_op, new.id, new.household_id, act,
          left(new.text, 200) || case when array_length(bits, 1) > 0 then ' (' || array_to_string(bits, ', ') || ')' else '' end, null,
          case tg_op when 'INSERT' then jsonb_build_object('new', to_jsonb(new))
                     else jsonb_build_object('old', jsonb_build_object('text', old.text, 'due', old.due, 'assignee', old.assignee, 'done', old.done),
                                             'new', jsonb_build_object('text', new.text, 'due', new.due, 'assignee', new.assignee, 'done', new.done)) end);
  return null;
end $$;
create trigger tasks_audit after insert or update on public.tasks for each row execute function private.audit_task();
create trigger tasks_no_truncate before truncate on public.tasks for each statement execute function private.refuse_truncate();

revoke all on function private.tasks_before(), private.audit_task() from public;
revoke all on public.tasks from public, anon, authenticated, service_role;
grant select on public.tasks to authenticated;
grant insert (id, household_id, text, kind, due, assignee, done), update (text, due, assignee, done) on public.tasks to authenticated;
alter table public.tasks enable row level security;
create policy tasks_read on public.tasks for select to authenticated using ((select private.my_role()) is not null);
create policy tasks_insert on public.tasks for insert to authenticated with check ((select private.at_least('contributor')));
create policy tasks_update on public.tasks for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.tasks;
  end if;
end $$;
