# Temporary accommodation market picture: project rules for Claude

The build shows, council by council, how many households are in temporary
accommodation, in what kind, and at what cost, then (phase 2) drafts move-forward plans on
synthetic records for a housing officer to approve.

## Hard rules

- Aggregates only. These are vulnerable households: no household-level data, no
  addresses, nothing that locates anyone. Phase 2 uses synthetic records only.
- No names of people or firms. Providers are described by type, never named.
  Publishers of cited sources may be named; providers and people never.
- No council names in comparisons in anything shared (docs/adr/0001).
- Never present a savings figure as fact. The price gap between nightly-paid and
  leased homes is an input the user sets.
- Every number traces to a processed table and an ingest-log entry, with its release.
- Every inference carries [Certain], [Likely] or [Guessing].
- Contains public sector information licensed under the Open Government Licence v3.0:
  this line goes on every screen and report that shows MHCLG data.
- Nothing leaves the repo until the fact-checker and guardrails-reviewer agents pass it
  (/review, then /ship).
- British English. No em dashes.

## Team (.claude/agents)

| Agent | Owns |
|---|---|
| housing-data-engineer | MHCLG pulls, releases, checksums, ingest log |
| market-analyst | Cost per household, accommodation mix, trends, outliers, savings model |
| move-forward-planner | Phase 2: move-forward plans on synthetic records into the approval queue |
| fact-checker | Re-derives every number before sharing |
| guardrails-reviewer | Blocks names, personal data, accusations, licence problems |

Commands: /pull, /picture, /review, /ship. The workflow is in WORKFLOW.md.

## Shared core

fd-core (../fd-core) provides the ingest log, snapshot checks, guardrails screen and
decision log. Install with pip install -e ../fd-core.
