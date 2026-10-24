# Move forward planner (phase 2)

The working tool on synthetic records: a caseload of 200 made-up households in temporary
accommodation; a file for each with the pathways and a selection of the checks that legislation
and MHCLG guidance give for its record (not the full code); a move-forward plan drafted with Claude or from a template, edited, and approved
by a second officer; the checks worked through; progress recorded; a scenario calculator; an
audit log; and the method.

Synthetic records only: every household is made up from a seed and none is a real person.
Plans are suggestions for an officer to approve, never decisions. Each statutory decision (an
offer, a referral, ending a duty) is made and recorded outside the planner.

## What runs where

| Part | Inside Claude (the pilot) | Hosted (built and tested here, not deployed: hosted/README.md) |
|---|---|---|
| Page | `app/dist`, published as an artifact | `app/dist-hosted` on Netlify: the same page, after the Supabase client and `app/src/hosted.js` |
| Shared store | The artifact's database (`db`), with the rules below | Supabase Postgres, London region, with row-level security |
| Sign-in and roles | The artifact's sharing levels (`user`) | Supabase Auth (an emailed code, invited people only), roles in `public.members` |
| Drafting | Claude on the viewer's own usage (`sample`) | The `draft-plan` Supabase Edge Function (Deno) with the owner's key, running the same `screen.mjs` with the private deny list |
| Downloads | The artifact's `downloads` | A browser download |

The page reaches all four through `claude.use(name)` and works without each of them: with no
store it runs in demo mode (changes stay in the tab), with no drafting it offers the template,
with no downloads it hides the export buttons. It loads nothing from other sites: no fonts, no
scripts, no tracking. The hosted build adds one script from another site, the Supabase client,
at a pinned version checked by its SHA-384.

## Getting around

The page runs fd-core's shared shell (`fdcore/shell.mjs`, inlined as `FdShell`), as the radar's
workspace does. The sidebar lists queues named for the job, with counts: Plans to approve (plans
awaiting approval that this officer may approve, which with four-eyes on leaves out a version
they saved), Returned to me (returned plans whose returned version they saved) and My
households; then three views of the caseload, Family in B&B, Out of district and Two years or
more in TA (104 weeks or more); the scenario and Lessons; and Method and the audit log. The whole
caseload is grouped by what each household needs next. A household opens with its place in the
list it came from ("2 of 67"), the previous and next household a key away, chips for its weeks in
TA, the checks it raises, its support needs, its routes out and the checks worked through, and a
line saying where its plan stands. The top bar shows where you are. Ctrl or Cmd + K, or /,
searches households (by record id, type of accommodation, check or route out) and pages; j and k
move through a list, or between households on a household; g then a letter goes to a page; ? lists
the keys. Below 900 pixels wide the sidebar becomes a drawer.

Each queue, view and page has its own link, the artifact's link plus `#review`, `#returned`,
`#mine`, `#bnb`, `#ood`, `#long`, `#caseload`, `#scenario`, `#lessons`, `#method` or `#audit`; a
household is `#file-SYN-nnnn`.

## Build

`python scripts/build_app.py`:

1. copies the code the page runs into `app/index.html`, between its markers: the spec ports
   `tamarket/spec/screen.mjs`, `scenario.mjs` and `prompt.mjs` as `TaScreen`, `TaScenario` and
   `TaPrompt`, then `app/src/template.js` (`TaTemplate`) and `app/src/page.js`. The page in git
   is the page that is published; `--check` fails if it is out of date.
2. writes `app/dist/` (gitignored): the page; `data/caseload.json` (the caseload unchanged);
   `spec/` (the screen rules, schema, pathways, prompt and scenario cases unchanged, and
   `fdcore_patterns.json` generated from fd-core, which stays out of git because it lists the
   words the screen blocks); and `data/manifest.json` with the commit, any inputs not committed
   as they are, the fd-core commit, the spec version and the SHA-256 of every file. The page
   checks each file against the manifest when it loads it, and will not draft or save plans
   if one does not match. `--clean` refuses to build from inputs that are not committed.

`tests/test_app.py` runs the code inside `app/index.html` (with node) against the shared screen
and scenario cases, checks that it gives Python's suggestions and drafting prompt for all 200
records and reads every drafting reply as `moveon.parse_reply` does, and checks that the
template plan passes both screens for every record with nothing cut to fit the schema.

## Records

| Path | Holds | Who can write it |
|---|---|---|
| `members/{id}` | That a person has worked in the planner (written on their first change) | That person |
| `versions/{id}/v/{version}` | Each plan version they saved: the screened plan, its SHA-256, its source (Claude, template, edited), the SHA-256 of the prompt for a Claude draft, the reviewer notes it answered and the lessons in front of its drafter | That person, at Contributor or above |
| `decisions/{id}/d/{decision}` | Each decision they made: approved, returned, rejected or reopened, with the version, its SHA-256 and the four-eyes setting; a return can carry a lesson (its scope and SHA-256); a lesson approved, not kept or retired, with the lesson's SHA-256 and a reason | That person, at Editor or above |
| `audit/{id}/e/{event}` | Every action they took: when, which household, what | That person |
| `files/{household}` | The status pointer (drafting or submitted), the current version, who has the household | Contributors and up |
| `checks/{household}` | Each check's state, who and when | Contributors and up |
| `moves/{household}` | Progress: the stage, the pathway, a screened note | Contributors and up |
| `notices/{household}~s208`, `notices/{household}~c{n}~child`, `notices/{household}~c{n}~child-{body}` | The s.208 notice (sent: date, how); for child n (numbered, never named), the answer, asked of the parent or of a 16 or 17 year old applicant, agreed or not body by body (`agreed_bodies`, `declined_bodies`); and that child's notice to one body: when the information about it arrived (`info_on`), then sent or no such body | Contributors and up |
| `reviews/{id}` | A review request: when, the owner, a longer period agreed, when the decision was notified | Contributors and up |
| `config/workflow` | Four-eyes on or off | Editors and the owner |
| `data/users/{id}/draft_{household}` | A person's unsaved, screened draft | That person only; nobody else can read it |

The rules declared at publish:

```json
{"rules": [
  {"path": "members", "read": "view", "write": "owner"}, {"path": "members/{self}", "write": "interact"},
  {"path": "versions", "read": "view", "write": "owner"}, {"path": "versions/{self}", "write": "interact"},
  {"path": "decisions", "read": "view", "write": "owner"}, {"path": "decisions/{self}", "write": "admin"},
  {"path": "audit", "read": "view", "write": "owner"}, {"path": "audit/{self}", "write": "interact"},
  {"path": "config", "write": "admin"}
]}
```

So the path, not a field anyone can type, says who saved a version, who decided and who did
what. A plan counts as approved only when a decision under an editor's path names a version
whose text still matches the SHA-256 saved with it and the SHA-256 the approver saw, and the
version was saved under someone else's path. An approval by the person who saved the version
counts only while the shared four-eyes setting is off and the decision records it as off; the
caseload, the household and the plan pack then mark it "One person", and turning four-eyes back
on stops it counting. An approval that fails any of these does not count, and the household's
page says why. A decided plan shows the version its
decision names, never a later save.

Limits [Certain]: the artifact's owner can write anywhere; times are set by the writer's
browser; a person can change or delete their own records; the status pointer, the checks and
the progress record are shared records any Contributor can change, so the audit log is the
attested record of who did what; one view reads the records of at most 18 people (the store
allows 64 live subscriptions per view) and the latest 1,000 audit entries per person. That the
platform enforces these rules for people other than the owner is [Likely]: it follows the
capability's type definitions and needs a check with a second account. The hosted version
(hosted/README.md: built and tested here, not deployed) closes the rest in the database: it sets
every author and time itself, writes the audit log from triggers, lets nobody edit or delete
versions, decisions or the log, and checks approvals against four-eyes and the plan's SHA-256.

## The plan

Claude sees only the drafting prompt (`spec/moveon_prompt.md`) with one synthetic record, its
suggestions and the plan schema filled in, as one message. The reply must be one JSON object
(a code fence around it is allowed) and must pass the screen (`spec/screen_rules.json`): plain
characters, the schema, the record, only the pathways listed for it, fd-core's guardrails, no
decision, no name, no figure that is not in the record. A reply that fails is never shown; the
officer sees which rules it broke and drafts again or starts from the template. The template
copies every check word for word. Every edit a person makes passes the same screen before it can
be saved, and every saved version is screened again when it loads. The screen is a net, not a
guarantee: it cannot catch a name in lower case or at the start of a sentence, so the officer
reads every plan. The private deny list of names is never sent to the page.

## Workflow

No plan, drafting, awaiting approval, then approved or rejected; a returned plan goes back to
drafting with the approver's note. What an editor writes when they return or reject a plan goes to
the next draft as a reviewer note (`screen_rules.json`, review): the returns with a note and the
rejections since the plan's last approval that counts, oldest first, the latest five. Claude is
given the notes apart from the record and told they are data, the template answers each with a
placeholder that a person must replace, and a version must answer each note once, in
`responds_to_review`, before it can be saved. A note never extends the record: a figure or a
name in a note is still refused in the plan. Each version keeps the notes it answered and is
screened against them; a version saved before the latest note cannot be submitted or approved. A
note that reads as an instruction to Claude is refused when the editor writes it, and a note
that fails the note checks is held back from Claude and shown to the officer as not required.
With four-eyes on, the person who saved a version cannot
approve it, and an approval by that person does not count. Editors can turn four-eyes off; the
change goes in the audit log. Approved and rejected plans are locked until an editor reopens them. Once a plan is
approved the officer works through the checks and records progress (referral made, offer made,
offer accepted, moved on, fell through). The plan pack (Markdown and JSON) carries the record,
the approved plan and its SHA-256 (checked against the approval), the checks, the progress, the
household's audit trail, the sources and the data manifest.

## Lessons

fd-core's memory core runs in the page (`fdcore/memory.mjs`, inlined by `scripts/build_app.py`
as `FdMemory`, with its rules in `spec/memory_rules.json`). An editor who returns a plan can keep
the note as a lesson for that household only, for one of its routes out (every household that
route is suggested for), or for its kind of accommodation (every household in it). The lesson is
a field on the return decision, so the path says who kept it, with the SHA-256 of its scope and
text, and the memory core's admission check runs first (a scope, a source, no names, no
instruction to a model). Every lesson waits for a second officer, not its author, to approve it
with a reason, because a note can carry text pasted from elsewhere (fd-core's
`research/POISONING_LOG.md`, P1.1) [Certain]. A lesson in force is recalled into every later
draft for a household it applies to, at most five, after the core's recall screen and a check of
its text against its SHA-256; a lesson that fails is held back and the file says why. It is shown
with its provenance (who kept it, from which household, who approved it, when and why), sent to
Claude as data with where it applies and its words only (no names, no dates), and recorded with
each version saved; the plan pack lists it. Its author can withdraw it while it waits, and
editors can retire it with a reason. The hosted build has no lessons yet. Whether a model
follows an instruction hidden in an approved lesson is the poisoning test's model run (P2), not
yet run [Certain].

In demo mode the planner opens on a sign-in screen: a housing officer (Contributor), a
reviewing officer and a team leader (both Editors), so four-eyes on plans and on lessons can be
tried in one tab, a finance officer (Viewer) and a service manager (owner). "Switch user" at the
foot of the sidebar brings it back and keeps the page.

## Follow-ups and add-ons (phase 6)

Each household's page has follow-ups (`tasks/<id>`, a shared record any Contributor writes): text,
a due date, an owner and done or not, with one-click templates (the landlord's answer, a viewing,
affordability, the support worker's part, the suitability checks). Text a person writes passes the
notes screen, which catches most names, places, providers and phone numbers: a net, not a
guarantee [Certain]. Every change is audited. The
Follow-ups page (`#tasks`) lists the open ones by due date, mine or everyone's. Hosted:
`public.tasks` (migration `20261022130000_move_on_followups.sql`). The add-ons (housing management
system, calendar, email or team chat) connect nothing and send nothing in this version: each shows
the text it would send.

## Notices, clocks, the handover and pilot timings (phase 6.5)

The rules are in `tamarket/spec/clocks.json`, each with the words that set its period and its
source; `tamarket/clocks.py` is the reference and `tamarket/spec/clocks.mjs` the port the page
uses (`TaClocks`), both checked against the file's shared cases. A period of N days "beginning
with" a day ends on that day plus N - 1 [Certain: s.208(4), s.213AA and reg. 9 all count so].

- **Records.** Each synthetic record now has `placed_on` (the caseload's date, 21 October 2026,
  less `weeks_in_ta` weeks: one placement per household) and, for households placed out of
  district, `s208_notice_sent_on`: a made-up history of notices before the planner (82 in 100
  sent within the 14 days, 10 later, 8 with none on record, by a hash of the id, and none after the
  caseload's date) [Guessing]. A household with no notice on record says, on its own page, that
  its placement date and history are made up for the demo.
- **Notices** (Contributors and up). s.208: the last day, a draft with placeholders, and "Record
  as sent" with the date and how. s.213AA is for each child (the DHSC guidance: one notification
  for each child placed), for a household with a child placed from 1 September 2026, a 16 or 17
  year old applicant counting as a child: for each child, ask the parent (or the young applicant,
  s.213AA(3)), record the answer for each body (agrees or not), then for each body agreed to the
  day the information about it arrived, and take reasonable steps to notify it within 14 days
  beginning with the latest of the agreement, that body's information and the placement. "Sent on
  time" uses that body's own date. A body not agreed to shows "Not agreed: no notice" and is never
  due; no notice is dated before the agreement or its body's information. Asking, the answer and
  the information may predate the placement (the latest of the three counts), but an answer is not
  dated before the asking, nor a notice before the placement. Each body's draft is built only from
  `child.contents` in `tamarket/spec/clocks.json`, each line with its basis: a council reference
  (no child count, no planner record); the GP practice's has no address (the DHSC guidance says GP
  notifications will not include the new temporary address); the health visiting service's has the
  family's address and postcode, a parent's contact number and the name on it, or, for a 16 or 17
  year old applicant, their own name and number, as the guidance says (the notes add that a
  pregnant child gives their own); the school's has only what the section requires (Keeping
  children safe in education 2026, Part one, lists no contents). The planner's own notes follow, marked as not
  part of the notice. A child with no GP practice: the page reminds the officer that the council
  gives the family information on registering. One agreement per body is the planner's reading
  [Likely], and the page says so. Compliance at risk lists each child's items: a child not yet
  asked is to start; an answer awaited, or a body's information, is listed under Waiting on the
  household (outside the count, as no clock runs yet); so a household leaves the page only when
  every child's notices are done. Up to 9 children are tracked; the page says so if a record has
  more. A young applicant under another priority need, or one living with a parent, is covered by
  a line on the clock. The duty does not apply where
  securing the accommodation ends the s.193 duty (s.213AA(1)); it arises once for each application,
  at the initial placement, which in the synthetic records is the placement on record. A
  placement before 1 September means
  an application before it too, so the duty does not apply; a later one may still follow an earlier
  application, which the page tells the officer to check.
- **6 weeks in B&B** for a family: the day to move by, the last day of 6 weeks beginning with the
  placement (the placement day plus 41, the planner's count, a day on the safe side, as the Order
  sets no counting rule); from the next day "6 weeks reached". Moved on ends it. The Order counts a
  total of periods; the synthetic records hold one each. The page says what the clock leaves out:
  art. 4(2)'s disregarded periods (Code 17.41), the restart after a change of circumstances (Code
  17.40, quoted at its scope: a change that brings the applicant within the Order), and that the
  date is a limit, B&B being a last resort (Code 17.35). The synthetic families in B&B are placed
  within the last 12 weeks (generator version 2).
- **Reviews** (`reviews/<id>`): the request date and an owner; due eight weeks beginning with the
  request (SI 2018/223 reg. 9(1)(b), which covers a suitability review), or a longer period agreed
  in writing, on or after that date; the date the decision was notified. Reviews decided in three,
  ten or twelve weeks (reg. 9(1)(a), (c) and (d)) are not tracked, and the page says so, as it says
  that the suitability of interim accommodation has no review under s.202(1)(f) (Code 17.67), while
  other s.202 reviews remain. A request may predate the placement.
- **Keyboard and screen readers.** After a notice or consent button the keyboard goes back to the
  clock's heading; a message is announced once, not again on each store refresh.
- **Compliance at risk** (`#compliance`): overdue, due in the next 14 days, and to start (a parent
  not yet asked, which has no time limit in the section, so none is shown). The sidebar counts the
  overdue and due items.
- **Handover summary** on each household: duty, placement, plan, officer, open follow-ups, clocks
  and the audit entries since a date the reader picks, saved as Markdown.
- **Pilot timings** (`#timings`): start a plan (first click to submission), send the notices for a
  placement (first action to the last notice recorded), prepare a handover (opened to saved). Each
  entry keeps the task, start, end and the number of buttons and fields used on the household's
  page meanwhile, in this browser's storage only, with no household, person or free text; export
  as CSV. Hosted: no table, on purpose (timing staff is workforce data, for a council and its staff
  to agree first).

Hosted: `public.notices` and `public.reviews` (migration `20261022160000_move_forward_clocks.sql`):
the database sets who recorded each row and when, refuses dates in the future, refuses a notice to
a child's body without the parent's agreement to that body on record or dated before the agreement
or the information, keeps a body already notified among those agreed, refuses a longer review
period ending before the statutory date, and audits every change; a saved handover is a page event.
The client inserts a notice and, if its id is taken, updates the value columns only: a PostgREST
upsert would also set the key, which the table's grants refuse.

## Monitor (phase 7)

- **Items** (`data/monitor.json`, a list, from `monitor/items.jsonl`; the register's names, terms
  and grades in `spec/monitor_sources.json`, an object with a `sources` list): each from a source in
  `monitor/sources.json`, with its address, published and read dates, the original title and a
  short passage quoted exactly, an English title and summary that name no council, person or firm,
  tags from `monitor/vocab.json` (the planner's checks, routes, clocks and references, and topics),
  and a proposed grade on the six-by-six scale (credibility 2, probably true, for a single source).
  Every figure in a summary is on the page cited, and an inference carries [Likely]. Each card shows
  its source's terms line. `scripts/monitor.py ingest` files them after a
  council-name screen and fd-core's checks (`fdcore.monitor`), with an ingest-log entry each;
  `monitor/RUNBOOK.md` says how a collection run reads the sources.
- **The Monitor page** (Work, with a count of items waiting): an officer accepts an item, setting
  the grade (any of the 36, the proposed one first), or rejects it with a reason (not relevant,
  already held, superseded, not reliable enough, or other with a note). A note is optional and
  screened. The decision is a shared record (`monitor/<item id>`), audited, and can be changed.
  Where a page shows a published and an updated date, the card shows both. A site copy of the
  build (its manifest has `site_copy`) says on this page and in Method how many items it leaves off
  and why. After a decision the item stays in the list until the list changes, and the keyboard moves to
  its status. If the monitoring files do not match the manifest, the Monitor page shows nothing and
  says so; plans are not affected.
- **Where an accepted item shows**: on the rail of each household it touches (through a check, a
  route or a clock; a reference alone touches none) as Monitoring notes, and beside the reference
  it touches in the References panel. Nothing reaches a plan unaccepted; drafting does not read
  items in this phase.
- Hosted: `public.monitor_decisions` (migration `20261022180000_move_forward_monitor.sql`).

## The scenario

`tamarket/spec/scenario.mjs`: arithmetic on inputs the person sets, never a forecast. The page
sets no input itself; it can offer the caseload's count of households on the first type as the
cap, and shows England's average weekly spend by type from RO4 for reference only.
