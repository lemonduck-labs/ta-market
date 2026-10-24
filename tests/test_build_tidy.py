"""Smoke test for scripts/build_tidy.py on synthetic files."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("build_tidy", ROOT / "scripts" / "build_tidy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_tidy_end_to_end(tmp_path, legacy_ta1, ro4_wide):
    pytest.importorskip("fdcore")
    raw = tmp_path / "raw"
    raw.mkdir()
    hh = raw / legacy_ta1.name
    sp = raw / ro4_wide.name
    hh.write_bytes(legacy_ta1.read_bytes())
    sp.write_bytes(ro4_wide.read_bytes())
    (raw / "MDIS_Tables_202603.ods").write_bytes(b"not listed in the manifest")
    manifest = tmp_path / "pull_manifest.csv"
    with manifest.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file_name", "bytes", "sha256", "downloaded_at"])
        w.writerow([hh.name, hh.stat().st_size, hashlib.sha256(hh.read_bytes()).hexdigest(), "2026-10-21T10:00:00+01:00"])
        w.writerow([sp.name, sp.stat().st_size, "", ""])
    out, log = tmp_path / "processed", tmp_path / "ingest_log.jsonl"
    common = ["--raw", str(raw), "--out", str(out), "--manifest", str(manifest), "--log", str(log)]
    script = load_script()

    assert script.main(common) == 1  # the unlisted file is refused
    report = json.loads((out / "parse_report.json").read_text())
    assert report["files"]["MDIS_Tables_202603.ods"]["accepted"] is False
    assert report["files"][hh.name]["verification"] == "sha256 and bytes match"
    assert report["files"][sp.name]["verification"] == "bytes match (no sha256 given)"
    assert report["files"][hh.name]["types_sum_to_total"] == "3 of 3 councils"
    assert report["files"][hh.name]["source_id"] == "hclic_la_202603"

    households = pd.read_csv(out / "ta_households.csv")
    spend = pd.read_csv(out / "ta_spend.csv")
    assert len(households) == 4 * 7 and set(households["quarter"]) == {"2026-Q1"}
    assert len(spend) == 3 * 7 * 2 and set(spend["measure"]) == {"total_expenditure", "net_current_expenditure"}

    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 2 and {e["method"] for e in entries} == {"browser"}
    hh_entry = next(e for e in entries if e["source"] == "hclic_la_202603")
    assert hh_entry["rows"] == 28 and hh_entry["licence"] == "OGL v3.0"
    assert hh_entry["retrieved_at"] == "2026-10-21T10:00:00+01:00"

    assert script.main(common + ["--allow-unverified"]) == 0
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 3  # the two earlier files are not logged twice
