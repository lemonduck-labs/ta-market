# 0007: Four-eyes approval bound to a SHA-256 fingerprint; approval is not the statutory decision

Date: 21 October 2026. Status: Accepted (a default, open to the owner).

## Context

Move-on plans are drafted by Claude or from a template, on synthetic records, for a housing
officer to approve (WORKFLOW.md stage 4). The radar's workspace had been reviewed first; its
finding 3 asked for the store itself to say who saved and who approved, and the planner took the
same design (decision log line 25).

## Decision

- Plan versions, decisions and the audit log are stored under each person's own path, which the
  store's rules let only that person write (decisions at Editor level), so the path says who
  saved, who approved and who did what (decision log line 25). That the platform enforces these
  rules for people other than the owner is [Likely] (Consequences).
- An approval counts only for a version whose text still matches its SHA-256 and, with
  four-eyes on (the default), was saved by someone else; a decided plan shows the version its
  decision names (decision log line 25).
- An approval by the person who saved the version counts only while the shared four-eyes
  setting is off and the decision records it as off; with four-eyes on it never counts, whatever
  the decision's own field says, since the approver writes that field. Such approvals are marked
  "One person" on the caseload, the household and the plan pack (decision log line 39).
- Approving a plan records that a second officer has read it and agrees it is the plan to work
  from. Each statutory decision (an offer, a referral, ending a duty) is made and recorded
  outside the planner (decision log line 26).
- On the hosted site the database refuses an approval when four-eyes is on and the approver
  saved the version, or when its SHA-256 is not the version's, and it reads the four-eyes
  setting itself; it also refuses a version whose SHA-256 is not that of its plan in the page's
  canonical JSON (decision log line 33).

## Options ruled out

- Letting the decision's own four-eyes field decide: replaced after the independent review of
  the planner (its finding 3) showed a self-approval marked four-eyes off counting with the
  setting on (decision log line 39; commit f1c5d19).
- No other option is recorded as ruled out.

## Consequences

- That the artifact platform enforces the path rules for people other than the owner is
  [Likely] until checked with a second account at Contributor and one at Editor (decision log
  line 25; deferred line 65).
- The hosted database's checks are tested on a local Postgres 16 with a stand-in for Supabase's
  auth, not on a live project (decision log, deferred line 67; `hosted/README.md` lines 280-287).
- Not guaranteed even when hosted: the table owner can still change the file pointer, checks,
  progress, the setting and members, or drop the triggers; and the database checks a plan's
  fingerprint, not its words (`hosted/README.md` lines 269-279).
- Since commit c165ef6 (22 October 2026) lessons follow the same pattern in the pilot, with no
  setting to turn off: a return note kept as a lesson is in force only once an officer other than
  the one who kept it approves it with a reason, for the SHA-256 saved with it. Demo mode has
  three demo officers (a housing officer at Contributor, a reviewing officer and a team leader
  at Editor), so four-eyes can be tried in one tab [Certain, from `app/src/page.js` at c165ef6].

## Where recorded

Line numbers are as at commit bf88a6e.

- `WORKFLOW.md` line 8.
- `docs/decision_log.md` lines 25, 26, 33 and 39; deferred lines 65 and 67.
- `app/README.md` lines 76-95 and 110-129.
- `app/src/page.js` lines 358-366 (`approvalCheck`).
- `supabase/migrations/20261021000000_move_on_planner.sql` lines 12, 318, 368 and 384;
  `tests/test_hosted_db.py`.
- `hosted/README.md` lines 250-279.
- Commits 50afd0b, f1c5d19 and d14b587.
