"""The language-neutral spec works unchanged in JavaScript: the ports in tamarket/spec/
(screen.mjs, scenario.mjs, prompt.mjs) pass the shared cases, reviewer notes included, and the
fd-core part of the screen gives the same findings as fd-core itself on a corpus of ASCII lines.
Needs node; skipped without it."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tamarket" / "spec"
FDCORE = ROOT.parent / "fd-core"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def corpus() -> list[str]:
    """ASCII lines from fd-core's own screen and tests (which name the words it blocks) and from
    this repository's tracked text files, plus fixtures split so this file does not trip the
    repository's screen (as fd-core's tests do for the checks that cannot be switched off)."""
    files = [FDCORE / "fdcore" / "guardrails.py", FDCORE / "tests" / "test_core.py"]
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    files += [ROOT / f for f in tracked.split() if f.endswith((".py", ".md", ".json", ".csv", ".txt", ".html", ".mjs"))]
    lines = []
    for f in files:
        if f.exists():
            lines += [l for l in f.read_text(encoding="utf-8", errors="replace").splitlines()
                      if l.strip() and l.isascii() and len(l) < 2000]
    lines += ["Refer to Placeholder Lettings " + "Ltd today.", "mail someone" + "@" + "example.org now",
              "office at " + "zz1" + " 1zz", "call 0207" + " 946 0000 or +44 20" + " 7946 0000",
              "the firm ev" + "aded checks, but this is not evidence of a breach", "value 1086532.3333333333 here"]
    return sorted(set(lines))


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_fdcore_patterns.py")], check=True,
                   capture_output=True)
    lines = corpus()
    path = tmp_path_factory.mktemp("corpus") / "corpus.json"
    path.write_text(json.dumps(lines))
    out = subprocess.run([NODE, str(SPEC / "run_cases.mjs"), str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout), lines


def test_js_screen_passes_the_shared_cases(js):
    out, _ = js
    cases = {c["id"]: c["expect"] for c in json.loads((SPEC / "screen_cases.json").read_text())["cases"]}
    assert {r["id"] for r in out["screen"]} == set(cases)
    for r in out["screen"]:
        assert (r["passed"], r["rules"]) == (cases[r["id"]]["passed"], cases[r["id"]]["rules"]), r["id"]


def test_js_note_checks_and_notes_from_decisions_pass_the_shared_cases(js):
    out, _ = js
    doc = json.loads((SPEC / "screen_cases.json").read_text())
    notes = {c["id"]: c["expect"] for c in doc["note_cases"]}
    assert {r["id"] for r in out["notes"]} == set(notes)
    for r in out["notes"]:
        assert (r["usable"], r["rules"]) == (notes[r["id"]]["usable"], notes[r["id"]]["rules"]), r["id"]
    froms = {c["id"]: c["expect"] for c in doc["notes_from_cases"]}
    assert {r["id"] for r in out["notesFrom"]} == set(froms)
    for r in out["notesFrom"]:
        assert r["got"] == froms[r["id"]], r["id"]


def test_js_scenario_gives_the_exact_outputs(js):
    out, _ = js
    cases = {c["id"]: c["expected"] for c in json.loads((SPEC / "scenario_cases.json").read_text())["cases"]}
    for r in out["scenario"]:
        assert r["got"] == cases[r["id"]], r["id"]


def test_js_fdcore_matches_fdcore_on_the_corpus(js):
    from fdcore.guardrails import scan_text
    out, lines = js
    assert len(lines) > 500
    flagged = 0
    for line, kinds in zip(lines, out["corpus"]):
        py = sorted(f.kind for f in scan_text(line, deny=[]))
        assert py == sorted(kinds), line
        flagged += bool(py)
    assert flagged > 20      # the corpus exercises every kind, not only clean lines


def test_js_clocks_pass_the_shared_cases(js):
    out, _ = js
    cases = {c["id"]: c["expect"] for c in json.loads((SPEC / "clocks.json").read_text())["cases"]}
    assert {r["id"] for r in out["clocks"]} == set(cases)
    for r in out["clocks"]:
        assert r["got"] == cases[r["id"]], r["id"]
