"""The files listed in share/README.md pass the guardrails screen with the private deny list and
name no council, and the council tables are never among them (docs/adr/0001)."""
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "share" / "README.md"
NEVER = ["data/processed/picture_councils_", "data/private/", "reports/private/"]


def shared_paths() -> list[Path]:
    table = INDEX.read_text(encoding="utf-8").split("| File |")[1].split("\n\n")[0]
    out = []
    for cell in re.findall(r"^\| ([^|]+) \|", table, re.M):
        for pat in re.findall(r"`([^`]+)`", cell):
            if pat.endswith("/"):
                continue           # app/dist/ is built, not tracked, and checked in tests/test_app.py
            out += sorted(ROOT.glob(pat)) if "*" in pat else [ROOT / pat]
    return out


def test_every_listed_file_exists_and_none_is_private():
    paths = shared_paths()
    assert len(paths) >= 12
    for p in paths:
        assert p.exists(), p
        rel = p.relative_to(ROOT).as_posix()
        assert not any(rel.startswith(n) for n in NEVER), rel


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "ta1_wide.csv").exists(), reason="processed tables not built")
def test_no_shared_file_names_a_council():
    ta1 = pd.read_csv(ROOT / "data" / "processed" / "ta1_wide.csv")
    ro4 = pd.read_csv(ROOT / "data" / "processed" / "ro4_wide.csv")
    names = {n for n in set(ta1[ta1.level == "council"].name.dropna()) | set(ro4.la_name.dropna()) if len(n) > 3}
    for p in shared_paths():
        text = p.read_text(encoding="utf-8")
        hits = [n for n in names if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text)]
        assert hits == [], (p.name, hits)


def test_every_shared_file_passes_the_guardrails_screen():
    from fdcore.guardrails import scan_text
    deny_file = ROOT / "config" / "deny_list.txt"
    deny = deny_file.read_text(encoding="utf-8").splitlines() if deny_file.exists() else []
    for p in shared_paths():
        found = scan_text(p.read_text(encoding="utf-8"), p.name, deny)
        assert found == [], (p.name, [(f.kind, f.text) for f in found][:5])
