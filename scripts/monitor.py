"""Move forward's monitoring layer (phase 7): the project's side of fd-core's fdcore.monitor.

    python scripts/monitor.py vocab             write monitor/vocab.json from tamarket/spec
    python scripts/monitor.py due [--today D]   the sources due a read (monitor/RUNBOOK.md)
    python scripts/monitor.py ingest            file the candidates in monitor/inbox/

- vocab: the tags an item may carry, from the planner's own spec: check ids (the general checks,
  the suitability checks and each route's officer checks), route ids, reference ids
  (tamarket/spec/references.json), the statutory clocks (tamarket/spec/clocks.json), and a short
  list of topics.
- ingest: before fd-core's checks, every candidate is screened for the name of an English council
  (the local authority names in data/processed/ta1_wide.csv, matched as whole words with their
  capitals): the planner names no council in a comparison or in anything shared, and an item's
  summary or excerpt is shown to every member. A candidate that names one is refused and goes to
  monitor/refused.jsonl (gitignored, as the inbox is: it can hold the text that was refused). Good
  candidates are appended to monitor/items.jsonl with an entry each in data/ingest_log.jsonl, whose
  out_file is the repo-relative path.
- updated: where a page shows both a published date and an updated (or last updated) date, the
  candidate gives the first as "published" and the second as "updated". fd-core's item has no such
  field and refuses unknown ones, so this script checks it (a date, on or after published, not after
  the page was read), files the item without it, then adds it to the item's line.

scripts/build_app.py publishes the items as data/monitor.json (a list) and the register's public
facts, terms and grades as spec/monitor_sources.json (an object with a "sources" list), so a site
build can keep only items whose source's terms_note starts with "Open Government Licence". Items
wait for an officer to accept or reject them; nothing reaches a plan unaccepted.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fdcore import monitor as FM  # noqa: E402
from fdcore.ingest_log import IngestLog  # noqa: E402

MON = ROOT / "monitor"
REGISTER = MON / "sources.json"
VOCAB = MON / "vocab.json"
ITEMS = MON / "items.jsonl"
INBOX = MON / "inbox"
REFUSALS = MON / "refused.jsonl"
LOG = ROOT / "data" / "ingest_log.jsonl"
SPEC = ROOT / "tamarket" / "spec"
COUNCILS = ROOT / "data" / "processed" / "ta1_wide.csv"
DENY = ROOT / "config" / "deny_list.txt"
TOPICS = ["release", "guidance", "legislation", "ombudsman", "notices", "suitability", "reviews", "private_renting"]
# Local authority codes: unitary (E06), district (E07), metropolitan (E08) and London borough (E09).
LA_CODE = re.compile(r"^E0[6-9]\d{6}$")


def vocab() -> dict[str, list[str]]:
    p = json.loads((SPEC / "pathways.json").read_text(encoding="utf-8"))
    checks = [c["id"] for c in p["general_checks"]] + [c["id"] for c in p["suitability_checks"]]
    checks += [c["id"] for pw in p["pathways"] for c in pw["officer_checks"]]
    refs = [r["id"] for r in json.loads((SPEC / "references.json").read_text(encoding="utf-8"))["references"]]
    clocks = [k for k, v in json.loads((SPEC / "clocks.json").read_text(encoding="utf-8"))["rules"].items() if isinstance(v, dict)]
    return {"checks": checks, "pathways": [pw["id"] for pw in p["pathways"]], "references": refs, "clocks": clocks, "topics": TOPICS}


def write_vocab() -> dict:
    v = vocab()
    VOCAB.write_text(json.dumps({"about": "Tags a monitoring item may carry, written by scripts/monitor.py vocab from tamarket/spec.", **v}, indent=1) + "\n", encoding="utf-8")
    return v


def council_names(path: Path = COUNCILS) -> list[str]:
    with path.open(encoding="utf-8") as fh:
        return sorted({r["name"].strip() for r in csv.DictReader(fh) if LA_CODE.match(r.get("code", "")) and r.get("name", "").strip()})


def council_problems(item: dict, names: list[str]) -> list[str]:
    text = "\n".join(str(item.get(k, "")) for k in ("title", "summary", "title_original", "excerpt_original"))
    out = []
    for n in names:
        if re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", text):
            out.append(f"names a council ({n}): the planner names no council in anything shared")
    return out


def _rel(p: Path) -> Path:
    """A path under the repo as the repo names it, so the ingest log records it the same on any machine."""
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT)
    except ValueError:
        return p


DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def updated_problems(cand: dict) -> list[str]:
    """The project's own check of "updated": a date on or after published, not after the page was read."""
    if "updated" not in cand:
        return []
    u = str(cand["updated"])
    try:
        d = date.fromisoformat(u) if DAY.match(u) else None
    except ValueError:
        d = None
    if d is None:
        return ["updated is not a date (YYYY-MM-DD)"]
    out = []
    if str(cand.get("published", "")) and u <= str(cand["published"]):
        out.append("updated must come after published: give the page's published date as published")
    try:
        if d > datetime.fromisoformat(str(cand.get("retrieved_at", "")).replace("Z", "+00:00")).date():
            out.append("updated is after the page was read")
    except ValueError:
        pass
    return out


def ingest(inbox: Path = INBOX, items: Path = ITEMS, log: Path = LOG, refusals: Path = REFUSALS, today: date | None = None,
           names: list[str] | None = None) -> dict:
    reg = FM.load_register(REGISTER)
    voc = vocab()
    names = council_names() if names is None else names
    deny = [x for x in DENY.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")] if DENY.exists() else None
    refused, updated = [], {}
    inbox, items, log, refusals = Path(inbox).resolve(), _rel(items), _rel(log), _rel(refusals)
    with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(ROOT):
        for n, f in enumerate(sorted(Path(inbox).glob("*.json"))):
            data = json.loads(f.read_text(encoding="utf-8"))
            ok = []
            for cand in data if isinstance(data, list) else [data]:
                probs = council_problems(cand, names) + updated_problems(cand)
                if probs:
                    refused.append({"file": f.name, "url": cand.get("url"), "problems": probs})
                    continue
                cand = dict(cand)
                if "updated" in cand:
                    updated[FM.item_id(cand)] = str(cand.pop("updated"))
                ok.append(cand)
            (Path(tmp) / f"{n:04d}.json").write_text(json.dumps(ok), encoding="utf-8")
        rep = FM.ingest(tmp, items, reg, IngestLog(log), voc, deny, today, refusals_path=refusals)
        filed = set(rep["filed"]) & set(updated)
        if filed:
            lines = Path(items).read_text(encoding="utf-8").splitlines()
            out = []
            for line in lines:
                rec = json.loads(line) if line.strip() else None
                if rec and rec.get("id") in filed:
                    rec = {k: v for k, v in rec.items()} | {"updated": updated[rec["id"]]}
                    line = json.dumps(rec, ensure_ascii=False)
                out.append(line)
            Path(items).write_text("\n".join(out) + "\n", encoding="utf-8")
        if refused:
            with Path(refusals).open("a", encoding="utf-8") as fh:
                for r in refused:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            rep["refused"] = refused + rep["refused"]
    return rep


def published_items(items_path: Path = ITEMS) -> list[dict]:
    """data/monitor.json: the filed items, newest first by the later of published and updated."""
    return sorted(FM.load_items(items_path), key=lambda i: (i.get("updated") or i["published"], i["id"]), reverse=True)


def published_sources() -> dict:
    """spec/monitor_sources.json: the register's public facts (each source with its terms_note), and
    the grades in words."""
    reg = FM.load_register(REGISTER)
    keep = ("id", "name", "publisher", "url", "kind", "terms_url", "terms_note", "reliability")
    return {"schema": "monitor-sources/1", "read_on": json.loads(REGISTER.read_text(encoding="utf-8")).get("read_on"),
            "sources": [{f: s[f] for f in keep} for s in reg.values()],
            "grades": {"reliability": FM.RELIABILITY, "credibility": FM.CREDIBILITY}}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["vocab", "due", "ingest"])
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    if a.cmd == "vocab":
        v = write_vocab()
        print(f"wrote {VOCAB.relative_to(ROOT)}: " + ", ".join(f"{len(x)} {k}" for k, x in v.items()))
        return 0
    if a.cmd == "due":
        print(json.dumps(FM.due(FM.load_register(REGISTER), FM.load_items(ITEMS), today), indent=1))
        return 0
    write_vocab()
    rep = ingest(today=today)
    print(json.dumps({k: len(v) for k, v in rep.items()}))
    for r in rep["refused"]:
        print(f"refused {r['url']}: " + "; ".join(r["problems"]), file=sys.stderr)
    return 1 if rep["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
