"""The shared demo data never carries a council's name or code (docs/adr/0001), and holds only
what the page shows: two typical examples, unnamed points over the councils shown, and counts."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "ta_demo_data.json"
DATASETS = ROOT / "demo" / "ta"
PAGE = DATASETS / "index.html"

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "ta1_wide.csv").exists(),
                                reason="processed tables not built")


@pytest.fixture(scope="module")
def built():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_demo_data.py")], check=True, capture_output=True)
    # the synthetic caseload in demo/ta is written by scripts/build_caseload.py and tested in test_synthetic.py
    return json.loads(DEMO.read_text()), {p.stem: json.loads(p.read_text()) for p in DATASETS.glob("*.json")
                                          if p.name != "synthetic_caseload.json"}


def test_demo_names_no_council(built):
    ta1 = pd.read_csv(ROOT / "data" / "processed" / "ta1_wide.csv")
    ro4 = pd.read_csv(ROOT / "data" / "processed" / "ro4_wide.csv")
    councils = ta1[ta1.level == "council"]
    names = {n for n in set(councils.name.dropna()) | set(ro4.la_name.dropna()) if len(n) > 3}
    codes = set(councils.code.dropna()) | set(ro4.ons_code.dropna()) | set(ro4.e_code.dropna().astype(str))
    codes = {c for c in codes if c[0] == "E" and c[1:].isdigit()}   # ONS (E + 8 digits) and finance (E + 4) codes
    texts = {"ta_demo_data.json": DEMO.read_text(), "index.html": PAGE.read_text()}
    texts |= {p.name: p.read_text() for p in DATASETS.glob("*.json")}
    for where, text in texts.items():
        # the brand's fonts are base64 in the page: encoded bytes, where a code-shaped run such as
        # E4704 can occur by chance, so they are left out as fd-core's screen leaves them out
        text = re.sub(r"(data:(?:font|image)/[\w.+-]+;base64,)[A-Za-z0-9+/]+=*", r"\1", text)
        assert [n for n in names if n in text] == [], where
        assert [c for c in codes if c in text] == [], where


def test_the_tracked_report_compares_the_councils_the_demo_shows(built):
    # Read beside the demo, the report must not point at a council left out for a data check:
    # the same councils compared, the data checks counted for England only, and no council
    # described by its size.
    d, _ = built
    report = (ROOT / "reports" / "phase0_picture.md").read_text()
    n = {r["pattern_id"]: r for r in d["patterns"]}
    assert f"The London comparison covers {n['shown']['london']} of the 33 London councils" in report
    assert f"| 2024-25 | London | {n['shown']['london']} of 33 |" in report
    assert f"| 2024-25 | Rest of England | {n['shown']['rest_of_england']} of 263 |" in report
    assert f"and {n['left_out']['england']} are left out until a person checks their figures" in report
    assert "a London borough with about" not in report
    assert f"{n['far_below']['england']} councils in 2024-25" in report
    far = report.split("### Far above")[1].split("| 2024-25 | ")[1]
    assert far.startswith(f"{n['far_above']['england']} |")


def test_only_the_two_typical_examples(built):
    d, files = built
    ids = ["typical-london", "typical-rest"]
    assert [e["id"] for e in d["examples"]] == ids
    assert [e["id"] for e in files["examples"]] == ids
    assert {r["id"] for r in files["example_mix"]} == set(ids)
    assert {r["id"] for r in files["example_questions"]} == set(ids)


def test_datasets_hold_only_fields_the_page_uses(built):
    _, files = built
    assert set(files) == {"national", "by_type", "spend_by_year", "peers", "quartiles", "examples",
                          "example_mix", "example_questions", "patterns"}
    assert all(set(e) == {"id", "label", "group", "year", "households_about", "gross_per_household",
                          "net_per_household", "ratio_to_peer_median", "peers_lower", "peers_shown",
                          "share_of_peers_lower_gross"} for e in files["examples"])
    assert all(set(p) == {"point", "year", "group", "gross", "net", "households"} for p in files["peers"])
    assert all(set(m) == {"example_type", "id", "type", "households_share", "spend_share"} for m in files["example_mix"])
    for name in ("peers", "quartiles", "by_type", "examples"):
        assert {r["year"] for r in files[name]} == {"2024-25"}, name


def test_shares_are_whole_per_cent_and_add_to_100(built):
    _, files = built
    for ex in ("typical-london", "typical-rest"):
        rows = [m for m in files["example_mix"] if m["id"] == ex]
        for f in ("households_share", "spend_share"):
            pts = [round(m[f] * 100, 6) for m in rows]
            assert all(p == int(p) for p in pts)
            assert sum(int(p) for p in pts) == 100


def test_patterns_are_counts_only_and_add_up(built):
    _, files = built
    n = {r["pattern_id"]: r for r in files["patterns"]}
    for r in files["patterns"]:
        assert set(r) == {"pattern_id", "section", "pattern", "may_mean", "london", "rest_of_england", "england"}
        assert isinstance(r["england"], int) and r["england"] >= 0
        if r["london"] is None:            # counts given for England only
            assert r["rest_of_england"] is None and r["pattern_id"] == "left_out"
            continue
        assert all(isinstance(r[g], int) and r[g] >= 0 for g in ("london", "rest_of_england"))
        assert r["london"] + r["rest_of_england"] == r["england"]
    for g in ("london", "rest_of_england", "england"):
        assert n["in_tables"][g] - n["not_shown"][g] == n["shown"][g]
    # No count of 1 to 4 for a peer group, so that no cell points at one council
    for r in files["patterns"]:
        for g in ("london", "rest_of_england"):
            assert r[g] is None or r[g] == 0 or r[g] >= 5 or r["section"] == "pattern", (r["pattern_id"], g)
    # The grey dots are the councils shown less the example, which is drawn once as "this council"
    by_group = pd.Series([p["group"] for p in files["peers"]]).value_counts()
    assert by_group["London"] == n["shown"]["london"] - 1
    assert by_group["Rest of England"] == n["shown"]["rest_of_england"] - 1
    # The band and median are over the grey dots only, so they cannot give the example back
    assert {q["group"]: q["councils"] for q in files["quartiles"]} == dict(by_group)


def test_share_of_peers_lower_leaves_the_example_out(built):
    _, files = built
    dots = {q["group"]: q["councils"] for q in files["quartiles"]}
    for e in files["examples"]:
        assert e["peers_shown"] == dots[e["group"]]
        assert abs(e["share_of_peers_lower_gross"] - e["peers_lower"] / e["peers_shown"]) <= 0.005


def test_page_has_no_em_dash_and_links_the_licence():
    page = PAGE.read_text()
    assert "\u2014" not in page
    assert "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/" in page
