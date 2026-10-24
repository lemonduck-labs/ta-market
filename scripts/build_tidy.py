#!/usr/bin/env python3
"""Verify, parse and log the MHCLG files in data/raw, then write tidy tables.

Files reach data/raw by a side route (a browser download), so each one is
checked against data/pull_manifest.csv (exact bytes, and SHA-256 where given)
before use. A file with no manifest entry is refused unless --allow-unverified
is passed, in which case its hash is logged and it is marked unverified.

Outputs (data/processed):
  ta_households.csv        la_code, la_name, quarter, accommodation_type, households, source_file
  ta_spend.csv             la_code, la_name, year, line, gbp, measure, source_file
  ta_spend_timeseries.csv  the same, from the multi-year CSV (only if it and its metadata are present)
  parse_report.json        per file: release, rows, councils, gaps, column mapping, checks

Each accepted raw file gets one entry in data/ingest_log.jsonl (fdcore.ingest_log),
skipped if the same file (hash) and output are already logged.

Usage:
  python scripts/build_tidy.py [--engine calamine] [--allow-unverified] [--no-log]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from tamarket import ATTRIBUTION, __version__, mhclg  # noqa: E402

MEASURES = ("total_expenditure", "net_current_expenditure")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_csv_rows(path: Path, key: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {r[key].strip(): r for r in csv.DictReader(fh) if r.get(key, "").strip()}


def check_against_manifest(path: Path, entry: dict | None) -> tuple[bool, str]:
    if entry is None:
        return False, "no manifest entry"
    want_bytes = (entry.get("bytes") or "").strip()
    want_sha = (entry.get("sha256") or "").strip().lower()
    if not want_bytes and not want_sha:
        return False, "manifest entry has neither bytes nor sha256"
    if want_bytes and int(want_bytes) != path.stat().st_size:
        return False, f"bytes differ: manifest {want_bytes}, file {path.stat().st_size}"
    if want_sha and want_sha != sha256_file(path):
        return False, "sha256 differs from the manifest"
    return True, "sha256 and bytes match" if want_sha and want_bytes else (
        "sha256 matches" if want_sha else "bytes match (no sha256 given)")


def caught_messages(caught) -> list[str]:
    return [str(w.message) for w in caught if issubclass(w.category, mhclg.TaMarketWarning)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--manifest", type=Path, default=ROOT / "data" / "pull_manifest.csv")
    ap.add_argument("--sources", type=Path, default=ROOT / "config" / "sources.csv")
    ap.add_argument("--log", type=Path, default=ROOT / "data" / "ingest_log.jsonl")
    ap.add_argument("--engine", default=None, help="pandas Excel engine, for example calamine (much faster)")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="use files with no manifest entry, logging them as unverified")
    ap.add_argument("--no-log", action="store_true", help="do not write ingest log entries")
    args = ap.parse_args(argv)

    sources = read_csv_rows(args.sources, "file_name")
    manifest = read_csv_rows(args.manifest, "file_name")
    groups = mhclg.discover_raw_files(args.raw)
    report: dict = {"tamarket_version": __version__, "attribution": ATTRIBUTION, "files": {}, "problems": []}
    accepted: dict[Path, str] = {}

    for paths in groups.values():
        for p in paths:
            ok, how = check_against_manifest(p, manifest.get(p.name))
            if not ok and how == "no manifest entry" and args.allow_unverified:
                ok, how = True, "unverified (no manifest entry)"
            report["files"][p.name] = {"verification": how, "accepted": ok,
                                       "source_id": sources.get(p.name, {}).get("id", "not in config/sources.csv")}
            if ok:
                accepted[p] = how
            else:
                report["problems"].append(f"{p.name}: refused ({how})")

    args.out.mkdir(parents=True, exist_ok=True)
    outputs: dict[Path, tuple[Path, int]] = {}

    # Households in TA, one file per quarter.
    hh_paths = [p for p in groups["households"] if p in accepted]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", mhclg.TaMarketWarning)
        chosen = mhclg.pick_household_files(hh_paths)
    for skipped in set(hh_paths) - set(chosen.values()):
        report["files"][skipped.name]["parsed"] = "skipped: another file covers the same quarter"
    frames = []
    for quarter, p in chosen.items():
        info = report["files"][p.name]
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", mhclg.TaMarketWarning)
                df = mhclg.read_ta_households(p, engine=args.engine)
        except Exception as exc:  # report and carry on with the other files
            info["parsed"] = f"failed: {exc}"
            report["problems"].append(f"{p.name}: {exc}")
            continue
        check = mhclg.validate_ta_households(df)
        complete = check.dropna(subset=["total", "sum_of_types"])
        info.update({
            "parsed": "ok", "quarter": quarter, "rows": len(df), "councils": int(df["la_code"].nunique()),
            "councils_with_missing_values": int(df[df["households"].isna()]["la_code"].nunique()),
            "types_sum_to_total": f"{int(complete['ok'].sum())} of {len(complete)} councils",
            "max_abs_difference": float(complete["difference"].abs().max()) if len(complete) else None,
            "layout": df.attrs["layout"], "column_map": df.attrs["column_map"],
            "non_numeric_values": df.attrs["non_numeric_values"], "warnings": caught_messages(caught),
        })
        frames.append(df)
    if frames:
        households = pd.concat(frames, ignore_index=True)
        target = args.out / "ta_households.csv"
        households.to_csv(target, index=False)
        for p in chosen.values():
            if report["files"][p.name].get("parsed") == "ok":
                outputs[p] = (target, report["files"][p.name]["rows"])

    # TA spend, one RO4 file per year, gross and net.
    spend_frames = []
    by_year = {mhclg.year_from_text(p.name) or p.name: p for p in groups["spend"] if p in accepted}
    for year, p in sorted(by_year.items()):
        info = report["files"][p.name]
        info.update({"parsed": "ok", "year": year, "rows": 0, "measures": {}})
        for measure in MEASURES:
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", mhclg.TaMarketWarning)
                    df = mhclg.read_ta_spend(p, measure=measure, engine=args.engine)
            except Exception as exc:
                info["measures"][measure] = f"failed: {exc}"
                report["problems"].append(f"{p.name} ({measure}): {exc}")
                continue
            totals = mhclg.total_ta_spend(df)
            info["rows"] += len(df)
            info["measures"][measure] = {
                "rows": len(df), "councils": int(df["la_code"].nunique()),
                "councils_with_missing_values": int(df[df["gbp"].isna()]["la_code"].nunique()),
                "sum_of_councils_gbp_lines_80_to_86": float(totals["gbp"].sum()),
                "layout": df.attrs["layout"], "column_map": df.attrs["column_map"],
                "non_numeric_values": df.attrs["non_numeric_values"], "warnings": caught_messages(caught),
            }
            spend_frames.append(df)
        if info["rows"] == 0:
            info["parsed"] = "failed"
    if spend_frames:
        spend = pd.concat(spend_frames, ignore_index=True)
        target = args.out / "ta_spend.csv"
        spend.to_csv(target, index=False)
        for p in by_year.values():
            if report["files"][p.name].get("rows"):
                outputs[p] = (target, report["files"][p.name]["rows"])

    # Optional: the multi-year data set.
    ts = [p for p in groups["ro_timeseries"] if p in accepted]
    meta = [p for p in groups["ro_metadata"] if p in accepted]
    if ts and meta:
        try:
            frames = [mhclg.read_ro_timeseries(ts[-1], meta[-1], measure=m) for m in MEASURES]
            series = pd.concat(frames, ignore_index=True)
            target = args.out / "ta_spend_timeseries.csv"
            series.to_csv(target, index=False)
            report["files"][ts[-1].name].update({"parsed": "ok", "rows": len(series),
                                                 "items": {m: f.attrs["items"] for m, f in zip(MEASURES, frames)}})
            outputs[ts[-1]] = (target, len(series))
        except Exception as exc:
            report["files"][ts[-1].name]["parsed"] = f"failed: {exc}"
            report["problems"].append(f"{ts[-1].name}: {exc}")

    # Ingest log: one entry per accepted file, unless already logged.
    if not args.no_log and accepted:
        try:
            from fdcore.ingest_log import IngestLog
        except ImportError:
            report["problems"].append("fdcore not installed (pip install -e ../fd-core); ingest log not written")
        else:
            log = IngestLog(args.log)
            seen = {(e.get("sha256"), e.get("out_file")) for e in log.entries()}
            for p, how in accepted.items():
                payload = p.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                target, rows = outputs.get(p, (None, None))
                out_file = str(target.relative_to(ROOT)) if target and target.is_relative_to(ROOT) else (
                    str(target) if target else None)
                report["files"][p.name]["sha256"] = digest
                if (digest, out_file) in seen:
                    continue
                src = sources.get(p.name, {})
                pulled = manifest.get(p.name, {}).get("downloaded_at") or None
                log.record(source=src.get("id", "unlisted"), url=src.get("file_url", ""),
                           licence=src.get("licence", "unknown"), payload=payload, rows=rows,
                           out_file=out_file, method="browser",
                           note=f"release: {src.get('period', 'unknown')} (published {src.get('published') or 'n/a'}, "
                                f"updated {src.get('updated') or 'n/a'}); check: {how}; "
                                f"parsed by tamarket {__version__}",
                           retrieved_at=pulled)

    (args.out / "parse_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    for name, info in report["files"].items():
        status = info.get("parsed", "not parsed")
        detail = info.get("quarter") or info.get("year") or ""
        print(f"{name}: {info['verification']}; {status} {detail} rows={info.get('rows', '-')}")
    for problem in report["problems"]:
        print(f"PROBLEM: {problem}")
    print(f"Wrote {args.out / 'parse_report.json'}")
    print(ATTRIBUTION)
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
