# Move forward: the temporary accommodation market picture and planner (England)

> **Start here.** [Live demo](https://lemonduck-labs.netlify.app/) of the market picture and the Move forward planner (static
> pages, synthetic households and people, nothing sent anywhere) · films: [market picture, 1:08](https://lemonduck-labs.netlify.app/videos/ta.mp4)
> and [planner, 2:57](https://lemonduck-labs.netlify.app/videos/planner.mp4) · what this public copy leaves out and why:
> [`PUBLIC.md`](PUBLIC.md) · how it was built and checked: [`docs/how_this_was_built.md`](docs/how_this_was_built.md)
> · decisions and what is still open: [`docs/decision_log.md`](docs/decision_log.md). Shared for review: [`NOTICE.md`](NOTICE.md).

**The problem.** Councils' spending on temporary accommodation (TA) jumped in 2024-25: on MHCLG's
figures, councils in England spent £2.824bn gross on it (revenue outturn lines 80 to 86, cash), up
23.8% on 2023-24, with nightly-paid self-contained accommodation up 78.1%; the 2025-26 first
release shows a further 3.9%, not yet comparable, and MHCLG schedules its second release for
December 2026. The figures are published, but in two releases that count different things
(households on four days a year; spend over the year), with gaps, first releases and
reclassifications that make a naive comparison wrong [Likely]. And moving a household on means
checking each route out against legislation and guidance, and recording who decided what.

**The outcome.** A council-by-council picture from published statistics alone, in which each
council is set against the others in its group without a name, and which opens with nine ways
its numbers could be wrong; and a Move forward planner that drafts plans on synthetic records,
screens them and puts each in front of a second officer for approval (four-eyes, on by default).

**Watch.** Captioned walkthroughs of the market picture (1:08) and the Move forward planner (2:57), on
the demo site that diversion-radar builds (its `site/`), at `/videos/ta.mp4` and
`/videos/planner.mp4`. Both run there as static pages, with no sign-in and no AI calls, at
[https://lemonduck-labs.netlify.app](https://lemonduck-labs.netlify.app/), kept out of search engines.

**Brand and guide.** The market picture and the planner share one look, kept in `brand/`: warm
paper, one deep teal for actions, clay for what is due, Poppins Bold Italic for the wordmark, titles
and headline figures and Source Sans 3 for text (SIL Open Font License, `brand/fonts/OFL.txt`) and an original logo mark. `scripts/build_app.py`
writes it into both pages with fd-core's `fdcore.brand`, fonts as data: URIs, so neither page
loads anything from elsewhere. The planner opens on an overview (plans waiting and for how long, the pipeline,
time in TA, the checks raised and the caseload's weekly cost range from its synthetic bands),
with a board of every household by plan stage. Each has a How it works guide (the planner's
sidebar, the picture's last tab): who uses it, a typical week (the planner) or how to read it (the picture),
what is demo data in that copy, and what a deployment could add.

Contains public sector information licensed under the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

## What it found (`reports/phase0_picture.md`)

- 2024-25, England: 125,235 households in TA on a yearly average (a straight-line average of
  MHCLG's quarter-end estimates, which are weighted for non-response and rounded to the nearest
  10); £2.653bn gross on accommodation (lines 80 to 85); £21,180 per household-year gross and
  £10,090 net, after income such as housing benefit. These are average outturns, not prices, and
  the spend may cover households the count does not [Certain for the figures; Likely on the
  coverage].
- By type, 2024-25: bed and breakfast £41,180 per household-year gross, nightly-paid
  self-contained £26,920, private sector leased £21,150. The gap between two types is not a
  saving: households, places and lease costs differ. [Certain for the figures]
- Each council is set against the others in its group, London or the rest of England, without
  a name. In 2024-25 the London comparison covers 24 of the 33 London councils (26 in 2025-26);
  point 1 of the report says why the others are left out. [Certain]
- The report opens with nine ways its numbers could be wrong, from councils missing from the
  counts to spend booked outside the TA lines and a 2025-26 first release.

## The Move forward planner (`app/`)

A caseload of 200 made-up households; a file for each with its routes out and a selection of the
checks legislation and MHCLG guidance set; a plan that Claude is asked to draft from that record,
its suggested routes and checks, any reviewer notes and any lessons in force, each approved by a
second officer and sent as data (inside Claude), or that starts from a template; a screen that stops the decision wording, names and figures it is built to catch (a
net, not a guarantee: the officer reads every plan); approval by a second officer (four-eyes, on
by default), which counts only while the text matches its SHA-256 fingerprint; reviewer notes
that the next draft must answer; progress, a scenario calculator and the audit log. It runs
inside Claude as an artifact. A hosted version on Supabase and Netlify is built and tested here
(the database on a local Postgres, the page and the drafting function against fakes) and not
deployed (`hosted/README.md`).

Phase 6.5 adds the statutory clocks, worked out from each record by rules that quote the law
(`tamarket/spec/clocks.json`, with Python as the reference and a JavaScript port that must give
the same answers): the notice to the council where a household is placed (s.208, 14 days), the
notices for each child to each of the GP practice, health visiting service and school agreed to,
each due from the information about that body (s.213AA, in force 1 September 2026), the day a family in B&B must move by
(SI 2003/3326) and eight weeks for a review decision (SI 2018/223, reg. 9(1)(b)). A Compliance at risk page lists what is overdue
or due; each household has a handover summary; a Pilot timings page times three tasks in the
browser. The planner drafts each notice with placeholders for personal details and records what
the officer says was sent. It sends nothing.

Phase 7 adds the monitoring layer: a register of lawful public sources (`monitor/sources.json`:
MHCLG's homelessness statistics and guidance, the code of guidance, legislation.gov.uk and the
Local Government and Social Care Ombudsman's published decisions, each with its terms), items
read from them and filed by `scripts/monitor.py` after fd-core's checks (`fdcore.monitor`) and a
screen for council names, and a Monitor page where an officer accepts an item, setting its grade
on the six-by-six scale, or rejects it with a reason. An accepted item shows on the rail of each
household it touches and beside the reference it touches. Nothing reaches a plan unaccepted, and
drafting does not read items. How a collection run works: `monitor/RUNBOOK.md`.

## What this is not

- Not a case management system. It holds no data about any real household: the picture is
  aggregates and the planner's households are synthetic. The planner records the names of the
  staff who act, as its accountability record.
- Not official statistics, and not an assessment of any council. A council far from its
  peers is a lead for a person to look into, not a finding.
- No names of households or of accommodation providers; providers are described by type.
- No savings figure is presented as fact. The price gap between nightly-paid and leased
  homes is an input the user sets.

## Data and licences

| Source | Publisher | Licence |
|---|---|---|
| Statutory homelessness detailed local authority tables (TA1) | MHCLG | Open Government Licence v3.0 |
| Revenue outturn RO4 housing services, data by local authority | MHCLG | Open Government Licence v3.0 |
| Revenue outturn multi-year data set (listed for the spreadsheet route; not used in phase 0) | MHCLG | Open Government Licence v3.0 |
| Local Authority District to Region (April 2025) lookup (listed; not used in phase 0) | ONS | Open Government Licence v3.0 |

URLs, release dates, file structure and caveats: `data/SOURCES.md`. Machine-readable list:
`config/sources.csv`. Download order: `docs/browser_pull.md`. Council mergers and recoding:
`config/code_changes.csv`.

Attribution for every screen or report that shows the data: "Contains public sector
information licensed under the Open Government Licence v3.0." with a link to the licence.
Where the ONS lookup is used, also "Source: Office for National Statistics licensed under
the Open Government Licence v3.0." The council code changes in `config/code_changes.csv`
were compiled with HM Land Registry's UK House Price Index change history, under the Open
Government Licence v3.0 (data.gov.uk, read 24 October 2026): "Contains HM Land Registry data
© Crown copyright and database right 2026. This data is licensed under the Open Government
Licence v3.0."

Private working copies that name councils in comparison lists (`reports/private/`,
`data/private/`) are gitignored. The tracked report gives counts and patterns only.

## Quick start

```bash
pip install -e ".[dev]"        # or ".[dev,fast]" for the much faster calamine reader
pip install -e ../fd-core      # ingest log, snapshot checks, guardrails
python -m pytest
# Route used so far (this workspace cannot reach gov.uk): verified browser extracts
python scripts/build_from_extracts.py   # checks data/raw/browser against MANIFEST.csv
python scripts/build_picture.py         # writes reports/phase0_picture.md
# Route for a machine that can download the spreadsheets: put them in data/raw as listed
# in docs/browser_pull.md, record them in data/pull_manifest.csv, then:
python scripts/build_tidy.py --engine calamine
```

## Layout

| Path | What |
|---|---|
| `tamarket/mhclg.py` | Parsers that find the table in each spreadsheet and return tidy tables (`ta_households`, `ta_spend`), plus checks and code harmonising |
| `tamarket/extracts.py` | Reader for the browser extracts: refuses any file whose hash, row count, row width or column sums differ from the browser's |
| `tamarket/picture.py` | Cost per household, mix, peer comparison, leads and recording checks |
| `tamarket/display.py` | Rounding, the councils shown and the per-line checks, shared by the demo and the private packs |
| `tamarket/pack.py` | Private per-council pack: one council's own figures against unnamed peers |
| `tamarket/scenario.py` | Savings scenario: arithmetic on a council's own inputs, never a forecast |
| `tamarket/synthetic.py` | Synthetic caseload generator, seeded, marked synthetic in every record |
| `tamarket/moveon.py` | Routes out, the plan screen and approval queue: the Python reference for `tamarket/spec/` |
| `tamarket/spec/` | Language-neutral spec a page or a Deno function loads unchanged: `pathways.json`, `moveon.schema.json`, `moveon_prompt.md`, `screen_rules.json`, shared cases (`screen_cases.json`, `scenario_cases.json`) and JavaScript ports (`screen.mjs`, `scenario.mjs`, `run_cases.mjs`) |
| `scripts/build_packs.py` | Writes one private pack per council to `data/private/packs/` (gitignored) |
| `scripts/build_caseload.py` | Writes `demo/ta/synthetic_caseload.json` with each record's move-forward suggestions |
| `scripts/export_fdcore_patterns.py` | Writes `tamarket/spec/fdcore_patterns.json` (gitignored) for the JavaScript screen |
| `scripts/build_from_extracts.py` | Verifies the browser extracts and writes the processed tables and ingest log |
| `scripts/build_picture.py` | Writes `reports/phase0_picture.md` and the picture tables; every number is computed there |
| `scripts/build_tidy.py` | Verifies raw files against the pull manifest, parses them, writes `data/processed` and the ingest log |
| `config/` | `sources.csv` (every file and URL), `code_changes.csv`, `guardrails_policy.txt`, `deny_list.example.txt` (the working `deny_list.txt` is local and gitignored; it stays empty until a name turns up that must never appear) |
| `data/raw/` | Files exactly as downloaded; never edited by hand |
| `data/processed/` | Tidy outputs, `extract_report.json` (checks per browser extract) and the picture tables; `parse_report.json` when the spreadsheet route is used |
| `docs/` | `browser_pull.md` and decision records |
| `tests/` | Tests on small synthetic spreadsheets, the processed tables, the spec and (with node) the JavaScript ports |

## Phase 2: private packs, scenarios and the Move forward planner

The tools run inside Claude first, as artifact pages. A hosted version on Supabase and Netlify
is built and tested here (the database on a local Postgres, the page and the drafting function
against fakes) and not deployed (`hosted/README.md`).
Whatever a page needs is in language-neutral files under `tamarket/spec/`; the Python modules
are the reference, and the shared cases there are what a port must pass. `tests/test_spec_js.py`
runs the JavaScript ports against them with node.

### Private per-council pack (`tamarket/pack.py`)

`council_pack(code, year="2024-25")` returns one council's pack: households, gross and net
spend per household-year, the ratio to the median of the other councils, the share of them
with a lower figure, the trend over the years held, the mix of households and spend by type,
questions (reasons first, then the question, each tagged), a data check when the council is
left out of the shared chart's dots (a check to make, never a finding), release notes, caveats
and the licence line. It names that council only. Its peers are the councils shown on the
shared demo in the same peer group, the council left out, and appear only as a count, a band
and a median. `python scripts/build_packs.py` writes one pack per council to
`data/private/packs/` (gitignored), for one-council private pages only, never a shared page.
A pack is shared only after the owner switches naming on for that copy (`docs/adr/0001`), a
person has done that council's data checks, and the fact-checker and guardrails reviewer
pass it.

### Private council pages (`scripts/build_council_pages.py`)

`python scripts/build_council_pages.py` renders each pack as one self-contained HTML page for that
council's officers in `reports/private/councils/` (gitignored; the script stops if it is not). Before
writing a page it checks that no other council is named or coded and that the licence line and link
are there; a page that fails is not written and the script exits 1. `--check` checks without writing;
`--only CODE` builds one page. The pages never leave the owner's machine except to the council each
names, and only after its pack's release gate (ADR 0001, data checks, fact-checker, guardrails reviewer).

### Savings scenario (`tamarket/scenario.py`)

`run_scenario(inputs)` does arithmetic on the council's own inputs and echoes them back:
households moved from one type to another, its own price gap per household-year, set-up cost
per household, void cost per household-year and lease term. It returns the gross and net
difference a year, the set-up cost, the net difference over the term and the payback in years,
rounded as stated in the module. It is never a forecast and never a saving the council will
make. `validate_inputs(inputs)` lists every problem; bad inputs raise `ScenarioInputError`.
`tamarket/spec/scenario_cases.json` holds 14 input sets with their exact outputs, including the
errors, and `tamarket/spec/scenario.mjs` is a JavaScript port that passes them.

### Synthetic caseload (`tamarket/synthetic.py`)

`generate_caseload(n, seed)` makes up households in TA: id, household type and size,
accommodation type, weekly cost band, weeks in TA, priority need, support needs and local
connection. Every record has `"synthetic": true`, an id starting `SYN-` and a record type that
says so; there are no names, addresses or postcodes. Shares follow MHCLG's England figures where
they are published ("Statutory homelessness in England: January to March 2026", 13 August 2026;
TA1 at 31 March 2026; RO4 2024-25) and stated guesses elsewhere, each listed with its
confidence in the file's meta block. The same seed gives the same records.
`python scripts/build_caseload.py` writes `demo/ta/synthetic_caseload.json` (200 records, seed
20261021), with each record's move-forward suggestions from `tamarket/moveon.py`.

### Move forward planner (`tamarket/moveon.py` and `tamarket/spec/`)

- `pathways.json`: social housing through the allocation scheme (`social-housing`), a private
  rented sector offer (`prs-offer`) and supported housing (`supported-housing`), plus
  suitability checks (B&B limits for families, for 16 and 17 year olds and for care leavers,
  children's services for young applicants, out-of-district placements, space and
  affordability, medical needs). Each has a stable id, a condition a
  program can evaluate (field, operator, value), the same condition in words, officer checks
  and citations (publisher, title, date) from legislation and MHCLG guidance only. Official links
  are in the private `data/private/phase2_sources.json`.
- `suggest_pathways(household)` lists, for one synthetic household, the pathways it could take
  with reasons and the checks an officer must make, and the suitability checks its record
  raises: suggestions for an officer to approve, never decisions. `eligible_pathways()` is the
  compact form the caseload file carries, as ids that `texts()` resolves.
- `moveon_prompt.md` and `moveon.schema.json`: the drafting prompt (`fill_prompt(household)`
  fills it) and the schema for the plan, with a confidence on every claim.
- `screen_plan(plan, household)` runs the fd-core guardrails screen on every text field and
  rejects a plan that does not match the schema, is not for a synthetic record, suggests a
  pathway not listed for it, states a decision, names a person or a provider, or uses a figure
  that is not in the record. `screen_rules.json` holds the rules and `screen_cases.json` 64
  plan cases (c01 to c35 and c60 to c74, and r01 to r14 on reviewer notes), 18 note cases and 11
  note-building cases; `screen.mjs` is the JavaScript port and `prompt.mjs` fills the prompt as Python does. Before a page or a function screens plans, run
  `python scripts/export_fdcore_patterns.py`: it writes fd-core's patterns to
  `tamarket/spec/fdcore_patterns.json`, which stays out of git because it lists the words the
  screen blocks. The deny list is never shipped to a page.
- `propose_plan(plan, household)` puts a plan that passes into the fd-core approval queue
  (`data/private/moveon_queue.jsonl`), where only a person can approve or reject it.

### Move forward planner page (`app/`)

The working tool on the synthetic caseload, run inside Claude as an artifact page for the pilot:
the caseload, a file per household with its pathways and checks, a plan drafted with Claude or
from the template and approved by a second officer (four-eyes, on by default), the checks worked through, progress, a
scenario calculator, the audit log and the method. Plan versions, decisions and the audit log
sit under each person's own path, so the store says who saved and who approved; an approval
counts only for text that still matches its SHA-256 and, with four-eyes on, someone else saved.
A note on a returned plan can be kept as a lesson for that household, a route out or a kind of
accommodation; once a second officer approves it with a reason, later drafts it applies to are
given it as data, with its provenance shown (fd-core's memory core).
`python scripts/build_app.py` builds the page and the publish folder `app/dist`;
`tests/test_app.py` runs the page's own code against the shared cases and every record. See
`app/README.md`.

## Status

- Phase 0 picture built (21 October 2026) from 12 MHCLG files read in a browser: TA1 at nine
  quarter ends (31 March 2024 to 31 March 2026) and RO4 for 2023-24, 2024-25 and 2025-26 (first
  release). Each extract is checked against the browser's hashes and sums before use
  (`data/raw/browser/MANIFEST.csv`). The spreadsheet parsers in `tamarket/mhclg.py` are tested
  on synthetic files only; the column positions they should find are in `data/SOURCES.md`.
- Next release: TA1 for April to June 2026, announced for 29 October 2026 (provisional).
- Phase 2: the planner runs inside Claude on the synthetic caseload; the hosted kit is built and
  tested, not deployed. What may leave the repo is listed in `share/README.md`.
