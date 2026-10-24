"""The private per-council pack names only the council it is for (docs/adr/0001, decision log
21 Oct 2026), its peers come from the shared demo's shown set with the council left out, and
it is written under data/private only."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from tamarket import picture as P
from tamarket.display import shown_set

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "ta1_wide.csv").exists(),
                                reason="processed tables not built")


@pytest.fixture(scope="module")
def inputs():
    from tamarket.pack import PackInputs
    return PackInputs.load()


@pytest.fixture(scope="module")
def packs(inputs):
    from tamarket.pack import council_pack
    return {c: council_pack(c, inputs=inputs) for c in inputs.codes()}


@pytest.fixture(scope="module")
def identities():
    """Every council name and code in the processed tables, by harmonised ONS code."""
    ta1 = pd.read_csv(ROOT / "data" / "processed" / "ta1_wide.csv")
    ro4 = pd.read_csv(ROOT / "data" / "processed" / "ro4_wide.csv")
    ids: dict[str, set[str]] = {}
    ta1 = ta1[ta1.level == "council"]          # regions and England are not councils
    for code, name in zip(ta1.code, ta1.name):
        if isinstance(code, str) and code.startswith("E"):
            ids.setdefault(P.RECODES.get(code, code), set()).update({code, name})
    for code, name, ecode in zip(ro4.ons_code, ro4.la_name, ro4.e_code):
        if isinstance(code, str) and code.startswith("E"):
            ids.setdefault(P.RECODES.get(code, code), set()).update(
                {code, name} | ({str(ecode)} if pd.notna(ecode) else set()))
    return {k: {v for v in vs if isinstance(v, str) and len(v) > 3} for k, vs in ids.items()}


def test_every_pack_names_only_its_own_council(packs, identities):
    for code, pack in packs.items():
        text = json.dumps(pack, ensure_ascii=False)
        own = identities[code]
        # Remove the council's own names and codes first, longest first, so that another
        # council's name inside its own (or a code inside its own code) is not a false alarm.
        for v in sorted(own, key=len, reverse=True):
            text = text.replace(v, " ")
        others = sorted({v for k, vs in identities.items() if k != code for v in vs} - own, key=len, reverse=True)
        found = re.findall(r"\b(?:" + "|".join(map(re.escape, others)) + r")\b", text)
        assert found == [], (code, found[:5])
        assert pack["council"]["code"] == code


def test_peers_are_the_shown_set_less_the_council(inputs, packs):
    t = inputs.tables["2024-25"]
    s = shown_set(t, inputs.left_out)
    for code, pack in packs.items():
        cmp = pack["comparison"]
        if cmp["status"] == "not compared":
            assert cmp["others"] is None and cmp["ratio_to_median_of_others"] is None
            continue
        r = t[t.code == code].iloc[0]
        others = s[(s.peer_group == r.peer_group) & (s.code != code)]
        assert code not in set(others.code)
        assert cmp["others"]["councils"] == len(others)
        assert cmp["others_lower"] == int((others.gross_per_household < r.gross_per_household).sum())
        median = others.gross_per_household.median()
        assert abs(cmp["ratio_to_median_of_others"] - r.gross_per_household / median) <= 0.005 + 1e-9
        assert cmp["status"] == ("provisional: data check outstanding" if code in inputs.left_out else "compared")


def test_data_check_is_a_check_never_a_finding(inputs, packs):
    for code, pack in packs.items():
        dc = pack["data_check"]
        assert dc["left_out_of_shared_chart"] == (code in inputs.left_out)
        if dc["left_out_of_shared_chart"]:
            assert dc["items"], code
            assert "never a finding" in dc["note"]
        else:
            assert dc["items"] == []


def test_questions_put_the_reason_first_and_carry_tags(packs):
    tag = re.compile(r"\[(?:Certain|Likely|Guessing)[^\]]*\]")
    for pack in packs.values():
        for q in pack["questions"]:
            assert q["question"].endswith("?")
            assert tag.search(q["reason"]), q
            assert not q["reason"].endswith("?")
        assert pack["attribution"].startswith("Contains public sector information licensed under the Open Government")


def test_far_from_the_median_still_gets_questions(packs):
    far = [p for p in packs.values() if p["comparison"]["position"] in
           ("more than twice the median of the others", "under a quarter of the median of the others")]
    assert far, "expected some councils far from the median in 2024-25"
    assert all(p["questions"] for p in far)


def test_pack_has_no_em_dash_and_no_judging_words(packs):
    from fdcore.guardrails import scan_text
    for code, pack in packs.items():
        text = json.dumps(pack, indent=1, ensure_ascii=False)
        assert "—" not in text
        bad = [f for f in scan_text(text, code, skip=["phone"]) if f.kind == "accusing language"]
        assert bad == [], bad[:3]


def test_build_script_writes_only_under_data_private(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_packs.py"), "--out", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "data/private" in (r.stdout + r.stderr)


def test_build_script_output_is_gitignored():
    out = ROOT / "data" / "private" / "packs" / "example.json"
    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", str(out)])
    assert r.returncode == 0
