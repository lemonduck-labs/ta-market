# How this was built

One person set the problem, the rules and every decision. Claude Code did the building,
directed through a team of agents, each with its own brief in `.claude/agents/`. The rules
come first and stay fixed: aggregates only for the market picture, synthetic records only for
the planner, no council named in a comparison, no person or provider named, and never a
savings figure presented as fact (`CLAUDE.md`, `docs/adr/`).

## The team

| Agent | Owns |
|---|---|
| housing-data-engineer | MHCLG pulls, releases, checksums, the ingest log |
| market-analyst | Cost per household, accommodation mix, trends, outliers, the savings illustration |
| move-forward-planner | Move-forward plans on synthetic records into the approval queue |
| fact-checker | Re-derives every number before anything is shared |
| guardrails-reviewer | Blocks names, personal data, accusations and licence problems |

Commands: `/pull`, `/picture`, `/review`, `/ship` (`WORKFLOW.md`).

## The gates

- Nothing leaves the repository until the fact-checker has re-derived every number and the
  guardrails reviewer has passed it (`/review`, then `/ship`).
- After each phase, a reviewer that did not write the work (a fresh agent given the code, the
  legislation and the guidance, not the builder's account of them) checks it and lists
  blocking and non-blocking points, each marked [Certain], [Likely] or [Guessing]. Blocking
  points are fixed before the work is shared or signed off, and the decision log records each one.
- The statutory clocks are written once as rules with shared test cases
  (`tamarket/spec/clocks.json`), and the Python and the page's JavaScript must agree on every
  case.
- Tests run in Python, as browser flows in Chromium, and against the hosted database on Postgres.
- Every inference carries its confidence. The decisions, the defaults set in the owner's absence
  and the checks left for later are in `docs/decision_log.md`.

## What the reviews caught

A few of the points the independent reviews raised, each fixed before the build moved on:

- The draft notice to a child's GP practice carried the family's temporary address. The DHSC
  guidance on the notification duty says GP notifications do not include it.
- Notices were kept one set per household, where the s.213AA duty runs for each child.
- The 14 days ran from one information date for all three bodies, where s.213AA(4)(b) counts
  from the information about each body.
- The health visiting draft asked for a parent's details when the applicant is 16 or 17, where
  the guidance asks for the young person's own.
- The reviews panel said other s.202 reviews run on eight weeks, where regulation 9(1) of
  SI 2018/223 gives three weeks for some and ten or twelve for others.

Synthetic records only: no household in the planner is or describes a real person.
