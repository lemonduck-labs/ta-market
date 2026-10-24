# What may be shared

The repository stays private. These are the files that may leave it, for a reviewer or on the
demo site, and the checks they pass (`tests/test_share.py`): the fd-core guardrails screen with
the private deny list (empty until the owner fills it), no council named, and, for the report,
the same councils compared as the demo shows.

| File | What it is |
|---|---|
| `README.md` | The repository's front page: what the build is, what it found and how to run it. |
| `reports/phase0_picture.md` | The phase 0 market picture: England figures, London and the rest of England over the councils the demo shows, peer quartiles and counts of patterns. No council is named; councils with a data check outstanding are counted for England only. |
| `demo/ta/index.html` and `demo/ta/*.json`, `demo/ta_demo_data.json` | The demo: two unnamed example councils against unnamed points, and counts. Council-level figures are shared only in this form. |
| `app/index.html` with `app/dist/` | The Move forward planner, on 200 synthetic households. |

Never shared: the council tables (`data/processed/picture_councils_*.csv`), which carry each
council's code and name beside its comparison; anything under `data/private/` or
`reports/private/`; and the private per-council packs. The decision log is in this public copy; it names no
council.

Contains public sector information licensed under the Open Government Licence v3.0.
