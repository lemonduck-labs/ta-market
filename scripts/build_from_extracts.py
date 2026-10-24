#!/usr/bin/env python3
"""Verify the browser extracts in data/raw/browser, then write the tidy tables.

Every extract is checked against data/raw/browser/MANIFEST.csv (its own SHA-256,
and the source file's name, size and SHA-256 as the browser recorded them), then
against the row count and column sums the browser computed. Any failure stops the
build: nothing is written from a file that does not match.

Outputs (data/processed):
  ta1_wide.csv        every TA1 column, England, regions and councils, per quarter
  ta_households.csv   councils: la_code, la_name, quarter, accommodation_type, households, source_file
  ro4_wide.csv        every authority in RO4 with its class, TA lines in pounds
  ta_spend.csv        housing authorities: la_code, la_name, year, line, gbp, measure, source_file
  extract_report.json checks per extract

One ingest-log entry per extract (data/ingest_log.jsonl), skipped if already logged.

Contains public sector information licensed under the Open Government Licence v3.0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from tamarket import ATTRIBUTION  # noqa: E402
from tamarket.extracts import (  # noqa: E402
    read_extract, read_manifest, ro4_england_check, ro4_wide, ta1_type_check, ta1_wide,
    ta_households_long, ta_spend_long, verify_against_manifest,
)

RAW = ROOT / "data" / "raw" / "browser"
OUT = ROOT / "data" / "processed"
LOG = ROOT / "data" / "ingest_log.jsonl"
LICENCE = "Open Government Licence v3.0"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-log", action="store_true", help="do not write ingest-log entries")
    args = ap.parse_args(argv)

    entries = read_manifest(RAW / "MANIFEST.csv")
    ta1_parts, ro4_parts, report = [], [], {"attribution": ATTRIBUTION, "extracts": []}
    for e in entries:
        ex = read_extract(RAW / e["extract_file"], e["extract_sha256"])
        verify_against_manifest(ex, e)
        item = {
            "extract_file": e["extract_file"], "extract_sha256": ex.extract_sha256,
            "source_file": ex.source_file, "source_bytes": ex.source_bytes,
            "source_sha256": ex.source_sha256, "source_url": e["source_url"], "sheet": ex.sheet,
            "title": ex.title, "rows": len(ex.rows), "checks": "sha256, rows, row width, column sums: all match",
            "browser_check": ex.check, "headers": dict(zip(ex.keys, ex.headers)),
        }
        if e["kind"] == "ta1":
            w = ta1_wide(ex, e["period"], e["snapshot_date"])
            ta1_parts.append(w)
            item["quarter"], item["snapshot_date"] = e["period"], e["snapshot_date"]
            item["type_check"] = ta1_type_check(w)
            c = w[w["level"] == "council"]
            item["councils_without_data"] = c.loc[c["total"].isna(), ["code", "name", "total_marker"]].to_dict("records")
            item["england_published_total"] = float(w.loc[w["level"] == "england", "total"].iloc[0])
            item["councils_sum_total"] = float(c["total"].sum())
        elif e["kind"] == "ro4":
            w = ro4_wide(ex, e["period"])
            ro4_parts.append(w)
            item["year"] = e["period"]
            item["england_check"] = ro4_england_check(w)
        else:
            raise SystemExit(f"unknown kind {e['kind']!r} in manifest")
        report["extracts"].append(item)

        if not args.no_log:
            from fdcore.ingest_log import IngestLog
            log = IngestLog(LOG)
            out_file = str((RAW / e["extract_file"]).relative_to(ROOT))
            seen = any(x.get("sha256") == ex.extract_sha256 and x.get("out_file") == out_file for x in log.entries())
            if not seen:
                log.record(
                    source="mhclg", url=e["source_url"], licence=LICENCE,
                    payload=(RAW / e["extract_file"]).read_bytes(), rows=len(ex.rows), out_file=out_file,
                    method="browser",
                    note=(f"{ex.source_file} ({ex.source_bytes} bytes, sha256 {ex.source_sha256}), sheet "
                          f"{ex.sheet}, read in the browser on {e['read_in_browser']}; extract checks match"),
                    retrieved_at=f"{e['read_in_browser']}T00:00:00+00:00",
                )

    OUT.mkdir(parents=True, exist_ok=True)
    ta1 = pd.concat(ta1_parts, ignore_index=True)
    ro4 = pd.concat(ro4_parts, ignore_index=True)
    ta1.to_csv(OUT / "ta1_wide.csv", index=False)
    ta_households_long(ta1).to_csv(OUT / "ta_households.csv", index=False)
    ro4.to_csv(OUT / "ro4_wide.csv", index=False)
    ta_spend_long(ro4).to_csv(OUT / "ta_spend.csv", index=False)
    (OUT / "extract_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"{len(entries)} extracts verified; {len(ta1)} TA1 rows, {len(ro4)} RO4 rows written to {OUT}")
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
