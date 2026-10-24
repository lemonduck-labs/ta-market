"""The monitoring layer (phase 7): the register, the vocabulary from the planner's spec, the filed
items, the council-name screen in front of fd-core's checks, and what the build publishes."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fdcore import monitor as FM  # noqa: E402
from scripts import monitor as TM  # noqa: E402

REG = FM.load_register(ROOT / "monitor" / "sources.json")
ITEMS = FM.load_items(ROOT / "monitor" / "items.jsonl")


def test_the_register_is_english_public_and_says_its_terms():
    assert {s["language"] for s in REG.values()} == {"en"}
    for s in REG.values():
        assert s["terms_url"].startswith("https://") and s["terms_note"].strip()
        assert s["reliability"] in "AB"


def test_the_vocabulary_comes_from_the_planners_spec_and_is_written_as_built():
    v = TM.vocab()
    pw = json.loads((ROOT / "tamarket" / "spec" / "pathways.json").read_text(encoding="utf-8"))
    assert {c["id"] for c in pw["suitability_checks"]} <= set(v["checks"])
    assert {c["id"] for p in pw["pathways"] for c in p["officer_checks"]} <= set(v["checks"])
    assert set(v["clocks"]) == {"s208", "child", "bnb_family", "review"}
    assert set(v["references"]) == {r["id"] for r in json.loads((ROOT / "tamarket" / "spec" / "references.json").read_text(encoding="utf-8"))["references"]}
    on_disk = json.loads((ROOT / "monitor" / "vocab.json").read_text(encoding="utf-8"))
    assert {k: on_disk[k] for k in v} == v, "monitor/vocab.json is stale: run python scripts/monitor.py vocab"


def test_every_filed_item_passes_the_checks_again_and_names_no_council():
    assert len(ITEMS) >= 5
    names = TM.council_names()
    assert len(names) > 250
    for it in ITEMS:
        cand = {k: v for k, v in it.items() if k not in ("id", "excerpt_sha256", "grade_words")}
        assert FM.validate(cand, REG, TM.vocab(), today=date(2026, 10, 22)) == [], it["id"]
        assert TM.council_problems(it, names) == [], it["id"]
        assert it["id"] == FM.item_id(cand) and it["excerpt_sha256"] == FM.excerpt_sha(cand)
        assert len(it["excerpt_original"]) < 300
        # One source, so credibility 2 (probably true) at most: 1 needs a second, independent source.
        assert int(it["grade_proposed"][1]) >= 2, it["id"]
    log = [json.loads(x) for x in (ROOT / "data" / "ingest_log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    filed = {e["note"].split()[-1]: e for e in log if e["source"].startswith("monitor:")}
    assert set(filed) == {i["id"] for i in ITEMS}
    assert {e["out_file"] for e in filed.values()} == {"monitor/items.jsonl"}, "the log names the items file by its repo-relative path"


def test_a_page_with_two_dates_gives_published_and_updated_apart():
    """Where a page shows a published date and an updated one, published is the first and updated
    the second (monitor/RUNBOOK.md): the announcement and chapter 17, read again on 22 October 2026."""
    by = {i["url"].rsplit("/", 1)[-1]: i for i in ITEMS}
    assert (by["statutory-homelessness-in-england-april-to-june-2026"]["published"], by["statutory-homelessness-in-england-april-to-june-2026"]["updated"]) == ("2026-02-26", "2026-03-04")
    assert (by["chapter-17-suitability-of-accommodation"]["published"], by["chapter-17-suitability-of-accommodation"]["updated"]) == ("2018-02-22", "2026-10-15")
    for it in ITEMS:
        assert TM.updated_problems(it) == [], it["id"]
    bad = dict(ITEMS[0], updated=ITEMS[0]["published"])
    assert "after published" in TM.updated_problems(bad)[0]
    assert "after the page was read" in TM.updated_problems(dict(ITEMS[0], updated="2026-12-01"))[0]


def test_a_source_that_is_not_open_government_licence_says_what_its_terms_allow():
    for s in REG.values():
        if not s["terms_note"].startswith("Open Government Licence"):
            assert s["terms_note"].startswith("Not the Open Government Licence") and "re-use" in s["terms_note"], s["id"]


def test_the_council_screen_refuses_before_fd_cores_checks(tmp_path):
    names = TM.council_names()
    good = {k: v for k, v in ITEMS[0].items() if k not in ("id", "excerpt_sha256", "grade_words")}
    named = dict(good, url=good["url"] + "?x=1", summary=good["summary"] + f" As in {names[0]}.")
    inbox = tmp_path / "inbox"; inbox.mkdir()
    (inbox / "a.json").write_text(json.dumps([good, named]))
    rep = TM.ingest(inbox, tmp_path / "items.jsonl", tmp_path / "log.jsonl", tmp_path / "refused.jsonl", today=date(2026, 10, 22), names=names)
    assert len(rep["filed"]) == 1 and len(rep["refused"]) == 1
    assert "names a council" in rep["refused"][0]["problems"][0]
    assert "names a council" in (tmp_path / "refused.jsonl").read_text()
    assert json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])["source"] == f"monitor:{good['source']}"


def test_an_updated_date_is_checked_here_and_kept_on_the_filed_line(tmp_path):
    """fd-core's item has no "updated": this project checks it, files the item without it, then adds it."""
    base = {k: v for k, v in ITEMS[0].items() if k not in ("id", "excerpt_sha256", "grade_words", "updated")}
    later = dict(base, updated="2026-09-01")
    wrong = dict(base, url=base["url"] + "?y=1", updated=base["published"])
    inbox = tmp_path / "inbox"; inbox.mkdir()
    (inbox / "a.json").write_text(json.dumps([later, wrong]))
    rep = TM.ingest(inbox, tmp_path / "items.jsonl", tmp_path / "log.jsonl", tmp_path / "refused.jsonl", today=date(2026, 10, 22), names=[])
    assert len(rep["filed"]) == 1 and len(rep["refused"]) == 1 and "after published" in rep["refused"][0]["problems"][0]
    filed = [json.loads(x) for x in (tmp_path / "items.jsonl").read_text().splitlines()]
    assert [f["updated"] for f in filed] == ["2026-09-01"] and filed[0]["id"] == FM.item_id(base)


def test_the_build_publishes_the_items_and_the_registers_public_facts_apart():
    """data/monitor.json is a list of items; spec/monitor_sources.json an object with a "sources"
    list, each with its terms_note, so a site build can keep only items under the Open Government
    Licence."""
    items, src = TM.published_items(), TM.published_sources()
    assert [i["id"] for i in items] == [i["id"] for i in sorted(ITEMS, key=lambda i: (i.get("updated") or i["published"], i["id"]), reverse=True)]
    assert isinstance(src["sources"], list) and {s["id"] for s in src["sources"]} == set(REG)
    assert all(s["terms_note"] for s in src["sources"])
    assert src["grades"]["reliability"]["A"] == "Completely reliable"
    dist = ROOT / "app" / "dist"
    if not (dist / "data" / "monitor.json").exists():
        pytest.skip("app/dist is not built")
    assert json.loads((dist / "data" / "monitor.json").read_text(encoding="utf-8")) == items
    assert json.loads((dist / "spec" / "monitor_sources.json").read_text(encoding="utf-8")) == src
    man = json.loads((dist / "data" / "manifest.json").read_text(encoding="utf-8"))
    assert {"data/monitor.json", "spec/monitor_sources.json"} <= set(man["files"])


def test_the_inbox_and_refusals_stay_out_of_git():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert "monitor/inbox/" in ignored and "monitor/refused.jsonl" in ignored
    assert TM.REFUSALS.name == "refused.jsonl"
