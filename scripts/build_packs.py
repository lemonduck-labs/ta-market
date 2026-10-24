"""Write one private pack per council to data/private/packs/<code>.json (gitignored).

Each pack names only the council it is for, against unnamed peers (tamarket/pack.py). Packs
are for one-council private pages only, never a shared page, and none is shared until the
owner switches naming on for that copy (docs/adr/0001), a person has done that council's data
checks, and the fact-checker and guardrails reviewer pass it (docs/decision_log.md).

Usage:  python scripts/build_packs.py [--year 2024-25] [--out data/private/packs]

Prints counts only, never a council's name.

Contains public sector information licensed under the Open Government Licence v3.0.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket.pack import YEAR, YEARS, PackInputs, council_pack  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "private" / "packs"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--year", default=YEAR, choices=YEARS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    out = args.out.resolve()
    private = (ROOT / "data" / "private").resolve()
    if private not in out.parents and out != private:
        raise SystemExit(f"packs name a council, so they are written under {private} only")
    out.mkdir(parents=True, exist_ok=True)
    inputs = PackInputs.load()
    status = Counter()
    for code in inputs.codes(args.year):
        pack = council_pack(code, args.year, inputs)
        status[pack["comparison"]["status"]] += 1
        (out / f"{code}.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {sum(status.values())} private packs for {args.year} to {out.relative_to(ROOT)}: "
          + ", ".join(f"{n} {s}" for s, n in sorted(status.items())))
    print("Private: each pack names its own council only. Not for any shared page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
