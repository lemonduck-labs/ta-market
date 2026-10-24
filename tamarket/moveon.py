"""Routes out (pathways), the AI-drafted plan schema and the plan screen, for synthetic records only.

The rules live in language-neutral files under tamarket/spec/, which a JavaScript page and a
Deno function load unchanged; this module is the Python reference that reads them:

- pathways.json: each pathway (social housing through the allocation scheme, a private rented
  sector offer, supported housing) and each suitability check, with a stable id, a condition a
  program can evaluate (field, operator, value), the same condition in words, officer checks
  and citations (publisher, title, date) from official guidance and legislation only;
- moveon.schema.json: the JSON schema for a plan drafted by AI;
- moveon_prompt.md: the drafting prompt;
- screen_rules.json: the screen, with screen_cases.json as the cases a port must pass.

suggest_pathways(household) lists, for one synthetic household, the pathways it could take,
with reasons and the checks an officer must make, plus the suitability checks its record
raises. These are suggestions for an officer to approve, never decisions.

screen_plan(plan, household) runs the fd-core guardrails screen on every text field of a
drafted plan and rejects any plan that does not match the schema, is not for a synthetic
record, suggests a pathway not listed for it, states a decision, names a person or a provider,
or uses a figure that is not in the record. It is a net, not a guarantee: the officer reads
every plan. propose_plan() puts a plan that passes into the fd-core approval queue, where only
a person can approve or reject it.

Reviewer notes (screen_rules.json, review): when an officer returns or rejects a plan, what they
wrote goes to the next draft. review_notes_from(decisions) builds the notes from a household's
decisions, usable_notes() keeps those that pass the note checks, fill_prompt() puts them in the
prompt apart from the record, and screen_plan(review=...) requires one answer to each in
responds_to_review. A note never extends the record: its figures and words are not allowed in
the plan unless the record or the suggestions hold them.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = Path(__file__).resolve().parent / "spec"
STATUS = "Suggestions for an officer to approve, never decisions."
QUEUE = ROOT / "data" / "private" / "moveon_queue.jsonl"
PROPOSED_BY = "agent:move-forward-planner"


# ---------------------------------------------------------------------------
# Spec files
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load(name: str) -> str:
    return (SPEC_DIR / name).read_text(encoding="utf-8")


def load_spec() -> dict:
    """The spec files as loaded by every implementation."""
    return {"pathways": json.loads(_load("pathways.json")), "rules": json.loads(_load("screen_rules.json")),
            "schema": json.loads(_load("moveon.schema.json")), "prompt": _load("moveon_prompt.md")}


def _rx(spec: dict | str, flags: str | None = None) -> re.Pattern:
    """A pattern from the spec, compiled as JavaScript reads it on ASCII text."""
    if isinstance(spec, dict):
        spec, flags = spec["pattern"], spec.get("flags", "")
    return re.compile(spec, re.ASCII | (re.IGNORECASE if "i" in (flags or "") else 0))


# ---------------------------------------------------------------------------
# Conditions and pathways
# ---------------------------------------------------------------------------

def holds(cond: dict, record: dict) -> bool:
    """Evaluate a condition from pathways.json against a record (see its condition_language)."""
    if "always" in cond:
        return bool(cond["always"])
    if "all" in cond:
        return all(holds(c, record) for c in cond["all"])
    if "any" in cond:
        return any(holds(c, record) for c in cond["any"])
    if "not" in cond:
        return not holds(cond["not"], record)
    field, op, value = cond["field"], cond["op"], cond.get("value")
    if field not in record:
        return False
    v = record[field]
    if op == "eq":
        return _same(v, value)
    if op == "ne":
        return not _same(v, value)
    if op == "in":
        return any(_same(v, x) for x in value)
    if op in ("gt", "gte", "lt", "lte"):
        if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
            return False
        return {"gt": v > value, "gte": v >= value, "lt": v < value, "lte": v <= value}[op]
    if op == "contains":
        return isinstance(v, list) and value in v
    if op == "nonempty":
        return isinstance(v, (list, str)) and len(v) > 0
    raise ValueError(f"unknown operator: {op}")


def _require_synthetic(household: dict) -> None:
    if not isinstance(household, dict) or household.get("synthetic") is not True:
        raise ValueError("move-forward suggestions are made for synthetic records only")


def suggest_pathways(household: dict, spec: dict | None = None) -> dict:
    """The pathways one synthetic household could take, each with its reasons and the checks an
    officer must make, and the suitability checks its record raises. Suggestions only."""
    _require_synthetic(household)
    doc = (spec or load_spec())["pathways"]
    used: set[str] = set()

    def item(x: dict) -> dict:
        used.update(x.get("citations", []))
        return {k: x[k] for k in ("id", "text", "citations", "confidence") if k in x}

    pathways = []
    for p in doc["pathways"]:
        if not holds(p["applies_when"], household):
            continue
        pathways.append({
            "pathway_id": p["id"], "title": p["title"], "summary": p["summary"], "ends_main_duty": p["ends_main_duty"],
            "why_listed": p["applies_when_text"],
            "reasons": [item(r) for r in p["reasons"]],
            "officer_checks": [item(c) for c in p["officer_checks"]]
            + [item(n) for n in p["notes"] if holds(n["when"], household)],
        })
    checks = [item(c) for c in doc["suitability_checks"] if holds(c["when"], household)]
    general = [item(c) for c in doc["general_checks"]]
    return {"household_id": household["id"], "synthetic": True, "status": STATUS, "general_checks": general,
            "pathways": pathways, "suitability_checks": checks,
            "statutory_figures": doc["statutory_figures"],
            "citations": {k: v for k, v in doc["citations"].items() if k in used}}


def eligible_pathways(household: dict, spec: dict | None = None) -> list[dict]:
    """The compact form the caseload file carries: [{pathway_id, reasons, officer_checks}],
    with ids that texts() resolves, so a page shows Python's output and never re-implements
    the rules."""
    s = suggest_pathways(household, spec)
    return [{"pathway_id": p["pathway_id"], "reasons": [f"{p['pathway_id']}.when"] + [r["id"] for r in p["reasons"]],
             "officer_checks": [c["id"] for c in p["officer_checks"]]} for p in s["pathways"]]


def suitability_check_ids(household: dict, spec: dict | None = None) -> list[str]:
    return [c["id"] for c in suggest_pathways(household, spec)["suitability_checks"]]


def texts(spec: dict | None = None) -> dict[str, dict]:
    """Every id used in the compact form, with its words, citations and confidence."""
    doc = (spec or load_spec())["pathways"]
    out: dict[str, dict] = {}
    for c in doc["general_checks"]:
        out[c["id"]] = {"text": c["text"], "citations": c["citations"], "confidence": c["confidence"]}
    for p in doc["pathways"]:
        out[f"{p['id']}.when"] = {"text": p["applies_when_text"], "citations": [], "confidence": "Certain"}
        for x in p["reasons"] + p["officer_checks"] + p["notes"]:
            out[x["id"]] = {"text": x["text"], "citations": x["citations"], "confidence": x["confidence"]}
            if "when_text" in x:
                out[x["id"]]["when"] = x["when_text"]
    for c in doc["suitability_checks"]:
        out[c["id"]] = {"text": c["text"], "citations": c["citations"], "confidence": c["confidence"],
                        "when": c["when_text"]}
    return out


# ---------------------------------------------------------------------------
# Schema (the subset of JSON Schema 2020-12 that moveon.schema.json uses)
# ---------------------------------------------------------------------------

def _same(a, b) -> bool:
    """JSON equality: true and 1 differ."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _type_ok(v, t: str) -> bool:
    num = isinstance(v, (int, float)) and not isinstance(v, bool)
    return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str),
            "boolean": isinstance(v, bool), "null": v is None, "number": num and math.isfinite(v),
            "integer": num and math.isfinite(v) and float(v).is_integer()}[t]


def _js_end(pattern: str) -> str:
    """A final $ as JavaScript reads it: the end of the text only, never before a last newline."""
    return pattern[:-1] + r"\Z" if pattern.endswith("$") and not pattern.endswith("\\$") else pattern


def validate_schema(value, schema: dict, root: dict | None = None, path: str = "") -> list[tuple[str, str]]:
    """(path, message) for every way value fails schema. Keywords: $ref (to #/$defs), const, enum,
    type, required, properties, additionalProperties (false), items, minItems, maxItems,
    minLength, maxLength (in code points) and pattern (searched, as JSON Schema does)."""
    root = root or schema
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return validate_schema(value, root["$defs"][name], root, path)
    errs: list[tuple[str, str]] = []
    where = path or "(plan)"
    if "const" in schema and not _same(value, schema["const"]):
        errs.append((where, f"must be {json.dumps(schema['const'])}"))
    if "enum" in schema and not any(_same(value, e) for e in schema["enum"]):
        errs.append((where, "must be one of " + ", ".join(json.dumps(e) for e in schema["enum"])))
    if "type" in schema and not _type_ok(value, schema["type"]):
        return errs + [(where, f"must be of type {schema['type']}")]
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append((where, f"missing {k}"))
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += validate_schema(v, props[k], root, f"{path}.{k}" if path else k)
            elif schema.get("additionalProperties") is False:
                errs.append((where, f"unexpected field {k}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append((where, f"needs at least {schema['minItems']} items"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append((where, f"takes at most {schema['maxItems']} items"))
        if "items" in schema:
            for i, v in enumerate(value):
                errs += validate_schema(v, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append((where, f"needs at least {schema['minLength']} characters"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append((where, f"takes at most {schema['maxLength']} characters"))
        if "pattern" in schema and not re.search(_js_end(schema["pattern"]), value):
            errs.append((where, f"must match {schema['pattern']}"))
    return errs


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

def normalise_text(s: str, rules: dict) -> str:
    for a, b in rules["normalise"]["replace"]:
        s = s.replace(a, b)
    return s


def _normalise(v, rules: dict):
    if isinstance(v, str):
        return normalise_text(v, rules)
    if isinstance(v, list):
        return [_normalise(x, rules) for x in v]
    if isinstance(v, dict):
        return {k: _normalise(x, rules) for k, x in v.items()}
    return v


def text_fields(plan, skip: set[str], path: str = "", key: str | None = None):
    """(path, text) for every string in the plan whose key is not skipped."""
    if isinstance(plan, str):
        if key not in skip:
            yield path, plan
    elif isinstance(plan, dict):
        for k, v in plan.items():
            yield from text_fields(v, skip, f"{path}.{k}" if path else k, k)
    elif isinstance(plan, list):
        for i, v in enumerate(plan):
            yield from text_fields(v, skip, f"{path}[{i}]", key)


@lru_cache(maxsize=None)
def _compiled(rules_json: str) -> dict:
    r = json.loads(rules_json)
    d, p, f = r["decision"], r["person"], r["figure"]
    words = sorted(f["number_words"], key=len, reverse=True)
    return {
        "refs": [_rx(x, r["references"]["flags"]) for x in r["references"]["patterns"]],
        "sentence": _rx(d["sentence_split"]), "clause": _rx(d["clause_split"]),
        "opener": _rx(d["conditional_opener"]), "strong": _rx(d["strong_hedge"]), "soft_hedge": _rx(d["soft_hedge"]),
        "hard": [_rx(x, d["flags"]) for x in d["hard"]], "soft": [_rx(x, d["flags"]) for x in d["soft"]],
        "never": [_rx(x, d["flags"]) for x in d["never_hedged"]],
        "honorific": _rx(p["honorific"]), "capitalised": _rx(p["capitalised_word"]), "acronym": _rx(p["acronym"]),
        "number": _rx(f["number"]), "number_word": _rx(r"\b(?:" + "|".join(words) + r")\b", "i"),
        "disallowed": _rx(r["style"]["disallowed_chars"]),
        "instruction": _rx(r["review"]["instruction"]), "note_id": _rx(r["review"]["note_id"]),
    }


def strip_references(text: str, rules: dict) -> str:
    c = _compiled(json.dumps(rules, sort_keys=True))
    for rx in c["refs"]:
        text = rx.sub(rules["references"]["replacement"], text)
    return text


def decision_findings(text: str, rules: dict) -> list[str]:
    c = _compiled(json.dumps(rules, sort_keys=True))
    out = []
    for sentence in c["sentence"].split(strip_references(text, rules)):
        out += [m.group(0) for rx in c["never"] for m in rx.finditer(sentence)]
        if c["opener"].search(sentence):
            continue
        if not c["soft_hedge"].search(sentence):
            out += [m.group(0) for rx in c["soft"] for m in rx.finditer(sentence)]
        for clause in c["clause"].split(sentence):
            if not c["strong"].search(clause):
                out += [m.group(0) for rx in c["hard"] for m in rx.finditer(clause)]
    return out


def _sentence_start(text: str, i: int, skip_back: str, starts: str) -> bool:
    j = i - 1
    while j >= 0 and text[j] in skip_back:
        j -= 1
    return j < 0 or text[j] in starts


def person_findings(text: str, rules: dict, record_id: str = "") -> list[str]:
    c = _compiled(json.dumps(rules, sort_keys=True))
    p = rules["person"]
    t = strip_references(text, rules)
    if record_id:
        t = t.replace(record_id, " ")
    allowed, acronyms = set(p["allowed_words"]), set(p["allowed_acronyms"])
    out = [m.group(0) for m in c["honorific"].finditer(t)]
    for m in c["capitalised"].finditer(t):
        word = m.group(0)
        for ending in p["word_endings_removed"]:
            if word.endswith(ending):
                word = word[: -len(ending)]
        if word in allowed or _sentence_start(t, m.start(), p["skip_back"], p["starts"]):
            continue
        out.append(word)
    out += [m.group(0) for m in c["acronym"].finditer(t) if m.group(0) not in acronyms]
    return out


def record_figures(record: dict, rules: dict) -> set[float]:
    c = _compiled(json.dumps(rules, sort_keys=True))
    ignored = set(rules["figure"]["record_keys_ignored"])
    out: set[float] = set()

    def walk(v, key=None):
        if key in ignored:
            return
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.add(float(v))
        elif isinstance(v, str):
            out.update(float(m.group(0).replace(",", "")) for m in c["number"].finditer(v))
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
    walk(record)
    return out


def figure_findings(text: str, record: dict, rules: dict, statutory: list[dict]) -> list[str]:
    c = _compiled(json.dumps(rules, sort_keys=True))
    t = text.replace(record["id"], " ") if record.get("id") else text
    phrases = sorted({x for s in statutory for x in [s["text"], *s.get("aliases", [])]}, key=len, reverse=True)
    for ph in phrases:
        t = re.sub(r"\b" + re.escape(ph) + r"\b", " ", t, flags=re.IGNORECASE | re.ASCII)
    t = strip_references(t, rules)
    allowed = record_figures(record, rules)
    words = rules["figure"]["number_words"]
    out = [m.group(0) for m in c["number"].finditer(t) if float(m.group(0).replace(",", "")) not in allowed]
    out += [m.group(0) for m in c["number_word"].finditer(t) if float(words[m.group(0).lower()]) not in allowed]
    return out


def _eligible_ids(household: dict, spec: dict) -> set[str]:
    if isinstance(household.get("eligible_pathways"), list):
        return {p["pathway_id"] for p in household["eligible_pathways"]}
    return {p["pathway_id"] for p in suggest_pathways(household, spec)["pathways"]}


def _deny_list() -> list[str]:
    f = ROOT / "config" / "deny_list.txt"
    return f.read_text().splitlines() if f.exists() else []


# ---------------------------------------------------------------------------
# Reviewer notes
# ---------------------------------------------------------------------------

def review_notes_from(decisions: list[dict], counts=None, rules: dict | None = None) -> list[dict]:
    """The reviewer notes for a household's next draft, from its decisions ({decision, note,
    reason, decided_at, id}): the returns with a note and the rejections since the last approval
    that counts, oldest first, the latest max_notes of them, as [{id, kind, text}]. counts(d)
    says whether an approval counts (the page's approval check); by default every one does.
    Decisions are ordered by decided_at, then id, compared as strings, as the page orders them."""
    R = (rules or load_spec()["rules"])["review"]
    counts = counts or (lambda d: True)
    ds = sorted(decisions, key=lambda d: (str(d.get("decided_at") or ""), str(d.get("id") or "")))
    start = 0
    for i in range(len(ds) - 1, -1, -1):
        if ds[i].get("decision") == "approved" and counts(ds[i]):
            start = i + 1
            break
    picked = [d for d in ds[start:] if (d.get("decision") == "returned" and str(d.get("note") or "").strip())
              or d.get("decision") == "rejected"][-int(R["max_notes"]):]
    out = []
    for i, d in enumerate(picked):
        note = str(d.get("note") or "").strip()
        if d["decision"] == "rejected":
            label = R["reject_labels"].get(d.get("reason"), R["reject_label_unknown"])
            text = f"{label}: {note}" if note else label
        else:
            text = note
        out.append({"id": f"review-{i + 1}", "kind": d["decision"], "text": text})
    return out


def check_review(review, rules: dict | None = None) -> list[dict]:
    """The notes as given, checked for shape: a list of at most max_notes objects, each with a
    unique id matching note_id, a kind (returned or rejected) and a text. Raises ValueError
    otherwise, a fault in the caller rather than in a draft."""
    rules = rules or load_spec()["rules"]
    R, c = rules["review"], _compiled(json.dumps(rules, sort_keys=True))
    notes = list(review or [])
    if len(notes) > int(R["max_notes"]):
        raise ValueError(f"at most {R['max_notes']} reviewer notes")
    ids = [n.get("id") if isinstance(n, dict) else None for n in notes]
    if any(not isinstance(i, str) or not c["note_id"].fullmatch(i) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("reviewer notes need unique ids review-1 to review-5")
    if any(not isinstance(n.get("text"), str) or n.get("kind") not in ("returned", "rejected") for n in notes):
        raise ValueError("every reviewer note needs a text and a kind, returned or rejected")
    return notes


def note_findings(text: str, household: dict, spec: dict | None = None, deny: list[str] | None = None) -> list[dict]:
    """The note checks (screen_rules.json, review) on one reviewer note, normalised and trimmed:
    style, the fd-core screen, the person rule, instruction and length. A note with any problem
    is held back from the prompt."""
    from fdcore.guardrails import scan_text

    spec = spec or load_spec()
    rules = spec["rules"]
    c = _compiled(json.dumps(rules, sort_keys=True))
    deny = [] if deny is None else deny
    t = normalise_text(str(text), rules).strip()
    out: list[dict] = []

    def add(rule: str, detail: str):
        out.append({"path": "note", "rule": rule, "detail": detail})
    if rules["style"]["em_dash"] in t:
        add("style", "em dash")
    for m in c["disallowed"].finditer(t.replace(rules["style"]["em_dash"], "")):
        add("style", f"character U+{ord(m.group(0)):04X} is outside ASCII")
    for f in scan_text(t, "note", deny):
        add(f"fdcore:{f.kind}", f.text)
    rid = str(household.get("id", "")) if isinstance(household, dict) else ""
    for n in person_findings(t, rules, rid):
        add("person", n)
    for line in t.split("\n"):
        m = c["instruction"].search(line)
        if m:
            add("instruction", m.group(0)[:80])
            break
    if len(t) > int(rules["review"]["max_note_length"]):
        add("length", str(len(t)))
    return out


def usable_notes(review, household: dict, spec: dict | None = None, deny: list[str] | None = None) -> dict:
    """{"usable": [...], "held": [...]}: the notes that pass note_findings, with their text
    normalised and trimmed, and the rest with their problems."""
    spec = spec or load_spec()
    rules = spec["rules"]
    usable, held = [], []
    for n in check_review(review, rules):
        probs = note_findings(n["text"], household, spec, deny)
        item = {"id": n["id"], "kind": n["kind"], "text": normalise_text(n["text"], rules).strip()}
        if probs:
            held.append({**item, "problems": probs})
        else:
            usable.append(item)
    return {"usable": usable, "held": held}


def review_problems(plan, review: list[dict], rules: dict) -> list[dict]:
    """The answers rule (screen_rules.json, review): one answer to each note given, none to any
    other, and none still the placeholder."""
    c = _compiled(json.dumps(rules, sort_keys=True))
    R = rules["review"]
    out: list[dict] = []

    def add(path: str, detail: str):
        out.append({"path": path, "rule": R["rule"], "detail": detail})
    given = [n["id"] for n in review]
    seen: set[str] = set()
    answers = plan.get("responds_to_review") if isinstance(plan, dict) else None
    for i, a in enumerate(answers if isinstance(answers, list) else []):
        nid = a.get("note") if isinstance(a, dict) else None
        if not isinstance(nid, str):
            continue
        shown = nid if c["note_id"].fullmatch(nid) else "an unknown note"
        if nid not in given:
            add(f"responds_to_review[{i}].note", f"{shown} is not one of the notes given")
            continue
        if nid in seen:
            add(f"responds_to_review[{i}].note", f"{shown} is answered more than once")
        seen.add(nid)
        change = a.get("change")
        if isinstance(change, str) and normalise_text(change, rules).strip() == R["placeholder"]:
            add(f"responds_to_review[{i}].change", f"the answer to {shown} is still the placeholder")
    missing = [n for n in given if n not in seen]
    if missing:
        add("responds_to_review", f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} no answer")
    return out


def screen_plan(plan: dict, household: dict, spec: dict | None = None, deny: list[str] | None = None,
                review: list[dict] | None = None) -> dict:
    """Screen an AI-drafted plan for one synthetic household. Returns {"passed", "problems",
    "plan"}: problems are {path, rule, detail}; plan is the normalised plan, the one to show.
    review is the list of usable reviewer notes the plan was drafted against (usable_notes), or
    None when there are none."""
    from fdcore.guardrails import scan_text

    spec = spec or load_spec()
    rules = spec["rules"]
    deny = _deny_list() if deny is None else deny
    notes = check_review(review, rules)
    problems: list[dict] = []

    def add(path: str, rule: str, detail: str):
        problems.append({"path": path, "rule": rule, "detail": detail})

    plan = _normalise(plan, rules)
    skip = set(rules["skip_keys"])
    fields = list(text_fields(plan, skip)) if isinstance(plan, (dict, list)) else []
    c = _compiled(json.dumps(rules, sort_keys=True))
    # style
    for path, text in fields:
        if rules["style"]["em_dash"] in text:
            add(path, "style", "em dash")
        for m in c["disallowed"].finditer(text.replace(rules["style"]["em_dash"], "")):
            add(path, "style", f"character U+{ord(m.group(0)):04X} is outside ASCII")
    # schema
    for path, msg in validate_schema(plan, spec["schema"]):
        add(path, "schema", msg)
    # record
    synthetic = isinstance(household, dict) and household.get("synthetic") is True
    if not synthetic:
        add("household", "record", "plans are drafted on synthetic records only")
    if isinstance(plan, dict) and isinstance(household, dict) and plan.get("household_id") != household.get("id"):
        add("household_id", "record", "does not match the record's id")
    # pathway
    if synthetic and isinstance(plan, dict):
        eligible = _eligible_ids(household, spec)
        known = set(spec["schema"]["$defs"]["pathway_id"]["enum"])
        for i, s in enumerate(plan.get("pathway_suggestions") or []):
            pid = s.get("pathway_id") if isinstance(s, dict) else None
            if pid in known and pid not in eligible:
                add(f"pathway_suggestions[{i}].pathway_id", "pathway", f"{pid} is not listed for this record")
        allowed_checks = eligible | set(rules["pathway"]["check_values"])
        for i, s in enumerate(plan.get("officer_checks") or []):
            pid = s.get("pathway_id") if isinstance(s, dict) else None
            if (pid in known or pid in rules["pathway"]["check_values"]) and pid not in allowed_checks:
                add(f"officer_checks[{i}].pathway_id", "pathway", f"{pid} is not listed for this record")
    # fd-core, decisions, names, figures on every text field
    record = household if isinstance(household, dict) else {}
    statutory = spec["pathways"]["statutory_figures"]
    for path, text in fields:
        for f in scan_text(text, path, deny):
            add(path, f"fdcore:{f.kind}", f.text)
        for d in decision_findings(text, rules):
            add(path, "decision", d)
        for n in person_findings(text, rules, str(record.get("id", ""))):
            add(path, "person", n)
        for n in figure_findings(text, record, rules, statutory):
            add(path, "figure", n)
    # reviewer notes
    problems += review_problems(plan, notes, rules)
    return {"passed": not problems, "problems": problems, "plan": plan}


class PlanRejected(ValueError):
    def __init__(self, problems: list[dict]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s): " + "; ".join(f"{p['path']}: {p['rule']}" for p in problems[:5]))


def propose_plan(plan: dict, household: dict, queue: Path | str = QUEUE) -> str:
    """Screen a plan and, if it passes, propose it in the fd-core approval queue for a person to
    approve or reject. Returns the queue item id; raises PlanRejected otherwise."""
    from fdcore.decisions import DecisionLog

    result = screen_plan(plan, household)
    if not result["passed"]:
        raise PlanRejected(result["problems"])
    return DecisionLog(queue).propose("move-forward plan (synthetic record)",
                                      {"household_id": household["id"], "plan": result["plan"],
                                       "screen": "passed", "spec_version": load_spec()["rules"]["spec_version"]},
                                      proposed_by=PROPOSED_BY)


MAX_DEPTH = 32


def _no_constants(name: str):
    raise ValueError(f"{name} is not JSON")


def _depth(v) -> int:
    best, stack = 0, [(v, 1)]
    while stack:
        x, d = stack.pop()
        if not isinstance(x, (dict, list)):
            continue
        best = max(best, d)
        if best > MAX_DEPTH:
            return best
        stack.extend((y, d + 1) for y in (x.values() if isinstance(x, dict) else x))
    return best


def parse_reply(text) -> dict:
    """A drafting reply must be one JSON object, nested at most MAX_DEPTH deep; a single code
    fence around it is allowed. Returns {"ok": True, "plan": ...} or {"ok": False, "problem":
    {path, rule, detail}}. Only ASCII white space is trimmed and NaN or Infinity is not JSON, as
    in prompt.mjs, so both read every reply the same way."""
    t = (text if isinstance(text, str) else "").strip(" \t\n\r")
    m = re.fullmatch(r"```[A-Za-z]*\n([\s\S]*?)\n?```", t)
    if m:
        t = m.group(1).strip(" \t\n\r")
    try:
        v = json.loads(t, parse_constant=_no_constants)
    except (ValueError, RecursionError):
        v = None
    if isinstance(v, dict) and _depth(v) <= MAX_DEPTH:
        return {"ok": True, "plan": v}
    return {"ok": False, "problem": {"path": "(reply)", "rule": "reply", "detail": "the reply is not one JSON object"}}


PLACEHOLDER = re.compile(r"\{\{(HOUSEHOLD_JSON|SUGGESTIONS_JSON|REVIEW_JSON|LESSONS_JSON|SCHEMA_JSON)\}\}")


def fill_prompt(household: dict, spec: dict | None = None, review: list[dict] | None = None,
                lessons: list[dict] | None = None) -> str:
    """The drafting prompt with its five placeholders filled, in one pass, for one synthetic
    household, the reviewer notes that passed the note checks (usable_notes) and the lessons
    recalled for it ({id, applies_to, text})."""
    _require_synthetic(household)
    spec = spec or load_spec()
    notes = check_review(review, spec["rules"])
    body = spec["prompt"].split("---PROMPT---", 1)[1].lstrip("\n")
    vals = {"HOUSEHOLD_JSON": json.dumps(household, indent=1, ensure_ascii=False),
            "SUGGESTIONS_JSON": json.dumps(suggest_pathways(household, spec), indent=1, ensure_ascii=False),
            "REVIEW_JSON": json.dumps([{"id": n["id"], "kind": n["kind"], "text": n["text"]} for n in notes],
                                      indent=1, ensure_ascii=False),
            "LESSONS_JSON": json.dumps([{"id": x["id"], "applies_to": x["applies_to"], "text": x["text"]} for x in (lessons or [])],
                                       indent=1, ensure_ascii=False),
            "SCHEMA_JSON": json.dumps(spec["schema"], indent=1)}
    return PLACEHOLDER.sub(lambda m: vals[m.group(1)], body)


# ---------------------------------------------------------------------------
# fd-core patterns for a port
# ---------------------------------------------------------------------------

def fdcore_patterns() -> dict:
    """fd-core's guardrails patterns and rules, for a JavaScript port of the screen. Written by
    scripts/export_fdcore_patterns.py to tamarket/spec/fdcore_patterns.json, which stays out of
    git because it lists the words the screen blocks."""
    from fdcore import guardrails as G

    def rx(p: re.Pattern) -> dict:
        return {"pattern": p.pattern, "flags": "i" if p.flags & re.IGNORECASE else ""}

    src = Path(G.__file__).read_bytes()
    return {
        "generated_from": "fdcore.guardrails", "fdcore_sha256": hashlib.sha256(src).hexdigest(),
        "kinds": G.KINDS,
        "patterns": {"company": rx(G.COMPANY), "email": rx(G.EMAIL), "phone": rx(G.PHONE),
                     "postcode": rx(G.UK_POSTCODE), "accusing": rx(G.ACCUSING), "clause_break": rx(G.CLAUSE_BREAK)},
        "hedges": list(G.HEDGES), "hedge_before": G.HEDGE_BEFORE, "hedge_after": G.HEDGE_AFTER,
        "email_allow": sorted(G.EMAIL_ALLOW),
        "rules": {
            "lines": "Scan each line separately.",
            "postcode": "Skip a match whose previous character is # (a hex colour).",
            "phone": "Report a match only when it holds at least 10 digits, the digits do not start with 19 or 20 "
                     "followed by two digits, and it does not sit inside a longer number or token: the character before "
                     "it is not an ASCII letter, a digit or a full stop, and the text after it does not start with a "
                     "full stop and a digit or with e or E.",
            "email": "Skip addresses in email_allow, compared in lower case.",
            "deny": "Each deny-list line (not blank, not starting #) is matched as literal text, ignoring case.",
            "accusing": "Report a match unless a hedge phrase sits in the same clause: the window runs from at most "
                        "hedge_before characters before the match, cut at the last clause break before it, to at "
                        "most hedge_after characters after it, cut at the first clause break after it, and is "
                        "compared in lower case.",
        },
    }
