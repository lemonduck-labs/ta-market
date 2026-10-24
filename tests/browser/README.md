# Browser flow for the planner page

An end-to-end flow for the Move forward planner (`app/dist`), run in Chromium against `mock.js`, a
stand-in for the claude.ai viewer's capabilities (`db`, `user`, `sample`, `downloads`). The mock
applies the same per-path rules the page declares at publish (author-bound versions, decisions
and audit; decisions and config at Editor level; private drafts), so the flow tests the page's
logic against those rules. It does not test the platform's own enforcement, which needs a second
account on the published artifact [Certain].

Users in the mock are role labels (Owner A, Editor B, Contributor C, Viewer D), chosen with
`?role=` and `?uid=` in the URL. Every household is synthetic.

## Run

```sh
python3 scripts/build_app.py    # from the repo root: writes app/dist
cd tests/browser
npm install                     # Playwright 1.64.1
npx playwright install chromium # once, if no Chromium is installed
sh build.sh
(cd dev && python3 -m http.server 8766) &
node flow.mjs http://localhost:8766 shots/flow
node lessons_flow.mjs http://localhost:8766 shots/lessons
node nav_flow.mjs http://localhost:8766 shots/nav
```

Each prints its steps and ends with `flow passed`, `lessons flow passed` or `nav flow passed`; a
failed step throws. `tests/test_browser_flows.py` builds the page and runs all three under pytest,
and is skipped when node or the pinned Playwright in `node_modules` is missing.

## What the flow covers

Template, save and submit; the screen stopping a stated decision, a figure not in the record,
a name and a phone number in a progress note; four-eyes (a self-approval does not count with the
setting on, including one whose decision claims it was off; with four-eyes off it counts and is
marked "One person"; turning it back on stops it counting); approval and the plan pack;
tampered and forged approvals; Claude drafts stopped and passed; roles; reviewer notes (a return
note that reads as an instruction is refused, Claude is given the note, a draft that ignores it is
stopped, the old version cannot be resubmitted, and the template opens the editor on the note);
demo mode with no store;
the scenario arithmetic; the audit export; narrow screens.

Lessons (`lessons_flow.mjs`): an editor keeps a return note as a lesson for a route out; its
author cannot approve it and a second officer approves it with a reason; a later plan for a
household with that route recalls it with its provenance, and Claude is sent it as data with no
names; a household without the route does not recall it; a changed text stops it being used;
retiring it ends it; the audit log records each step; three demo officers in one tab; narrow
screens.

Navigation (`nav_flow.mjs`), fd-core's shell as the planner uses it: the sidebar's queues and views
with their counts (an empty work queue shows none); a view's own link (#ood), its households and
order; j and k through the list and between households, with the household's place in the view;
Escape back to the row it came from; the search palette by record id and by page, and its empty
state; the shortcuts sheet, whose Escape leaves the page as it was; g then a letter; keys ignored
while typing in a field; a view reloaded from its link; the drawer on a narrow screen.
