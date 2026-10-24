"""Build the Move forward planner page and its publish folder.

1. Writes the brand (brand/brand.css with its fonts as data: URIs, by fd-core's fdcore.brand) into
   app/index.html and demo/ta/index.html, then copies the spec ports and the page script into
   app/index.html, between its markers:
   tamarket/spec/screen.mjs, scenario.mjs and prompt.mjs become window.TaScreen, TaScenario and
   TaPrompt (their "export" keywords dropped, each wrapped in a function), then
   app/src/template.js and app/src/page.js go in as they are. app/index.html is tracked, so the
   page in git is the page that is published.
2. Writes app/dist/ (gitignored), the folder that is published as the artifact and later
   deployed to Netlify as it is:
   - index.html, the built page;
   - data/caseload.json, demo/ta/synthetic_caseload.json unchanged (synthetic records only);
   - data/monitor.json, the monitoring items (monitor/items.jsonl, a list), and
     spec/monitor_sources.json, the register's names, terms and standing grades (an object with a
     "sources" list), by scripts/monitor.py: items wait for an officer to accept or reject them;
   - spec/: screen_rules.json, moveon.schema.json, pathways.json, moveon_prompt.md and
     scenario_cases.json unchanged, and fdcore_patterns.json generated from fd-core (it lists
     the words the screen blocks, so it stays out of git, as tamarket/spec's copy does);
   - data/manifest.json: the commit the build came from, whether the tree had uncommitted
     changes (fd-core's files are checked in fd-core's own repository, whose commit it also
     names), the spec version and the SHA-256 of every file the page loads, which the page
     checks when it loads them.

3. With --target hosted, writes app/dist-hosted/ (gitignored) instead, the folder deployed to
   Netlify (hosted/README.md): the same data and spec files and manifest, and a full HTML document
   that loads the Supabase client (supabase-js, its UMD build from jsDelivr at a pinned version,
   checked by its SHA-384), the project's URL and publishable key, app/src/hosted.js (a stand-in
   for claude.use over Supabase), then the page unchanged; a Netlify _headers file whose
   Content-Security-Policy allows only those scripts and the project's own API. It also writes the
   drafting function's bundle, supabase/functions/draft-plan/_bundle/ (gitignored): the caseload,
   prompt, screen rules and fd-core patterns of the same build, and copies of prompt.mjs and
   screen.mjs. The URL and the key come from --supabase-url and --publishable-key (or the
   TA_SUPABASE_URL and TA_SUPABASE_PUBLISHABLE_KEY environment variables); without them the build
   writes placeholders and the page says it has no project settings. Only a publishable (anon)
   key is taken: a secret or service-role key is refused.

Usage:  python scripts/build_app.py            build both
        python scripts/build_app.py --check    exit 1 if app/index.html is out of date
        python scripts/build_app.py --clean    refuse to build from a tree with uncommitted changes
        python scripts/build_app.py --target hosted [--supabase-url URL --publishable-key KEY]

Synthetic records only. Suggestions for an officer to approve, never decisions.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tamarket import moveon as M  # noqa: E402

APP = ROOT / "app"
PAGE = APP / "index.html"
DIST = APP / "dist"
SPEC = ROOT / "tamarket" / "spec"
# fd-core's memory core (its screens) and its shell (the navigation both tools share) come from
# beside this repo, or from FD_CORE; their SHA-256 goes in the page, and the manifest gives
# fd-core's commit.
FDCORE = Path(os.environ.get("FD_CORE") or ROOT.parent / "fd-core")
MODULES = [("fd-core:fdcore/memory.mjs", "FdMemory"), ("fd-core:fdcore/shell.mjs", "FdShell"), ("tamarket/spec/screen.mjs", "TaScreen"), ("tamarket/spec/scenario.mjs", "TaScenario"), ("tamarket/spec/clocks.mjs", "TaClocks"),
           ("tamarket/spec/prompt.mjs", "TaPrompt"), ("app/src/template.js", None)]
SCRIPT = "app/src/page.js"
# The brand (brand/brand.css, its fonts and mark) goes into app/index.html and the market picture
# (demo/ta/index.html) between /* BEGIN brand */ and /* END brand */, by fd-core's fdcore.brand,
# with the fonts as data: URIs so neither page loads anything from elsewhere.
BRAND = ROOT / "brand"
DEMO_PAGE = ROOT / "demo" / "ta" / "index.html"
BRAND_INPUTS = ["brand/brand.css", "brand/mark.svg", *sorted(f"brand/fonts/{f.name}" for f in (ROOT / "brand" / "fonts").glob("*.woff2"))]
BLOCKS = {
    "MODULES": ("/* BEGIN MODULES (written by scripts/build_app.py from the files named below; edit those) */",
                "/* END MODULES */"),
    "PAGE": ("/* BEGIN PAGE (written by scripts/build_app.py from app/src/page.js; edit that) */", "/* END PAGE */"),
}
SPEC_FILES = ["screen_rules.json", "moveon.schema.json", "pathways.json", "moveon_prompt.md", "scenario_cases.json", "references.json", "clocks.json"]
# Everything the published folder is built from. The manifest names the commit only as the source
# when each of these is in that commit as it is.
INPUTS = ["app/index.html", SCRIPT, *[p for p, _ in MODULES], *BRAND_INPUTS, "demo/ta/synthetic_caseload.json",
          *[f"tamarket/spec/{n}" for n in SPEC_FILES], "tamarket/moveon.py", "tamarket/clocks.py", "scripts/build_app.py",
          "monitor/items.jsonl", "monitor/sources.json", "scripts/monitor.py"]
HOSTED = APP / "dist-hosted"
BUNDLE = ROOT / "supabase" / "functions" / "draft-plan" / "_bundle"
HOSTED_JS = "app/src/hosted.js"
HOSTED_INPUTS = [*INPUTS, HOSTED_JS, "supabase/functions/draft-plan/core.mjs", "supabase/functions/draft-plan/index.ts"]
# The Supabase client: its UMD build at an exact version, with the SHA-384 of that file as npm
# publishes it (dist/umd/supabase.js in the package), which jsDelivr serves unchanged.
SUPABASE_JS_VERSION = "2.117.2"
SUPABASE_JS = {
    "version": SUPABASE_JS_VERSION,
    "url": f"https://cdn.jsdelivr.net/npm/@supabase/supabase-js@{SUPABASE_JS_VERSION}/dist/umd/supabase.js",
    "integrity": "sha384-Rj26LVGvoeRVR6+mwQmFfcR3QOBEwT+ZmuCWpuiqeTzJpCs0ER4ITAWGb4Hiy3Ok",
}
URL_PLACEHOLDER = "https://YOUR-PROJECT-REF.supabase.co"
KEY_PLACEHOLDER = "YOUR-PUBLISHABLE-KEY"
HOSTED_CSS = """/* The sign-in bar of the hosted planner (app/src/hosted.js). */
.hs-bar { background: var(--panel); border-bottom: 1px solid var(--line); font-size: 0.8125rem; color: var(--fg-2); }
.hs-bar [hidden] { display: none !important; }
.hs-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding-block: 8px; }
.hs-form { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.hs-bar input { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line-strong); border-radius: var(--r-sm); padding: 5px 8px; width: 16rem; max-width: 100%; min-width: 0; }
.hs-notice { padding-block: 0 8px; }
.hs-notice-in { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
"""
EXPORTED = re.compile(r"^export (?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", re.M)
EXPORT_KEYWORD = re.compile(r"^export (?=(?:async\s+)?(?:function\*?|const|let|class)\s)", re.M)


def as_global(src: str, name: str, path: str) -> str:
    """An ES module with only `export function` / `export const` declarations, as a function
    that returns its exports, assigned to window[name]."""
    if re.search(r"^\s*import[\s{*]", src, re.M) or re.search(r"^export\s+(?:default|\{|\*)", src, re.M):
        raise SystemExit(f"{path}: only 'export function' and 'export const' declarations can be inlined")
    names = EXPORTED.findall(src)
    body = EXPORT_KEYWORD.sub("", src).rstrip("\n")
    return f"/* {path} as window.{name} */\nwindow.{name} = (function () {{\n'use strict';\n{body}\nreturn {{ {', '.join(names)} }};\n}})();\n"


def module_path(path: str) -> Path:
    if path.startswith("fd-core:"):
        p = FDCORE / path.split(":", 1)[1]
        if not p.exists():
            raise SystemExit(f"{p} not found: put fd-core beside this repo or set FD_CORE")
        return p
    return ROOT / path


def modules_text() -> str:
    parts = []
    for path, name in MODULES:
        src = module_path(path).read_text(encoding="utf-8")
        if path.startswith("fd-core:"):
            path = f"{path} (SHA-256 {hashlib.sha256(src.encode('utf-8')).hexdigest()})"
        parts.append(as_global(src, name, path) if name else f"/* {path} */\n{src.rstrip()}\n")
    return "\n".join(parts)


def fdbrand():
    """fd-core's brand module, from beside this repo or FD_CORE."""
    if str(FDCORE) not in sys.path:
        sys.path.insert(0, str(FDCORE))
    from fdcore import brand
    return brand


def branded(page: str, name: str) -> str:
    return fdbrand().apply(page, BRAND, name)


def built_page(page: str) -> str:
    out = branded(page, "app/index.html")
    for key, text in (("MODULES", modules_text()), ("PAGE", (ROOT / SCRIPT).read_text(encoding="utf-8").rstrip() + "\n")):
        begin, end = BLOCKS[key]
        i, j = out.find(begin), out.find(end)
        if i < 0 or j < i:
            raise SystemExit(f"app/index.html: the {key} markers are missing")
        if "</script" in text.lower():
            raise SystemExit(f"{key}: the code holds a closing script tag")
        out = out[: i + len(begin)] + "\n" + text + out[j:]
    return out


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def uncommitted(paths: list[str]) -> list[str]:
    """Inputs that are not in HEAD as they are on disk (untracked, or changed since). An input from
    fd-core ("fd-core:<path>") is checked in fd-core's own repository, whose commit the manifest
    names as fdcore_commit."""
    out = []
    for p in paths:
        repo, rel = (FDCORE, p.split(":", 1)[1]) if p.startswith("fd-core:") else (ROOT, p)
        tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", rel], capture_output=True).returncode == 0
        same = tracked and subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", rel], capture_output=True).returncode == 0
        if not same:
            out.append(p)
    return out


def fdcore_commit() -> str | None:
    r = subprocess.run(["git", "-C", str(FDCORE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clear(dest: Path, marker: str) -> None:
    """Empty a folder this script wrote before (it holds `marker`), and never any other folder."""
    if dest.exists():
        if any(dest.iterdir()) and not (dest / marker).exists():
            raise SystemExit(f"{dest} is not empty and was not written by this script, so it is left alone")
        shutil.rmtree(dest)


def build_dist(dest: Path = DIST, inputs: list[str] = INPUTS) -> dict:
    """The publish folder's data and spec files and its manifest, with the built page as index.html."""
    clear(dest, "data/manifest.json")
    (dest / "data").mkdir(parents=True)
    (dest / "spec").mkdir()
    shutil.copyfile(PAGE, dest / "index.html")
    shutil.copyfile(ROOT / "demo" / "ta" / "synthetic_caseload.json", dest / "data" / "caseload.json")
    from scripts import monitor as monitoring
    (dest / "data" / "monitor.json").write_text(json.dumps(monitoring.published_items(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for name in SPEC_FILES:
        shutil.copyfile(SPEC / name, dest / "spec" / name)
    (dest / "spec" / "fdcore_patterns.json").write_text(json.dumps(M.fdcore_patterns(), indent=1) + "\n", encoding="utf-8")
    (dest / "spec" / "monitor_sources.json").write_text(json.dumps(monitoring.published_sources(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    from fdcore import memory as fdmemory
    (dest / "spec" / "memory_rules.json").write_text(json.dumps(fdmemory.rules_json(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    caseload = json.loads((dest / "data" / "caseload.json").read_text(encoding="utf-8"))
    if not all(r.get("synthetic") is True and str(r.get("id", "")).startswith("SYN-") for r in caseload["records"]):
        raise SystemExit("the caseload holds a record that is not synthetic")
    files = {}
    for p in sorted(dest.rglob("*")):
        if p.is_file() and p.name != "index.html":
            files[p.relative_to(dest).as_posix()] = sha256(p)
    unc = uncommitted(inputs)
    manifest = {
        "built_by": "scripts/build_app.py",
        "source_commit": git("rev-parse", "--short", "HEAD"),
        "source_dirty": bool(unc),
        "uncommitted_inputs": unc,
        "fdcore_commit": fdcore_commit(),
        "spec_version": M.load_spec()["rules"]["spec_version"],
        "caseload": {"records": len(caseload["records"]), "seed": caseload["meta"]["seed"], "synthetic": True},
        "page_sha256": sha256(PAGE),
        "files": files,
    }
    (dest / "data" / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- the hosted build

def check_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not re.fullmatch(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)+", url):
        raise SystemExit(f"--supabase-url must be the project's https URL with no path, for example {URL_PLACEHOLDER}")
    return url


def check_public_key(key: str) -> str:
    """Only a key that is safe in a browser: a publishable key, or a legacy anon key. A secret or
    service-role key would give anyone who opens the page the whole database."""
    key = key.strip()
    if key.startswith("sb_secret_"):
        raise SystemExit("that is a secret key: the page takes only the publishable key. Revoke the secret key if it was shared.")
    if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{8,}", key):
        return key
    parts = key.split(".")
    if len(parts) == 3:
        try:
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        except ValueError:
            claims = {}
        if claims.get("role") == "anon":
            return key
        raise SystemExit(f"that key's role is {claims.get('role')!r}: the page takes only the publishable (anon) key")
    raise SystemExit("--publishable-key must be the project's publishable key (sb_publishable_...) or its legacy anon key")


def script_hash(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def inline_blocks(html: str, tag: str) -> list[str]:
    """The text of every inline <script> (no src) or <style> block, exactly as a browser hashes it."""
    pat = r"<script>(.*?)</script>" if tag == "script" else r"<style>(.*?)</style>"
    return re.findall(pat, html, re.S)


def hosted_page(page: str, url: str, key: str) -> str:
    """The built page as a full document, with the Supabase client, the project settings and
    app/src/hosted.js ahead of the page's own scripts. The page's code is not changed."""
    end = page.find("</style>")
    if not page.startswith("<title>") or end < 0:
        raise SystemExit("app/index.html: expected <title>, <meta> and <style>, then the page's body")
    cut = end + len("</style>")
    head, body = page[:cut], page[cut:].lstrip("\n")
    at = body.find("<script>\n" + BLOCKS["MODULES"][0])
    if at < 0:
        raise SystemExit("app/index.html: the MODULES script is missing")
    config = json.dumps({"url": url, "anonKey": key}).replace("</", "<\\/")
    hosted_js = (ROOT / HOSTED_JS).read_text(encoding="utf-8").rstrip() + "\n"
    if "</script" in hosted_js.lower():
        raise SystemExit(f"{HOSTED_JS}: the code holds a closing script tag")
    s = SUPABASE_JS
    inject = (f'<script src="{s["url"]}" integrity="{s["integrity"]}" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
              f"<script>\nwindow.TA_HOSTED_CONFIG = {config};\n</script>\n"
              f"<script>\n/* {HOSTED_JS} */\n{hosted_js}</script>\n")
    return ("<!doctype html>\n<html lang=\"en-GB\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"referrer\" content=\"no-referrer\">\n<meta name=\"robots\" content=\"noindex, nofollow\">\n"
            f"{head}\n<style>\n{HOSTED_CSS}</style>\n</head>\n<body>\n{body[:at]}{inject}{body[at:]}</body>\n</html>\n")


def shell_css(page: str) -> str:
    """The text of the one <style> element fd-core's shell adds when it mounts (fdcore/shell.mjs,
    SHELL_CSS), as the page inlines it, so the policy can allow it by its SHA-256."""
    m = re.search(r"^const SHELL_CSS = `(.*?)`;$", page, re.M | re.S)
    if not m or "\\" in m.group(1) or "${" in m.group(1):
        raise SystemExit("app/index.html: fd-core's shell styles (SHELL_CSS) are missing or not plain text")
    return m.group(1)


def netlify_headers(html: str, url: str) -> str:
    host = url.split("://", 1)[1]
    scripts = " ".join(script_hash(t) for t in inline_blocks(html, "script"))
    styles = " ".join(script_hash(t) for t in [*inline_blocks(html, "style"), shell_css(html)])
    csp = (f"default-src 'none'; script-src {scripts} {SUPABASE_JS['url']}; style-src {styles}; "
           f"connect-src 'self' https://{host} wss://{host}; img-src 'self' data:; font-src data:; base-uri 'none'; "
           "form-action 'none'; frame-ancestors 'none'; object-src 'none'")
    return ("# Written by scripts/build_app.py --target hosted. The page's inline scripts and styles, and the\n"
            "# style element fd-core's shell adds, are allowed by their SHA-256, the Supabase client by its exact\n"
            "# URL (and its SHA-384 in the page).\n"
            "/*\n"
            f"  Content-Security-Policy: {csp}\n"
            "  X-Content-Type-Options: nosniff\n"
            "  Referrer-Policy: no-referrer\n"
            "  X-Frame-Options: DENY\n"
            "  Cross-Origin-Opener-Policy: same-origin\n"
            "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()\n"
            "/data/*\n  Cache-Control: no-cache\n"
            "/spec/*\n  Cache-Control: no-cache\n")


def build_bundle(manifest: dict, dest: Path = BUNDLE) -> None:
    """The draft-plan function's copy of this build: what it drafts and screens with."""
    clear(dest, "data.mjs")
    dest.mkdir(parents=True)
    for name in ["prompt.mjs", "screen.mjs"]:
        shutil.copyfile(SPEC / name, dest / name)
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    data = {
        "caseload": load(ROOT / "demo" / "ta" / "synthetic_caseload.json"),
        "prompt": (SPEC / "moveon_prompt.md").read_text(encoding="utf-8"),
        "spec": {"rules": load(SPEC / "screen_rules.json"), "schema": load(SPEC / "moveon.schema.json"),
                 "pathways": load(SPEC / "pathways.json"), "fdcore": M.fdcore_patterns()},
        "manifest": {k: manifest[k] for k in ["source_commit", "source_dirty", "fdcore_commit", "spec_version", "files"]},
    }
    (dest / "data.mjs").write_text(
        "// Written by scripts/build_app.py --target hosted, with the hosted page of the same build. Not in git:\n"
        "// it holds the fd-core patterns. Synthetic records only.\n"
        f"export const DATA = {json.dumps(data, indent=1)};\n", encoding="utf-8")


def build_hosted(url: str | None, key: str | None, dest: Path = HOSTED, bundle: Path = BUNDLE) -> dict:
    url = check_url(url) if url else URL_PLACEHOLDER
    key = check_public_key(key) if key else KEY_PLACEHOLDER
    manifest = build_dist(dest, HOSTED_INPUTS)
    html = hosted_page(PAGE.read_text(encoding="utf-8"), url, key)
    (dest / "index.html").write_text(html, encoding="utf-8")
    (dest / "_headers").write_text(netlify_headers(html, url), encoding="utf-8")
    (dest / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    manifest.update({"target": "hosted", "hosted_page_sha256": sha256(dest / "index.html"), "supabase_js": SUPABASE_JS,
                     "supabase_url": url, "configured": url != URL_PLACEHOLDER and key != KEY_PLACEHOLDER})
    (dest / "data" / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    build_bundle(manifest, bundle)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if app/index.html is out of date")
    ap.add_argument("--clean", action="store_true", help="refuse a tree with uncommitted changes")
    ap.add_argument("--target", choices=["artifact", "hosted"], default="artifact",
                    help="artifact: app/dist (the default); hosted: app/dist-hosted and the function's bundle")
    ap.add_argument("--supabase-url", default=os.environ.get("TA_SUPABASE_URL"), help="hosted: the project's URL")
    ap.add_argument("--publishable-key", "--anon-key", dest="key", default=os.environ.get("TA_SUPABASE_PUBLISHABLE_KEY"),
                    help="hosted: the project's publishable (anon) key, never a secret key")
    ap.add_argument("--out", type=Path, default=HOSTED, help="hosted: the site folder (default app/dist-hosted)")
    ap.add_argument("--bundle-out", type=Path, default=BUNDLE, help="hosted: the function's bundle (default supabase/functions/draft-plan/_bundle)")
    args = ap.parse_args(argv)
    page = PAGE.read_text(encoding="utf-8")
    want = built_page(page)
    demo = DEMO_PAGE.read_text(encoding="utf-8")
    want_demo = branded(demo, "demo/ta/index.html")
    if args.check:
        stale = [n for n, a, b in (("app/index.html", want, page), ("demo/ta/index.html", want_demo, demo)) if a != b]
        if stale:
            print(" and ".join(stale) + " out of date: run python scripts/build_app.py")
            return 1
        print("app/index.html and demo/ta/index.html are up to date")
        return 0
    if want != page:
        PAGE.write_text(want, encoding="utf-8")
        print("updated app/index.html")
    if want_demo != demo:
        DEMO_PAGE.write_text(want_demo, encoding="utf-8")
        print("updated demo/ta/index.html")
    inputs = HOSTED_INPUTS if args.target == "hosted" else INPUTS
    if args.clean and uncommitted(inputs):
        print("these inputs are not committed as they are: " + ", ".join(uncommitted(inputs)) + ". Commit them first.")
        return 1
    if args.target == "hosted":
        m = build_hosted(args.supabase_url, args.key, args.out, args.bundle_out)
        rel = lambda q: q.resolve().relative_to(ROOT).as_posix() if q.resolve().is_relative_to(ROOT) else str(q)  # noqa: E731
        print(f"wrote {rel(args.out)} and {rel(args.bundle_out)} from {m['source_commit']}"
              f"{' (uncommitted changes)' if m['source_dirty'] else ''}: {len(m['files'])} files, {m['caseload']['records']} synthetic records"
              + ("" if m["configured"] else "; no project settings yet, so the page will say so (see hosted/README.md)"))
        return 0
    m = build_dist()
    print(f"wrote app/dist from {m['source_commit']}{' (uncommitted changes)' if m['source_dirty'] else ''}: "
          f"{len(m['files'])} files, {m['caseload']['records']} synthetic records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
