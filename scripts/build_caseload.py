"""Write demo/ta/synthetic_caseload.json: the synthetic caseload the planner page ships.

SYNTHETIC. Records are made up by tamarket/synthetic.py from a fixed seed; none is or
describes a real person. Each record carries the output of tamarket/moveon.py for it, so the
page shows Python's suggestions and never re-implements the rules:

- eligible_pathways: [{pathway_id, reasons, officer_checks}], ids resolved by meta.moveon.texts;
- suitability_checks: ids of the suitability checks the record raises.

Pathway ids are stable slugs (social-housing, prs-offer, supported-housing); a page stores
officer decisions against them. Suggestions for an officer to approve, never decisions.

Usage:  python scripts/build_caseload.py [--n 200] [--seed 20261021]

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket import moveon as M  # noqa: E402
from tamarket.synthetic import DEFAULT_N, DEFAULT_SEED, generate_caseload  # noqa: E402

OUT = ROOT / "demo" / "ta" / "synthetic_caseload.json"


def build(n: int = DEFAULT_N, seed: int = DEFAULT_SEED) -> dict:
    doc = generate_caseload(n, seed)
    spec = M.load_spec()
    for r in doc["records"]:
        r["eligible_pathways"] = M.eligible_pathways(r, spec)
        r["suitability_checks"] = M.suitability_check_ids(r, spec)
    pw = spec["pathways"]
    doc["meta"]["moveon"] = {
        "spec_version": pw["spec_version"], "status": M.STATUS, "built_by": "tamarket/moveon.py",
        "pathways": {p["id"]: {"title": p["title"], "summary": p["summary"], "ends_main_duty": p["ends_main_duty"]}
                     for p in pw["pathways"]},
        "general_checks": [c["id"] for c in pw["general_checks"]],
        "texts": M.texts(spec), "statutory_figures": pw["statutory_figures"], "citations": pw["citations"],
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)
    doc = build(args.n, args.seed)
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(doc['records'])} synthetic records (seed {args.seed}), "
          f"{OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
