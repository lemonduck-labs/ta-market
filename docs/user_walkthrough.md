# Move forward planner: user walkthrough script

A 30-minute usability session with one housing officer, run by the owner. The planner runs on
the demo site in demo mode: 200 made-up households, no sign-in, no AI drafting, nothing sent
anywhere.

## 1. Purpose and what we want to learn

We want to see whether a housing officer can use the planner for their own work without help,
and where it gets in their way. We are testing the tool, not the officer.

Research questions:

1. Can an officer find the households that have been longest in temporary accommodation, or
   that they would see first for another reason, and see why a route out is suggested for one
   of them?
2. Do they trust a first draft of a plan enough to edit it rather than rewrite it?
3. Do they understand that the screen is a net and that they decide: the planner suggests, the
   officer decides, and each statutory decision is made and recorded outside the planner?
4. Does four-eyes approval, where a second officer signs off every plan, fit how their team
   works?
5. Do they read the scenario calculator's result as arithmetic on figures they set, not a
   forecast and not a saving?

The session is not for showing the tool off, training anyone or collecting case information.
The participant brings nothing and types nothing from their work.

## 2. Before the session (for the owner)

**The link.** The demo site's planner page: `https://lemonduck-labs.netlify.app/planner/`.
Nothing to install, no sign-in. Open the planner itself, not the site's front page, so the
session starts on the caseload. The site was published on 24 October 2026 (diversion-radar's
`site/README.md`). An in-person session can also run from a local copy on
your own laptop: in diversion-radar, build the site (`python scripts/build_site.py`, with
ta-market beside it; add `--clean` for the copy you publish), serve it
with `python -m http.server 8000 --directory site/dist`, and open
`http://localhost:8000/planner/` on the same laptop.

**Who to invite.** A housing officer who works with households in temporary accommodation, for
example in a temporary accommodation, move-on, allocations or housing options team. No technical
knowledge needed. They should not have seen the planner or its walkthrough video.

**What to tell them beforehand.** It takes 30 minutes. If remote, they need a laptop or desktop
with a recent browser (a phone works, but editing a plan is easier on a bigger screen). They
bring nothing: no files, case notes or figures.

**Synthetic records only.** Every household in the planner is made up from a seed. None is a
real person, and the records hold no names, addresses or postcodes. Never ask the participant to
bring or type case data, names, addresses or their council's own figures. If they start to, stop
them and steer back to the made-up records. If they mention a household or a colleague aloud,
don't write it down.

**Nothing they type is kept after the tab closes.** The demo has no shared store: plans, notes,
checks and progress live in the browser tab, go when it closes, and are never sent anywhere. One
catch: in an ordinary window the browser remembers who you are acting as, the scenario figures,
the caseload's filters and order, and the last page shown, until its site data is cleared. So
always open the link in a new private window and close it at the end; then nothing at all is
kept.

**Consent.** Ask before you start; the welcome below has the words. Notes need their yes. Record
only if they agree, and then only the screen and your voices; keep the recording in the same
private place as the log, never in a repo, and delete it by the date you give them.

**Checklist**

- [ ] The site is built from the pages you mean to test: rebuild diversion-radar's `site/dist`
      before the first session and check that its `site.json` names the commits you expect, with
      no uncommitted changes. On 22 October 2026 at 02:37 the copy there was built with
      `--clean` from diversion-radar 33ca4fb, ta-market 98c745a and fd-core 72ead08.
- [ ] The link opens on the device and network the participant will use. Council networks often
      block new sites: check a day ahead, and have your own laptop ready.
- [ ] You have run every task yourself on the build you will test, in a private window, and
      corrected the crib below if anything has moved.
- [ ] A new private window is open on the planner's caseload, acting as the housing officer, with
      no filters set. Open it in the minutes before the session; never reuse one from a rehearsal
      or an earlier participant.
- [ ] You won't reload the page or press back during the session: in demo mode that clears the
      plans made so far.
- [ ] The log (section 4) is ready in a private document or on paper, with a clock to hand.
- [ ] You have the fallback line for task 4 ready: "The household is eligible for social
      housing."
- [ ] You have not sent the walkthrough video or screenshots: finding things is part of what we
      test.
- [ ] You have asked whether they use screen magnification, a screen reader or other settings,
      and set the device up to match.
- [ ] Remote: they open the link in a private window and share their screen. If it won't open on
      their network, share yours and let them tell you what to do; note that in the log.

**Owner's crib for today's build** (for you only: never read it out or point to it)

Checked on 22 October 2026 against the page at commit 01164e9 (the counts, labels and screen
results below against its committed code and data); task 1's B&B count and stay re-checked on
22 October 2026 against the synthetic records of generator version 2 (commit d232df1), which place
families in B&B within the last 12 weeks. The layout will change; the task wording
should not.

| Task | Where it is today | What the tool shows when it works |
|---|---|---|
| 1 | Caseload page. The list opens in "Longest in TA first" order (top: SYN-0165, 519 weeks). Buttons filter by plan state; menus set accommodation type, check raised and order; a box finds a record id. "Check raised: Family in B&B" leaves 5 households, the longest SYN-0184 at 8 weeks. The "Acting as" menu at the top of the page starts on "Housing officer (demo)", a Contributor. | A household's file opens, marked "Synthetic record", with its plan state. |
| 2 | The household's file. On the right, "What legislation and guidance say for this record (a selection)": each route with "Listed because:" and its reasons, each marked Certain, Likely or Guessing, with sources. Lower left, "Checks", in groups, each with Open, Checked and Not applicable. | They read out a reason and a check. |
| 3 | "Move-forward plan" card: "Start from the template" is the only way to start, as AI drafting is off in the demo. Then "Edit"; "Done editing" works only when the plan passes the screen; then "Save draft". "Cancel" in the editor drops that round of edits. | "Drafting", "Version 1 of 1, saved (time) by Housing officer (demo) (you)". |
| 4 | Any text box in the editor. A saved plan reopens with "Edit this version". | "Not yet: fix these before saving." and "States a decision; write a suggestion or a check instead", with "Done editing" off. |
| 5 | "Submit for approval" shows once a version is saved and no unsaved draft is open. As the housing officer they then see "Awaiting approval by an editor." and nothing to press. To play the second officer they switch "Acting as" to "Reviewing officer (demo)", an Editor; "Team leader (demo)" is a third person, also an Editor. The return form has a box, "Keep this note as a lesson for later plans", whose lesson waits on the Lessons page for an officer other than the one who kept it. | "Awaiting approval". As the reviewing officer: Approve, "Return with a note" and "Reject" are open. An Editor who saved the version cannot approve it while four-eyes is on. The four-eyes switch is on the Method page, for Editors. |
| 6 | Scenario page: seven inputs, all needed before any result shows. "Use it as the cap" offers the caseload's count. The England averages are for reference only. | Five money results and a payback, under "Arithmetic on the inputs you set. Not a forecast, and not a saving the council will make." |

Switched off in the demo: AI drafting, and every download (plan pack, audit export, scenario
file). If they reach one, ask what they expected it to do.

What the screen does on today's build, checked on 22 October 2026, so you can log what you see:

- Short case-note lines that state a decision are stopped, for example "Discharge duty into the
  private rented sector.", "Offer refused, close the case." or "Approve the offer." (since commit
  4c2d8e1). If a line that states a decision still gets through, log it as a miss by the screen,
  not a mistake by the participant.
- Named public services pass, for example "Children's Services" written with capitals (since
  4c2d8e1). Log any other ordinary term stopped as a possible name.
- A figure from the record passes wherever it is used: "within 2 weeks" passes for a household
  of two.

## 3. Script: 30 minutes

| Clock | Block | Minutes |
|---|---|---|
| 0:00 | Welcome, ground rules and consent | 3 |
| 3:00 | Warm-up: how they do this work today | 3 |
| 6:00 | Task 1: find a household to look at first | 3 |
| 9:00 | Task 2: why a route out is suggested, and its checks | 3 |
| 12:00 | Task 3: a first plan, edited | 4 |
| 16:00 | Task 4: write down a decision | 2 |
| 18:00 | Task 5: pass the plan for sign-off | 3 |
| 21:00 | Task 6: work out a scenario | 3 |
| 24:00 | Closing questions | 5 |
| 29:00 | Thanks and close the window | 1 |

Running late: at 16:00, if no plan is saved yet, help them save one so tasks 4 and 5 can follow,
and mark task 3 "with help". If you are more than three minutes behind at 21:00, keep task 6 to
finding the calculator and reading one result. Never cut the closing questions.

How to run the tasks:

- Read each task as written. Don't name a page, button or menu, and don't point. Finding the way
  is part of the test.
- Let silence run. If they go quiet, ask "What are you thinking?"
- If they ask you something, turn it back: "What do you think it does?" Note the question.
- If they are stuck, wait about a minute, then ask "What would you try next?" If they are still
  stuck when the task's time is up, show them and mark the task "with help".
- Note the clock when each task starts and ends.

### 0:00 Welcome, ground rules and consent (3 minutes)

Say:

> Thank you for giving me half an hour. I'm going to show you a tool for planning moves out of
> temporary accommodation, and ask you to try a few things with it.
>
> We are testing the tool, not you. If something is hard to find or doesn't make sense, that's a
> problem with the tool, and it's what I most need to hear. There are no wrong answers.
>
> Please think aloud as you go: what you're looking for, what you expect to happen, and anything
> that surprises or annoys you. If you go quiet, I may ask what you're thinking.
>
> I won't help much while you work, because I want to see what you'd do on your own. If you ask
> me something, I may ask what you think first. I'll answer anything at the end. I'll keep us to
> time, so I may move us on before you've finished something, and that's fine.
>
> Every household in this tool is made up. None is a real person, and there are no names or
> addresses in it. Please don't type anything from your own work: no names, addresses, case
> details or your council's figures. If you need an example, make one up.
>
> This is a demo. It runs in this browser window, sends nothing anywhere, and keeps nothing once
> the window is closed. A few things are switched off, such as downloads. If you reach one, tell
> me what you'd expect it to do.
>
> The screens are going to be redesigned, so anything that doesn't work for you is the most
> useful thing you can tell me.
>
> I'd like to take notes. They won't have your name or your employer on them, and I keep them
> privately. Is that all right?

Wait for the answer. If you would like a recording, ask:

> Would you be happy for me to record the screen and our voices, so I can check my notes? I'd
> delete it by [date]. It's fine to say no.

Then:

> You can stop at any time, or skip anything. Any questions before we start?

### 3:00 Warm-up (3 minutes)

Say:

> Before we look at the tool: tell me how you work out a move-forward plan for a household in
> temporary accommodation today. Think of the last one you did, and keep it general: no names or
> details that could identify anyone.

Follow-ups, as time allows:

- "How do you decide which household to look at first?"
- "Where do you write the plan down, and who sees it?"
- "Does anyone check or sign off a plan before you act on it? Who?"
- "What takes the longest?"

Listen for how they prioritise, where plans and decisions are recorded today, and whether a
second officer checks plans now. Note systems by type ("case management system", "spreadsheet"),
never by product or supplier. You will come back to these in tasks 1, 3 and 5.

### 6:00 Task 1: find a household to look at first (3 minutes)

Say:

> Here's the caseload. Find a household you would want to look at first today, and tell me why.

**Success looks like:** they open one household and give a reason that comes from its record:
time in temporary accommodation, a family in bed and breakfast, cost, children, medical needs, a
placement outside the district. Better still, they bring that kind of household to the top or
narrow the list, rather than scrolling through 200.

**Watch for:**

- Whether they notice the list is already in an order, and which.
- Whether they find a way to show only some households (families in bed and breakfast, say),
  and how long it takes.
- What they weigh, and anything they look for that the list doesn't offer, such as a review
  date, a risk flag or the officer who has the case.
- Whether the made-up figures look believable to them: the top of the list has been in
  temporary accommodation for 519 weeks.

**Prompts:**

- "What made you pick that one?"
- "What did you expect to see in this list?"
- "How does this compare with how you'd find that household today?"

### 9:00 Task 2: why a route out is suggested, and its checks (3 minutes)

Say:

> For this household, tell me which routes out the tool suggests, why it suggests one of them,
> and what you would need to check before you acted on it.

Any household works. If they have moved on from the one they chose, let them carry on with the
one in front of them.

**Success looks like:** they name the routes listed, give the tool's reason for one of them in
their own words, and name at least one check they would make before acting, with where it comes
from.

**Watch for:**

- Whether they read "listed" as "the household qualifies" or "is owed it".
- Whether they notice the marks Certain, Likely and Guessing, and the sources, and what they make
  of them.
- Whether they notice the checks are a selection, not the whole code of guidance.
- Whether they mark a check as done, and what they think that records.
- A route they expected that isn't listed.

**Prompts:**

- "What does 'listed' mean to you here?"
- "How sure is the tool about that? How can you tell?"
- "What would you check that isn't here?"

### 12:00 Task 3: a first plan, edited (4 minutes)

Say:

> Get a first draft of a move-forward plan for this household. Then make it read the way you'd want
> it to: change, add or take out whatever you would. Keep to this made-up household, please.

**Success looks like:** they start a plan (in the demo the template is the only way), change at
least one thing, and save it as a version. They can say whether they would work from this draft
or start again.

**Watch for:**

- How they find where to start, and what they expect a template to give them.
- Their first reaction to the draft: its length, its wording (the checks are copied word for word
  from legislation and guidance), its order.
- Whether they edit a few lines or clear it out and rewrite (research question 2).
- Whether finishing an edit feels like saving it. Today the plan is not kept as a version until
  it is saved: note whether they notice.
- Whether they cancel an edit and lose their changes.
- What they make of the confidence and owner choices on each line.

**Prompts:**

- "What did you expect to happen?"
- "Would you send this as it is, edit it, or start again? Why?"
- "What would you change first?"
- "Is anything missing that you'd expect in a plan?"

### 16:00 Task 4: write down a decision (2 minutes)

Say:

> Add a line to the plan recording what you've decided for this household, as you'd write it in
> your own case notes. Keep it to this made-up household: no names or addresses.

If the screen lets their line through, ask "Did you expect it to accept that?", then:

> Could you also try this exact line: "The household is eligible for social housing."

**Success looks like:** the screen stops the line, they read why, and they can say what it means:
the tool suggests, the officer decides, and the decision is recorded outside the planner. They
then reword it as a suggestion or a check, or take it out.

**Watch for:**

- Their first reaction: annoyed, reassured, confused, amused.
- Whether the message tells them how to fix the line, in words they would use.
- Whether they try to get round it with a rewording that means the same.
- Whether their own wording got through. If a line that states a decision does, log the line,
  if it holds nothing from a live case, as a miss by the screen.
- Where they say the decision itself would be recorded.

**Prompts:**

- "What is the tool telling you there?"
- "What did you expect to happen when you typed that?"
- "Where would you record the decision itself?"

If they can't get past the screen, let them cancel that edit: the version saved in task 3 is
still there for task 5. While an unsaved draft is open, the plan can't be sent on until the draft
is saved or discarded.

### 18:00 Task 5: pass the plan for sign-off (3 minutes)

Say:

> This plan needs a second officer to sign it off. Pass it to them using the tool. Then tell me
> what you expect that officer to do with it, and what happens if they don't agree with it.

If time allows, ask: "Could you now play that second officer?"

**Success looks like:** the plan is waiting for approval. They describe the second officer
reading it and then approving it, sending it back with a note, or rejecting it, and they notice
that they can't sign off their own plan. If they play the second officer, they act as the
reviewing officer and approve the plan, return it with a note or reject it.

**Watch for:**

- Whether they expect the second officer to be told. The tool sends no message today: ask how
  they would let that officer know.
- Whether they try to approve it themselves, and their reaction when they can't.
- Whether they work out how to become the second officer, and how long it takes.
- If they keep a return note as a lesson for later plans: what they expect it to do, and who
  they think must approve it.
- What "approve" means to them: agreeing the plan to work from, or making a statutory decision.
- If they find the switch that lets one person approve, what they make of it.
- Whether a second officer is realistic in their team: who, how often, how soon.

**Prompts:**

- "What did you expect to happen?"
- "Who would that be in your team?"
- "How would they know it's waiting for them?"
- "What should happen if they disagree?"
- "How does this compare with how plans are signed off where you work?"

### 21:00 Task 6: work out a scenario (3 minutes)

Say:

> Your manager asks what it would come to if some households moved from nightly-paid
> accommodation into leased homes. Use the tool to work it out. Please use made-up round numbers,
> not your council's figures.

If they ask what numbers to use: "Any round numbers will do. For example, 20 households."

**Success looks like:** they find the calculator, set every input, and describe the result as
arithmetic on the figures they set: not a forecast, and not a saving the council will make.

**Watch for:**

- Whether they expect the tool to fill in a price gap or a cost for them. It never does.
- Whether they take the England averages as their own price gap.
- Whether they call the result a saving, and what they would do with the figure. Saving it as a
  file is off in the demo; note what they expected.
- How they read the payback, and "not recovered".
- Whether the messages on the inputs make sense to them.

**Prompts:**

- "What does that figure tell you?"
- "How would you describe it to your manager?"
- "What would you need before you put it in a report?"

### Optional, in a longer session: the notices for a placement (4 minutes)

Say:

> A family has just been placed in another council's area. What does the tool say needs doing,
> and how would you show it was done?

**Success looks like:** they find Notices and clocks on the household (or Compliance at risk),
read the last day for each notice, open a draft, and record a notice as sent with its date. They
say that the tool does not send anything.

**Watch for:**

- Whether the placeholders in the draft are clear, and whether they would copy the draft into
  their own system.
- Whether "ask the parent" before the child's notices matches how they work, and who asks.
- Whether the dates they expect match the planner's (the last day, not the day after).

**Prompts:**

- "Where would this notice go from here?"
- "Who else would need to know?"

### 24:00 Closing questions (5 minutes)

Say:

> Thank you. A few last questions.

1. "How did that feel to use, overall?"
2. "On a scale of 1 to 5, where 1 is 'I would not feel confident using this' and 5 is 'I would
   feel confident using it every day', how confident would you feel using it day to day?" Then:
   "What makes it that number and not one higher?"
3. "What would stop you using it?"
4. "If you could change one thing first, what would it be?"
5. "Was there anything you expected to find that wasn't there?"
6. "Is there anything you'd like to ask me?"

Answer their questions now, including any you turned back during the tasks.

### 29:00 Thanks and close (1 minute)

Say:

> Thank you, that's given me a lot to work on. I'll close the window now, which clears
> everything you typed.

Close the private window. Note the end time.

## 4. Log template

Copy this for each session and fill it in during the session or straight after.

Rules for the log:

- Write quotes without the participant's name or employer, and without the name of their council
  or team.
- Write systems by type ("case management system"), never by product or supplier.
- Keep the log in a private place, such as a private folder or document, not in the repo. It
  goes in the repo only if the participant has agreed and it holds no names.
- If they typed or said anything from a live case, don't copy it: note only that it happened.

**Session**

| Field | Entry |
|---|---|
| Session id | P1, P2 and so on |
| Date | |
| Participant's role, in general terms | for example "housing officer, temporary accommodation team" |
| In person or remote; device and browser | |
| Notes agreed | yes / no |
| Recording agreed; where kept; delete by | yes / no |
| Build tested | the commit shown at the foot of the page |

**Tasks**

| Task | Completed (yes / with help / no) | Time taken | What they said, in their own words | What went wrong | Severity (blocks / slows / annoys) | Change they asked for |
|---|---|---|---|---|---|---|
| Warm-up | n/a | | | | | |
| 1. Find a household to look at first | | | | | | |
| 2. Why a route out, and its checks | | | | | | |
| 3. A first plan, edited | | | | | | |
| 4. Write down a decision | | | | | | |
| 5. Pass the plan for sign-off | | | | | | |
| 6. Work out a scenario | | | | | | |

Severity:

- **blocks**: they could not finish without help, or they misread something in a way that would
  lead to a wrong action at work, such as taking a suggestion for a decision or a scenario result
  for a saving.
- **slows**: they finished, but with wrong turns, hesitation or a question.
- **annoys**: they finished without trouble but disliked something.

**Closing answers**

| Question | Answer |
|---|---|
| Confidence, 1 to 5, and why | |
| What would stop them using it | |
| One thing to change first | |
| Expected but not there | |
| Their questions | |

**Summary** (straight after the session)

- Top three problems, with task numbers:
  1.
  2.
  3.
- Top three things that worked:
  1.
  2.
  3.
- Quotes worth keeping (no name, employer or council):
- Changes to make:
- What this session says about each research question (1 to 5):
- Screen: lines it let through that state a decision, or stopped wrongly (reworded, nothing from
  a live case):

## 5. After the session

1. Finish the log within the hour, while it is fresh. Allow 10 minutes after each session.
2. Delete any recording by the date you promised.
3. After every three to five sessions, merge the logs into one list of problems. For each, note
   the tasks, the sessions it was seen in and its highest severity.
4. Rank the list by severity first (blocks, then slows, then annoys), then by how many sessions
   it was seen in. A block seen in two or more sessions comes first. A research question that
   came out "no" points to the next ones. Annoyances go on a list for the redesign.
5. Turn each problem into one change with one owner (a role, not a name), a date, and the session
   and task ids it came from. Keep each change small: one problem, one change.
6. A screen finding (a decision it let through, or a line it stopped wrongly) becomes a new case
   in `tamarket/spec/screen_cases.json`, written fresh as a made-up example, never in the
   participant's words if they could point to anyone. Then change `screen_rules.json` until the
   Python reference and the JavaScript port both pass it.
7. Record each change and why in `docs/decision_log.md`, citing session ids only.
8. Re-test: after a change, run the same task, worded the same way, with at least two new
   participants. Close the change when neither hits the problem; if one does, look again.
9. After the redesign, update the owner's crib and run the same six tasks unchanged, so the
   results compare.
