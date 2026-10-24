# 0008: Inside Claude first, then Supabase in London and Netlify, with the database holding the rules

Date: 21 October 2026. Status: Accepted (open to the owner; nothing is deployed).

## Context

The TA tools needed a shared store, sign-in, drafting and downloads. The build session's brief
was to run them inside Claude first and move them to hosting of their own later (decision log
line 20).

## Decision

- The tools run inside Claude first, as artifact pages, with AI drafting through the page's own
  call to Claude (no API key), and move to Supabase and Netlify later, with drafting through a
  Deno edge function. The move-on rules are language-neutral files under `tamarket/spec/`; the
  Python modules are the reference and the shared cases are what a port must pass (decision log
  line 20).
- The hosted store is Supabase Postgres in London. The database, not the page, sets every author
  (from `auth.uid()`) and every time (`now()`), writes the audit log from triggers on every
  insert, update or delete of the other tables, and refuses any update, delete or truncate of
  versions, decisions, drafts, page events and the audit log, the dashboard included. Reading
  needs an active member, not only a signed-in account, because a Supabase project accepts new
  sign-ups unless they are turned off (decision log line 32).
- Drafting on the hosted site goes through the `draft-plan` function with the owner's key, read
  from the function's secrets. It builds the prompt from its own copy of the record, drafts only
  for a member at Contributor or above within a cap per person per hour, screens with the
  fd-core patterns and the private deny list, records every draft before returning it and never
  returns a draft that fails the screen. The default model is `claude-sonnet-5-5`, open to the
  owner (decision log line 36).
- The page does not change for hosting: `app/src/hosted.js` stands in for the page's
  `claude.use(...)` calls. Sign-in is an emailed code for invited people only. The Supabase
  client is pinned and checked by its SHA-384, the Content-Security-Policy allows only the page's
  own inline code by hash, that script and the project's API, and the build takes only a
  publishable key (decision log line 37).

## Options ruled out

None recorded for the hosting itself. ADR 0010 records the options ruled out for how reviewer
notes reach the drafting function.

## Consequences

- Nothing is deployed: no Supabase project, no Netlify site, no secret and no API key exists
  for it. The kit is built and tested on this machine: the migration on a local Postgres 16
  with a stand-in for Supabase's auth, `hosted.js` in node against a fake client and in headless
  Chromium against fakes of the project's endpoints, and the function under Deno 2.9 against a
  faked project and a faked Claude (`hosted/README.md` lines 280-302) [Certain, as that file
  records].
- That the services behave as the fakes do is [Likely] until the checks in
  `hosted/README.md` step 10 run on a live project (decision log, deferred line 67).
- Staff names and emails sit in the hosted tables and the audit log, and need the data
  protection officer's agreement first (decision log, deferred line 68).
- Lessons (commit c165ef6) run in the pilot only: the hosted build has no lessons yet, and the
  page does not compile the memory core's rules when `app/src/hosted.js` has loaded [Certain, as
  the commit records and the code shows].
- The owner holds the steps: create the project in London, run the migration, close sign-up,
  build, set the function's secrets, deploy, invite colleagues by role and run the checks
  (`hosted/README.md` steps 1 to 10).

## Where recorded

Line numbers are as at commit bf88a6e.

- `docs/decision_log.md` lines 20, 32, 35, 36, 37 and 38; deferred lines 66, 67 and 68.
- `hosted/README.md` (all of it; the tests at lines 234-248, the limits at 250-319).
- `app/README.md` lines 13-27.
- `supabase/migrations/`, `supabase/functions/draft-plan/`, `app/src/hosted.js`,
  `scripts/build_app.py --target hosted`; `tests/test_hosted_db.py`, `tests/test_hosted_js.py`.
- Commits 779d3f6 (the spec), d14b587 (the hosted kit), e2ece8d and 07e5f43.
