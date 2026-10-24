"""The synthetic caseload is marked synthetic in every record and file, reproducible from its
seed, holds no names, addresses or postcodes, and follows the published England shares it
claims to follow."""
import collections
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASELOAD = ROOT / "demo" / "ta" / "synthetic_caseload.json"
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "ta1_wide.csv").exists(),
                                reason="processed tables not built")
FIELDS = {"id", "synthetic", "record_type", "household_type", "adults", "children", "household_size",
          "accommodation_type", "accommodation", "placed_in_another_district", "weekly_cost_band", "weekly_cost_from",
          "weekly_cost_to", "weeks_in_ta", "priority_need", "support_needs", "local_connection", "placed_on",
          "s208_notice_sent_on"}


@pytest.fixture(scope="module")
def pub():
    from tamarket.synthetic import published_inputs
    return published_inputs()


@pytest.fixture(scope="module")
def many(pub):
    from tamarket.synthetic import generate_records
    return generate_records(9999, 11, pub)


def test_reproducible_from_the_seed(pub):
    from tamarket.synthetic import generate_caseload
    a, b, c = generate_caseload(60, 5, pub), generate_caseload(60, 5, pub), generate_caseload(60, 6, pub)
    assert a == b
    assert a["records"] != c["records"]


def test_every_record_and_the_file_say_synthetic(pub):
    from tamarket.synthetic import RECORD_TYPE, generate_caseload
    doc = generate_caseload(50, 1, pub)
    assert doc["meta"]["synthetic"] is True and doc["meta"]["notice"].startswith("SYNTHETIC")
    for i, r in enumerate(doc["records"], start=1):
        assert set(r) == FIELDS
        assert r["synthetic"] is True and r["record_type"] == RECORD_TYPE and r["id"] == f"SYN-{i:04d}"


def test_no_names_addresses_or_postcodes(pub):
    from fdcore.guardrails import scan_text
    from tamarket.synthetic import generate_caseload
    text = json.dumps(generate_caseload(500, 3, pub), indent=1, ensure_ascii=False)
    # phone is switched off for demo/ta/*.json by the policy file: numbers there are counts and pounds
    assert scan_text(text, "caseload", skip=["phone"]) == []
    assert not FIELDS & {"name", "address", "postcode", "date_of_birth", "phone", "email"}


def test_published_shares_hold(many, pub):
    n = len(many)
    share = lambda pred: sum(1 for r in many if pred(r)) / n  # noqa: E731
    assert share(lambda r: r["children"] > 0) == pytest.approx(86_460 / 135_580, abs=0.02)
    families = [r for r in many if r["children"] > 0]
    assert sum(r["accommodation_type"] == "bed_and_breakfast" for r in families) / len(families) == pytest.approx(
        1_900 / 86_460, abs=0.006)
    assert sum(r["children"] for r in families) / len(families) == pytest.approx(177_530 / 86_460, abs=0.06)
    assert share(lambda r: bool(r["support_needs"])) == pytest.approx(0.618, abs=0.02)
    assert share(lambda r: "history of mental health problems" in r["support_needs"]) == pytest.approx(0.306, abs=0.02)
    assert share(lambda r: "physical ill health and disability" in r["support_needs"]) == pytest.approx(0.241, abs=0.02)
    assert share(lambda r: "at risk of or has experienced domestic abuse" in r["support_needs"]) == pytest.approx(
        0.134, abs=0.02)
    assert share(lambda r: r["placed_in_another_district"]) == pytest.approx(43_180 / 135_580, abs=0.02)
    total = sum(pub["types"].values())
    for t, v in pub["types"].items():
        assert share(lambda r: r["accommodation_type"] == t) == pytest.approx(v / total, abs=0.02), t
    assert all(r["priority_need"] == "household includes dependent children" for r in families)


def test_published_most_common_stays(many):
    from tamarket.synthetic import STAY_BANDS

    def band(w):
        return next(label for label, lo, hi in STAY_BANDS if lo <= w <= hi)
    fam = collections.Counter(band(r["weeks_in_ta"]) for r in many if r["children"] > 0)
    adults = collections.Counter(band(r["weeks_in_ta"]) for r in many if r["children"] == 0)
    assert fam.most_common(1)[0][0] == "2 to 5 years"
    assert adults.most_common(1)[0][0] == "less than 6 months"


def test_assumptions_are_tagged_and_sourced(pub):
    from tamarket.synthetic import ASSUMPTIONS, SOURCES, generate_caseload
    ids = {s["id"] for s in SOURCES}
    for a in ASSUMPTIONS:
        assert "[Certain]" in a["confidence"] or "[Likely]" in a["confidence"] or "[Guessing]" in a["confidence"]
        for s in (a["source"] or "").split("; "):
            assert not s or s in ids
    assert all({"publisher", "title", "date"} <= set(s) for s in SOURCES)
    assert generate_caseload(5, 1, pub)["meta"]["attribution"].startswith("Contains public sector information")


def test_shipped_caseload_is_the_seeded_build():
    import scripts.build_caseload as B   # noqa: N813
    shipped = json.loads(CASELOAD.read_text())
    meta = shipped["meta"]
    assert meta["synthetic"] is True and meta["notice"].startswith("SYNTHETIC")
    assert shipped == json.loads(json.dumps(B.build(meta["records"], meta["seed"]), ensure_ascii=False))


def test_stays_fit_priority_needs_tied_to_age(many):
    from tamarket.synthetic import AGE_CAP_WEEKS
    capped = [r for r in many if r["priority_need"] in AGE_CAP_WEEKS]
    assert capped
    assert all(r["weeks_in_ta"] <= AGE_CAP_WEEKS[r["priority_need"]] for r in capped)


def test_pregnancy_stays_and_young_person_needs_are_plausible(many):
    from tamarket.synthetic import NOT_WITH, PREGNANCY_CAP_WEEKS
    pregnant = [r for r in many if r["priority_need"] == "household includes a pregnant woman"]
    assert pregnant
    assert all(r["weeks_in_ta"] <= PREGNANCY_CAP_WEEKS for r in pregnant)
    for priority, need in NOT_WITH.items():
        assert not [r for r in many if r["priority_need"] == priority and need in r["support_needs"]]


def test_placement_dates_count_back_from_the_caseload_date(pub):
    import datetime as dt
    from tamarket.synthetic import AS_OF, generate_records, placed_on
    assert placed_on(0) == AS_OF and placed_on(1) == "2026-10-14" and placed_on(52) == "2025-10-22"
    for r in generate_records(300, 3, pub):
        assert (dt.date.fromisoformat(AS_OF) - dt.date.fromisoformat(r["placed_on"])).days == 7 * r["weeks_in_ta"]


def test_s208_history_only_out_of_district_and_never_before_the_placement(pub):
    from tamarket.synthetic import generate_records
    recs = generate_records(3000, 4, pub)
    away = [r for r in recs if r["placed_in_another_district"]]
    assert all(r["s208_notice_sent_on"] is None for r in recs if not r["placed_in_another_district"])
    assert all(r["s208_notice_sent_on"] is None or r["s208_notice_sent_on"] >= r["placed_on"] for r in away)
    none = sum(r["s208_notice_sent_on"] is None for r in away) / len(away)
    assert 0.04 < none < 0.13          # 8 in 100 by construction, give or take the hash


def test_s208_history_ends_on_the_caseload_date(pub):
    """A made-up notice the hash would place after the caseload's date is not on record yet."""
    from tamarket.synthetic import AS_OF, generate_records, s208_history
    recs = generate_records(3000, 4, pub)
    assert all(r["s208_notice_sent_on"] is None or r["s208_notice_sent_on"] <= AS_OF for r in recs)
    later = []
    for i in range(1, 400):
        r = {"id": f"SYN-{i:04d}", "placed_in_another_district": True, "placed_on": "2026-10-20"}
        uncapped = s208_history(r, as_of="2099-12-31")
        if uncapped and uncapped > AS_OF:
            later.append(r)
            assert s208_history(r) is None
    assert later, "no id gives a notice after the caseload's date: the test checks nothing"

