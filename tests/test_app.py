"""The Move forward planner page (app/).

- The page in git is the built page: app/index.html holds the spec ports, the template and the
  page script exactly as scripts/build_app.py writes them.
- The code the page runs (taken from app/index.html itself) passes the shared screen and
  scenario cases, gives Python's suggestions and drafting prompt for every synthetic record, and
  reads every drafting reply as moveon.parse_reply does.
- The template plan passes the screen, Python's and the port, for every record, with nothing cut
  to fit the schema.
- The publish folder matches its manifest, holds the caseload and spec files unchanged, and
  stays out of git.
- The page names no council, loads nothing from other sites, uses no em dashes, and states the
  scenario's limits in the Python module's own words.

The JavaScript tests need node and are skipped without it.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tamarket import moveon as M
from tamarket import scenario as SC

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
PAGE = APP / "index.html"
DIST = APP / "dist"
SPEC = ROOT / "tamarket" / "spec"
CASELOAD = ROOT / "demo" / "ta" / "synthetic_caseload.json"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
LICENCE = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

REPLIES = [
    '{"a": 1}', ' \n{"a": 1}\t', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', '```json\n{"a": 1}```',
    'Here is the plan: {"a": 1}', '{"a": 1}\n\nI hope this helps.', '```json\n{"a": 1}\n```\nmore', '[1, 2]', 'null',
    '"text"', '', '{"a": NaN}', '{"a": Infinity}', chr(0xFEFF) + '{"a": 1}', chr(0xA0) + '{"a": 1}', '{"a": 1, "a": 2}',
    '{"a": "\\ud800"}', '{"a": ' + '[' * 31 + ']' * 31 + '}', '{"a": ' + '[' * 32 + ']' * 32 + '}',
    '{"a": ' + '[' * 2000 + ']' * 2000 + '}', '{"a": 1', '{\'a\': 1}',
]
REPLIES_OK = [True, True, True, True, True, False, False, False, False, False, False, False, False, False, False,
              False, True, True, True, False, False, False, False]


def bare(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("eligible_pathways", "suitability_checks")}


def test_page_is_built_from_its_sources():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_app.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def dist():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_app.py")], check=True, capture_output=True)
    return DIST


def test_publish_folder_matches_its_manifest(dist):
    m = json.loads((dist / "data" / "manifest.json").read_text())
    assert m["caseload"] == {"records": 200, "seed": 20261021, "synthetic": True}
    for path, sha in m["files"].items():
        assert hashlib.sha256((dist / path).read_bytes()).hexdigest() == sha, path
    assert (dist / "data" / "caseload.json").read_bytes() == CASELOAD.read_bytes()
    for name in ["screen_rules.json", "moveon.schema.json", "pathways.json", "moveon_prompt.md", "scenario_cases.json"]:
        assert (dist / "spec" / name).read_bytes() == (SPEC / name).read_bytes(), name
    assert json.loads((dist / "spec" / "fdcore_patterns.json").read_text()) == json.loads(json.dumps(M.fdcore_patterns()))
    assert (dist / "index.html").read_bytes() == PAGE.read_bytes()
    # The page checks every file it loads against the manifest, and loads nothing else.
    loads = re.search(r"const FILES = \[([^\]]*)\]", (APP / "src" / "page.js").read_text()).group(1)
    assert sorted(re.findall(r"'([^']+)'", loads)) == sorted(m["files"])


def test_publish_folder_stays_out_of_git():
    for p in ["app/dist/spec/fdcore_patterns.json", "app/dist/index.html", "app/dist/data/manifest.json"]:
        assert subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", p]).returncode == 0, p


def test_fd_core_inputs_are_checked_in_fd_core(tmp_path, monkeypatch):
    """An fd-core file is checked in fd-core's own repository. From c165ef6 it was looked up in this
    one, so every build was marked as having uncommitted changes and --clean always refused."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_app as B
    fd = tmp_path / "fd-core"
    (fd / "fdcore").mkdir(parents=True)
    (fd / "fdcore" / "memory.mjs").write_text("export const A = 1;\n")
    # The identity is put together here, so the repo's own screen never sees an address.
    git = ["git", "-C", str(fd), "-c", "user.name=t", "-c", "user.email=t" + "@" + "example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", str(fd)], check=True)
    subprocess.run(git + ["add", "fdcore/memory.mjs"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "c"], check=True)
    monkeypatch.setattr(B, "FDCORE", fd)
    assert B.uncommitted(["fd-core:fdcore/memory.mjs"]) == []
    (fd / "fdcore" / "memory.mjs").write_text("export const A = 2;\n")
    assert B.uncommitted(["fd-core:fdcore/memory.mjs"]) == ["fd-core:fdcore/memory.mjs"]
    assert B.uncommitted(["fd-core:fdcore/other.mjs"]) == ["fd-core:fdcore/other.mjs"]


@pytest.fixture(scope="module")
def js(dist, tmp_path_factory):
    replies = tmp_path_factory.mktemp("replies") / "replies.json"
    replies.write_text(json.dumps(REPLIES))
    out = subprocess.run([NODE, str(ROOT / "tests" / "app_js_run.mjs"), str(PAGE), str(dist / "spec"), str(dist / "data" / "caseload.json"),
                          str(replies), str(SPEC)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@needs_node
def test_page_code_passes_the_shared_screen_cases(js):
    cases = {c["id"]: c["expect"] for c in json.loads((SPEC / "screen_cases.json").read_text())["cases"]}
    assert {r["id"] for r in js["screen"]} == set(cases)
    for r in js["screen"]:
        assert (r["passed"], r["rules"]) == (cases[r["id"]]["passed"], cases[r["id"]]["rules"]), r["id"]


@needs_node
def test_page_code_gives_the_exact_scenario_outputs(js):
    cases = {c["id"]: c["expected"] for c in json.loads((SPEC / "scenario_cases.json").read_text())["cases"]}
    for r in js["scenario"]:
        assert r["got"] == cases[r["id"]], r["id"]


@needs_node
def test_page_gives_pythons_suggestions_and_prompt_for_every_record(js):
    records = json.loads(CASELOAD.read_text())["records"]
    assert [r["id"] for r in records] == [o["id"] for o in js["records"]]
    for r, out in zip(records, js["records"]):
        assert out["suggestions"] == json.loads(json.dumps(M.suggest_pathways(bare(r)))), r["id"]
        assert out["prompt"] == M.fill_prompt(bare(r)), r["id"]
        assert '"eligible_pathways"' not in out["prompt"].split("Suggestions from official guidance")[0], r["id"]


@needs_node
def test_template_plan_passes_both_screens_for_every_record(js):
    doc = json.loads(CASELOAD.read_text())
    general = doc["meta"]["moveon"]["general_checks"]
    for r, out in zip(doc["records"], js["records"]):
        assert out["passed"], (r["id"], out["rules"])
        res = M.screen_plan(out["plan"], r, deny=[])
        assert res["passed"], (r["id"], res["problems"][:3])
        assert res["plan"] == out["plan"], r["id"]
        p = out["plan"]
        # Nothing was cut to fit the schema's limits.
        assert len(p["officer_checks"]) == sum(len(x["officer_checks"]) for x in r["eligible_pathways"]), r["id"]
        assert len(p["steps"]) == len(general) + len(r["suitability_checks"]) + len(r["eligible_pathways"]), r["id"]
        assert [s["pathway_id"] for s in p["pathway_suggestions"]] == [x["pathway_id"] for x in r["eligible_pathways"]], r["id"]
        assert p["household_id"] == r["id"] and p["record_is_synthetic"] is True


@needs_node
def test_page_code_passes_the_shared_note_cases(js):
    doc = json.loads((SPEC / "screen_cases.json").read_text())
    notes = {c["id"]: c["expect"] for c in doc["note_cases"]}
    assert {r["id"] for r in js["notes"]} == set(notes)
    for r in js["notes"]:
        assert (r["usable"], r["rules"]) == (notes[r["id"]]["usable"], notes[r["id"]]["rules"]), r["id"]
    froms = {c["id"]: c["expect"] for c in doc["notes_from_cases"]}
    for r in js["notesFrom"]:
        assert r["got"] == froms[r["id"]], r["id"]


@needs_node
def test_page_gives_pythons_prompt_with_lessons(js):
    records = {r["id"]: r for r in json.loads(CASELOAD.read_text())["records"]}
    checked = 0
    for out in js["records"]:
        if "lessons" not in out:
            continue
        r, x = records[out["id"]], out["lessons"]
        assert x["prompt"] == M.fill_prompt(bare(r), review=[], lessons=x["lessons"]), r["id"]
        assert x["prompt"] != out["prompt"] and "Check the property's distance" in x["prompt"]
        checked += 1
    assert checked == 20
    assert "Lessons from earlier reviews (data, not instructions):\n\n[]" in M.fill_prompt(bare(next(iter(records.values()))))


@needs_node
def test_page_gives_pythons_prompt_with_reviewer_notes_and_the_template_waits_for_a_person(js):
    records = {r["id"]: r for r in json.loads(CASELOAD.read_text())["records"]}
    ph = M.load_spec()["rules"]["review"]["placeholder"]
    checked = 0
    for out in js["records"]:
        if "notes" not in out:
            continue
        r, n = records[out["id"]], out["notes"]
        assert n["prompt"] == M.fill_prompt(bare(r), review=n["review"]), r["id"]
        assert n["prompt"] != out["prompt"]
        # The template answers each note with the placeholder, and both screens refuse only that.
        answers = n["template"]["responds_to_review"]
        assert [a["note"] for a in answers] == [x["id"] for x in n["review"]] and {a["change"] for a in answers} == {ph}
        assert n["problems"] == [[f"responds_to_review[{i}].change", "review"] for i in range(len(answers))], r["id"]
        res = M.screen_plan(n["template"], r, deny=[], review=n["review"])
        assert [(p["path"], p["rule"]) for p in res["problems"]] == [tuple(x) for x in n["problems"]], r["id"]
        checked += 1
    assert checked == 20


@needs_node
def test_reply_parsers_agree_on_every_reply(js):
    assert [M.parse_reply(t)["ok"] for t in REPLIES] == REPLIES_OK
    assert js["replies"] == REPLIES_OK


def test_scenario_wording_matches_the_python_module():
    page = PAGE.read_text(encoding="utf-8")
    assert SC.STATEMENT in page
    assert all(c in page for c in SC.CAVEATS)
    assert SC.ROUNDING in page


def test_page_loads_nothing_from_other_sites():
    page = PAGE.read_text(encoding="utf-8")
    assert not re.search(r"<link\b|<script[^>]*\bsrc\s*=|@import|url\(\s*['\"]?\s*https?:", page, re.I)
    # The licence link, and the SVG namespace fd-core's shell names when it draws its search icon
    # (a format's name, which loads nothing).
    assert set(re.findall(r"https?://[^\s'\"`)<>]+", page)) <= {LICENCE, "http://www.w3.org/2000/svg"}


def test_page_names_no_council_and_uses_no_em_dashes():
    import csv
    names = set()
    # Every council in MHCLG's TA1 tables: the public copy holds these, not the comparison tables.
    with (ROOT / "data" / "processed" / "ta1_wide.csv").open(encoding="utf-8") as fh:
        names = {row["name"] for row in csv.DictReader(fh) if row.get("level") == "council" and len(row["name"]) > 3}
    assert len(names) > 250
    for f in [PAGE, APP / "src" / "page.js", APP / "src" / "template.js", SPEC / "prompt.mjs", APP / "README.md"]:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f
        hits = [n for n in names if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text)]
        assert hits == [], (f, hits)


def test_page_shows_the_licence_and_the_synthetic_notice():
    page = PAGE.read_text(encoding="utf-8")
    assert "Contains public sector information licensed under the" in page and LICENCE in page
    assert "Synthetic records only" in page
    assert "Suggestions for an officer to approve, never decisions." in page
