# Monitoring runbook (phase 7)

How a collection session reads Move forward's sources and files what it finds. The session may be
a person, or a Claude session started on a schedule; either way it works only through the steps
below, and an officer decides what each item is worth. Nothing reaches a plan unaccepted.

## 1. What is due

    python scripts/monitor.py due

lists the sources in use (`monitor/sources.json`) whose last item was read longer ago than their
cadence, oldest first. Each entry says what to watch for.

## 2. Read each due source, as a person would

- Read only the source's public pages, at the address in the register or under it. No sign-in,
  no VPN or hidden identity, no paid access, nothing the source's terms (in the register) do not
  allow.
- Look for what changed since the last item from that source: a release or its announcement, a
  chapter's update and change note, a new statutory instrument, a published ombudsman decision on
  temporary accommodation.
- Never collect personal data or anything about a household, and never name a council, a person or
  a firm in what you write. Where an original title names a council (an ombudsman decision, say),
  `title_original` holds only the decision's reference.

## 3. Write a candidate

Add an object to a JSON file in `monitor/inbox/` (gitignored), with:

| Field | What |
|---|---|
| `source` | the register id |
| `url` | the page read, on the source's own site |
| `published` | the date the page gives as published ("Published", first published), YYYY-MM-DD; never an updated date; if the page gives none, do not guess, leave the item out |
| `updated` | only where the page also shows an updated or last updated date ("Updated", "Last updated"): that date. `scripts/monitor.py` checks it (after `published`, not after the read) and keeps it on the item; the card shows both |
| (sections of a manual) | a chapter of the code of guidance is a section of a GOV.UK manual: its "Updated" date is the whole manual's. Check the manual's updates page (`.../updates`) for which sections changed, and file a change to a section from that page, under that page's address. For such an item this row overrides the `published` row: `published` is the date of the entry reported (the page calls those amendments published), and leave `updated` out, as the page's Updated date is the manual's latest entry, which may be another section's |
| (correcting a filed item) | an item's id is a hash of its address, `published` and `title_original`, so a correction to anything else keeps the id. Take the item's line out of `monitor/items.jsonl` and its entry out of `data/ingest_log.jsonl` in the same commit, file it again, and say in the commit and in `docs/decision_log.md` what changed. A decision already recorded on the item stays on its id: say in the decision log that it was taken on the earlier wording |
| `retrieved_at` | when it was read (ISO time) |
| `language` | `en` |
| `title_original`, `excerpt_original` | the title and one short passage quoted exactly (under 300 characters: this project's limit, which its tests enforce; fd-core allows up to 600), naming no council, person or firm |
| `title`, `summary` | in plain English: what changed and which of the planner's checks, routes, clocks or references it touches (600 characters at most). Every figure, date and word such as "provisional" must be on the page at `url` itself, not on a page it links to; anything you infer (what an item bears on, what a change might be) carries [Likely] |
| `translated_by` | `not translated` |
| `tags` | from `monitor/vocab.json` only: `checks`, `pathways`, `references`, `clocks`, `topics` |
| `grade_proposed` | on the six-by-six scale: the source's reliability (A to F, never above its standing grade in the register) and the information's credibility (1 to 6): 2 (probably true) for a single source, 1 only where the summary cites an independent second source that confirms it. The officer sets the grade |

## 4. File

    python scripts/monitor.py ingest

screens each candidate for council names, then runs fd-core's checks (`fdcore.monitor`): a
registered source in use, the address on its site, dates, tags from the vocabulary, the grade on
the scale, and the guardrails screen on the English and on the excerpt. Good items are appended to
`monitor/items.jsonl`, each with an entry in `data/ingest_log.jsonl` (source, address, the
source's terms, the excerpt's SHA-256, and `monitor/items.jsonl` as the repo-relative out_file).
Refused ones go to `monitor/refused.jsonl` (gitignored: it can hold the text that was refused) with
their reasons: fix and file again, or leave them out.

## 5. Publish

    python scripts/build_app.py

publishes the items as `data/monitor.json` (a list) and the register's names, terms and grades as
`spec/monitor_sources.json` (an object with a `sources` list), both in the manifest. A site build
can keep only the items whose source's `terms_note` starts with "Open Government Licence". Items wait
on the Monitor page for an officer to accept (setting the grade) or reject (with a reason). An
accepted item shows on the rail of each household it touches and beside the reference it touches.
Drafting does not read items in this phase.
