# 0002: People and providers are never named; providers are described by type

Date: 21 October 2026. Status: Accepted (the owner's approval).

## Context

The households in temporary accommodation are vulnerable, and the market picture is about
councils' spending on accommodation that providers supply. The first CLAUDE.md (commit 6478719)
already said: no names of people or firms; providers are described by type, never named. Among
the owner's approvals of 21 October 2026 it gained a line on who may be named (commit ab4edce).

## Decision

- No names of people or firms. Providers are described by type, never named. Publishers of
  cited sources may be named; providers and people never (CLAUDE.md; decision log line 12).
- Pathways and checks in the planner cite publisher, title and date from legislation and MHCLG
  guidance only; the official links sit in the private `data/private/phase2_sources.json`.
- One deliberate exception: plan packs and audit exports carry the names of the officers who
  acted, as the accountability record, limited to staff and never households. A name that does
  not resolve is shown as "a member of staff (name not available)", never the platform's id
  (decision log line 42).

## Options ruled out

None recorded.

## Consequences

- Staff names and emails are personal data, held in the hosted tables and the audit log. The
  council's data protection officer should agree where the project is hosted, who can open the
  dashboard and how long the log is kept, before anyone outside a test uses it (decision log,
  deferred line 68; `hosted/README.md` lines 317-319).
- The README said the planner held no personal data. The fact-check of 21 October 2026 found
  that it records staff names, and the README now says so (commit 07e5f43).
- This repo's guardrails reviewer checks for people and providers in every file, chart label,
  data column and commit message (`.claude/agents/guardrails-reviewer.md` lines 22-24).

## Where recorded

Line numbers are as at commit bf88a6e.

- `CLAUDE.md` lines 11-12.
- `docs/decision_log.md` lines 12 and 42; deferred line 68.
- `README.md` lines 55-62 and 177-184.
- `.claude/agents/guardrails-reviewer.md` lines 22-24.
- Commits 6478719, ab4edce, f1c5d19 and 07e5f43.
