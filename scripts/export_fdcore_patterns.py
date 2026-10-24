"""Write tamarket/spec/fdcore_patterns.json: fd-core's guardrails patterns and rules, for a
JavaScript port of the plan screen (tamarket/spec/screen_rules.json, "fdcore").

The file is generated, never edited, and stays out of git: it lists the words the screen
blocks, which the repository's own screen would flag. Run this before publishing a page or
deploying a function that screens plans.

Usage:  python scripts/export_fdcore_patterns.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket.moveon import SPEC_DIR, fdcore_patterns  # noqa: E402

OUT = SPEC_DIR / "fdcore_patterns.json"


def main() -> int:
    OUT.write_text(json.dumps(fdcore_patterns(), indent=1, ensure_ascii=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} (generated from fd-core; not tracked by git)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
