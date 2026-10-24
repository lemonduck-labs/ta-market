# 0005: Four rule-chosen example councils in the shared demo

Date: 21 October 2026. Status: Superseded by 0006.

## Context

ADR 0001 (decided by the owner at 12:46 on 21 October 2026) keeps council names out of anything
shared: the demo shows one example council against unnamed peers. The demo needed a way to pick
which councils serve as examples.

## Decision

As built at 13:05 (commit 5bc053d): `scripts/build_demo_data.py` wrote the "yours against the
rest" data with every compared council as an unnamed point sorted by cost, quartiles, and four
examples chosen by fixed rules (a typical London council, a typical one in the rest of England,
a figure driven by how spend is booked, and a very low figure), each with rounded figures and
the questions it raises. Councils with quarter jumps or empty TA lines were never examples. A
test checked that no council name or code reached the file.

## Options ruled out

None recorded at the time.

## Consequences

- At 14:12 (commit b80f5a6) the shared demo moved to two typical examples, with councils far
  from their peers counted and never shown on their own (ADR 0006). The decision log row gives
  the consideration: examples are unnamed, not anonymous, since each matches one council in the
  published data (decision log line 15). That an unusual example shown on its own could be
  matched to a council and read as a judgement on it, as ADR 0001 warns for named lists, is the
  reading of that row [Likely: the commit does not say so in these words].
- The first version of the TA dashboard, published privately earlier on 21 October 2026, held
  the unusual examples and every compared council as a dot. None of those versions is to be
  shared, since comparing them with the current version would point at the councils left out
  (decision log line 18).

## Where recorded

Line numbers are as at commit bf88a6e.

- Commits 5bc053d (the four examples), 17e0e65 and fc128a8 (the datasets and page built on
  them), b80f5a6 (the change).
- `docs/decision_log.md` lines 15 and 18.
- `docs/adr/0001-no-council-names-in-shared-outputs.md`.
