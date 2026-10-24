# Hosting the Move forward planner on Supabase and Netlify

The kit for moving the Move forward planner (app/) from the pilot inside Claude to a site of its own:
Supabase Postgres in London for the shared store, sign-in and the drafting function, and Netlify
for the page. It is built and tested on this machine. **Nothing is deployed**: no Supabase project,
no Netlify site, no secret and no API key exists for it yet. Everything below is for the owner to
do, in order.

Synthetic records only: every household is made up from a seed, none is a real person, and the
database refuses any household id that is not SYN-0001 to SYN-9999. Plans are suggestions for an
officer to approve, never decisions. Each statutory decision (an offer, a referral, ending a duty)
is made and recorded outside the planner.

## What runs where

| Part | Inside Claude (the pilot) | Hosted (this kit) |
|---|---|---|
| Page | `app/dist`, published as an artifact | `app/dist-hosted` on Netlify: the same page, unchanged, after the Supabase client and `app/src/hosted.js` |
| Shared store | The artifact's database, with its path rules | Supabase Postgres (London), with row-level security and triggers (`supabase/migrations/`) |
| Sign-in and roles | The artifact's sharing levels | Supabase Auth (an emailed code, invited people only), roles in `public.members` |
| Drafting | Claude on the viewer's own usage | The `draft-plan` Edge Function, with the owner's Anthropic key, screening with the private deny list |
| Audit log | Written by the page under each person's path | Written by the database from triggers; nobody can change or delete it |
| Downloads | The artifact's downloads | A browser download |

## What is in the kit

| Path | What it is |
|---|---|
| `supabase/migrations/20261021000000_move_on_planner.sql` | Tables, roles, row-level security, the triggers that set who and when, check four-eyes and fingerprints, and write the audit log |
| `supabase/migrations/20261022130000_move_on_followups.sql` | Follow-ups (phase 6) |
| `supabase/migrations/20261022160000_move_forward_clocks.sql` | Notices and reviews (phase 6.5), and the handover as a page event |
| `supabase/functions/draft-plan/index.ts` | The drafting function for Supabase (Deno); `core.mjs` holds its logic |
| `supabase/functions/draft-plan/_bundle/` | Written by the build, not in git: the caseload, prompt, screen rules and fd-core patterns the function uses |
| `app/src/hosted.js` | The page's `claude.use(...)` over Supabase, and the sign-in bar |
| `scripts/build_app.py --target hosted` | Writes `app/dist-hosted/` (not in git) and the function's bundle |
| `tests/test_hosted_db.py`, `tests/test_hosted_js.py` | The tests (see the last section) |

How the page's records map to tables is set out at the top of the migration and of `hosted.js`.

## Before you start

- A Supabase account and organisation, a Netlify account, and an Anthropic Console account where
  you can create an API key and set a spend limit.
- This repo with its tools: Python with the repo's dependencies and fd-core (`pip install -e
  ../fd-core`), and node. The Supabase and Netlify command-line tools run through npx at pinned
  versions, so nothing needs installing globally. Set the versions once in your shell:
  ```
  SUPABASE_CLI=2.120.0
  NETLIFY_CLI=27.11.2
  ```
- The list of people and the role each should have (see step 9).
- A decision on who holds the Anthropic key and pays for it. The key never goes in the repo, the
  page or a message: only into the Supabase dashboard.

## Step 1. Create the Supabase project in London

1. In the Supabase dashboard, create a project in your organisation. Choose the **specific region
   London (eu-west-2)**, not a general "Europe" grouping, which can also mean another country
   [Likely: the label in the dashboard].
2. Set a strong database password and keep it in your password manager.
3. Note the project's URL (`https://<project-ref>.supabase.co`) and, under the API keys settings,
   its **publishable key** (`sb_publishable_...`). The publishable key is the only key that ever
   goes into the page. Never copy the secret key (`sb_secret_...`) or the legacy service-role key
   anywhere.

## Step 2. Run the migration

Either way works; use one.

- **Dashboard**: open the SQL Editor and run each file in `supabase/migrations/` once, whole, in
  the order of their names (the first is `20261021000000_move_on_planner.sql`).
- **Command line** [Likely: CLI behaviour not run here]:
  ```
  npx supabase@$SUPABASE_CLI login
  npx supabase@$SUPABASE_CLI init                       # once, if supabase/config.toml does not exist
  npx supabase@$SUPABASE_CLI link --project-ref <project-ref>
  npx supabase@$SUPABASE_CLI db push
  ```

Then check, in the Table Editor, that the sixteen tables exist with row-level security on, and in
Database, Publications, that `supabase_realtime` includes members, versions, decisions, audit,
files, checks, moves, config, tasks, notices, reviews and monitor_decisions. The security advisor will note that `public.deny_terms` has
row-level security on and no policy: that is on purpose, so that only the drafting function reads it.

## Step 3. Make yourself the owner

1. In Authentication, Users, add yourself (send an invitation or create the user).
2. In the SQL Editor, give yourself the owner role. The name is what colleagues will see in the
   audit log and in plan packs:
   ```sql
   insert into public.members (user_id, role, display_name)
   select id, 'owner', '<your name as colleagues know it>' from auth.users where email = '<your work email>';
   ```

## Step 4. Close sign-up and set up the sign-in email

1. In the Authentication settings, turn off new sign-ups, so that only people you invite can sign
   in [Likely: the setting's label]. The page also asks Supabase never to create an account.
2. In Authentication, Email Templates, edit the **Magic Link** template so that it shows the code:
   add `{{ .Token }}`, for example "Your sign-in code for the Move forward planner is {{ .Token }}". The
   page asks for that code.
3. Supabase's built-in email sender has low rate limits; for more than a handful of people, set up
   your own SMTP sender in the Authentication settings [Likely].

## Step 5. Build the hosted folder

```
python scripts/build_app.py --target hosted --supabase-url https://<project-ref>.supabase.co --publishable-key sb_publishable_...
```

This writes `app/dist-hosted/` and `supabase/functions/draft-plan/_bundle/` from the same build.
The build refuses a secret or service-role key, and a URL that is not https. Without the two
settings it writes placeholders, and the page says it has no project settings. Add `--clean` to
refuse to build from files that are not committed, so the manifest names a commit you can find.

## Step 6. Set the function's secrets and deploy it

1. In the Anthropic Console, create an API key for this project only, and set a monthly spend
   limit on its workspace.
2. In Supabase, Edge Functions, Secrets, add:

   | Secret | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | The key from 1 (required) |
   | `DENY_LIST` | The private deny list, one term per line (optional; or add terms to `public.deny_terms` from the SQL Editor) |
   | `ALLOWED_ORIGINS` | The Netlify site's address, once you have it (step 8) |
   | `ANTHROPIC_MODEL` | Optional; the function uses `claude-sonnet-5-5` without it |
   | `DRAFTS_PER_HOUR` | Optional cap per person; 30 without it |

   Supabase gives every function its URL and server key itself.
3. Deploy the function, with JWT checking at the gateway off, because the function checks the
   caller's session itself and Supabase's gateway check does not take the new key types
   [Likely: CLI behaviour not run here]:
   ```
   npx supabase@$SUPABASE_CLI functions deploy draft-plan --no-verify-jwt --project-ref <project-ref>
   ```

The function drafts only for a signed-in member at Contributor or above, only for a synthetic
record in its own copy of the caseload, only when the page's prompt is the one it builds itself
(otherwise it answers that the builds differ), and never more than the hourly cap. It reads the
household's reviewer notes from `public.decisions` itself, never from the caller, with the
version each decision names and the four-eyes setting, so it starts the notes again after the
same approval the page counts; a note the private deny list would hold back stops the draft
(`note_blocked`) instead of reaching Claude. Each version row keeps the notes it answers
(`public.versions.review`), and the database refuses a version whose plan does not answer each
of them once. Every draft is
recorded in `public.drafts` (who, which household, passed or not, which rules, token counts, never
the text) before anything is returned. A draft that fails the screen is never returned.

## Step 7. Deploy the site to Netlify

Deploy the built folder, not the repo: the build needs fd-core and writes files that stay out of git.

- **Dashboard**: add a new site, deploy manually, and drop the `app/dist-hosted` folder.
- **Command line** [Likely: CLI behaviour not run here]:
  ```
  npx netlify-cli@$NETLIFY_CLI deploy --dir app/dist-hosted --prod
  ```

The folder carries a `_headers` file: a Content-Security-Policy that lets the page run only its own
inline code (by SHA-256), the pinned Supabase client and calls to your project, with no framing and
no referrer. It also carries `robots.txt`, which asks search engines to keep out.

## Step 8. Point Supabase and the function at the site

1. In Authentication, URL Configuration, set the Site URL and the redirect URL to the Netlify address.
2. Set the function's `ALLOWED_ORIGINS` secret to the same address (comma-separated if there is
   more than one). No redeploy is needed for secrets.

## Step 9. Invite colleagues by role

| Role | Can |
|---|---|
| viewer | Read everything shared; export plan packs and the audit log |
| contributor | Also take households, draft (with Claude or the template), save and submit versions, work the checks and record progress |
| editor | Also approve, return, reject and reopen plans, and turn four-eyes on or off |
| owner | Also add members and change their roles (from the SQL Editor or the API) |

For each person: add them in Authentication, Users (send an invitation), then in the SQL Editor:

```sql
insert into public.members (user_id, role, display_name)
select id, 'contributor', '<their name as colleagues know it>' from auth.users where email = '<their work email>';
```

To change a role, `update public.members set role = 'editor' where user_id = '<their id>';`. To
remove access, `update public.members set active = false where user_id = '<their id>';`. Their
records keep their name. Deleting the account of anyone in `public.members` is refused, by design,
so that no record loses its author.

## Step 10. What to check first

Use two colleagues, or two accounts of your own: one at Contributor and one at Editor, besides
yours as owner. The owner meets every level, so the owner alone cannot test the roles.

1. **Sign-in.** Open the site. Sign in as the Contributor with the emailed code. The bar says
   "Signed in as ..., contributor" and the store chip says "Shared store". An account that is
   signed in but not in `public.members` sees that it has not been given access, and nothing else.
2. **A plan through the workflow.** As the Contributor, take a household, start from the template,
   save and submit. The Contributor is not offered Approve. As the Editor, open the household and
   approve. The audit log shows each step under the right name.
3. **Four-eyes.** As the Editor, save and submit a version of another household, then look for
   Approve: it is not offered for your own version. The database refuses it too, whatever the page
   does. To see that, run this in the SQL Editor with the Editor's id and, from `public.versions`,
   the `key`, `household_id` and `sha256` of a version they saved; it rolls back either way
   [Likely: that the SQL Editor lets you take the authenticated role like this]:
   ```sql
   begin;
   set local role authenticated;
   set local request.jwt.claims to '{"sub": "<editor user id>", "role": "authenticated"}';
   insert into public.decisions (id, household_id, decision, version_id, plan_sha256)
   values ('check~four-eyes', '<household_id>', 'approved', '<key>', '<sha256>');
   rollback;
   ```
   Expected: "four-eyes is on: the person who saved this version cannot approve it". The same with
   the Contributor's id gives "only an Editor or the owner can record a decision".
4. **The audit log cannot be changed.** In the SQL Editor, `update public.audit set detail = 'x'
   where id = 1;` is refused ("audit is insert-only"), and so is a delete, even for you.
5. **Drafting.** As the Contributor, draft with Claude once. A row appears in `public.drafts`, the
   function's logs show the household id and the rules only, and a plan appears in the page for
   the officer to read. If a draft is stopped by the screen, the bar says which rules it broke and
   the page says the draft did not arrive; draft again or use the template.
6. **The browser console.** No Content-Security-Policy errors, and no integrity error for the
   Supabase script. If the Supabase script is blocked, check that the file jsDelivr serves still
   has the SHA-384 in `scripts/build_app.py` (`curl -s <the URL> | openssl dgst -sha384 -binary | openssl base64 -A`).
7. **Live updates.** With two browsers open, a change in one shows in the other within seconds.

## Changing things later

- After any change to the caseload, the spec, the prompt, the page or `hosted.js`: build with
  `--target hosted` again, then deploy both the function (step 6.3) and the site (step 7). The
  function refuses to draft for a page from a different build.
- A schema change is a new file in `supabase/migrations/`; never edit one that has been run.
- To rotate the Anthropic key, create a new one, replace the secret, then revoke the old one.

## Running the tests

`python -m pytest -q` runs everything that needs only Python, node and Postgres. Two checks run only
when their tools are there:

- the drafting function under Deno: put Deno on the path, or set `TA_DENO` to it;
- the site in a real browser: Playwright with its Chromium (found with `npm root -g`, or set
  `TA_PLAYWRIGHT` to its `index.mjs`), and a copy of the pinned Supabase client:
  ```
  SUPABASE_JS=2.117.2
  npm pack "@supabase/supabase-js@$SUPABASE_JS"
  tar -xzf "supabase-supabase-js-$SUPABASE_JS.tgz" package/dist/umd/supabase.js
  export TA_SUPABASE_UMD="$PWD/package/dist/umd/supabase.js"
  ```
  The test skips unless the file has the SHA-384 the page checks.

## What the database guarantees, and what it does not

Guaranteed by the database, whatever any page or script sends [Certain: tested on Postgres 16,
with a stand-in for Supabase's auth schema and roles]:

- Every author, actor and time is set by the database from the signed-in caller and its clock.
- Every active member reads; a signed-in account that is not a member reads nothing; nobody reads
  without signing in. Only Contributors and up save versions, move the status pointer, work the
  checks and record progress; only Editors and the owner record decisions and change four-eyes;
  only the owner manages members, and cannot change their own role or remove the last owner.
- An approval is refused when four-eyes is on and the approver saved the version, when the SHA-256
  it names is not the version's, when the version is not the one submitted, or when the plan has
  not been submitted again since the last decision. A version is refused unless its SHA-256 is the
  SHA-256 of its plan in the page's canonical JSON, which the tests check against the page's own
  code for every template plan.
- Nobody, the dashboard included, changes or deletes versions, decisions, drafts, page events or
  the audit log, and no audited table can be truncated. Every insert, update or delete of the
  other tables writes an audit row, with the person, the database role and the change.
- Follow-ups (`public.tasks`, migration `20261022130000_move_on_followups.sql`): only Contributors
  and up add one, tick it off or change its text, date or owner; who added and who finished each
  are set by the database; a new owner must be an active member; a follow-up's id and household
  never change; nobody deletes one, and every change writes an audit row.
- Notices and reviews (`public.notices`, `public.reviews`, migration
  `20261022160000_move_forward_clocks.sql`): only Contributors and up record them; the database
  sets who recorded each and when, refuses dates in the future, keeps s.213AA rows per child
  (child_no) and per body, refuses a notice (or information) for a child's GP practice, health
  visiting service or school unless the agreement to that body is on record for that child,
  refuses a notice with no information about that body on record or dated before the agreement or
  that information, keeps a sent s.213AA notice's status and dates fixed (the owner alone corrects
  one, through `public.correct_notice`, below), keeps a body already notified
  among those agreed and the agreement dated no later than any notice sent on it, refuses an answer
  dated before the asking, keeps a review's request date fixed and any longer period on
  or after the statutory date, and audits every change; nobody deletes one. Members may
  update a notice's value columns only, so the client inserts and, on a taken id, updates them.
  The pilot timings have no table: they stay in each browser.

Not guaranteed:

- The table owner (the dashboard's SQL Editor) can still change the file pointer, checks,
  progress, the setting and members; each change is in the audit log with no person and the
  database role [Certain]. The owner could also drop the triggers [Certain]: the audit log is as
  trustworthy as the people who hold the database password.
- The page still trusts itself for what a plan says: the database checks its fingerprint, not its
  words. The screen runs in the page and in the function; the database does not run it [Certain].
- Page events (exports) are reported by the page; the database sets who and when, not whether the
  file was really saved [Certain].

- Monitoring decisions (`public.monitor_decisions`, migration `20261022180000_move_forward_monitor.sql`):
  only Contributors and up decide; an acceptance needs a grade on the six-by-six scale and no
  reason, a rejection a reason from the list and no grade, and "other" a note; who decided and
  when are set by the database; a decision's item never changes; nobody deletes one, and every
  change writes an audit row. The items themselves are published with the page, not stored.

- Correcting a sent s.213AA notice: the Owner calls `public.correct_notice(id, status, sent_on,
  info_on, method, reason)` through the API (`rpc('correct_notice', ...)` with the Owner signed in;
  the SQL editor has no signed-in member, so it cannot). The reason is one of `wrong_date`,
  `not_sent` or `recorded_in_error`, so no free text reaches the audit; every other check on the
  row still applies, and the audit row is `notice_corrected`, with the reason. The page offers no
  button for it. An s.208 notice is not locked and is corrected as any change is, audited.

## What is not built or not tested

- Nothing is deployed, and nothing here has run against a real Supabase project, Netlify or the
  Anthropic API [Certain].
- The migration is tested on a local Postgres 16 with a stand-in for Supabase's `auth.uid()`,
  roles and default grants (`tests/hosted_supabase_stub.sql`). That it behaves the same on
  Supabase is [Likely]; the stand-in copies how Supabase sets `request.jwt.claims` but is not
  Supabase.
- `hosted.js` is tested in node with a fake Supabase client, through the page's own store code,
  and in headless Chromium with the real supabase-js 2.117.2 (loaded past its SHA-384 check) under
  the site's Content-Security-Policy, against a fake of the project's Auth, REST and function
  endpoints: a Contributor and an Editor sign in with an emailed code and take a plan through the
  template, a Claude draft, a draft stopped by the screen, submission and approval, with nothing
  blocked by the policy and no page error [Certain: run in this session]. It has not run against a real
  project, and live updates over Supabase Realtime are untested: the check closes the socket, so
  the page falls back to polling every 20 seconds [Certain]. That the real services behave like
  the fakes is [Likely]. Real email delivery of the code is untested [Certain].
- `index.ts` is type-checked and run end to end under Deno 2.9 against a faked project and a
  faked Claude [Certain]; the test in `tests/test_hosted_js.py` repeats both only where Deno is
  installed. Until the test ran `deno check` (22 October 2026), the claim that it was type-checked
  was wrong: from e2ece8d it failed the check on one type in `core.mjs`, which `deno run` does not
  check; that type is corrected [Certain, from the runs]. It imports nothing from outside its folder, but Supabase's Edge Runtime
  is not Deno 2.9 itself, so that it deploys and runs unchanged is [Likely]. Its calls to the
  project (Auth's user endpoint and four REST calls) follow Supabase's documented headers for the
  new secret key and the legacy service-role key [Likely until run on a project].
- The SHA-384 of the Supabase client was computed from the npm package; that jsDelivr serves the
  same bytes is [Likely] (check 6 above).
- The Content-Security-Policy's hashes are tested to match the page, and Chromium runs the page
  under it with nothing blocked [Certain]; other browsers [Likely] until check 6.
- The Method view tells the two versions apart by whether `app/src/hosted.js` has loaded
  (`window.TaHosted`): on the hosted site it describes the database's rules and limits, drafting by
  the function on the owner's key, and the one script from another site [Certain, from the code;
  not yet seen on a deployed site].
- The page's own limits stay: it reads the records of at most 18 people and the latest 1,000 audit
  entries per person [Certain].
- When a draft fails the screen, the page says the draft did not arrive, because it cannot show
  the function's list of rules without a change to the page; the bar shows the list [Certain].
- The dashboard labels named above, the CLI commands and the region label may differ from what
  Supabase and Netlify show today [Likely].
- Staff names and emails are personal data, in `auth.users`, `public.members` and the audit log.
  The council's data protection officer should agree where the project is hosted, who can open the
  dashboard and how long the log is kept, before anyone outside a test uses it [Likely].
