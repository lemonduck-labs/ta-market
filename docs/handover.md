# Handover

For someone taking this repo over. Written on 22 October 2026 against commit bf88a6e and brought
up to date at 01164e9, after c165ef6 (lessons in the planner), 4c2d8e1 (the plan screen) and
01164e9 (private council pages), and at 98c745a, which fixes the page build's check of fd-core's
files. Phase 4 (8688747 to 8567d7d, 22 October 2026) gives the planner fd-core's shared
navigation: queues named for the job, a search palette, keys to move through a list, and a
household's place in its list with its approval trail (`app/README.md`, "Getting around").

## What it is

- A council-by-council picture of temporary accommodation in England from MHCLG's published
  statistics: households by type and spend per household-year, each council set against unnamed
  peers, opening with nine ways its numbers could be wrong.
- A Move forward planner on 200 synthetic households: plans drafted with Claude or from a template,
  screened, and approved by a second officer under four-eyes, with an audit log. A return note
  can be kept as a lesson for later plans once a second officer approves it (fd-core's memory
  core, since c165ef6).
- A council far from its peers is a lead for a person, never a finding; no council is named in
  anything shared, and no savings figure is presented as fact.

## Set up and run

With fd-core cloned beside this repo:

```bash
pip install -e ".[dev]"                    # or ".[dev,fast]" for the calamine reader
pip install -e ../fd-core
python scripts/export_fdcore_patterns.py   # the JavaScript screen's patterns, not in git
python -m pytest                           # 300 tests at 8567d7d (299 at 98c745a, 298 at 01164e9)
python scripts/build_from_extracts.py      # verifies the browser extracts, writes data/processed
python scripts/build_picture.py            # reports/phase0_picture.md and the picture tables
python scripts/build_demo_data.py          # the demo's datasets (demo/ta)
python scripts/build_caseload.py           # demo/ta/synthetic_caseload.json, 200 records, seed 20261021
python scripts/build_app.py                # the planner page and app/dist; --target hosted for the kit
python evals/run.py screen                 # no model, no key (needs inspect-ai)
```

`python scripts/build_packs.py` writes the private per-council packs to `data/private/packs/`
(gitignored); a pack is never shared until the owner switches naming on for that copy.
`python scripts/build_council_pages.py` renders each pack as one private page for that council in
`reports/private/councils/` (gitignored), checking each page before it writes it; `--check`
writes nothing. With a machine that can download the spreadsheets, `scripts/build_tidy.py` is
the other route (`docs/browser_pull.md`). The hosted tests need node, Postgres 16, Deno and Playwright's Chromium
(`hosted/README.md`, "Running the tests"). Before anything leaves the repo: `/review`, then
`/ship`.

## Where things live

| Path | What |
|---|---|
| `CLAUDE.md`, `WORKFLOW.md` | The hard rules and the stages, owners and gates |
| `docs/decision_log.md` | Every decision, default and deferred check (internal: it records the data checks in working detail) |
| `docs/adr/` | Decision records 0001 to 0010 |
| `docs/quality_strategy.md` | Tests, screens, reviews, evals, and what is not covered |
| `docs/phase6_platform.md` | Phase 6 research: the work and its pressures, how casework systems are built, extensions, the phase 7 fit |
| `tamarket/` | Parsers, extract checks, the picture, display rules, packs, the scenario, the synthetic caseload, the planner's rules |
| `tamarket/spec/` | The language-neutral planner spec and its JavaScript ports, with the shared cases a port must pass |
| `data/` | Raw extracts with their manifest, processed tables, the ingest log, `SOURCES.md`; `data/private/` is gitignored |
| `reports/` | The phase 0 report; `reports/private/` (gitignored) names councils and holds the private council pages |
| `demo/ta/`, `app/` | The market picture demo and the planner page |
| `supabase/`, `app/src/hosted.js`, `hosted/README.md` | The hosted kit: migration, drafting function and runbook |
| `share/README.md` | The files that may leave the repo, and what never does |
| `evals/`, `.github/workflows/ci.yml` | Inspect evals and the CI workflow |

## What is open

- **New data**: TA1 for April to June 2026 is announced for 29 October 2026 (provisional), with a
  revised count for 31 March 2026; rebuild the picture and the demo when it lands. RO4 2025-26's
  second release is scheduled for December (decision log, deferred rows "TA1 count for 31 March 2026" and "RO4 2025-26 second release").
- **Deferred items** (the Deferred table in `docs/decision_log.md`), among them: a code licence; the commit
  author email; which households RO4 spend covers; the HRA statement; the spreadsheet parsers on
  the published files; a person's data checks; the tracked council tables that name councils
  beside their ratio; ADR 0001's "anonymised" wording; the empty deny list; the synthetic
  caseload's shapes; the planner's rules to re-check; the planner agent file (now `move-forward-planner`, rewritten 22 Oct); the
  planner's rules on a live artifact; a failed hosted draft shown as "did not arrive"; the hosted
  planner on a live project; staff data on the hosted site.
- **CI** is set up but has not run: the repo has no remote, and the workflow needs the secret
  `FD_CORE_TOKEN`. The repo passes its own git-mode screen again since ba17c6b (no findings in
  145 files at 8567d7d); from bf88a6e until ba17c6b one line of the workflow held a pinned
  package name that read as an email address [Certain, from runs of the screen on 22 October
  2026].
- **Deferred line 66** now lists only a failed hosted draft shown as "did not arrive". Its other
  part, the Method view's hosted wording, was done in commit 07e5f43 and was dropped from the row
  on 22 October 2026 [Certain, from the code; not seen on a deployed site].
- **The page build's dirty flag**: from c165ef6 until 98c745a, `scripts/build_app.py` looked up
  fd-core's module `fd-core:fdcore/memory.mjs` in this repo's git, so every manifest was marked
  dirty (and the Method view said the build had uncommitted changes) and `--clean` always
  refused, which also stopped diversion-radar's `scripts/build_site.py --clean`. Since 98c745a it
  checks fd-core's files in fd-core's own repository, a test covers it, and both clean builds
  work: the site's wrote `site/dist` at 02:37 on 22 October 2026 [Certain, from the runs].
- **The fact-check of 22 October 2026** (on 230e69e; report in the build session's scratchpad,
  `reviews/factcheck_ta_2026-10-22.md`) found 18 problems; the guardrails review of the same day
  passed the shared files with low fixes. The fixes are in the commit that adds this paragraph:
  the report's worked example moved to the private copy, the market picture says its dots are
  unnamed, not anonymous, the planner's Method view lists the lessons Claude is given, and the
  release figures the caseload uses are logged (`data/raw/releases/`). A verification of the
  fixes the same day (`reviews/verification_2026-10-22.md`) passed them for sharing on two owner
  decisions, the dots among them (below), and found a few small slips, fixed in the commit that
  adds this sentence [Certain].
- **Do not make this repository public as it is** (guardrails review of 22 October 2026): every
  commit carries the owner's name, personal email and a session link, the browser tests hold a
  made-up personal name and firm, no licence is chosen for the code, and the licence of HM Land
  Registry's change history behind `config/code_changes.csv` is not recorded. Publish anything public as a
  separate repository on fresh history, from the shared files and the code, put through
  `/review` first.
- **Lessons** (c165ef6) have no review recorded, and the hosted build has none yet. Whether a
  model follows an instruction hidden in an approved lesson waits for fd-core's poisoning test
  P2 [Certain].

## Decisions that wait for the owner

- Every row marked "open to the owner" in `docs/decision_log.md`: lines 15, 16, 20, 22, 23, 24,
  25, 32 and 36 (including the default model for hosted drafting), the 22 October 2026 row on
  references with URLs, and the row of 22 October 2026 on the dots, before the market picture is shared. Each of the 182 dots and both examples
  can be matched to its council from MHCLG's tables; and because the page states its rules,
  every selection it counts (the councils left out for a data check, the councils far above or
  far below the median) can be recomputed from those tables whatever the page draws. ADR 0001
  keeps such selections private, so publishing the counts with their rules needs the owner's
  decision in writing. The choices: keep the dots and the counts (the default, as built); show
  the band and median only, which protects the dots' figures but not the selections; or drop
  the data-check and pattern counts, or their rules, from the shared page.
- ADR 0001's revisit: naming a council on its own figures in a private copy shared with that
  council, which also needs that council's data checks and both reviews to pass.
- Who holds and pays for the API key of the hosted drafting function (`hosted/README.md`,
  "Before you start").
- The data protection officer's agreement on where the hosted project lives, who can open its
  dashboard and how long the audit log is kept, before anyone outside a test uses it
  (deferred line 68).
- The edit of the agent files (deferred line 64), the licence and the commit email (deferred lines
  51 and 52), and every step that publishes.

## How hosting would work

`hosted/README.md` is the runbook. The planner moves from the pilot inside Claude to Supabase
Postgres in London (store, sign-in by an emailed code for invited people, the `draft-plan`
drafting function) and Netlify (the page, `app/dist-hosted`), in ten steps for the owner: create
the project, run the migration, make yourself the owner, close sign-up, build with
`--target hosted`, set the function's secrets and deploy it, deploy the site, point Supabase and
the function at it, invite colleagues by role, and run the checks with a second account at
Contributor and one at Editor.

Built and tested here, not deployed: the migration on a local Postgres 16 with a stand-in for
Supabase's auth, `hosted.js` against a fake client and in headless Chromium against fakes, and the
function under Deno against a faked project and a faked Claude. Nothing has run against a live
Supabase project, Netlify or the model provider's API (`hosted/README.md`, "What is not built or
not tested") [Certain, as that file records]. The hosted build has no lessons yet (c165ef6). The market picture and the planner also appear,
in demo mode with no AI calls, on the static demo site that diversion-radar builds, which is not
deployed either.
