# 0009: The deny list stays out of git and off the page; the screen's word lists stay out of git

Date: 21 October 2026. Status: Accepted (a default, open to the owner).

## Context

The planner's screen runs fd-core's checks in JavaScript, which needs fd-core's patterns,
including the accusing and judging words it blocks. A file listing those words would trip this
repository's own screen. The private deny list holds names that must never appear anywhere.

## Decision

- The working deny list, `config/deny_list.txt`, is local and gitignored; the tracked file is
  `config/deny_list.example.txt`. The deny list is never shipped to a page (`README.md` lines
  122 and 199).
- fd-core's patterns for the JavaScript screen are generated into
  `tamarket/spec/fdcore_patterns.json` by `scripts/export_fdcore_patterns.py` and kept out of
  git, because the file lists the words the screen blocks (decision log line 22). The page needs
  them, so they ship in `app/dist` and on the demo site; only the deny list never ships (title
  corrected on 22 October 2026, after the fact-check of that day).
- The patterns reach the hosted site and the drafting function the same way, generated at build
  time into folders that stay out of git, so neither the repo nor the policy file changes
  (decision log line 38).
- On the hosted site only the drafting function reads the deny list, from a secret or a table
  that only it can read, and it drafts nothing if the list cannot be read. Private drafts and the
  deny list are not audited, so the shared log never holds either (decision log lines 35 and 36).
- Test fixtures that must trip the screen are stored split into parts and joined at test time,
  as fd-core's own tests do (decision log line 23).

## Options ruled out

- A guardrails policy line for the generated patterns file: named as the alternative and not
  taken (decision log line 22).
- Switching checks off for test paths: not taken; fixtures are split instead (decision log
  line 23).

## Consequences

- The page cannot run the deny-list check. The fact-check of 21 October 2026 found the Method
  view saying the page's screen covers "names on the deny list"; it now says that only the
  hosted function does (commit 07e5f43).
- The deny list is empty and is to be reviewed before anything is public (decision log,
  deferred line 61). The guardrails review of 21 October 2026 found both repos' lists hold only a
  comment line, so the name check matches nothing (item 6) [Certain from the file].
- Before a page or a function screens plans, `scripts/export_fdcore_patterns.py` must have run;
  `tests/test_moveon.py` checks that the export matches fd-core and stays out of git.

## Where recorded

Line numbers are as at commit bf88a6e.

- `README.md` lines 118, 122 and 196-199; `app/README.md` lines 104-108.
- `docs/decision_log.md` lines 22, 23, 35, 36 and 38; deferred line 61.
- `.gitignore` lines 8-9, 15-17, 19-20 and 22-25.
- `tests/test_moveon.py` (`test_fdcore_export_matches_fdcore`,
  `test_fdcore_export_stays_out_of_git`, `test_deny_list_names_are_rejected`).
- Commits 779d3f6, d14b587 and 07e5f43.
