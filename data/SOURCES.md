# Data sources

Contains public sector information licensed under the Open Government Licence v3.0.

Compiled 21 October 2026. Links, sizes and dates were read from the GOV.UK pages with a
web fetch tool. This workspace cannot reach gov.uk or open the spreadsheets, so anything
about the inside of a file is marked as checked (from MHCLG's own text) or not checked.
Every file, with its URL, size and dates, is in `config/sources.csv`; the download order
is in `docs/browser_pull.md`; changes to council codes are in `config/code_changes.csv`.

Confidence markers: [Certain] stated by the publisher; [Likely] inferred from strong
evidence; [Guessing] a judgement that needs checking.

## At a glance

| Dataset | What the build uses | Latest available (21 Oct 2026) | Publisher, licence |
|---|---|---|---|
| Statutory homelessness detailed local authority tables (H-CLIC) | Sheet TA1: households in TA at the end of each quarter, by type, by council | January to March 2026 (snapshot 31 March 2026), published 13 August 2026. Next: April to June 2026, announced for 29 October 2026, 9:30am (provisional) | MHCLG, OGL v3.0 |
| Revenue outturn RO4 housing services, data by local authority | TA lines 80 to 86, total expenditure and net current expenditure, by council and year | 2025-26 first release, 17 September 2026 (377 of 413 authorities). 2024-25 third release, 11 June 2026 (410 of 411) | MHCLG, OGL v3.0 |
| Revenue outturn multi-year data set | The same lines for 2017-18 to 2025-26 in one CSV | Updated 17 September 2026 | MHCLG, OGL v3.0 |
| Local Authority District to Region (April 2025) lookup | Region and official name for each council | Updated 11 August 2025 | ONS, OGL v3.0 |

## 1. Households in temporary accommodation (H-CLIC)

Pages:

- Live tables: https://www.gov.uk/government/statistical-data-sets/live-tables-on-homelessness (latest change note 13 August 2026)
- Latest release: https://www.gov.uk/government/statistics/statutory-homelessness-in-england-january-to-march-2026
- Next release: https://www.gov.uk/government/statistics/announcements/statutory-homelessness-in-england-april-to-june-2026
- Technical note: https://www.gov.uk/government/statistics/statutory-homelessness-in-england-october-to-december-2025/statutory-homelessness-in-england-quarterly-technical-note

Latest file: https://assets.publishing.service.gov.uk/media/6a82eeb83bd75b81e2329a7a/Statutory_Homelessness_Detailed_Local_Authority_Data_202603.ods
(ODS, 1.13 MB, 13 August 2026). The release page attaches a file of the same name under
another asset ID (`media/6a82ee2c92ec93e1e0329a7f/`).

### Where the time series lives

- There is no council-level time series file. [Certain: none on the live tables page.] The
  council series is built by stacking one detailed LA file per quarter. The files listed
  here run from April to June 2019, which sits on its release page rather than the live
  tables page; H-CLIC began in April 2018 and the 2018-19 quarters are not listed. Formats
  vary: most are ODS, four are XLSX (April to June 2019, July to September 2019, January
  to March 2024, April to June 2025).
- The England-level series is `Statutory_Homelessness_England_Time_Series_202603.ods`
  (England only; useful for checking national totals).
- Each release revises the previous quarter, so the live tables page holds the latest
  revision of each file. Keep every release that is used and record it in the ingest log.
- Before April 2018 the P1E return used different categories (discontinued tables on the
  live tables page). [Likely not comparable; not used.]

### Checked from MHCLG's text

- TA1 is "households in TA at quarter end, by TA type"; TA2 to TA9 cover household type,
  duty, length of stay, age, ethnicity, children and out-of-area placements. [Certain]
- The sheet is named TA1: the 26 February 2026 change note refers to "sheets TA1 of our
  data files". [Certain]
- TA1 includes households with children in B&B for more than six weeks (including those
  pending appeal); those figures were corrected on 26 February 2026 for April to June 2024
  onwards. [Certain]
- Missing or withheld data are shown as `..` with yellow highlighting. [Certain]
- Council figures are not rounded or imputed; England and regional figures are weighted
  for non-response and rounded to the nearest 10. A sum of councils will not equal the
  published England total. [Certain]
- 294 of 296 housing authorities responded for October to December 2025. [Certain]
- TA counts are a snapshot on the last day of the quarter. [Certain]
- Prototype "accessible" versions exist for July to September 2025 (revised) and
  October to December 2025, added 30 April 2026. [Certain]
- Corrections on 19 June 2026 to household projection values in the 2022-23, April to
  June 2025 and April to June 2021 files. [Certain]

### Not checked (the parser finds these at run time)

- Header row numbers, merged header layout, exact column wording, and the label of the
  code column.
- That codes are ONS codes (E06, E07, E08, E09). [Likely, as in other MHCLG council
  tables; the technical note does not say.]
- Expected TA1 columns [Likely], worded as in the H-CLIC and RO4 categories: total
  households in TA; Bed and breakfast hotels (including shared annexes); Nightly paid,
  privately managed accommodation, self-contained; Hostels (including reception centres,
  emergency units and refuges); Private sector accommodation leased by the authority or by
  a registered provider; Local authority or housing association (LA/HA) stock; Any other
  type of accommodation; "of which" columns for households with children; households
  placed in another district; possibly a rate per 1,000 households.
- How the prototype accessible layout differs from the standard one.

### National figures for checks (31 March 2026, from the release)

135,580 households in TA (up 3.6% on a year earlier); 86,460 with children; 51,390 in
nightly-paid self-contained accommodation (37.9%); 12,220 in B&B (9.0%); 43,180 placed in
another council's area. [Certain, as published; weighted England figures.]

## 2. TA spend: revenue outturn RO4 (housing services)

One "data by LA" ODS per financial year. Pages follow the pattern
`https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-YYYY-to-YYYY-individual-local-authority-data-outturn`.

| Year | File | Size | Published | Last updated |
|---|---|---|---|---|
| 2025-26 | https://assets.publishing.service.gov.uk/media/6ab26f188cb3c0580e500fa7/RO4_LA_Data_2025-26_data_by_LA.ods | 367 KB | 17 Sep 2026 | 17 Sep 2026 (first release) |
| 2024-25 | https://assets.publishing.service.gov.uk/media/6a291b65e371d9d2c0052b83/RO4_LA_Data_2024-25_data_by_LA.ods | 347 KB | 18 Sep 2025 | 11 Jun 2026 (410 of 411 authorities) |
| 2023-24 | https://assets.publishing.service.gov.uk/media/6a29120f3b15d05a7ce31ff7/RO4_2023-24_data_by_LA.ods | 354 KB | 29 Aug 2024 | 11 Jun 2026 (all authorities) |
| 2022-23 | https://assets.publishing.service.gov.uk/media/6a7adb8a7349adb729babee5/RO4_2022-23_data_by_LA.ods | 353 KB | 12 Oct 2023 | 13 Aug 2026 (RO4 formula errors corrected) |
| 2021-22 | https://assets.publishing.service.gov.uk/media/6825a5e47293a87b6c75ec90/RO4_2021-22_data_by_LA_Live.ods | 347 KB | 20 Oct 2022 | 15 May 2025 |
| 2020-21 | https://assets.publishing.service.gov.uk/media/67dc26a2cb8c6838d74b4fd5/RO4_2020-21_data_by_LA_March_2025.ods | 401 KB | 21 Oct 2021 | 20 Mar 2025 |
| 2019-20 | https://assets.publishing.service.gov.uk/media/6656f573dc15efdddf1a84bd/RO4_2019-20_data_by_LA.ods | 444 KB | 22 Oct 2020 | 30 May 2024 |

### TA lines (from MHCLG's 2021-22 final outturn technical notes)

New homelessness sub-categories started in 2020-21, aligned with H-CLIC. [Certain]

| Line (2020-21 on) | Name | Key in `ta_spend` | Line up to 2019-20 |
|---|---|---|---|
| 80 | Nightly paid, privately managed accommodation, self-contained | nightly_paid_self_contained | 39 "Other nightly paid, privately managed accommodation" (also held annexes with shared facilities) |
| 81 | Private sector accommodation leased by authority or by a registered provider | private_sector_leased | 40 and 43 (leased by the authority; leased by RSLs) |
| 82 | Hostels (including reception centres, emergency units and refuges) | hostels | 41 |
| 83 | Bed and breakfast hotels (including shared annexes) | bed_and_breakfast | 42, plus all annexes with shared facilities |
| 84 | Local authority or housing association (LA/HA) stock | la_ha_stock | 45 or 48 |
| 85 | Any other type of temporary accommodation (including private landlord and not known) | other | 44 or 46 |
| 86 | Temporary accommodation administration | ta_admin | none (old 47 was all homelessness administration) |

Lines 87 and 88 are homelessness services, not TA. The 2025-26 guidance names them
"Homelessness Services: Administration, Prevention, Relief & Main Duty" and "Homelessness
Services: Specialist Services and Support"; earlier releases called them "Homeless
Reduction Act: Administration, Prevention, Relief & Support" and "Non Homelessness
Reduction Act: Administration and Support". [Certain] Old lines 47, 49 and 50
(homelessness administration, prevention, support) have no TA equivalent. [Certain]

### Not checked inside the files

- Sheet names and header rows. Shelter's notes describe an "LA drop-down", so each file
  probably has a one-council drop-down sheet and an all-council data sheet. [Likely]
- Columns per line: employees, running expenses, total expenditure, sales fees and
  charges, other income, total income, net current expenditure. [Likely: the RO form
  layout; not confirmed in these files.]
- Values in GBP thousand. [Likely: the multi-year guidance says GBP thousands.]
- Codes: both an ONS code and an MHCLG finance code (E0701 style). [Likely: the
  multi-year CSV carries `ONS_code` and `LA_LGF_code`.] The parser falls back to finance
  codes with a warning.
- Whether England and class total rows are in the file. [Likely, see below.]

### How Shelter's figures map to the lines

Shelter's press release (18 September 2025) uses RO4 2024-25 "total expenditure".

- GBP 2.842091bn: total expenditure on lines 80 to 86 for England, including GBP 173.682m
  of TA administration (line 86); GBP 2.668409bn without it (lines 80 to 85). [Likely:
  Shelter names the measure and the administration element but not line numbers; lines
  80 to 86 are the only TA lines.]
- GBP 1.078283bn (up 79% in a year, "the biggest increase in spending in one year"):
  line 80, nightly paid self-contained, total expenditure. [Likely] Shelter does not give
  the 2023-24 figure; 79% growth implies about GBP 0.60bn. [Likely, derived]
- GBP 844.236m for "B&Bs and hostels" (32% of the total excluding administration): lines
  82 and 83. [Likely]
- Net current expenditure GBP 1.437397bn on lines 80 to 86. This equals MHCLG's first
  release England figure for "Homelessness: Temporary accommodation including
  administration" (GBP 1,437m, Table 2a), which the second release revised to GBP 1,411m.
  [Certain for MHCLG's figures; Likely that Shelter read the England total row.]
- Shelter used the first release: returns from 388 of 410 authorities, England totals
  grossed up for the rest. [Certain] The current file (410 of 411) will not reproduce
  GBP 2.842bn exactly, and a sum of council rows differs from a grossed England total.
  [Likely] Expect a figure near GBP 2.8bn, not equal to it.
- Shelter's 2019-20 comparator (GBP 1.224531bn without administration) uses the old
  lines. [Likely: old lines 39 to 46 and 48.]

### Caveats for analysis

- Gross and net: MHCLG describes gross expenditure as "before income such as housing
  benefit and other contributions are accounted for" (2025-26 first release, section 3.4).
  Net current expenditure is total expenditure less income (C7 = C3 - C6 in the column
  headers). [Certain] Gross per household is the cost of provision; net per household is
  the part the council funds itself. [Likely]
- Comparability: the 2020-21 restructure moved shared-facility annexes from nightly paid
  to B&B. [Certain] The 2025-26 first release reports "large changes within the
  sub-categories of temporary accommodation expenditure" and says Lambeth, Newham and
  Westminster changed their reporting across these sub-categories. [Certain] Compare
  totals rather than sub-lines for those councils.
- A sub-line's year-on-year change may partly reflect reclassification between lines by
  some councils. [Guessing] Check large moves against the total.
- TA costs a council books in its Housing Revenue Account rather than on lines 80 to 86
  would not appear in this picture. [Likely; MHCLG's technical notes do not say how much,
  and RO4 does carry some lines for charges to the Housing Revenue Account]
- The Centre for Homelessness Impact (29 October 2024) judges TA spend likely to be
  under-reported and recommends matching H-CLIC TA types to RO4 lines. [Certain that the
  report says so.] Per-type unit costs will be noisier than totals.

### Multi-year data set

Page: https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-revenue-outturn-multi-year-data-set

- CSV: https://assets.publishing.service.gov.uk/media/6ab26ffffe72ed1e2b02ee74/Revenue_Outturn_time_series_data_v4.csv (23.2 MB)
- Metadata: https://assets.publishing.service.gov.uk/media/6aaa93a044ec1aa417346b5b/Revenue_Outturn_metadata.ods (109 KB)
- Covers 2017-18 to 2025-26 (change note 17 September 2026; the guidance page still says
  to 2024-25). Wide format, one row per authority per year. First columns `year_ending`
  (YYYYMM, 201803 for 2017-18), `ONS_code`, `LA_LGF_code`, `LA_name`, `status`,
  `LA_class`, `LA_subclass`, then about 2,000 coded items (for example `RS_hous_net_exp`).
  GBP thousand, cash terms. Blanks are the text `Not set`. Class total rows carry codes
  such as `E06` with `UA`. England and class totals are grossed up for missing returns;
  MHCLG advises using those rows rather than summing councils. [Certain, from the guidance
  and the CSV preview]
- The data dictionary (in the metadata file) maps each item to its form, row (line) and
  column. The RO4 item names were not checked; the parser picks them by description.

## 3. Council codes and names

- ONS Local Authority District to Region (April 2025) Lookup in EN (V2):
  CSV https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/1c17a07ff8fc44218883049f0afa3de1/csv?layers=0,
  page https://open-geography-portalx-ons.hub.arcgis.com/datasets/ons::local-authority-district-to-region-april-2025-lookup-in-en-v2.
  Columns `LAD25CD`, `LAD25NM`, `RGN25CD`, `RGN25NM`, `ObjectId`. [Certain, from the
  data.gov.uk preview] Licence: ONS products are under OGL v3.0; the data.gov.uk record's
  licence field reads "Not set". An April 2026 edition was not found.
- The RO metadata file also holds a council catalogue (ONS code, finance code, name,
  class, subclass, region, start and end dates, notes on mergers). [Certain, from the
  guidance]
- `config/code_changes.csv`: 42 predecessor codes for the 2019, 2020, 2021 and 2023
  mergers, and the April 2025 recoding of Barnsley (E08000016 to E08000038) and Sheffield
  (E08000019 to E08000039) after a boundary change. Source: HM Land Registry UK House
  Price Index change history, https://landregistry.data.gov.uk/app/ukhpi/changelog, read
  21 October 2026, under the Open Government Licence v3.0 (data.gov.uk's UK House Price Index
  page, read 24 October 2026): "Contains HM Land Registry data © Crown copyright and database
  right 2026. This data is licensed under the Open Government Licence v3.0." [Certain] The four Somerset district codes are not in that log and are marked
  Likely. Which code each MHCLG file uses for Barnsley and Sheffield in 2024-25 and
  2025-26 is not checked: check before joining spend to counts across that change.
  `tamarket.mhclg.harmonise_codes` moves predecessor rows onto successor codes and adds
  them up, keeping gaps as gaps.

## 4. Context, not ingested

- Shelter press release, 18 September 2025:
  https://england.shelter.org.uk/media/press_release/bill_for_homeless_accommodation_soars_by_25_hitting_28_bn_
  (figures above; data source named as MHCLG revenue outturn RO4, using the local
  authority drop-down, for 2024-25, 2023-24 and 2019-20).
- Centre for Homelessness Impact, "Spending on temporary accommodation: value for money",
  29 October 2024: https://homelessnessimpact.org/publication/spending-on-temporary-accommodation-value-for-money

## 4a. Monitoring sources (phase 7, terms read 22 October 2026)

Read through their public pages only, for the monitoring layer (`monitor/sources.json`,
`monitor/RUNBOOK.md`). Items quote at most a short passage, credit the source and keep the
original beside the summary. The build publishes the items as `data/monitor.json` and each source's
terms as `spec/monitor_sources.json`, so a site that shows only Open Government Licence material can
keep only the items whose source's `terms_note` starts with "Open Government Licence".

| Source | Address | Terms |
|---|---|---|
| MHCLG homelessness statistics | https://www.gov.uk/government/collections/homelessness-statistics | Open Government Licence v3.0 except where otherwise stated (https://www.gov.uk/help/terms-conditions) |
| Homelessness code of guidance | https://www.gov.uk/guidance/homelessness-code-of-guidance-for-local-authorities | as above |
| MHCLG news and guidance | https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government | as above |
| legislation.gov.uk | https://www.legislation.gov.uk/ | Open Government Licence v3.0 except where otherwise stated; Crown and database right (https://www.legislation.gov.uk/help) |
| Local Government and Social Care Ombudsman decisions | https://www.lgo.org.uk/decisions/housing/homelessness | Not the Open Government Licence. Its copyright page (https://www.lgo.org.uk/copyright): "You may re-use the information on this website free of charge in any format"; "you must acknowledge the source and our copyright in cases where you supply the information to others"; "you must reproduce the information accurately, without amendment"; "you must not use the information in a misleading way"; "you must not use the information for the principal purpose of advertising or promoting a particular product or service". Summaries are the planner's own words; the passage quoted is unchanged; the items stay off anything used to promote a service |

## 4b. Guidance behind the statutory clocks (read 22 October 2026)

The clocks (`tamarket/spec/clocks.json`) quote legislation.gov.uk and cite these GOV.UK pages
(Open Government Licence v3.0) for what the law leaves to guidance:

- Temporary accommodation notification duty: Department of Health and Social Care guidance to GP
  practices and health visiting services (published 1 September 2026):
  https://www.gov.uk/government/publications/temporary-accommodation-notification-duty/temporary-accommodation-notification-duty-department-of-health-and-social-care-guidance-to-gp-practices-and-health-visiting-services
  (what a GP practice's and a health visiting service's notice contain; one notification for each child).
- Temporary accommodation notification duty: information to accompany the homelessness code of
  guidance: https://www.gov.uk/government/publications/temporary-accommodation-notification-duty/temporary-accommodation-notification-duty-information-to-accompany-the-homelessness-code-of-guidance
  (the duty arises once for each application, at the initial placement).
- Homelessness code of guidance, chapter 17, paragraphs 17.35, 17.40, 17.41 and 17.67:
  https://www.gov.uk/guidance/homelessness-code-of-guidance-for-local-authorities/chapter-17-suitability-of-accommodation
  (B&B as a last resort; the 6 weeks after a change of circumstances; periods disregarded; no
  review of interim accommodation's suitability).

- Keeping children safe in education 2026, Part one (statutory guidance for schools), section on
  homelessness, read 22 October 2026:
  https://assets.publishing.service.gov.uk/media/6a9088e19a177a1decf97b01/Keeping_children_safe_in_education_2026_Part_one.pdf
  It describes the duty to notify educational institutions, says the notification "should be made
  when consent has been given from the parent", and that it does not replace safeguarding and
  welfare duties. It does not say what a notification contains, so the school's draft gives only
  what s.213AA(2)(a) requires [Likely].
- The code of guidance's updates page:
  https://www.gov.uk/guidance/homelessness-code-of-guidance-for-local-authorities/updates
  (which chapters each update changed: a chapter's own page shows the whole code's date).

## 5. Checked inside the files (21 October 2026)

Twelve files were opened in a browser and read; the extracts and their checks are in
`data/raw/browser/` (`MANIFEST.csv` gives each source file's size, SHA-256 and
Last-Modified header). What the files contain: [Certain for these twelve files]

- **TA1, 2024-25 layout** (31 Mar 2024 to 30 Sep 2025 files, ODS and XLSX): 35 columns.
  Code in column 0, name in 1, total households in TA in 4, households in the area
  (thousands) in 5, with children in 7, children in 8, the six types in 10, 16, 19, 22,
  25, 28, placed in another district in 31, duty owed with no accommodation secured in 33.
  Missing councils show `..` in every cell; the placed-in-another-district column uses `-`
  for suppressed cells in some files.
- **TA1, 2025-26 layout** (31 Dec 2025 and 31 Mar 2026 files): 25 columns. Code 0, name 1,
  total 2, area households 3, with children 5, children 6, the six types in 7, 12, 14, 16,
  18, 20, placed in another district 22, no accommodation secured 23. Missing councils
  show `[x]`; suppressed cells `[c]`.
- Every TA1 file has 307 coded rows: England, the nine regions with London repeated, and
  296 councils. In every council row with all values present, the six types add up to the
  total exactly.
- Councils without data in some quarters include several large London boroughs; in the
  2024-25 files three boroughs have no count in any of the five quarter ends. See the
  coverage section of `reports/phase0_picture.md`.
- Barnsley and Sheffield appear under their old codes, labelled "(up to 202503)" in the
  31 March 2025 file, and under new codes (E08000038, E08000039) from 30 June 2025.
- **RO4**: sheet `RO4_LA_Data_2023-24` (header row 12, item codes in row 8 such as
  `C3R80`), `RO4_LA_Data_202425` and `RO4_LA_Data_202526` (header row 7). Values in GBP
  thousand. Lines 80 to 86 total expenditure (C3) and net current expenditure (C7) sit
  in columns 37/41, 44/48, 51/55, 58/62, 65/69, 72/76, 79/83 in 2023-24 and 2024-25, and
  41/46, 49/54, 57/62, 65/70, 73/78, 81/86, 89/94 in 2025-26, which adds a "management and
  support services" column per line. Total homelessness is columns 100/104 (2023-24,
  2024-25) and 113/118 (2025-26).
- RO4 rows cover every authority type (police, fire, county councils and others); 296 are
  housing authorities (classes SD, UA, MD, LB). Two county councils report small amounts on
  TA lines. The Greater London Authority appears twice (the second copy in a hidden row).
- MHCLG's England row equals the sum of authorities for most lines in 2024-25 and exceeds
  it by a little where one authority's return is missing; in 2025-26 (first release, 25
  housing authorities missing) it exceeds the sum of returns by £42.9m on lines 80 to 86.
  [Certain] MHCLG's technical notes say the first release covers 377 of 413 authorities and
  that England totals include estimates for missing returns, from grant allocations where
  known and otherwise from 2024-25 proportions; a second release follows in December.
  [Certain: https://www.gov.uk/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-first-release/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-technical-notes]
- Some councils report nothing on lines 80 to 86 while housing many households in TA. [Certain]

## 6. Not verified

- Header rows and column wording of the files not yet opened (older quarters and years).
  `scripts/build_tidy.py` prints and saves the layout and column mapping it used for each
  file; check `data/processed/parse_report.json` after a pull.
- Which RO4 lines Shelter summed (inferred from its notes; see above).
- Original release dates for some older quarterly files (marked in `config/sources.csv`).
- Whether the four Somerset district codes in `config/code_changes.csv` are right.
- Whether an April 2026 ONS lookup has been published.

## Attribution

- MHCLG data: "Contains public sector information licensed under the Open Government
  Licence v3.0."
- ONS lookup: "Source: Office for National Statistics licensed under the Open Government
  Licence v3.0."
