-- Monitoring decisions (phase 7): what an officer decided about each monitoring item.
--
-- The items themselves are published with the page (data/monitor.json, from monitor/items.jsonl,
-- filed by scripts/monitor.py after fd-core's checks); the database holds only the decision on
-- each, the page's monitor/<item id> record (app/src/page.js, decideItem; app/src/hosted.js maps
-- it here). An item is accepted with a grade on the six-by-six scale or rejected with a reason
-- from a short list; a note is optional, and the page screens it. Any Contributor decides, and
-- may change a decision; the database sets who decided and when, writes the audit log itself,
-- and nobody deletes a row. Nothing reaches a plan unaccepted, and drafting does not read items.

create table public.monitor_decisions (
  id text primary key check (id ~ '^mon-[0-9a-f]{12}$'),
  decision text not null check (decision in ('accepted', 'rejected')),
  grade text check (grade ~ '^[A-F][1-6]$'),
  reason text check (reason in ('not_relevant', 'duplicate', 'superseded', 'unreliable', 'other')),
  note text not null default '' check (char_length(note) <= 240),
  decided_by uuid,
  decided_at timestamptz not null default now(),
  check (decision <> 'accepted' or (grade is not null and reason is null)),
  check (decision <> 'rejected' or (reason is not null and grade is null)),
  check (reason is distinct from 'other' or btrim(note) <> '')
);
comment on table public.monitor_decisions is 'An officer''s decision on a monitoring item: accepted with a grade, or rejected with a reason. Who and when set by the database. No deletes.';

create function private.monitor_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' and new.id <> old.id then
    perform private.refuse('a decision''s item cannot change');
  end if;
  if tg_op = 'UPDATE' and (new.decision, new.grade, new.reason, new.note) is not distinct from (old.decision, old.grade, old.reason, old.note) then
    new.decided_by := old.decided_by; new.decided_at := old.decided_at;   -- nothing changed, so nothing happened
  else
    new.decided_by := auth.uid(); new.decided_at := now();
  end if;
  return new;
end $$;
create trigger monitor_before before insert or update on public.monitor_decisions for each row execute function private.monitor_before();

create function private.audit_monitor() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  claims jsonb;
  act text;
begin
  if tg_op = 'UPDATE' and (new.decision, new.grade, new.reason, new.note) is not distinct from (old.decision, old.grade, old.reason, old.note) then
    return null;
  end if;
  begin
    claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    claims := null;
  end;
  act := case when tg_op = 'UPDATE' then 'monitor_changed' when new.decision = 'accepted' then 'monitor_accepted' else 'monitor_rejected' end;
  insert into public.audit (at, actor, actor_role, table_name, op, row_key, household_id, action, detail, spec_version, change)
  values (now(), auth.uid(), coalesce(claims ->> 'role', 'database'), 'monitor_decisions', tg_op, new.id, null, act,
          new.id || ': ' || new.decision || coalesce(', ' || new.grade, '') || coalesce(', ' || new.reason, ''), null,
          case tg_op when 'INSERT' then jsonb_build_object('new', to_jsonb(new))
                     else jsonb_build_object('old', to_jsonb(old) - 'decided_by' - 'decided_at', 'new', to_jsonb(new) - 'decided_by' - 'decided_at') end);
  return null;
end $$;
create trigger monitor_audit after insert or update on public.monitor_decisions for each row execute function private.audit_monitor();
create trigger monitor_no_truncate before truncate on public.monitor_decisions for each statement execute function private.refuse_truncate();

revoke all on function private.monitor_before(), private.audit_monitor() from public;
revoke all on public.monitor_decisions from public, anon, authenticated, service_role;
grant select on public.monitor_decisions to authenticated;
grant insert (id, decision, grade, reason, note), update (decision, grade, reason, note) on public.monitor_decisions to authenticated;
alter table public.monitor_decisions enable row level security;
create policy monitor_read on public.monitor_decisions for select to authenticated using ((select private.my_role()) is not null);
create policy monitor_insert on public.monitor_decisions for insert to authenticated with check ((select private.at_least('contributor')));
create policy monitor_update on public.monitor_decisions for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.monitor_decisions;
  end if;
end $$;
