# Quality strategy

How quality is assured in this repo as it stands. Written on 22 October 2026 against commit
bf88a6e and brought up to date at 01164e9, after c165ef6 (lessons in the planner), 4c2d8e1 (the
plan screen) and 01164e9 (private council pages), and at 98c745a, which changes only the page
build's check of fd-core's files and adds its test; line numbers below refer to 01164e9.

## 1. The rules every output is held to

From `CLAUDE.md`: aggregates only, and synthetic records only in phase 2; no names of people or
firms, providers described by type; no council names in comparisons in anything shared
(ADR 0001); no savings figure presented as fact; every number traced to a processed table and an
ingest-log entry, with its release; every inference tagged [Certain], [Likely] or [Guessing];
the Open Government Licence line on every screen and report with MHCLG data; nothing leaves the
repo until the fact-checker and guardrails-reviewer agents pass it; British English, no em
dashes.

## 2. Tests

Run from the repo root, with fd-core beside it:

```bash
pip install -e ".[dev]"          # or ".[dev,fast]" for the calamine reader
pip install -e ../fd-core
python scripts/export_fdcore_patterns.py   # the JavaScript screen's patterns (not in git)
python -m pytest                 # 299 tests at 98c745a (298 at 01164e9, 273 at bf88a6e)
```

Some tests skip without their inputs or tools [Certain, from the skip markers]: node for the
JavaScript ports and the page's code; Postgres (`initdb`, `pg_ctl`, `psql`) for the database
tests, which also need a `postgres` user when run as root; Deno (on the path or `TA_DENO`) for
the drafting function; Playwright's Chromium and a copy of the pinned Supabase client
(`TA_SUPABASE_UMD`) for the hosted site in a browser; node and Playwright in
`tests/browser/node_modules` for the browser flows; Inspect (`inspect-ai`) for the eval tests;
`data/processed/ta1_wide.csv` for the tests that read the processed tables; and the private packs
in `data/private/packs` for the council page tests.
`hosted/README.md` lines 234-248 say how to provide each.

| Suite | Tests | What it covers |
|---|---|---|
| `test_extracts.py` | 7 | The browser extracts: a wrong hash, row count, width or changed cell fails |
| `test_mhclg.py` | 36 | The spreadsheet parsers, on small synthetic spreadsheets only |
| `test_build_tidy.py` | 1 | The spreadsheet route end to end, on synthetic files |
| `test_picture.py` | 6 | Cost per household (trapezoid and gaps), group and national figures, recodes, councils left out for a data check |
| `test_demo_data.py` | 8 | The demo names no council, shows only the two typical examples, gives counts that add up, and the tracked report compares the councils the demo shows |
| `test_pack.py` | 8 | Private packs name only their own council, are written only under `data/private` and stay out of git |
| `test_scenario.py` | 8 | The scenario's arithmetic and rounding, refused inputs, inputs echoed, never a forecast |
| `test_synthetic.py` | 9 | The caseload: every record says synthetic, no names, addresses or postcodes, reproducible from the seed, plausible stays |
| `test_moveon.py` | 114 | Pathways and checks, the plan screen and its shared cases, reviewer notes, the approval queue (only a person decides), official dated citations with no link |
| `test_spec_js.py` | 4 | The JavaScript ports against the shared cases (node) |
| `test_app.py` | 16 | The page's own code against the shared cases, Python's suggestions and prompt for all 200 records, with and without lessons, the template plan passing both screens, the publish folder against its manifest, and fd-core's files checked in fd-core's own repository (since 98c745a) |
| `test_browser_flows.py` | 2 | The planner's browser flows, lessons included, run under pytest (since c165ef6) |
| `test_council_pages.py` | 14 | The private council pages: one per council asked for, each naming and coding only its own council, the licence line and link, nothing that loads or runs, the guardrails screen, `--check` writing nothing, a gitignored folder (since 01164e9) |
| `test_share.py` | 3 | Every file that may be shared passes the guardrails screen and names no council |
| `test_hosted_db.py` | 20 | The hosted database on a local Postgres 16 with a stand-in for Supabase's auth: authors and times set by the database, four-eyes and fingerprints, insert-only tables, the audit rows |
| `test_hosted_js.py` | 37 | The hosted build and function: the node suite, the function under Deno, the site in headless Chromium, the Content-Security-Policy hashes, a publishable key only |
| `test_evals.py` | 6 | The offline evals reach their bar, the planted notes reach the prompt, the eval's token limit is the drafting function's |

`tests/browser/` holds the planner's Playwright flows (`flow.mjs`, and `lessons_flow.mjs` since
c165ef6) against a mock of the platform that applies the page's path rules
(`tests/browser/README.md`); `tests/test_browser_flows.py` runs them under pytest. They test the
page against the rules, not the platform's own enforcement [Certain, as that README states].

## 3. CI

`.github/workflows/ci.yml` (commit 215bf05) is set up to run, on every push and pull request,
the tests (with PostgreSQL 16, Deno 2.9.6, Chromium and the pinned Supabase client, so the hosted
tests run too, and, since c165ef6, the browser flows, as it installs Playwright in
`tests/browser`) and the two evals that need no model, after generating the screen's patterns
from fd-core; the live eval would run only when started by hand with an API key set as a secret.
It reads fd-core with a read-only token the owner adds (`FD_CORE_TOKEN`). It has not yet run: the
repo has no remote [Certain, from the workflow and `git remote`]. It does not run fd-core's
screen over the tracked files and commit messages [Certain, from the workflow].

## 4. Screens and build checks

- **fd-core's screen** over every tracked file and every commit message:
  `python -m fdcore.guardrails --deny config/deny_list.txt --git . --policy config/guardrails_policy.txt`.
  The policy switches the accusing check off for the agent and command files and the phone check
  off for `demo/ta/*.json` (money in pounds); names, company names, emails and postcodes are
  always checked. Run on the committed trees of bf88a6e and 01164e9 on 22 October 2026, it found
  one thing each time (in 128 and 132 files): the pinned Supabase client, written as package
  name, at sign and version on line 78 of `.github/workflows/ci.yml`, read as an email address.
  It is not personal data. The test 98c745a added wrote a placeholder git identity the same way,
  a second finding. ba17c6b puts the version in a shell variable and assembles the identity at
  run time; the screen then finds nothing, in 144 files [Certain, from the run].
- **The plan screen** (`tamarket/spec/screen_rules.json`): the Python reference
  (`tamarket/moveon.py`) and the JavaScript port (`tamarket/spec/screen.mjs`) pass the same 93
  shared cases: 64 plan cases, 18 note cases and 11 note-building cases (85 at bf88a6e;
  4c2d8e1 added c67 to c74). A plan that fails is never shown or saved, and every saved version
  is screened again when it loads. The screen is a net, not a guarantee: the officer reads every
  plan. Since bf88a6e its phone check reads a digit run that follows a letter or digit as part
  of a token, as fd-core's does. Since 4c2d8e1 it stops terse decision lines ("Discharge duty
  into the private rented sector.", "Close the case.", "Approve the offer.") and lets named
  public services such as "Children's Services" through [Certain, from the shared cases].
- **Lessons** (since c165ef6): the page runs fd-core's `memory.mjs`, inlined by
  `scripts/build_app.py`, which also writes the core's rules from `fdcore.memory`. A kept note
  passes the core's admission check, counts only once an officer other than the one who kept it
  approves it with a reason, and is recalled into at most five later drafts after the core's
  recall screen and a check against its SHA-256. The hosted build has no lessons yet [Certain,
  from the code and the commit].
- **Inputs**: `scripts/build_from_extracts.py` refuses any extract whose hash, row count, row
  width or column sums differ from the browser's (`data/raw/browser/MANIFEST.csv`), and writes
  one ingest-log entry per extract.
- **The page**: `scripts/build_app.py` writes a manifest with the commit, any inputs not
  committed as they are, and the SHA-256 of every file; the page checks each file against it and
  will not draft or save if one does not match. `--clean` refuses uncommitted inputs. Since
  c165ef6 the inputs include fd-core's module under the name `fd-core:fdcore/memory.mjs`; until
  98c745a the check looked that name up in this repo's git, so every build was marked dirty and
  `--clean` always refused, with diversion-radar's `scripts/build_site.py --clean` after it.
  Since 98c745a fd-core's files are checked in fd-core's own repository
  (`tests/test_app.py::test_fd_core_inputs_are_checked_in_fd_core`) [Certain, from the code and
  the runs].
- **Private council pages** (since 01164e9): `scripts/build_council_pages.py` checks each page
  before writing it to `reports/private/councils/` (gitignored): no other council named or
  coded, no ONS code but its own, the licence line and link, its own name, no dash, nothing
  that loads or runs.
- **What may leave the repo** is listed in `share/README.md` and checked by `tests/test_share.py`.

## 5. Independent review: `/review`, then `/ship`

- `.claude/agents/fact-checker.md` re-derives every number with its own script and marks each
  one MATCHES, WRONG, UNSOURCED or OVERSTATED, checking tags, dropped caveats, British English
  and dashes. It reports and never edits.
- `.claude/agents/guardrails-reviewer.md` is this repo's own reviewer, which replaced the copy
  carried over from the radar (decision log line 11). It runs fd-core's screen and reads every
  file for households and anything that locates them, people and providers, verdicts on
  councils, savings presented as fact, confidence tags, licences and release status. It returns
  PASS or BLOCK and never edits.
- `/review` runs both; `/ship` requires `pytest` to pass, the review to pass on every file
  shared, the licence line on every screen and report with MHCLG data, and a README that opens
  with the problem, the outcome and a video link.
- The record so far: the first fact-check and guardrails review of the picture (commit 6cd1fec),
  an independent review of the planner (f1c5d19), a fact-check of everything that would be shared
  (07e5f43), the planner's evals, which found four kinds of statement the plan screen let
  through (09b9c40), and a user walkthrough, which found a terse decision line let through and a
  named public service stopped (4c2d8e1). Errors found up to bf88a6e are logged in
  `../fd-core/docs/where_claude_was_wrong.md`, which lists the later ones as not yet entered. No
  review of c165ef6, 4c2d8e1 or 01164e9 is recorded [Certain, from the records].

## 6. Pre-registration

This repo runs no backtest, so nothing here is pre-registered [Certain]. The phase 0 report
instead opens with nine ways its numbers could be wrong, each rated, before it says what they
show (`reports/phase0_picture.md`). The memory core's poisoning test, which is pre-registered,
lives in fd-core and covers the core the planner's lessons use since c165ef6
(`scripts/build_app.py` imports `fdcore.memory`; the page inlines `fdcore/memory.mjs`). Its entry
P1.2 records the planner's second officer on every lesson as adopted and not yet measured
[Certain].

## 7. Records

- There is no research log here. Decisions, defaults and deferred checks are in
  `docs/decision_log.md`, a table of current decisions: rows are rewritten when a decision
  changes (for example commit 05180d1 rewrote the data-check row), and git history keeps the
  earlier wording [Certain].
- Decision records are in `docs/adr/`.

## 8. Evals (Inspect)

`evals/plan_evals.py`, `evals/run.py` and `evals/fake_drafter.py`, committed in 215bf05, with
`tests/test_evals.py`:

- `plan_screen`: the plan screen on the 93 shared cases (85 when committed in 215bf05), with no
  model; the scorer makes the calls
  `tests/test_moveon.py` makes, on cases built as it builds them. Bar 1.0.
- `plan_live`: the page's own drafting prompt, as one user message, on all 200 synthetic records,
  and on 6 of them again with a planted reviewer note. Scored on whether the reply parses as one
  plan and passes the screen, and whether the plan says what a planted note asks (outside its
  answers to the notes). A case passes only if every epoch passes. It needs a model and an API
  key, and costs money: 206 prompts per epoch. It reports scores and has no bar.
- `pipeline`: `plan_live` on a stand-in drafter that answers with the page's template plan; it
  shows the scorers can pass, not that a model does. The commit records that a stand-in that
  obeys the notes scores 0 of 6.
- Run with `python evals/run.py screen`, `python evals/run.py pipeline` or
  `python evals/run.py live --model <provider>/<model> [--epochs 3]`; logs go to `evals/logs`,
  which git ignores.
- What they have found so far: the screen let through a saving stated as fact (with a figure from
  the record or none), checks waved off ("the suitability checks are not needed") and a priority
  stated; commit 09b9c40 stops all four, with seven new shared cases (c60 to c66).
- No live eval has been run. `evals/logs` does not exist; the only Inspect logs on this machine
  are in the build session's scratchpad, and every one is a run on `mockllm`, the stand-in
  drafter or a stand-in that obeys the notes [Certain, from the logs' headers].
- The evals leave the prompt's lessons block empty: `evals/plan_evals.py` fills the prompt with
  reviewer notes only [Certain, from the code].

## 9. What is not covered or checked

- **CI has not run.** The workflow is set up but the repo has no remote, so the tests and evals
  run only when someone runs them, and fd-core's screen over the repo is not part of CI
  [Certain].
- **The spreadsheet parsers** are tested on synthetic files only; the phase 0 picture came from
  browser extracts (decision log, deferred line 56).
- **The data checks** (quarter jumps and empty TA lines) wait for a person; until then those
  councils are only counted (deferred line 57).
- **Disclosure through tracked tables.** `data/processed/picture_councils_*.csv` name every
  council beside its ratio to the peer median; this public copy leaves them out (`PUBLIC.md`).
- **The platform's own enforcement** of the planner's path rules for people other than the owner
  is untested; it needs a second account at Contributor and one at Editor (deferred line 65).
- **The hosted kit** has run only against a local Postgres with a stand-in for Supabase's auth,
  a fake Supabase client, fake project endpoints and a faked Claude; nothing has run against a
  live Supabase project, Netlify or the model provider's API, and delivery of the sign-in code
  by email is untested (`hosted/README.md` lines 280-319).
- **The planner's rules** need a second read: the private rented offer rules were rewritten on
  21 October 2026; an offer made before 1 May 2026 but accepted after it was not checked; some
  duties are not in the checks (deferred line 63). The checks are a selection, not the full code.
- **The synthetic caseload's shapes** beyond the published shares are guesses (deferred line 62).
- **Names.** The deny list is empty, so the name check matches nothing; people's names are
  caught only through it, firm names only by legal-form endings, and the screen misses a name in
  lower case or at the start of a sentence [Certain, from the code and `app/README.md`].
- **Meaning.** The plan screen checks wording, figures and structure, not meaning; the eval's
  planted-note score looks for phrases, so it sees a plan that says what a note asks, not one
  that quietly leaves something out (`evals/plan_evals.py`, docstring).
- **Releases.** RO4 2025-26 is a first release covering 377 of 413 authorities; TA1 for
  31 March 2026 is expected to be revised with the release announced for 29 October 2026
  (deferred lines 53 and 60).
- **Sources not yet confirmed**: which households RO4 spend covers, and the HRA statement in
  `data/SOURCES.md`, both [Likely] (deferred lines 54 and 55).
- **A model in the loop.** No plan drafted by a model has been scored by an eval yet. Whether a
  model follows an instruction hidden in an approved lesson is fd-core's poisoning test P2, not
  yet run [Certain].
