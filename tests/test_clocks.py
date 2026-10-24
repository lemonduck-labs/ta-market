"""The statutory clocks: the Python reference gives the answers in tamarket/spec/clocks.json's
cases (the JavaScript port is checked against the same cases in tests/test_spec_js.py), each
rule quotes the words that set its period, and the periods count as the law counts them."""
import json
from pathlib import Path

import pytest

from tamarket import clocks as K

SPEC = Path(__file__).resolve().parent.parent / "tamarket" / "spec" / "clocks.json"
DOC = json.loads(SPEC.read_text())


@pytest.mark.parametrize("case", DOC["cases"], ids=[c["id"] for c in DOC["cases"]])
def test_reference_passes_the_shared_cases(case):
    assert K.run_case(case, DOC["rules"]) == case["expect"]


def test_every_rule_quotes_its_words_and_cites_its_source():
    for key in ("s208", "child", "bnb_family", "review"):
        r = DOC["rules"][key]
        assert r["words"] and r["citation"] and r["url"].startswith("https://www.legislation.gov.uk/"), key
        assert "—" not in json.dumps(r, ensure_ascii=False), key


def test_a_period_beginning_with_a_day_includes_that_day():
    assert K.last_day("2026-10-01", 14) == "2026-10-14"
    assert K.last_day("2026-12-25", 14) == "2027-01-07"
    assert K.add_days("2028-02-28", 1) == "2028-02-29"


def test_the_demo_caseload_has_live_clocks():
    """The shipped caseload gives each clock something to show: out-of-district notices with
    none on record, families in B&B, and households with children placed since 1 September 2026."""
    recs = json.loads((SPEC.parent.parent.parent / "demo" / "ta" / "synthetic_caseload.json").read_text())["records"]
    assert all(r["placed_on"] and r["placed_on"] <= "2026-10-21" for r in recs)
    away = [r for r in recs if r["placed_in_another_district"]]
    assert any(r["s208_notice_sent_on"] is None for r in away)
    assert any(K.bnb(r, "2026-10-22", DOC["rules"])["applies"] for r in recs)
    assert any(K.child_scope(r, DOC["rules"])["applies"] for r in recs)


def test_the_review_lines_agree_on_which_reviews_the_clock_tracks():
    """SI 2018/223 reg. 9(1): eight weeks for (b), three for (a) (s.202(1)(ba)(i), (bc)), ten for (c),
    twelve for (d). The panel's two lines say the same."""
    rv = DOC["rules"]["review"]
    for text in (rv["covers"], rv["interim"]):
        assert "reg. 9(1)(b)" in text and "reg. 9(1)(a)" in text and "the same eight weeks" not in text, text
    assert "ten weeks (reg. 9(1)(c)" in rv["covers"] and "twelve weeks (reg. 9(1)(d)" in rv["covers"]
    assert "s.202(1)(ba)(i) or (bc)" in rv["covers"] and "s.202(1)(ba)(i) or (bc)" in rv["interim"]


def test_each_bodys_notice_is_built_from_its_listed_lines_with_their_basis():
    """The drafts are built only from child.contents (app/src/page.js, noticeDraft; the browser flow
    checks each line is in the draft). Each line says why it is there; a line the guidance does not
    give is tagged as the planner's reading."""
    c = DOC["rules"]["child"]["contents"]
    assert set(c) - {"about"} == set(DOC["rules"]["child"]["bodies"])
    for body in DOC["rules"]["child"]["bodies"]:
        for line in c[body]["notice"]:
            assert line["draft"] and line["basis"], (body, line)
            assert "DHSC" in line["basis"] or "s.213AA" in line["basis"] or "[Likely]" in line["basis"], (body, line)
        assert c[body]["officer_notes"], body
    gp = {x["draft"]: x["basis"] for x in c["gp"]["notice"]}
    assert "[Likely]" in gp["Child: {child’s name and date of birth}"]
    assert not any("address" in d.lower() for d in gp), "a GP practice's notice has no address"
    hv = c["health_visiting"]["notice"]
    assert [x["draft_applicant"] for x in hv if "draft_applicant" in x] == [
        "The applicant’s own contact number: {the applicant’s contact number}", "The applicant’s own name: {the applicant’s name}"]
    assert any("pregnant" in n for n in c["health_visiting"]["officer_notes"])
