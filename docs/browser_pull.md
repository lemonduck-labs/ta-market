# Browser pull list

This workspace cannot reach gov.uk, so the files below are downloaded in a browser and
copied into `data/raw/`. The list is generated from `config/sources.csv` (same order,
same URLs); `data/SOURCES.md` explains each dataset. Links were read from the GOV.UK
pages on 21 October 2026.

## How to pull

1. Download each URL and save it in `data/raw/` under the exact file name shown (the
   last part of the URL). Do not rename files: the parsers read the quarter or year from
   the name. If the browser adds ` (1)` or similar, remove it. The ONS lookup downloads
   under a different name; save it as `LAD25_RGN25_EN_LU.csv`.
2. Do not open and save the files in a spreadsheet program first. That changes the bytes
   and can change cell values.
3. For every file, add a line to `data/pull_manifest.csv` (outside `data/raw`):
   `file_name,bytes,sha256,downloaded_at`. `bytes` is the exact size in bytes; `sha256`
   comes from `shasum -a 256 FILE` (macOS, Linux) or `certutil -hashfile FILE SHA256`
   (Windows); `downloaded_at` is an ISO time such as `2026-10-21T14:05:00+01:00`. The
   build refuses a file whose bytes or hash do not match its line. If a hash cannot be
   taken, give the bytes alone; the ingest log then records the check as bytes only.
4. Run `python scripts/build_tidy.py` (add `--engine calamine` after
   `pip install python-calamine` for a much faster read; odfpy can take tens of seconds
   per file). It writes `data/processed/ta_households.csv`, `data/processed/ta_spend.csv`,
   `data/processed/parse_report.json` and one ingest log entry per file in
   `data/ingest_log.jsonl`. Check the column mapping in the report before using the
   numbers.

Duplicates to avoid: the January to March 2026 file is attached twice on GOV.UK (live
tables page and release page) under the same name; pull the live tables copy listed here.

## Priority 1: minimum for a first market picture (6 files, about 6.7 MB)

2024-25 spend (the year behind Shelter's GBP 2.842bn) joined to the four 2024-25 quarter-end counts, which gives cost per household as spend divided by the average of the four snapshots, plus the latest snapshot (31 March 2026) for the current mix of B&B and nightly-paid accommodation.

1. 2024-25: `RO4_LA_Data_2024-25_data_by_LA.ods` (ODS, 347 KB)  
   https://assets.publishing.service.gov.uk/media/6a291b65e371d9d2c0052b83/RO4_LA_Data_2024-25_data_by_LA.ods
2. January to March 2025 (snapshot 31 Mar 2025): `Statutory_Homelessness_Detailed_Local_Authority_Data_202503_revised.ods` (ODS, 1.65 MB)  
   https://assets.publishing.service.gov.uk/media/699d95ae07d7bff3604d6c0c/Statutory_Homelessness_Detailed_Local_Authority_Data_202503_revised.ods
3. October to December 2024 (snapshot 31 Dec 2024): `Statutory_Homelessness_Detailed_Local_Authority_Data_202412_revised.ods` (ODS, 1.2 MB)  
   https://assets.publishing.service.gov.uk/media/699d956edb2401de164d6c1c/Statutory_Homelessness_Detailed_Local_Authority_Data_202412_revised.ods
4. July to September 2024 (snapshot 30 Sep 2024): `Statutory_Homelessness_Detailed_Local_Authority_Data_202409_revised.ods` (ODS, 1.19 MB)  
   https://assets.publishing.service.gov.uk/media/699d953607d7bff3604d6c0a/Statutory_Homelessness_Detailed_Local_Authority_Data_202409_revised.ods
5. April to June 2024 (snapshot 30 Jun 2024): `Statutory_Homelessness_Detailed_Local_Authority_Data_202406_revised.ods` (ODS, 1.19 MB)  
   https://assets.publishing.service.gov.uk/media/699d950a532c9ad91ebbcbd2/Statutory_Homelessness_Detailed_Local_Authority_Data_202406_revised.ods
6. January to March 2026 (snapshot 31 Mar 2026), latest: `Statutory_Homelessness_Detailed_Local_Authority_Data_202603.ods` (ODS, 1.13 MB)  
   https://assets.publishing.service.gov.uk/media/6a82eeb83bd75b81e2329a7a/Statutory_Homelessness_Detailed_Local_Authority_Data_202603.ods

## Priority 2: the latest spend year and the year before (9 files, about 11.8 MB)

2025-26 spend (first release, 91% of authorities) with three of its quarters (the fourth, January to March 2026, is in priority 1), and 2023-24 spend with its four quarters, for change over the year.

1. 2025-26: `RO4_LA_Data_2025-26_data_by_LA.ods` (ODS, 367 KB)  
   https://assets.publishing.service.gov.uk/media/6ab26f188cb3c0580e500fa7/RO4_LA_Data_2025-26_data_by_LA.ods
2. October to December 2025 (snapshot 31 Dec 2025): `Statutory_Homelessness_Detailed_Local_Authority_Data_202512_revised.ods` (ODS, 1.12 MB)  
   https://assets.publishing.service.gov.uk/media/6a8302c63be22055c1aaa3c2/Statutory_Homelessness_Detailed_Local_Authority_Data_202512_revised.ods
3. July to September 2025 (snapshot 30 Sep 2025): `Statutory_Homelessness_Detailed_Local_Authority_Data_202509_revised.ods` (ODS, 1.7 MB)  
   https://assets.publishing.service.gov.uk/media/69f089bd606c20d4121634b7/Statutory_Homelessness_Detailed_Local_Authority_Data_202509_revised.ods
4. April to June 2025 (snapshot 30 Jun 2025): `Detailed_LA_202506_revised_corrected.xlsx` (XLSX, 2.44 MB)  
   https://assets.publishing.service.gov.uk/media/6a2c1fe0e50716856ed4b008/Detailed_LA_202506_revised_corrected.xlsx
5. 2023-24: `RO4_2023-24_data_by_LA.ods` (ODS, 354 KB)  
   https://assets.publishing.service.gov.uk/media/6a29120f3b15d05a7ce31ff7/RO4_2023-24_data_by_LA.ods
6. January to March 2024 (snapshot 31 Mar 2024): `Detailed_LA_202403.xlsx` (XLSX, 2.21 MB)  
   https://assets.publishing.service.gov.uk/media/6747279da72d7eb7f348c04c/Detailed_LA_202403.xlsx
7. October to December 2023 (snapshot 31 Dec 2023): `Detailed_LA_202312_Revised_No_Dropdowns.ods` (ODS, 1.14 MB)  
   https://assets.publishing.service.gov.uk/media/66b331c5a3c2a28abb50ddfd/Detailed_LA_202312_Revised_No_Dropdowns.ods
8. July to September 2023 (snapshot 30 Sep 2023): `Detailed_LA_202309_revised.ods` (ODS, 1.23 MB)  
   https://assets.publishing.service.gov.uk/media/662f6dd89e82181baa98a8f5/Detailed_LA_202309_revised.ods
9. April to June 2023 (snapshot 30 Jun 2023): `Detailed_LA_202306_revised.ods` (ODS, 1.24 MB)  
   https://assets.publishing.service.gov.uk/media/65df3f24cf7eb16adff57f55/Detailed_LA_202306_revised.ods

## Priority 3: trend back to 2019-20 (22 files, about 44 MB)

The multi-year CSV and its metadata cover every year of spend from 2017-18 in one file; the separate RO4 files for 2019-20 to 2022-23 are a cross-check. The quarterly files give the counts for the same years.

1. 2017-18 to 2025-26: `Revenue_Outturn_time_series_data_v4.csv` (CSV, 23.2 MB)  
   https://assets.publishing.service.gov.uk/media/6ab26ffffe72ed1e2b02ee74/Revenue_Outturn_time_series_data_v4.csv
2. 2017-18 to 2025-26: `Revenue_Outturn_metadata.ods` (ODS, 109 KB)  
   https://assets.publishing.service.gov.uk/media/6aaa93a044ec1aa417346b5b/Revenue_Outturn_metadata.ods
3. 2022-23: `RO4_2022-23_data_by_LA.ods` (ODS, 353 KB)  
   https://assets.publishing.service.gov.uk/media/6a7adb8a7349adb729babee5/RO4_2022-23_data_by_LA.ods
4. 2021-22: `RO4_2021-22_data_by_LA_Live.ods` (ODS, 347 KB)  
   https://assets.publishing.service.gov.uk/media/6825a5e47293a87b6c75ec90/RO4_2021-22_data_by_LA_Live.ods
5. 2020-21: `RO4_2020-21_data_by_LA_March_2025.ods` (ODS, 401 KB)  
   https://assets.publishing.service.gov.uk/media/67dc26a2cb8c6838d74b4fd5/RO4_2020-21_data_by_LA_March_2025.ods
6. 2019-20: `RO4_2019-20_data_by_LA.ods` (ODS, 444 KB)  
   https://assets.publishing.service.gov.uk/media/6656f573dc15efdddf1a84bd/RO4_2019-20_data_by_LA.ods
7. January to March 2023: `Detailed_LA_202303_Revised.ods` (ODS, 1.18 MB)  
   https://assets.publishing.service.gov.uk/media/65804b3f83ba38000de1b77a/Detailed_LA_202303_Revised.ods
8. October to December 2022: `Detailed_LA_202212_revised.ods` (ODS, 1.19 MB)  
   https://assets.publishing.service.gov.uk/media/64be88f41e10bf000e17cd3a/Detailed_LA_202212_revised.ods
9. July to September 2022: `V2_Detailed_LA_202209_revised.ods` (ODS, 1.27 MB)  
   https://assets.publishing.service.gov.uk/media/645a5900479612000cc29274/V2_Detailed_LA_202209_revised.ods
10. April to June 2022: `Detailed_LA_202206_revised_Updated.ods` (ODS, 1.19 MB)  
   https://assets.publishing.service.gov.uk/media/6400d30c8fa8f527ff6b42db/Detailed_LA_202206_revised_Updated.ods
11. January to March 2022: `Detailed_LA_202203_revised.ods` (ODS, 1.23 MB)  
   https://assets.publishing.service.gov.uk/media/637e39e0d3bf7f153b8b321c/Detailed_LA_202203_revised.ods
12. October to December 2021: `Detailed_LA_202112_revised.ods` (ODS, 1.25 MB)  
   https://assets.publishing.service.gov.uk/media/62e14c208fa8f564a21dcd8a/Detailed_LA_202112_revised.ods
13. July to September 2021: `DetailedLA_202109_revised.ods` (ODS, 1.25 MB)  
   https://assets.publishing.service.gov.uk/media/62694963d3bf7f0e7121ae4b/DetailedLA_202109_revised.ods
14. April to June 2021: `DetailedLA_202106_revised_corrected.ods` (ODS, 1.18 MB)  
   https://assets.publishing.service.gov.uk/media/6a2c204ce50716856ed4b00e/DetailedLA_202106_revised_corrected.ods
15. January to March 2021: `DetailedLA_202103_Revised.ods` (ODS, 1.18 MB)  
   https://assets.publishing.service.gov.uk/media/61796748e90e0719833464ff/DetailedLA_202103_Revised.ods
16. October to December 2020: `DetailedLA_202012_Revised_updated.ods` (ODS, 1.17 MB)  
   https://assets.publishing.service.gov.uk/media/60fae728d3bf7f04599e2170/DetailedLA_202012_Revised_updated.ods
17. July to September 2020: `DetailedLA_202009_Revised.ods` (ODS, 1.22 MB)  
   https://assets.publishing.service.gov.uk/media/60803c88e90e076aab2a0531/DetailedLA_202009_Revised.ods
18. April to June 2020: `Detailed_LA_202006_Revised_Fixed.ods` (ODS, 1.2 MB)  
   https://assets.publishing.service.gov.uk/media/65e6e8372f2b3be8b07cd78e/Detailed_LA_202006_Revised_Fixed.ods
19. January to March 2020: `Detailed_LA_202003_Revised_Fixed.ods` (ODS, 858 KB)  
   https://assets.publishing.service.gov.uk/media/65e6e8207bc329020bb8c266/Detailed_LA_202003_Revised_Fixed.ods
20. October to December 2019: `DetailedLA_201912_revised.ods` (ODS, 850 KB)  
   https://assets.publishing.service.gov.uk/media/5f749aaad3bf7f2868b3ffa2/DetailedLA_201912_revised.ods
21. July to September 2019: `DetailedLA_201909_revised.xlsx` (XLSX, 1.4 MB)  
   https://assets.publishing.service.gov.uk/media/5ec53218e90e0754d1dedf18/DetailedLA_201909_revised.xlsx
22. April to June 2019: `DetailedLA_201906_revised.xlsx` (XLSX, 1.39 MB)  
   https://assets.publishing.service.gov.uk/media/5f31589b8fa8f57acebf6820/DetailedLA_201906_revised.xlsx

## Priority 4: checks and reference (7 files)

England totals for checking, the council-to-region lookup, the RO forms, the prototype accessible layout and the financial year file.

1. England series up to January to March 2026: `Statutory_Homelessness_England_Time_Series_202603.ods` (ODS, 275 KB)  
   https://assets.publishing.service.gov.uk/media/6a82eee63bd75b81e2329a7b/Statutory_Homelessness_England_Time_Series_202603.ods
2. 2023-24 and 2024-25: `RO_2024-25_Table_2a_2b.ods` (ODS, 15.1 KB)  
   https://assets.publishing.service.gov.uk/media/6a2aa1e2c39255c595b506fc/RO_2024-25_Table_2a_2b.ods
3. 2024-25 and 2025-26: `RO_2025-26_Table_2a_2b.ods` (ODS, not shown)  
   https://assets.publishing.service.gov.uk/media/6aa91cf4086ce7c57b81847e/RO_2025-26_Table_2a_2b.ods
4. April 2025 geography: `LAD25_RGN25_EN_LU.csv` (CSV, not shown)  
   https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/1c17a07ff8fc44218883049f0afa3de1/csv?layers=0
5. 2025-26: `RO_2025-26_v1.3.xlsx` (XLSX, 1.78 MB)  
   https://assets.publishing.service.gov.uk/media/6a4e6d5543f694ee291df829/RO_2025-26_v1.3.xlsx
6. July to September 2025: `Statutory_Homelessness_Detailed_Local_Authority_Data_202509_revised_accessible.ods` (ODS, 1.11 MB)  
   https://assets.publishing.service.gov.uk/media/6a83027a3be22055c1aaa3c0/Statutory_Homelessness_Detailed_Local_Authority_Data_202509_revised_accessible.ods
7. Financial year 2024-25: `Statutory_Homelessness_Detailed_Local_Authority_Data_2024-2025_corrected.ods` (ODS, 1.27 MB)  
   https://assets.publishing.service.gov.uk/media/6a2ff87cd95ffddb05d4b063/Statutory_Homelessness_Detailed_Local_Authority_Data_2024-2025_corrected.ods

## After 29 October 2026

The April to June 2026 release is announced for 29 October 2026 at 9:30am (provisional).
It will add a new detailed LA file and a revised January to March 2026 file, both under
new asset URLs. Read the live tables page again, add the new files to
`config/sources.csv`, and pull them; keep the earlier January to March 2026 file in the
ingest log as the release it was. The 2025-26 RO4 second release is due in December 2026 (MHCLG's technical notes schedule a second release in December)
under the same pattern.

Contains public sector information licensed under the Open Government Licence v3.0.
