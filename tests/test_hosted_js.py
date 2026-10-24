"""The hosted planner's code outside the database: the drafting function, the page's stand-in for
claude.use over Supabase, and the hosted build.

- The draft-plan function's logic (supabase/functions/draft-plan/core.mjs), with Claude and the
  database mocked: a passing draft is screened, recorded and returned with the page's SHA-256; a
  draft that fails is recorded and never returned, and a deny-list name never comes back; only a
  signed-in Contributor or above drafts, only a synthetic record, within the hourly cap, with the
  deny list loaded and the same build as the page; the key goes only to the Messages API.
- app/src/hosted.js, with a fake Supabase client, driven through the page's own store code
  (app/src/page.js): every record path maps to its table; nothing the page sends as an author,
  actor or time reaches the database; reads come back in the page's shapes and time format;
  errors come back as the codes the page knows; drafting goes to the function.
- scripts/build_app.py --target hosted: the site holds the page unchanged, loads only the pinned,
  hash-checked Supabase client, has a Content-Security-Policy that allows exactly its own inline
  code, matches its manifest, takes only a publishable key, and comes with a function bundle of
  the same build, whose prompt for every record is the page's.
- With Deno installed, index.ts runs end to end against a faked project and a faked Claude.
- With Playwright, its Chromium and a copy of the pinned Supabase client (TA_SUPABASE_UMD), the
  hosted site runs in a real browser under its own Content-Security-Policy against a faked project:
  two people sign in with an emailed code and take a plan through drafting, Claude, submission and
  approval (tests/hosted_browser_check.mjs).

The JavaScript tests need node and are skipped without it.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tamarket import moveon as M

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
DENO = os.environ.get("TA_DENO") or shutil.which("deno")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
PAGE = ROOT / "app" / "index.html"
SPEC = ROOT / "tamarket" / "spec"
URL = "https://abcdefghijklmnopqrst.supabase.co"
KEY = "sb_publishable_" + "k" * 32

_spec = importlib.util.spec_from_file_location("build_app", ROOT / "scripts" / "build_app.py")
build_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_app)

SUITE = [
    "function: a passing draft is screened, recorded and returned",
    "function: a draft that states a decision is refused and never returned",
    "function: a deny-list name is caught, from the secret and from the table, and never echoed",
    "function: a reply that is not one JSON object, is cut off or is declined fails",
    "function: the caller must be a signed-in Contributor or above",
    "function: only a synthetic record from its own caseload is drafted",
    "function: it stops before calling Claude without a key, over the hourly cap, without the deny list or on a different build",
    "function: Claude's errors become retry or set-up answers, and an unrecorded draft is not returned",
    "function: CORS and methods",
    "function: its canon is the page's, and only safe details are returned",
    "function: reviewer notes come from the database, reach Claude apart from the record, and the draft must answer them",
    "function: an approval that counts starts the notes again, as the page's approval check decides",
    "function: a note the deny list would hold back is not sent, and notes that cannot be read stop the draft",
    "hosted: every page path maps to its table, and others are refused",
    "hosted: the user capability gives each role what the page expects",
    "hosted: nobody outside the members table gets a store",
    "hosted: the page's own store code saves a version, moves the pointer and records an export through the tables",
    "hosted: decisions, checks, progress, the setting and private drafts go to their tables with no who or when",
    "hosted: follow-ups go to public.tasks with no who or when, and read back in the page's shape",
    "hosted: notices and reviews go to their tables with no who or when, a notice recorded again updates only its value columns, and a handover is a page event",
    "hosted: a monitoring decision goes to public.monitor_decisions with no who or when",
    "hosted: the audit log is read per person, newest first, in the page's words",
    "hosted: long tables are read past the 1,000-row page",
    "hosted: errors reach the page as the codes it knows",
    "hosted: one live channel, and a change refreshes only the watches it touches",
    "hosted: drafting goes to the function with the record id and the prompt's SHA-256",
    "hosted: downloads hand the page's file to the browser",
    "hosted: the build's placeholders are not taken for a project",
]


@pytest.fixture(scope="module")
def patterns(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("fdcore") / "fdcore_patterns.json"
    p.write_text(json.dumps(M.fdcore_patterns()), encoding="utf-8")
    return p


@pytest.fixture(scope="module")
def suite(patterns):
    out = subprocess.run([NODE, str(ROOT / "tests" / "hosted_js_run.mjs"), "suite", str(ROOT), str(patterns)],
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return {r["name"]: r for r in json.loads(out.stdout)["results"]}


@needs_node
@pytest.mark.parametrize("name", SUITE)
def test_node_suite(suite, name):
    assert name in suite, f"the check did not run: {name}"
    assert suite[name]["ok"], suite[name].get("error")


@needs_node
def test_the_suite_has_no_check_this_file_does_not_list(suite):
    assert sorted(suite) == sorted(SUITE)


# ============================================================== the hosted build

@pytest.fixture(scope="module")
def hosted(tmp_path_factory):
    base = tmp_path_factory.mktemp("hosted")
    site, bundle = base / "site", base / "fn" / "_bundle"
    assert build_app.main(["--target", "hosted", "--supabase-url", URL + "/", "--publishable-key", KEY, "--out", str(site), "--bundle-out", str(bundle)]) == 0
    return site, bundle


def blocks(html: str, name: str) -> str:
    begin, end = build_app.BLOCKS[name]
    return html[html.index(begin): html.index(end)]


def test_the_hosted_site_holds_the_page_unchanged(hosted):
    site, _ = hosted
    html = (site / "index.html").read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>\n<html lang=\"en-GB\">")
    for name in ["MODULES", "PAGE"]:
        assert blocks(html, name) == blocks(page, name), name
    assert (ROOT / "app" / "src" / "hosted.js").read_text(encoding="utf-8").rstrip() in html
    config = json.loads(re.search(r"window\.TA_HOSTED_CONFIG = (\{.*?\});", html).group(1))
    assert config == {"url": URL, "anonKey": KEY}
    # One script from another site: the Supabase client at its exact version, checked by its hash.
    srcs = re.findall(r"<script\b[^>]*\bsrc=\"([^\"]+)\"[^>]*>", html)
    assert srcs == [build_app.SUPABASE_JS["url"]]
    assert re.fullmatch(r"https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@\d+\.\d+\.\d+/dist/umd/supabase\.js", srcs[0])
    assert f'integrity="{build_app.SUPABASE_JS["integrity"]}" crossorigin="anonymous"' in html
    assert re.fullmatch(r"sha384-[A-Za-z0-9+/]{64}", build_app.SUPABASE_JS["integrity"])
    assert not re.search(r"<link\b|@import|url\(\s*['\"]?\s*https?:", html, re.I)
    # In order: the client, the settings, the stand-in, then the page's own code.
    order = [html.index(srcs[0]), html.index("window.TA_HOSTED_CONFIG"), html.index("/* app/src/hosted.js */"),
             html.index(build_app.BLOCKS["MODULES"][0]), html.index(build_app.BLOCKS["PAGE"][0])]
    assert order == sorted(order)
    assert html.count("<title>") == 1 and html.index("<title>") < html.index("</head>")


def test_the_hosted_site_matches_its_manifest(hosted):
    site, _ = hosted
    m = json.loads((site / "data" / "manifest.json").read_text())
    assert (m["target"], m["configured"], m["supabase_url"], m["supabase_js"]) == ("hosted", True, URL, build_app.SUPABASE_JS)
    for path, sha in m["files"].items():
        assert hashlib.sha256((site / path).read_bytes()).hexdigest() == sha, path
    assert m["hosted_page_sha256"] == hashlib.sha256((site / "index.html").read_bytes()).hexdigest()
    assert (site / "data" / "caseload.json").read_bytes() == (ROOT / "demo" / "ta" / "synthetic_caseload.json").read_bytes()
    for name in build_app.SPEC_FILES:
        assert (site / "spec" / name).read_bytes() == (SPEC / name).read_bytes(), name
    loads = re.search(r"const FILES = \[([^\]]*)\]", (ROOT / "app" / "src" / "page.js").read_text()).group(1)
    assert sorted(re.findall(r"'([^']+)'", loads)) == sorted(m["files"])
    assert (site / "robots.txt").read_text() == "User-agent: *\nDisallow: /\n"


def test_the_content_security_policy_allows_exactly_the_pages_own_code(hosted):
    site, _ = hosted
    html = (site / "index.html").read_text(encoding="utf-8")
    headers = (site / "_headers").read_text(encoding="utf-8")
    csp = re.search(r"Content-Security-Policy: (.*)", headers).group(1)
    d = {part.split()[0]: part.split()[1:] for part in (p.strip() for p in csp.split(";")) if part}
    h = lambda t: "'sha256-" + base64.b64encode(hashlib.sha256(t.encode("utf-8")).digest()).decode() + "'"  # noqa: E731
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    styles = re.findall(r"<style>(.*?)</style>", html, re.S)
    assert len(scripts) == 4 and len(styles) == 2
    assert d["script-src"] == [h(t) for t in scripts] + [build_app.SUPABASE_JS["url"]]
    # The one style element fd-core's shell adds when it mounts, by the hash of its exact text.
    shell = build_app.shell_css(html)
    assert shell.lstrip().startswith(".fs {") and "fd-shell-css" in html
    assert d["style-src"] == [h(t) for t in styles] + [h(shell)]
    host = URL.split("://")[1]
    assert d["connect-src"] == ["'self'", f"https://{host}", f"wss://{host}"]
    assert d["default-src"] == ["'none'"] and d["frame-ancestors"] == ["'none'"] and d["base-uri"] == ["'none'"]
    assert "unsafe" not in csp
    assert "X-Content-Type-Options: nosniff" in headers and "Referrer-Policy: no-referrer" in headers


def test_without_settings_the_build_writes_placeholders(tmp_path):
    site = tmp_path / "site"
    assert build_app.main(["--target", "hosted", "--supabase-url", "", "--publishable-key", "", "--out", str(site), "--bundle-out", str(tmp_path / "b")]) == 0
    html = (site / "index.html").read_text(encoding="utf-8")
    config = json.loads(re.search(r"window\.TA_HOSTED_CONFIG = (\{.*?\});", html).group(1))
    assert config == {"url": build_app.URL_PLACEHOLDER, "anonKey": build_app.KEY_PLACEHOLDER}
    assert json.loads((site / "data" / "manifest.json").read_text())["configured"] is False


def _jwt(payload: dict) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{seg({'alg': 'HS256', 'typ': 'JWT'})}.{seg(payload)}.{'s' * 43}"


def test_the_build_takes_only_a_publishable_key_and_an_https_project_url(tmp_path):
    bad_keys = ["sb_secret_" + "k" * 32, _jwt({"role": "service_role", "iss": "supabase"}), _jwt({"role": "authenticated"}), "not-a-key"]
    for i, key in enumerate(bad_keys):
        with pytest.raises(SystemExit) as e:
            build_app.main(["--target", "hosted", "--supabase-url", URL, "--publishable-key", key, "--out", str(tmp_path / f"s{i}"), "--bundle-out", str(tmp_path / f"b{i}")])
        assert "publishable" in str(e.value), key
        assert not (tmp_path / f"s{i}").exists()
    for i, url in enumerate(["http://abcdefghijklmnopqrst.supabase.co", URL + "/rest/v1", "abcdefghijklmnopqrst.supabase.co"]):
        with pytest.raises(SystemExit, match="https URL"):
            build_app.main(["--target", "hosted", "--supabase-url", url, "--publishable-key", KEY, "--out", str(tmp_path / f"u{i}"), "--bundle-out", str(tmp_path / f"v{i}")])
    assert build_app.check_public_key(_jwt({"role": "anon", "iss": "supabase"})).count(".") == 2
    assert build_app.check_public_key(KEY) == KEY


def test_the_build_never_clears_a_folder_it_did_not_write(tmp_path):
    mine = tmp_path / "mine"
    mine.mkdir()
    (mine / "notes.txt").write_text("keep me")
    with pytest.raises(SystemExit, match="left alone"):
        build_app.main(["--target", "hosted", "--out", str(mine), "--bundle-out", str(tmp_path / "b")])
    assert (mine / "notes.txt").read_text() == "keep me"


def _bundle_data(bundle: Path) -> dict:
    text = (bundle / "data.mjs").read_text(encoding="utf-8")
    return json.loads(text[text.index("export const DATA = ") + len("export const DATA = "): text.rstrip().rindex(";")])


@needs_node
def test_the_function_bundle_is_the_same_build_as_the_site(hosted, patterns):
    site, bundle = hosted
    data = _bundle_data(bundle)
    assert data["caseload"] == json.loads((ROOT / "demo" / "ta" / "synthetic_caseload.json").read_text())
    assert data["prompt"] == (SPEC / "moveon_prompt.md").read_text(encoding="utf-8")
    assert data["spec"]["rules"] == json.loads((SPEC / "screen_rules.json").read_text())
    assert data["spec"]["schema"] == json.loads((SPEC / "moveon.schema.json").read_text())
    assert data["spec"]["pathways"] == json.loads((SPEC / "pathways.json").read_text())
    assert data["spec"]["fdcore"] == json.loads(json.dumps(M.fdcore_patterns()))
    m = json.loads((site / "data" / "manifest.json").read_text())
    assert data["manifest"]["source_commit"] == m["source_commit"] and data["manifest"]["files"] == m["files"]
    for name in ["prompt.mjs", "screen.mjs"]:
        assert (bundle / name).read_bytes() == (SPEC / name).read_bytes(), name
    out = subprocess.run([NODE, str(ROOT / "tests" / "hosted_js_run.mjs"), "bundle", str(ROOT), str(patterns), str(site), str(bundle)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == {"records": 200, "same": 200, "fn_records": 200}


def test_the_hosted_outputs_and_local_secrets_stay_out_of_git():
    for p in ["app/dist-hosted/index.html", "app/dist-hosted/_headers", "supabase/functions/draft-plan/_bundle/data.mjs",
              "supabase/.temp/project-ref", "supabase/functions/.env", "supabase/.env"]:
        assert subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", p]).returncode == 0, p
    for p in ["supabase/functions/draft-plan/index.ts", "supabase/functions/draft-plan/core.mjs", "app/src/hosted.js", "hosted/README.md"]:
        assert subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", p]).returncode == 1, p


def test_the_hosted_code_names_no_council_and_uses_no_em_dashes():
    import csv
    names = set()
    # Every council in MHCLG's TA1 tables: the public copy holds these, not the comparison tables.
    with (ROOT / "data" / "processed" / "ta1_wide.csv").open(encoding="utf-8") as fh:
        names = {row["name"] for row in csv.DictReader(fh) if row.get("level") == "council" and len(row["name"]) > 3}
    assert len(names) > 250
    files = [ROOT / "app" / "src" / "hosted.js", ROOT / "hosted" / "README.md", ROOT / "tests" / "hosted_supabase_stub.sql",
             *sorted((ROOT / "supabase").rglob("*.sql")), *[p for p in sorted((ROOT / "supabase" / "functions").rglob("*")) if p.is_file() and "_bundle" not in p.parts]]
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f
        hits = [n for n in names if re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", text)]
        assert hits == [], (f, hits)


# ============================================================== index.ts under Deno

@pytest.mark.skipif(DENO is None or NODE is None, reason="Deno (and node) are not installed")
def test_the_function_runs_under_deno_against_a_faked_project(hosted, patterns, tmp_path):
    _, bundle = hosted
    fn = tmp_path / "draft-plan"
    fn.mkdir()
    for name in ["index.ts", "core.mjs"]:
        shutil.copyfile(ROOT / "supabase" / "functions" / "draft-plan" / name, fn / name)
    shutil.copytree(bundle, fn / "_bundle")
    # Deno 2's run does not type-check, so the function is checked first (from e2ece8d until this
    # check was added, index.ts failed it on the type of the decisions it passes to core.mjs).
    check = subprocess.run([DENO, "check", "--no-lock", str(fn / "index.ts")], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, DENO_NO_UPDATE_CHECK="1"))
    assert check.returncode == 0, check.stderr[-3000:]
    canon = subprocess.run([NODE, str(ROOT / "tests" / "hosted_js_run.mjs"), "canon", str(ROOT), str(patterns)], capture_output=True, text=True, check=True)
    reply = tmp_path / "reply.txt"
    plan = json.loads(canon.stdout)[0]["plan"]
    # The fake project holds one returned note for SYN-0001, so the reply answers it.
    plan["responds_to_review"] = [{"note": "review-1", "change": "The risks now include a move out of the district.", "confidence": "Likely"}]
    reply.write_text(json.dumps(plan), encoding="utf-8")
    r = subprocess.run([DENO, "run", "--no-lock", "--allow-read", "--allow-env", "--allow-net=127.0.0.1", str(ROOT / "tests" / "hosted_deno_smoke.ts"), str(reply), str(fn)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads([line for line in r.stdout.splitlines() if line.startswith("{")][-1])
    assert out["ok"]["status"] == 200 and out["ok"]["body"]["passed"] is True and out["ok"]["body"]["plan"]["household_id"] == "SYN-0001"
    assert out["stale"] == {"status": 401, "body": {"error": "not_signed_in"}}
    assert [c["key"] for c in out["sentToClaude"]] == ["test-key-not-real"]
    assert out["sentToClaude"][0]["version"] == "2023-06-01"
    row = out["recorded"][0]
    assert (row["household_id"], row["passed"], row["rules"]) == ("SYN-0001", True, [])
    assert any(s.startswith("POST api.anthropic.com/v1/messages") for s in out["seen"])
    assert any(s.startswith("POST project.invalid/rest/v1/drafts") for s in out["seen"])
    # The session goes only to Auth's user endpoint; the REST calls carry the secret key on the
    # apikey header only, as Supabase asks for its new secret keys.
    for k in out["keys"]:
        want = ("secret", "user") if k["path"] == "/auth/v1/user" else ("secret", "none")
        assert (k["apikey"], k["authorization"]) == want, k
    assert {k["path"] for k in out["keys"]} == {"/auth/v1/user", "/rest/v1/members", "/rest/v1/drafts", "/rest/v1/deny_terms",
                                                "/rest/v1/decisions", "/rest/v1/config"}
    # The reviewer notes are read from the household's decisions, each with the version it names.
    q = next(s for s in out["seen"] if s.startswith("GET project.invalid/rest/v1/decisions"))
    assert "household_id=eq.SYN-0001" in q and "version%3Aversions%28author%2Csha256%2Chousehold_id%29" in q
    assert out["sentToClaude"][0]["notes"] == [{"id": "review-1", "kind": "returned", "text": "Add the risks of a move out of the district."}]


# ============================================================== the site in a real browser

def _playwright() -> str | None:
    cand = os.environ.get("TA_PLAYWRIGHT")
    if not cand and shutil.which("npm"):
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
        cand = str(Path(root) / "playwright" / "index.mjs") if root else None
    return cand if cand and Path(cand).exists() else None


def _umd_matches(path: str | None) -> bool:
    if not path or not Path(path).exists():
        return False
    digest = base64.b64encode(hashlib.sha384(Path(path).read_bytes()).digest()).decode()
    return "sha384-" + digest == build_app.SUPABASE_JS["integrity"]


@pytest.mark.skipif(NODE is None or _playwright() is None or not _umd_matches(os.environ.get("TA_SUPABASE_UMD")),
                    reason="needs node, Playwright with its Chromium, and TA_SUPABASE_UMD set to the pinned dist/umd/supabase.js")
def test_the_hosted_site_works_in_a_real_browser(hosted, patterns, tmp_path):
    site, _ = hosted
    canon = subprocess.run([NODE, str(ROOT / "tests" / "hosted_js_run.mjs"), "canon", str(ROOT), str(patterns)], capture_output=True, text=True, check=True)
    replies = tmp_path / "replies.json"
    replies.write_text(json.dumps({r["id"]: r["plan"] for r in json.loads(canon.stdout) if r["id"].startswith("SYN-")}), encoding="utf-8")
    r = subprocess.run([NODE, str(ROOT / "tests" / "hosted_browser_check.mjs"), _playwright(), str(site), os.environ["TA_SUPABASE_UMD"], str(replies)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout)
    if any("Executable doesn't exist" in e or "browserType.launch" in e for e in out["errors"]):
        pytest.skip("Playwright's Chromium is not installed")
    assert out["errors"] == [] and out["csp"] == []
    bad = [s for s in out["steps"] if not s["ok"]]
    assert bad == [], bad
    assert len(out["steps"]) == 17
