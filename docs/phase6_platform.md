# Phase 6: how Move forward fits the work, and where it goes next

Written 22 October 2026 for the owner. The sources are listed at the end. Each claim carries [Certain], [Likely] or [Guessing]; anything not from a source is marked as judgement. Suppliers are described by type, never named.

## 1. The work it supports, and the pressure on it now

- **Households in temporary accommodation.** 135,580 on 31 March 2026, up 1.1% on the previous quarter, with 177,530 children (MHCLG, January to March 2026, published 13 August 2026) [Certain].
- **Bed and breakfast.** 1,900 households with children were in B&B on 31 March 2026, and 1,000 of them (52.6%) had been there beyond the six-week limit (the Homelessness (Suitability of Accommodation) (England) Order 2003) [Certain].
- **Out of area.** 43,180 households owed a temporary accommodation duty were placed in another council's area [Certain].
- **Spend.** The National Plan to End Homelessness (December 2025) gives £2.8 billion spent on temporary accommodation in 2024-25, almost five times the 2010-11 level; the plan notes that comparisons across years are imperfect [Certain].
- **Targets.** The plan sets a target to end the use of B&B for families, other than very short emergency use, by the end of this parliament. Each council must publish an action plan alongside its homelessness strategy, with local targets aligned to a new outcomes framework; the government will publish national progress reports at least every two years [Certain].
- **Private renting.** Section 21 "no fault" evictions ended on 1 May 2026, with court claims on earlier notices to be brought by 31 July 2026. A private rented sector database is due from late 2026 [Certain].

**What this means for the planner [Likely].** The pressure is on moving households out, not only on placing them: every week a family spends in B&B past six weeks is a breach of the order, and councils will now be measured against local targets. A tool that keeps each household's route out, its checks and its next step in one place, and counts the overdue ones, is aimed at that.

## 2. How casework systems in this space are built

What councils use, by type (from the statistics' own collection and public guidance; judgement where marked):

| Layer | What it does | In practice | Sources |
|---|---|---|---|
| Case management | Records each application, the duties owed, decisions and reviews | Housing or homelessness case management systems, often part of a wider housing management suite [Likely] | H-CLIC specification |
| Statutory return | Case-level data sent to MHCLG each quarter | H-CLIC: XML against a published schema, sent through DELTA; councils without a compatible IT system and with a low caseload key cases into an online form, and an API route exists. Sections cover the applicant, household members, support needs, prevention, relief, decisions, final duties, assistance, temporary accommodation and reviews [Certain] | H-CLIC v1.5.5 (April 2023) |
| Placements | Booking and paying for nightly-paid, leased and council-owned homes | Procurement and booking tools; regional agreements on rates and out-of-area placements [Likely] | Judgement |
| Allocation | The housing register and offers of social housing | Choice-based lettings or direct offers under the allocation scheme [Likely] | Allocation guidance |
| Reporting | Spend, length of stay, B&B over six weeks, out of area | Statutory tables (TA1 and the detailed local authority data) and the RO4 revenue outturn [Certain] | Tables on homelessness; RO4 |

H-CLIC's temporary accommodation section records the date a household entered temporary accommodation, each placement's entry and exit dates, its type, its number of bedrooms, the duty it was given under, and whether it is in another council's district [Certain]. The planner's synthetic records carry three of them: the type, the out-of-district flag, and the time in temporary accommodation as a count of weeks rather than dates [Certain].

### Where Move forward stands against that

| Layer | Move forward after phase 6 | Gap |
|---|---|---|
| Case management | A file per household with its plan, checks, progress, follow-ups and audit trail | Not a system of record: it reads a caseload and writes plans; the case stays in the council's own system [Certain] |
| Statutory return | None | It could check a plan against the H-CLIC fields it touches, without sending anything [Likely] |
| Placements | Type, band, weeks in TA and out-of-district flag per household | No booking or rates; the scenario takes the price gap as an input, never as a fact [Certain] |
| Allocation | Routes out (social housing, a private rented offer, supported housing) with their checks | No register data; offers are recorded as progress, decided outside the planner [Certain] |
| Reporting | The market picture from MHCLG's published tables; the planner's overview counts plans and stages | No council-level target tracking yet [Certain] |

## 3. What phase 6 added

All built in this repository, with browser tests for the flows named in `tests/browser/` [Certain].

- **Name.** Move-on is now Move forward, and the plans are move-forward plans. Pathway ids, module names (`tamarket/moveon.py`) and the agents' names are unchanged.
- **Sign-in screen.** Synthetic people at each role (officer, reviewing officer, team leader, finance officer, service manager). The hosted version keeps sign-in by emailed code, for invited people only.
- **Record layout.** A household's file now reads as one record:
  - a header with the next step for the person looking at it ("Start the plan", "Review and decide", "Record progress", which opens the progress form);
  - sections that fold and stay folded (household, plan, progress, checks, routes out);
  - a rail with properties, follow-ups, official references and add-ons.
- **Drill-through.** The breadcrumb runs from the caseload to the household's type of accommodation. Each type and each route out has its own page listing every household in it, with counts.
- **Follow-ups.** Steps with an owner and a due date, with templates ("Chase the landlord or agent for an answer on the offer", "Review the placement's suitability checks again"). Text is screened for names, addresses and phone numbers before it is saved.
- **References.** Seven official pages (the code of guidance overview and chapters 15 and 17, sections 193 and 208 of the Housing Act 1996, the allocation guidance and the live tables), each with the date it was read.
- **Team and access.** Who holds which role and what each role can do.
- **Brand.** Poppins Bold Italic for the wordmark and titles (self-hosted, under the SIL Open Font Licence), one light palette in every theme, on a white page.

## 3a. What phase 6.5 added

Built and tested in this repository, on synthetic records [Certain]:

- **Statutory clocks** from rules that quote the law (`tamarket/spec/clocks.json`), with Python as the reference and a JavaScript port checked against the same cases:
  - the s.208 notice to the council where a household is placed, due before the end of 14 days beginning with the day the accommodation was made available (s.208(4));
  - the s.213AA notices to a child's GP practice, health visiting service and school, once the parent agrees, due within 14 days beginning with the latest of the agreement, the information about the bodies and the placement (in force 1 September 2026);
  - 6 weeks for a family in B&B (SI 2003/3326, art. 4(1));
  - eight weeks beginning with a review request for the decision, or a longer period agreed in writing (SI 2018/223, reg. 9).
- **Notices.** A draft for each, with placeholders where personal details go; the officer records when and how it was sent. The planner sends nothing. A child's notices cannot be recorded as sent without the parent's agreement on record (in the hosted database too).
- **Compliance at risk**: one page of what is overdue, due within 14 days, or to start.
- **Handover summary** on each household, with the changes since a chosen date.
- **Pilot timings**: three tasks timed in the browser, with no household, person or free text kept, for a pilot to set against the same tasks done without the planner.
- **Synthetic dates.** Each record has a placement date counted back from the caseload's date, and a made-up history of s.208 notices before the planner (the share missed is a guess, not a published figure) [Guessing].

## 4. Extensions, ordered by fit

Judgement, [Likely]:

| Extension | Fit | What it needs | Main risk |
|---|---|---|---|
| B&B six-week watch: families in B&B, the day each reaches six weeks, and the plan for each | Built in phase 6.5 on synthetic dates | Real placement dates, and earlier B&B stays (the Order counts a total of periods) | A countdown must not stand in for the officer's suitability decision |
| Local targets: the council's action plan targets against the caseload | Close | The outcomes framework's measures once published | The framework's measures are not yet set [Likely] |
| H-CLIC check: a plan's fields set against the return's TA and duty fields | Medium | The XSD; a mapping table | Must never send to DELTA itself; the system of record does that |
| Private rented offers under the new tenancy rules | Close (the checks already follow the Act as commenced) | Landlord registration once the database opens | The database's start date may move |
| Out-of-area placements: notice to the receiving council and the duty to consider location | The notice built in phase 6.5; the location duty not | The council's own sending route | Personal data leaves the planner only through the council's own route |
| Case management connector: read a caseload from, and write a plan back to, the council's system | Further | An interface per supplier type; a data processing agreement | Real personal data, so a deployment needs a lawful basis and a DPIA first |

## 5. Phase 7: the monitoring layer, as built

Built on 22 October 2026 at the owner's go ("run with phase 6.5 and subsequently then with 7") [Certain]:

- **Sources** (`monitor/sources.json`, terms read 22 October 2026): MHCLG's homelessness statistics, the code of guidance, legislation.gov.uk, the Local Government and Social Care Ombudsman's published homelessness decisions, and MHCLG news and guidance. English only; each read through its public pages, with no sign-in, VPN or hidden identity. Councils' own committee papers are left out for now: they name the council.
- **Items**: the original title and a short passage quoted exactly, an English summary that says what changed (every figure on the page cited; an inference tagged [Likely]) and which checks, routes, clocks or references it touches, and a proposed grade. Filed by `scripts/monitor.py` after a council-name screen and fd-core's checks (`fdcore.monitor`), each with an ingest-log entry.
- **Eight seed items** read on 22 October 2026 and read again at 16:45 that day (the announcement and the third ombudsman decision again at 17:30, chapter 17 and the code's updates page at 18:15): the January to March 2026 statutory homelessness release and the announcement of the next one (published 26 February 2026, updated 4 March 2026; release 29 October 2026, shown as provisional on the page); the temporary accommodation notification duty's guidance (1 September 2026); chapter 17 of the code, whose page shows the whole code's update of 15 October 2026 [Likely], and, from the code's updates page, chapter 17's own last amendment, of 1 May 2026, to paragraphs 17.15 b and 17.66; and three ombudsman decisions of April and May 2026 on a suitability review delayed, a family 28 weeks past the six-week limit, and a placement unsuitable for medical needs, none naming the council. Each single-source item proposes credibility 2 (probably true). The ombudsman's items are not under the Open Government Licence: its terms allow re-use with acknowledgement, accurately, not misleadingly and not mainly to advertise or promote a product or service, and a site that shows only OGL material leaves them out. Where a page shows a published and an updated date, an item keeps both (`published`, `updated`).
- **Output**: the Monitor page, where an officer accepts an item with a grade or rejects it with a reason; accepted items show on the households and references they touch.
- **Not yet**: drafting does not read accepted items (a deferred decision); collection runs by hand or by a scheduled session, which the owner has not switched on; no household data leaves the planner, and nothing is searched about a household.

## Sources

- [Statutory homelessness in England: January to March 2026](https://www.gov.uk/government/statistics/statutory-homelessness-in-england-january-to-march-2026/statutory-homelessness-in-england-january-to-march-2026)
- [A National Plan to End Homelessness (CP 1452, December 2025)](https://assets.publishing.service.gov.uk/media/693a6e3f5cc812f50aa41fb2/A_National_Plan_to_End_Homelessness.pdf)
- [Historic protections for renters in action across England (MHCLG, 30 April 2026)](https://www.gov.uk/government/news/historic-protections-for-renters-in-action-across-england)
- [Implementing the Renters' Rights Act 2025: roadmap](https://www.gov.uk/government/publications/renters-rights-act-2025-implementation-roadmap/implementing-the-renters-rights-act-2025-our-roadmap-for-reforming-the-private-rented-sector)
- [H-CLIC data specification v1.5.5 (UK Data Service copy)](https://doc.ukdataservice.ac.uk/doc/8997/mrdoc/pdf/8997_h-clic_data_specification_v1_5_5.pdf)
- [Homelessness code of guidance, chapter 17: suitability of accommodation](https://www.gov.uk/guidance/homelessness-code-of-guidance-for-local-authorities/chapter-17-suitability-of-accommodation)
- [Tables on homelessness](https://www.gov.uk/government/statistical-data-sets/live-tables-on-homelessness)
- [Local authority revenue expenditure and financing, 2024 to 2025, individual local authority data (RO4)](https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2024-to-2025-individual-local-authority-data-outturn)
