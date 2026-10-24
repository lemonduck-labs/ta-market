Use the housing-data-engineer agent to fetch the latest MHCLG statutory homelessness detailed local
authority tables and revenue outturn files listed in docs/browser_pull.md, verify them, parse them with
tamarket/mhclg.py into data/processed, and report the release, row counts and gaps. If this machine
cannot reach gov.uk, say so and stop.
