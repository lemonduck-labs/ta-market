# 0003: A savings figure is never presented as fact

Date: 21 October 2026. Status: Accepted (a rule in CLAUDE.md).

## Context

The picture shows what councils spend per household-year on each type of temporary
accommodation. A gap between two types (nightly-paid against leased homes, for example) reads
easily as a saving a council could make, though households, places and lease costs differ.

## Decision

- No savings figure is presented as fact. The price gap between nightly-paid and leased homes
  is an input the user sets (CLAUDE.md lines 14-15).
- `tamarket/scenario.py` does arithmetic on a council's own inputs and echoes them back:
  households moved, its own price gap per household-year, set-up cost, void cost and lease term.
  It returns the gross and net difference a year, the set-up cost, the net difference over the
  term and the payback, and is never a forecast and never a saving the council will make.
- The scenario on the planner page sets no input itself. It can offer the caseload's count on
  the first type as the cap, and shows England's average weekly spend by type from RO4 for
  reference only, labelled as averages and not a price gap (decision log line 30).

## Options ruled out

None recorded.

## Consequences

- The README gives the 2024-25 figures by type with the line that the gap between two types is
  not a saving (`README.md` lines 33-35).
- `tamarket/spec/scenario_cases.json` holds 14 input sets with their exact outputs, including
  the errors, and the JavaScript port passes them (`tests/test_spec_js.py`, `tests/test_app.py`)
  [Certain].
- The planner's evals found that the plan screen let a saving through when stated as fact,
  whether with a figure from the record or with none. Since commit 09b9c40 (22 October 2026) the
  screen's decision rule stops it, and a saving given as a pound figure is stopped even when
  hedged; shared cases c60 to c66 hold this [Certain, as the commit records].
- The move-on-planner agent file still describes plans that say "what each move would save
  under the user's assumptions"; it is out of date and waits for the owner's next edit of the
  agents (decision log, deferred line 64). Updated 22 October 2026: rewritten as
  `.claude/agents/move-forward-planner.md`, which refuses to present a saving as a fact.

## Where recorded

Line numbers are as at commit bf88a6e.

- `CLAUDE.md` lines 14-15.
- `README.md` lines 33-35, 63-64 and 152-161.
- `tamarket/scenario.py` lines 1-27.
- `docs/decision_log.md` line 30; deferred line 64.
- `app/README.md` lines 131-135.
- `tests/test_scenario.py` (`test_inputs_are_echoed_and_it_is_never_a_forecast`).
- `tamarket/spec/screen_rules.json` and `tamarket/spec/screen_cases.json` (cases c60 to c66).
- Commits 779d3f6 (the scenario), 50afd0b (the page) and 09b9c40 (the screen).
