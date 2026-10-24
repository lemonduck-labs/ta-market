"""Private council pages (scripts/build_council_pages.py, docs/adr/0001): each page names its own
council and no other, carries no ONS code but its own, has the Open Government Licence line and
link, and is written only where git cannot commit it.

No council's name or code is written in this file: they are read at run time from the processed
tables the packs are built from. The page tests skip when data/private/packs is absent (it is
gitignored, so CI has none); the rest run everywhere.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_council_pages.py"
PACKS = ROOT / "data" / "private" / "packs"
TABLES = ROOT / "data" / "processed"
OGL_LINE = "Contains public sector information licensed under the Open Government Licence v3.0."
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
ONS_CODE = re.compile(r"(?<![A-Za-z0-9])[EWSNK]\d{8}(?![A-Za-z0-9])")

needs_packs = pytest.mark.skipif(not (PACKS.is_dir() and any(PACKS.glob("*.json"))),
                                 reason="no private packs: data/private/packs is gitignored (python scripts/build_packs.py)")


def load_script():
    spec = importlib.util.spec_from_file_location("build_council_pages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


@pytest.fixture(scope="module")
def identities() -> dict[str, set[str]]:
    """Every local authority's names and codes in the processed tables, by ONS code after the
    recodes, built here without the script's own code: TA1 councils and every RO4 authority but
    the England row."""
    from tamarket.picture import RECODES
    ta1 = pd.read_csv(TABLES / "ta1_wide.csv", usecols=["code", "name", "level"])
    ro4 = pd.read_csv(TABLES / "ro4_wide.csv", usecols=["ons_code", "la_name", "e_code", "class"])
    ids: dict[str, set[str]] = {}
    ta1 = ta1[ta1.level == "council"]
    for code, name in zip(ta1.code, ta1.name):
        ids.setdefault(RECODES.get(code, code), set()).update({code, name})
    ro4 = ro4[ro4["class"] != "Eng"]
    for code, name, ecode in zip(ro4.ons_code, ro4.la_name, ro4.e_code):
        ids.setdefault(RECODES.get(code, code), set()).update({code, name, ecode})
    out = {k: {" ".join(v.split()) for v in vs if isinstance(v, str) and len(v.strip()) > 3} for k, vs in ids.items()}
    assert len(out) > 300 and sum(map(len, out.values())) > 1000
    return out


def spans(text: str, s: str) -> list[tuple[int, int]]:
    """Where s occurs in text as a whole name or code (not inside a longer word or number)."""
    out, i = [], text.find(s)
    while i != -1:
        j = i + len(s)
        if (i == 0 or not text[i - 1].isalnum()) and (j == len(text) or not text[j].isalnum()):
            out.append((i, j))
        i = text.find(s, i + 1)
    return out


def other_councils(text: str, code: str | None, identities: dict[str, set[str]]) -> set[str]:
    """Codes of the councils other than `code` that text names or codes. A match lying inside
    one of the council's own names (another council's name within its own) does not count."""
    own = identities.get(code, set()) if code else set()
    inside = [sp for s in own for sp in spans(text, s)]
    found = set()
    for k, vs in identities.items():
        if k == code:
            continue
        for v in vs - own:
            if any(not any(a <= i and j <= b for a, b in inside) for i, j in spans(text, v)):
                found.add(k)
    return found


def readings(page: str) -> tuple[str, str]:
    """The page as its source reads and as its text reads, entities decoded, white space collapsed."""
    source = " ".join(html.unescape(page).split())
    body = re.sub(r"<style\b.*?</style\s*>|<!--.*?-->", " ", page, flags=re.S | re.I)
    text = " ".join(html.unescape(re.sub(r"<[^>]*>", " ", body)).split())
    return source, text


@pytest.fixture(scope="module")
def packs() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(PACKS.glob("*.json"))}


@pytest.fixture(scope="module")
def chosen(packs, identities) -> list[str]:
    """A handful of councils, picked from the packs at run time to cover the shapes a page takes."""
    from tamarket.picture import RECODES

    def first(test):
        return next((c for c, p in packs.items() if test(p)), None)

    def holds_another(p):
        name, code = p["council"]["name"], p["council"]["code"]
        return any(spans(name, v) for k, vs in identities.items() if k != code for v in vs if v != name)

    picks = [first(lambda p: p["comparison"]["status"] == "compared" and p["council"]["peer_group"] == "London"),
             first(lambda p: p["comparison"]["status"] == "compared" and p["council"]["peer_group"] != "London"
                   and len(p["questions"]) >= 2),
             first(lambda p: p["comparison"]["status"].startswith("provisional")),
             first(lambda p: p["comparison"]["status"] == "not compared"),
             first(lambda p: p["comparison"]["households_average"] is None),
             first(holds_another),                       # its own name holds another council's name
             first(lambda p: p["council"]["code"] in RECODES.values())]
    out = list(dict.fromkeys(c for c in picks if c))
    assert len(out) >= 5, out
    return out


@pytest.fixture(scope="module")
def written(script, chosen, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("council-pages")       # outside any git repository
    args = ["--out", str(out)] + [a for c in chosen for a in ("--only", c)]
    assert script.main(args) == 0
    return out


@needs_packs
def test_a_page_is_written_for_each_council_asked_for_and_no_other(written, chosen):
    assert sorted(p.stem for p in written.glob("*")) == sorted(chosen)


@needs_packs
def test_each_page_passes_the_scripts_own_checks(script, written, chosen, packs):
    councils = script.Councils.load()
    for code in chosen:
        page = (written / f"{code}.html").read_text(encoding="utf-8")
        assert script.check_page(page, code, packs[code]["council"]["name"], councils) == [], code


@needs_packs
def test_each_page_names_its_own_council_and_no_other(written, chosen, packs, identities):
    for code in chosen:
        source, text = readings((written / f"{code}.html").read_text(encoding="utf-8"))
        assert packs[code]["council"]["name"] in text, code
        for reading in (source, text):
            assert other_councils(reading, code, identities) == set(), code


@needs_packs
def test_no_ons_code_but_its_own(written, chosen):
    for code in chosen:
        for reading in readings((written / f"{code}.html").read_text(encoding="utf-8")):
            assert set(ONS_CODE.findall(reading)) <= {code}, code


@needs_packs
def test_licence_line_and_link(written, chosen):
    for code in chosen:
        page = (written / f"{code}.html").read_text(encoding="utf-8")
        assert OGL_LINE in readings(page)[1], code
        assert re.search(r'<a\s[^>]*href="' + re.escape(OGL_URL) + '"', page), code


@needs_packs
def test_pages_are_private_self_contained_and_dated(written, chosen, packs):
    for code in chosen:
        page = (written / f"{code}.html").read_text(encoding="utf-8")
        text = readings(page)[1]
        name = packs[code]["council"]["name"]
        assert f"Private: for {name} only" in text, code
        assert re.search(r"Built on \d{1,2} [A-Z][a-z]+ \d{4} from commit [0-9a-f]{7,}", text), code
        assert not re.search(r"<script|<link|<img|<iframe|\bsrc\s*=|url\(|@import", page, re.I), code
        assert "\u2014" not in page and "\u2013" not in page, code
        assert "prefers-color-scheme: dark" in page and "@media print" in page and 'name="viewport"' in page


@needs_packs
def test_pages_pass_the_guardrails_screen(written, chosen):
    from fdcore.guardrails import scan_text
    deny_file = ROOT / "config" / "deny_list.txt"
    deny = deny_file.read_text(encoding="utf-8").splitlines() if deny_file.exists() else []
    for code in chosen:
        found = scan_text((written / f"{code}.html").read_text(encoding="utf-8"), code, deny)
        assert found == [], (code, [(f.kind, f.text) for f in found][:5])


@needs_packs
def test_check_mode_checks_every_pack_and_writes_nothing(script, packs, tmp_path, capsys):
    assert script.main(["--check", "--out", str(tmp_path / "pages")]) == 0
    assert not (tmp_path / "pages").exists()
    assert f"checked {len(packs)} pages in memory and wrote nothing: {len(packs)} pass" in capsys.readouterr().out


@needs_packs
def test_a_page_that_fails_is_not_written(script, packs, chosen, identities, tmp_path, capsys):
    code = chosen[0]
    other = next(k for k in sorted(identities) if k != code and k in packs)
    name = packs[other]["council"]["name"]
    pack = json.loads(json.dumps(packs[code]))
    pack["caveats"].append(f"A line that names {name} and carries {other}.")
    folder = tmp_path / "packs"
    folder.mkdir()
    (folder / f"{code}.json").write_text(json.dumps(pack), encoding="utf-8")
    shutil.copyfile(PACKS / f"{chosen[1]}.json", folder / f"{chosen[1]}.json")
    out = tmp_path / "pages"
    assert script.main(["--packs", str(folder), "--out", str(out)]) == 1
    printed = capsys.readouterr().out
    assert not (out / f"{code}.html").exists()
    assert (out / f"{chosen[1]}.html").exists()          # the page that passes is still written
    assert f"{code}.html: names another council: {other}" in printed
    assert "carries an ONS code other than its own" in printed
    assert name not in printed                            # it lists codes, never a name


@needs_packs
def test_the_check_names_each_problem(script, written, chosen, packs, identities):
    code = chosen[0]
    name = packs[code]["council"]["name"]
    page = (written / f"{code}.html").read_text(encoding="utf-8")
    councils = script.Councils.load()
    other = next(k for k in sorted(identities) if k != code)

    def problems(p):
        return " | ".join(script.check_page(p, code, name, councils))

    assert "Open Government Licence line is missing" in problems(page.replace(OGL_LINE, "Contains information."))
    assert "link to the Open Government Licence is missing" in problems(page.replace(f'href="{OGL_URL}"', 'href="#"'))
    assert f"names another council: {other}" in problems(page.replace("</footer>", f"<p>{other}</p></footer>"))
    assert "does not name its own council" in problems(page.replace(html.escape(name), "the council"))
    assert "em or en dash" in problems(page.replace("</footer>", "<p>a \u2013 b</p></footer>"))
    assert "loads or runs something" in problems(page.replace("</head>", "<script></script></head>"))


def test_the_default_folder_is_gitignored(script):
    assert script.OUT == ROOT / "reports" / "private" / "councils"
    probe = script.OUT / "page.html"
    assert subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", str(probe)]).returncode == 0
    assert script.folder_problem(script.OUT) == ""


def test_it_refuses_a_folder_git_would_track(script):
    folder = ROOT / "docs" / "council-pages-test"
    assert not folder.exists()
    with pytest.raises(SystemExit) as stop:
        script.main(["--out", str(folder)])
    assert "not writing any page" in str(stop.value) and "not gitignored" in str(stop.value)
    assert not folder.exists()


def test_these_files_name_and_code_no_council(identities):
    for path in (SCRIPT, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert other_councils(text, None, identities) == set(), path.name
        assert ONS_CODE.findall(text) == [], path.name


def test_the_sources_are_the_shared_demos(script):
    demo = (ROOT / "demo" / "ta" / "index.html").read_text(encoding="utf-8")
    links = [u for s in script.SOURCES for u in re.findall(r'href="([^"]+)"', s)]
    assert len(links) == 7
    assert all(f'href="{u}"' in demo for u in links)
