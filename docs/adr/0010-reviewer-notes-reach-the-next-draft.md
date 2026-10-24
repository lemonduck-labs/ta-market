# 0010: Reviewer notes reach the next draft and must be answered

Date: 21 October 2026. Status: Accepted (signed off by the owner for phase 3).

## Context

When an editor returns or rejects a plan, what they write should shape the next draft, but text
that reaches a drafting prompt can carry a planted instruction. The radar's analyst briefs had
taken the same step first (decision log line 43).

## Decision

- What an editor writes when returning or rejecting a plan goes to the next draft as a reviewer
  note, apart from the record, and the next version must answer each note before it can be
  saved, submitted or approved.
- Notes are rebuilt from the decisions (since the last approval that counts, latest five), so the
  hosted function reads them from the database rather than taking them from the page. Each
  version keeps the notes it answered and is screened against them.
- A note never extends the record: a figure or a name in a note is still refused in the plan. A
  note that reads as an instruction to Claude is refused at the return and held back if it gets
  through.
- Signed off by the owner on 21 October 2026 ("Continue with phase 3 builds").

## Options ruled out

- Notes sent by the page to the function: a caller could plant one (decision log line 43).
- A version screened against the notes of today rather than of its own day: an old version
  would no longer pass the screen (decision log line 43).

## Consequences

- The template answers each note with a placeholder that the screen refuses until a person
  writes the answer (`app/README.md` lines 115-119).
- The Python reference and the JavaScript ports pass 14 new screen cases, 18 note cases and 11
  notes-from-decisions cases (commit e2ece8d) [Certain, as the commit records].
- The database refuses a version whose plan does not answer the notes it lists
  (`hosted/README.md` lines 139-144).
- Since commit c165ef6 an editor returning a plan can also keep the note as a lesson for the
  household, a route out or a kind of accommodation. Once a second officer approves it, later
  drafts it applies to recall at most five lessons and are given them as data in their own
  block, apart from the notes (ADR 0007; fd-core research log P1.2) [Certain, from the commit
  and `app/src/page.js`].

## Where recorded

Line numbers are as at commit bf88a6e.

- `docs/decision_log.md` line 43.
- `app/README.md` lines 110-122.
- `tamarket/spec/screen_rules.json` (review), `app/src/page.js`,
  `supabase/functions/draft-plan/core.mjs`.
- Commit e2ece8d.
