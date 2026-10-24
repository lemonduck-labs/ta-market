-- Notices and review clocks (phase 6.5): what an officer says was done about the statutory clocks.
--
-- The page's notices/<id> and reviews/<id> records (app/src/page.js, saveNotice and reviewsPanel;
-- app/src/hosted.js maps them here). The planner sends nothing: a row records that an officer sent
-- a notice, asked a parent, or that a review was asked for and decided, with the date the officer
-- gives. The database sets who recorded each row and when, refuses dates in the future, and writes
-- the audit log itself. Nobody deletes a row. Synthetic records only. The pilot timings stay in
-- each browser and have no table: timing staff is workforce data, for a council and its staff to
-- agree before it is kept.
--
-- s.213AA (Housing Act 1996) is for each child (the DHSC guidance: "A notification will be issued
-- for each child placed in temporary accommodation"), so its rows carry the child's number on the
-- record (child_no, 1 to 9; no name): <household>~c<n>~child is the agreement for child n, asked of
-- the parent, or of a 16 or 17 year old applicant (s.213AA(3)), and recorded body by body
-- (agreed_bodies, declined_bodies); <household>~c<n>~child-<body> is that child's notice to one
-- body, with the day the information about that body arrived (info_on: the 14 days run from it,
-- s.213AA(4)(b)), then sent or no such body. The database refuses a notice to a body not agreed,
-- one with no information on record, and one dated before the agreement or that body's
-- information; once a notice is sent, the agreement cannot drop the body or move after it.
-- <household>~s208 is the notice under s.208.

create table public.notices (
  id text primary key check (id ~ '^SYN-[0-9]{4}~(s208|c[1-9]~child(-gp|-health_visiting|-education)?)$'),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  kind text not null check (kind in ('s208', 'child', 'child-gp', 'child-health_visiting', 'child-education')),
  child_no smallint check (child_no between 1 and 9),
  status text not null check (status in ('sent', 'none', 'info', 'asked', 'agreed', 'refused')),
  sent_on date,
  method text check (method in ('Letter', 'Email', 'Secure online form', 'By hand', 'Other')),
  asked_on date,
  agreed_on date,
  info_on date,
  refused_on date,
  -- The answer for one child, body by body (kind 'child' only): the bodies agreed to the council
  -- notifying, and those not.
  agreed_bodies text[] not null default '{}' check (agreed_bodies <@ array['gp', 'health_visiting', 'education']),
  declined_bodies text[] not null default '{}' check (declined_bodies <@ array['gp', 'health_visiting', 'education']),
  recorded_by uuid,
  recorded_at timestamptz not null default now(),
  check ((kind = 's208') = (child_no is null)),
  check (id = household_id || '~' || case when child_no is null then '' else 'c' || child_no || '~' end || kind),
  check (case kind when 's208' then status = 'sent'
                   when 'child' then status in ('asked', 'agreed', 'refused')
                   else status in ('info', 'sent', 'none') end),
  check (status <> 'sent' or (sent_on is not null and method is not null)),
  check (status <> 'asked' or asked_on is not null),
  check (status <> 'agreed' or agreed_on is not null),
  check (status <> 'refused' or refused_on is not null),
  -- An answer is not dated before the asking.
  check (agreed_on is null or asked_on is null or agreed_on >= asked_on),
  check (refused_on is null or asked_on is null or refused_on >= asked_on),
  -- The information is about one body: it sits on that body's row, and a notice needs it.
  check (info_on is null or kind like 'child-%'),
  check (kind not like 'child-%' or status = 'none' or info_on is not null),
  check (not (agreed_bodies && declined_bodies)),
  check (kind = 'child' or (agreed_bodies = '{}' and declined_bodies = '{}')),
  check (status <> 'agreed' or cardinality(agreed_bodies) > 0),
  check (status not in ('asked', 'refused') or agreed_bodies = '{}')
);
comment on table public.notices is 'What an officer recorded about the s.208 notice and the s.213AA notices for each child of a placement: sent (date, how), information received, no such body, or the parent (or a 16 or 17 year old applicant) asked, and agreed or not body by body. Who and when set by the database. No deletes.';
create index notices_household on public.notices (household_id);

create function private.notices_before() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  d date;
  c public.notices;
begin
  foreach d in array array[new.sent_on, new.asked_on, new.agreed_on, new.info_on, new.refused_on] loop
    if d is not null and d > current_date then
      perform private.refuse('a notice''s dates cannot be in the future');
    end if;
  end loop;
  if tg_op = 'UPDATE' and (new.id <> old.id or new.household_id <> old.household_id or new.kind <> old.kind or new.child_no is distinct from old.child_no) then
    perform private.refuse('a notice''s id, household, child and kind cannot change');
  end if;
  -- A child's notice once sent stays sent, on its date and its information's date: the locks on the
  -- child's agreement below rest on it. Only the owner corrects one, through public.correct_notice,
  -- which marks the row it is correcting for this transaction and writes the reason to the audit.
  if tg_op = 'UPDATE' and old.kind like 'child-%' and old.status = 'sent'
     and (new.status, new.sent_on, new.info_on) is distinct from (old.status, old.sent_on, old.info_on)
     and coalesce(current_setting('ta.correcting', true), '') <> old.id then
    perform private.refuse('a child''s notice once sent cannot change its status, its date or its information''s date');
  end if;
  if new.kind like 'child-%' and new.status in ('info', 'sent') then
    select * into c from public.notices where id = new.household_id || '~c' || new.child_no || '~child';
    -- The agreement is per child and per body: information is taken, and a notice goes, only for a
    -- body agreed to.
    if c.id is null or c.status <> 'agreed' or not (substr(new.kind, 7) = any(c.agreed_bodies)) then
      perform private.refuse('a notice to a child''s GP practice, health visiting service or school needs the agreement to that body on record for that child (s.213AA)');
    end if;
    -- The 14 days run from the latest of the agreement, this body's information and the placement:
    -- a notice is never dated before the first two (greatest() would pass over a missing date, so
    -- the information is required by a check above).
    if new.status = 'sent' and new.sent_on < greatest(c.agreed_on, new.info_on) then
      perform private.refuse('a child''s notice cannot be sent before the agreement and the information about that body (s.213AA(4))');
    end if;
  end if;
  -- Once a body is notified, the child's agreement keeps that body and cannot be dated after the notice.
  if new.kind = 'child' and exists (
       select 1 from public.notices n where n.household_id = new.household_id and n.child_no = new.child_no and n.kind like 'child-%' and n.status = 'sent'
         and (new.status <> 'agreed' or not (substr(n.kind, 7) = any(new.agreed_bodies)))) then
    perform private.refuse('a body already notified must stay among the bodies agreed');
  end if;
  if new.kind = 'child' and exists (
       select 1 from public.notices n where n.household_id = new.household_id and n.child_no = new.child_no and n.kind like 'child-%' and n.status = 'sent'
         and n.sent_on < new.agreed_on) then
    perform private.refuse('the agreement cannot be dated after a notice already sent on it');
  end if;
  new.recorded_by := auth.uid();
  new.recorded_at := now();
  return new;
end $$;
create trigger notices_before before insert or update on public.notices for each row execute function private.notices_before();

create function private.audit_notice() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  claims jsonb;
  act text;
begin
  if tg_op = 'UPDATE' and (new.status, new.sent_on, new.method, new.asked_on, new.agreed_on, new.info_on, new.refused_on, new.agreed_bodies, new.declined_bodies)
     is not distinct from (old.status, old.sent_on, old.method, old.asked_on, old.agreed_on, old.info_on, old.refused_on, old.agreed_bodies, old.declined_bodies) then
    return null;
  end if;
  begin
    claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    claims := null;
  end;
  -- A notice is recorded when it first becomes sent (or no such body); the information step creates
  -- a body's row first, so for s.213AA that is usually an update.
  act := case when coalesce(current_setting('ta.correcting', true), '') = new.id then 'notice_corrected'
              when new.kind = 'child' then 'consent_recorded' when new.status = 'info' then 'notice_info_recorded'
              when new.status in ('sent', 'none') and (tg_op = 'INSERT' or old.status is distinct from new.status) then 'notice_recorded'
              else 'notice_changed' end;
  insert into public.audit (at, actor, actor_role, table_name, op, row_key, household_id, action, detail, spec_version, change)
  values (now(), auth.uid(), coalesce(claims ->> 'role', 'database'), 'notices', tg_op, new.id, new.household_id, act,
          coalesce('child ' || new.child_no || ' ', '') || new.kind || ': ' || new.status || coalesce(' ' || coalesce(new.sent_on, new.info_on, new.refused_on, new.agreed_on, new.asked_on)::text, '')
            || case when new.kind = 'child' and new.status = 'agreed' then ' (' || array_to_string(new.agreed_bodies, ', ')
                    || coalesce('; not ' || nullif(array_to_string(new.declined_bodies, ', '), ''), '') || ')' else '' end
            || case when coalesce(current_setting('ta.correcting', true), '') = new.id then ' (corrected by the owner: ' || current_setting('ta.correcting_reason', true) || ')' else '' end, null,
          case tg_op when 'INSERT' then jsonb_build_object('new', to_jsonb(new))
                     else jsonb_build_object('old', to_jsonb(old) - 'recorded_by' - 'recorded_at', 'new', to_jsonb(new) - 'recorded_by' - 'recorded_at') end);
  return null;
end $$;
create trigger notices_audit after insert or update on public.notices for each row execute function private.audit_notice();

-- The owner's correction of a sent s.213AA notice (a mistyped date, a notice recorded that was not
-- sent): the only way past the lock above. The reason is one of a fixed list, so no free text
-- reaches the audit; who and when are set as for any change, and the audit row says "corrected".
create function public.correct_notice(p_id text, p_status text, p_sent_on date, p_info_on date, p_method text, p_reason text) returns void
language plpgsql security definer set search_path = '' as $$
declare
  n public.notices;
begin
  if not (select private.at_least('owner')) then
    perform private.refuse('only the owner corrects a sent notice');
  end if;
  if p_reason is null or p_reason not in ('wrong_date', 'not_sent', 'recorded_in_error') then
    perform private.refuse('a correction needs its reason: wrong_date, not_sent or recorded_in_error');
  end if;
  select * into n from public.notices where id = p_id;
  if n.id is null or n.kind not like 'child-%' or n.status <> 'sent' then
    perform private.refuse('only a sent s.213AA notice is corrected this way');
  end if;
  perform set_config('ta.correcting', p_id, true);
  perform set_config('ta.correcting_reason', p_reason, true);
  update public.notices set status = p_status, sent_on = p_sent_on, info_on = p_info_on, method = p_method where id = p_id;
  perform set_config('ta.correcting', '', true);
  perform set_config('ta.correcting_reason', '', true);
end $$;
comment on function public.correct_notice(text, text, date, date, text, text) is 'The owner corrects a sent s.213AA notice, with a reason from a fixed list; audited as notice_corrected. Every other check on the row still applies.';
revoke all on function public.correct_notice(text, text, date, date, text, text) from public, anon;
grant execute on function public.correct_notice(text, text, date, date, text, text) to authenticated;
create trigger notices_no_truncate before truncate on public.notices for each statement execute function private.refuse_truncate();

create table public.reviews (
  id text primary key check (id ~ '^review~[0-9a-z]{1,12}~[0-9a-z]{1,8}$'),
  household_id text not null check (household_id ~ '^SYN-[0-9]{4}$'),
  requested_on date not null,
  assignee uuid,
  agreed_to date,
  decided_on date,
  decided_by uuid,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_by uuid,
  updated_at timestamptz not null default now(),
  -- A longer period agreed in writing ends on or after the statutory date: the last day of eight
  -- weeks beginning with the request (SI 2018/223 reg. 9(1)(b)), the request day plus 55.
  check (agreed_to is null or agreed_to >= requested_on + 55),
  check (decided_on is null or decided_on >= requested_on)
);
comment on table public.reviews is 'Review requests on a household (s.202) decided in eight weeks: when asked, the owner, any longer period agreed in writing, and when the decision was notified. The decision is due eight weeks beginning with the request (SI 2018/223 reg. 9(1)(b)); reviews with other periods are not tracked here. No deletes.';
create index reviews_household on public.reviews (household_id);

create function private.reviews_before() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.requested_on > current_date or (new.decided_on is not null and new.decided_on > current_date) then
    perform private.refuse('a review''s dates cannot be in the future');
  end if;
  if new.assignee is not null and (tg_op = 'INSERT' or new.assignee is distinct from old.assignee)
     and not exists (select 1 from public.members m where m.user_id = new.assignee and m.active) then
    perform private.refuse('a review''s owner must be an active member');
  end if;
  if tg_op = 'INSERT' then
    new.created_by := auth.uid(); new.created_at := now();
    new.updated_by := auth.uid(); new.updated_at := now();
    new.decided_by := case when new.decided_on is not null then auth.uid() end;
    return new;
  end if;
  if new.id <> old.id or new.household_id <> old.household_id or new.requested_on <> old.requested_on then
    perform private.refuse('a review''s id, household and request date cannot change');
  end if;
  new.created_by := old.created_by; new.created_at := old.created_at;
  new.decided_by := case when new.decided_on is distinct from old.decided_on then (case when new.decided_on is not null then auth.uid() end) else old.decided_by end;
  if (new.assignee, new.agreed_to, new.decided_on) is not distinct from (old.assignee, old.agreed_to, old.decided_on) then
    new.updated_by := old.updated_by; new.updated_at := old.updated_at;
  else
    new.updated_by := auth.uid(); new.updated_at := now();
  end if;
  return new;
end $$;
create trigger reviews_before before insert or update on public.reviews for each row execute function private.reviews_before();

create function private.audit_review() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  claims jsonb;
  act text;
begin
  if tg_op = 'UPDATE' and (new.assignee, new.agreed_to, new.decided_on) is not distinct from (old.assignee, old.agreed_to, old.decided_on) then
    return null;
  end if;
  begin
    claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    claims := null;
  end;
  act := case when tg_op = 'INSERT' then 'review_requested'
              when new.decided_on is distinct from old.decided_on then 'review_decided'
              when new.agreed_to is distinct from old.agreed_to then 'review_extended'
              else 'review_changed' end;
  insert into public.audit (at, actor, actor_role, table_name, op, row_key, household_id, action, detail, spec_version, change)
  values (now(), auth.uid(), coalesce(claims ->> 'role', 'database'), 'reviews', tg_op, new.id, new.household_id, act,
          'requested ' || new.requested_on::text || coalesce(', decided ' || new.decided_on::text, '') || coalesce(', to ' || new.agreed_to::text, ''), null,
          case tg_op when 'INSERT' then jsonb_build_object('new', to_jsonb(new))
                     else jsonb_build_object('old', jsonb_build_object('assignee', old.assignee, 'agreed_to', old.agreed_to, 'decided_on', old.decided_on),
                                             'new', jsonb_build_object('assignee', new.assignee, 'agreed_to', new.agreed_to, 'decided_on', new.decided_on)) end);
  return null;
end $$;
create trigger reviews_audit after insert or update on public.reviews for each row execute function private.audit_review();
create trigger reviews_no_truncate before truncate on public.reviews for each statement execute function private.refuse_truncate();

-- Saving a handover changes no table: it is a page event, like an export.
alter table public.events drop constraint events_action_check;
alter table public.events add constraint events_action_check check (action in ('pack_exported', 'audit_exported', 'handover_exported'));

revoke all on function private.notices_before(), private.audit_notice(), private.reviews_before(), private.audit_review() from public;
revoke all on public.notices, public.reviews from public, anon, authenticated, service_role;
grant select on public.notices, public.reviews to authenticated;
-- Value columns only on update: the client inserts, and on a duplicate id updates these (a PostgREST
-- upsert would also set id, household_id and kind, which nobody may update).
grant insert (id, household_id, kind, child_no, status, sent_on, method, asked_on, agreed_on, info_on, refused_on, agreed_bodies, declined_bodies),
      update (status, sent_on, method, asked_on, agreed_on, info_on, refused_on, agreed_bodies, declined_bodies) on public.notices to authenticated;
grant insert (id, household_id, requested_on, assignee, agreed_to, decided_on),
      update (assignee, agreed_to, decided_on) on public.reviews to authenticated;
alter table public.notices enable row level security;
alter table public.reviews enable row level security;
create policy notices_read on public.notices for select to authenticated using ((select private.my_role()) is not null);
create policy notices_insert on public.notices for insert to authenticated with check ((select private.at_least('contributor')));
create policy notices_update on public.notices for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));
create policy reviews_read on public.reviews for select to authenticated using ((select private.my_role()) is not null);
create policy reviews_insert on public.reviews for insert to authenticated with check ((select private.at_least('contributor')));
create policy reviews_update on public.reviews for update to authenticated using ((select private.at_least('contributor'))) with check ((select private.at_least('contributor')));

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.notices;
    alter publication supabase_realtime add table public.reviews;
  end if;
end $$;
