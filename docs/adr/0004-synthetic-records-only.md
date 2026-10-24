# 0004: Synthetic records only for anything about households

Date: 21 October 2026. Status: Accepted (a rule in CLAUDE.md).

## Context

The move-on planner works household by household, and the households in temporary
accommodation are vulnerable. The market picture uses aggregates; the planner needed records to
work on.

## Decision

- Aggregates only: no household-level data, no addresses, nothing that locates anyone. Phase 2
  uses synthetic records only (CLAUDE.md lines 9-10).
- `tamarket/synthetic.py` makes up households from a seed. Every record carries
  `"synthetic": true`, an id starting `SYN-` and a record type that says so; there are no names,
  addresses or postcodes. Shares follow MHCLG's England figures where they are published and
  stated guesses elsewhere, each listed with its confidence.
- The hosted database refuses any household id that is not SYN-0001 to SYN-9999, on every table
  (`hosted/README.md`; the migration).

## Options ruled out

None recorded.

## Consequences

- Synthetic stays were capped where a draw was implausible: for priority needs tied to age
  after one record showed a 16 or 17 year old in temporary accommodation for 500 weeks, and at
  36 weeks for households accepted because they include a pregnant woman, after the review found
  42 and 43 week pregnancies. The caps are [Guessing] (decision log lines 31 and 45).
- Household composition, most length-of-stay bands, adult-only priority needs, most support
  needs, how needs combine, local connection and the spread of weekly cost are guesses; the
  caseload is for testing the planner only (decision log, deferred line 62).
- Each statutory decision (an offer, a referral, ending a duty) is made and recorded outside the
  planner; plans are suggestions for an officer to approve (`app/README.md` lines 9-11).

## Where recorded

Line numbers are as at commit bf88a6e.

- `CLAUDE.md` lines 9-10.
- `README.md` lines 163-173.
- `tamarket/synthetic.py` lines 1-25.
- `docs/decision_log.md` lines 31 and 45; deferred line 62.
- `hosted/README.md` lines 9-12; `supabase/migrations/20261021000000_move_on_planner.sql` lines
  3 and 65.
- `tests/test_synthetic.py`.
- Commits 779d3f6, 50afd0b and f1c5d19.
