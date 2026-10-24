# 0006: Two typical unnamed examples, counts of patterns, and data checks left out of the dots

Date: 21 October 2026. Status: Accepted (a default, open to the owner).

## Context

ADR 0005's four examples included two chosen for being unusual. Each example is unnamed but
matches one council in the published data, and some councils' figures need a person's check
before anything is said about them (quarter-to-quarter jumps in the counts, or nothing booked on
the TA spend lines).

## Decision

- The shared demo shows two example councils only, the council closest to the median in each
  peer group (London, and the rest of England). Councils far from their peers are counted on the
  Patterns card, never shown on their own; the unusual examples stay in private copies
  (decision log line 15).
- Councils averaging at least 100 households with a quarter-to-quarter change of more than 40%
  in the counts held, or with nothing on TA lines 80 to 86 in 2024-25 or 2025-26, are left out
  of the dots, quartiles and examples and only counted, for England as a whole, until a person
  checks them. Councils more than twice or under a quarter of their peer median stay in as
  unnamed dots (their own published figures) and are counted. No lead or check flag is shown for
  any council (decision log line 16).
- Coverage counts give one "not shown as dots" row by peer group and the data-check count for
  England only, so that no small count points at one council. Each example is drawn once, as
  "this council" at its rounded figures, and is not also a grey dot. A tie for the example goes
  to the lower gross figure (decision log line 17).
- The band, median and ratio beside an example are computed over the other councils shown, so
  the example keeps its rounding (commit d61e73a).
- The tracked phase 0 report compares the councils the demo shows, and gives the reasons a
  council is not compared for England only (decision log line 44).

## Options ruled out

- The four rule-chosen examples of ADR 0005, replaced by this decision.
- No other option is recorded as ruled out.

## Consequences

- The data checks wait for a person; until then the councils concerned are only counted
  (decision log, deferred line 57).
- The council tables `data/processed/picture_councils_2024-25.csv` and `_2025-26.csv` name every
  council beside its ratio to the peer median; this public copy leaves them out (`PUBLIC.md`).
- ADR 0001 still calls the examples "anonymised"; they are unnamed, not anonymous (decision log,
  deferred line 59).
- Earlier dashboard versions are not to be shared, and the artifact's file store still holds a
  first quartiles upload with the example inside the median, which gives its gross figure back
  to about 10 pounds; that adds nothing to identification, since each example already matches
  one council on its rounded figure [Likely] (decision log line 18).

## Where recorded

Line numbers are as at commit bf88a6e.

- `docs/decision_log.md` lines 15, 16, 17, 18 and 44; deferred lines 57, 58 and 59.
- `scripts/build_demo_data.py`, `scripts/build_picture.py`, `tamarket/display.py`.
- `tests/test_demo_data.py` (`test_only_the_two_typical_examples`,
  `test_patterns_are_counts_only_and_add_up`,
  `test_the_tracked_report_compares_the_councils_the_demo_shows`).
- Commits b80f5a6, 05180d1, d61e73a, 8b9b13f and ee66ec2.
