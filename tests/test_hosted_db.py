"""The hosted planner's database (supabase/migrations), run on a real local Postgres.

The tests start a scratch Postgres cluster, add a stand-in for Supabase's auth schema and roles
(tests/hosted_supabase_stub.sql), run the migration, and act as each person the way PostgREST
does for a request: one transaction, the authenticated role, and the caller's id in
request.jwt.claims. They check that:

- a Contributor cannot record a decision; a version's author is the caller whatever the client
  sends; every timestamp is the server's;
- an Editor's approval of their own version is refused with four-eyes on, and an approval naming
  the wrong SHA-256 is refused; a version whose SHA-256 is not its plan's is refused, and the
  database's canonical JSON gives the page's SHA-256 for every template plan;
- a version lists the reviewer notes its plan answers, and its plan answers each once and no other;
- nobody, the dashboard included, updates or deletes versions, decisions or the audit log, and
  no audited table can be truncated;
- every action leaves an audit row with the right actor, written by the database;
- the workflow, the roles, the private drafts and the deny list hold.

They need Postgres (initdb, pg_ctl and psql) and are skipped without it. As root, the cluster
runs as the postgres user, since initdb refuses to run as root.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
import shutil
import string
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
STUB = ROOT / "tests" / "hosted_supabase_stub.sql"
NODE = shutil.which("node")


def _pg_bin() -> Path | None:
    for cand in [os.environ.get("TA_PG_BIN"), *(str(Path(p).parent) for p in [shutil.which("initdb")] if p),
                 *sorted(glob.glob("/usr/lib/postgresql/*/bin"), key=lambda p: int(re.sub(r"\D", "", p) or 0), reverse=True),
                 "/usr/local/bin", "/opt/homebrew/bin"]:
        if cand and all((Path(cand) / b).exists() for b in ("initdb", "pg_ctl", "psql")):
            return Path(cand)
    return None


PG_BIN = _pg_bin()
pytestmark = pytest.mark.skipif(PG_BIN is None, reason="Postgres (initdb, pg_ctl, psql) is not installed")


class Refused(Exception):
    pass


class Db:
    """One scratch database. sql() runs as the database owner, as the dashboard's SQL editor does;
    as_() runs one request as a person."""

    def __init__(self, socket_dir: Path):
        self.cmd = [str(PG_BIN / "psql"), "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", str(socket_dir), "-U", "postgres", "-d", "planner"]

    def _run(self, text: str) -> list[str]:
        r = subprocess.run(self.cmd, input=text, capture_output=True, text=True)
        if r.returncode != 0:
            m = re.search(r"ERROR:\s+(.*)", r.stderr)
            raise Refused(m.group(1).strip() if m else r.stderr.strip())
        return [line for line in r.stdout.splitlines() if line != ""]

    def sql(self, text: str) -> list[str]:
        return self._run(text)

    def as_(self, who: str | None, text: str, role: str = "authenticated") -> list[str]:
        claims = {"role": role}
        if who:
            claims["sub"] = who
        return self._run(f"begin;\nset local role {role};\nset local request.jwt.claims to {lit(json.dumps(claims))};\n{text};\ncommit;\n")

    def refused(self, who: str | None, text: str, role: str = "authenticated") -> str:
        with pytest.raises(Refused) as e:
            self.as_(who, text, role)
        return str(e.value)

    def one(self, text: str) -> str:
        rows = self.sql(text)
        assert len(rows) == 1, rows
        return rows[0]


def lit(s: str) -> str:
    tag = "q" + "".join(random.choices(string.ascii_lowercase, k=8))
    assert f"${tag}$" not in s
    return f"${tag}${s}${tag}$"


def canon(v) -> str:
    """The page's canonical JSON for plans (strings, booleans, null, arrays, objects with ASCII keys)."""
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(plan: dict) -> str:
    return hashlib.sha256(canon(plan).encode("utf-8")).hexdigest()


def b36(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + out
    return out or "0"


def new_id(hid: str) -> str:
    return f"{hid}~{b36(int(time.time() * 1000))}~{''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=4))}"


def plan_for(hid: str, words: str = "Check the household's wishes before any step.") -> dict:
    return {"schema_version": "1", "household_id": hid, "record_is_synthetic": True, "status": "draft for officer review",
            "summary": {"text": words, "confidence": "Likely"}, "pathway_suggestions": [], "steps": [], "officer_checks": [], "risks": []}


@pytest.fixture(scope="module")
def db():
    base = Path(tempfile.mkdtemp(prefix="ta-planner-pg-"))
    prefix: list[str] = []
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        import pwd
        try:
            pw = pwd.getpwnam("postgres")
        except KeyError:
            pytest.skip("running as root and there is no postgres user to run the cluster")
        os.chown(base, pw.pw_uid, pw.pw_gid)
        prefix = ["runuser", "-u", "postgres", "--"] if shutil.which("runuser") else ["su", "postgres", "-c"]
        if prefix[0] == "su":
            pytest.skip("running as root without runuser")
    data = base / "data"
    run = lambda args: subprocess.run(prefix + [str(a) for a in args], check=True, capture_output=True, text=True)  # noqa: E731
    run([PG_BIN / "initdb", "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--locale=C"])
    run([PG_BIN / "pg_ctl", "-D", data, "-o", f"-k {base} -c listen_addresses='' -c fsync=off", "-l", base / "log", "-w", "start"])
    try:
        boot = Db(base)
        boot.cmd[boot.cmd.index("planner")] = "postgres"
        boot.sql("create database planner")
        d = Db(base)
        d.sql("alter database planner set timezone to 'UTC'")   # as on Supabase
        d.sql(STUB.read_text(encoding="utf-8"))
        assert MIGRATIONS, "no migration in supabase/migrations"
        for m in MIGRATIONS:
            d.sql(m.read_text(encoding="utf-8"))
        yield d
    finally:
        subprocess.run(prefix + [str(PG_BIN / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"], capture_output=True)
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="module")
def people(db):
    """Made-up people at every level, plus one signed-in person who is not a member and one whose
    access was removed. Ids are random, so no fixed number appears in the repo."""
    roles = {"owner": "owner", "editor": "editor", "editor2": "editor", "contributor": "contributor",
             "contributor2": "contributor", "viewer": "viewer", "removed": "contributor"}
    ids = {k: str(uuid.uuid4()) for k in [*roles, "outsider"]}
    db.sql("insert into auth.users (id, email) values " + ", ".join(f"('{v}', '{k}@planner.test')" for k, v in ids.items()))
    db.sql("insert into public.members (user_id, role, display_name) values "
           + ", ".join(f"('{ids[k]}', '{r}', 'Officer {k}')" for k, r in roles.items()))
    db.sql(f"update public.members set active = false where user_id = '{ids['removed']}'")
    return ids


class Flow:
    """The page's calls, as the SQL that PostgREST runs for them (app/src/hosted.js)."""

    def __init__(self, db: Db, people: dict):
        self.db, self.p = db, people

    def save(self, who: str, hid: str, plan: dict | None = None, *, sha256: str | None = None, extra: str = "", extra_vals: str = "") -> str:
        plan = plan or plan_for(hid)
        vid = new_id(hid)
        self.db.as_(self.p[who], f"insert into public.versions (id, household_id, source, from_source, plan, screen, sha256, prompt_sha256{extra}) values "
                    f"({lit(vid)}, '{hid}', 'template', null, {lit(json.dumps(plan))}::jsonb, '{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, "
                    f"'{sha256 or sha(plan)}', null{extra_vals})")
        key = f"{self.p[who]}/{vid}"
        self.pointer(who, hid, "drafting", key)
        return key

    def pointer(self, who: str, hid: str, status: str, key: str):
        self.db.as_(self.p[who], f"insert into public.files (household_id, status, version_id) values ('{hid}', '{status}', '{key}') "
                    f"on conflict (household_id) do update set status = excluded.status, version_id = excluded.version_id")

    def submit(self, who: str, hid: str, key: str):
        self.pointer(who, hid, "submitted", key)

    def decide(self, who: str, hid: str, decision: str, key: str | None, plan_sha: str | None, extra: str = ""):
        cols = "id, household_id, decision, version_id, plan_sha256" + (", note" if decision == "returned" else "") + (", reason" if decision == "rejected" else "")
        vals = f"{lit(new_id(hid))}, '{hid}', '{decision}', {lit(key) if key else 'null'}, {lit(plan_sha) if plan_sha else 'null'}" \
            + (", 'What needs to change.'" if decision == "returned" else "") + (", 'changed'" if decision == "rejected" else "")
        self.db.as_(self.p[who], f"insert into public.decisions ({cols}{extra}) values ({vals})")

    def version_sha(self, key: str) -> str:
        return self.db.one(f"select sha256 from public.versions where key = '{key}'")


@pytest.fixture()
def flow(db, people):
    return Flow(db, people)


def fresh_household(db: Db) -> str:
    used = set(db.sql("select household_id from public.files union select household_id from public.versions union select household_id from public.drafts "
                      "union select household_id from public.events where household_id is not null union select household_id from public.private_drafts "
                      "union select household_id from public.checks union select household_id from public.tasks "
                      "union select household_id from public.notices union select household_id from public.reviews"))
    for n in range(1, 10000):
        hid = f"SYN-{n:04d}"
        if hid not in used:
            return hid
    raise AssertionError("no household left")


# ============================================================== reads

def test_members_read_and_nobody_else_does(db, people, flow):
    hid = fresh_household(db)
    flow.save("contributor", hid)
    assert int(db.as_(people["viewer"], "select count(*) from public.versions")[0]) >= 1
    for t in ["members", "versions", "decisions", "files", "checks", "moves", "config", "audit", "events", "drafts"]:
        # Signed in but not a member, or a member whose access was removed: nothing.
        assert db.as_(people["outsider"], f"select count(*) from public.{t}") == ["0"], t
        assert db.as_(people["removed"], f"select count(*) from public.{t}") == ["0"], t
        # Not signed in at all: no access to the table.
        assert "permission denied" in db.refused(None, f"select count(*) from public.{t}", role="anon"), t


# ============================================================== who and when

def test_a_contributor_cannot_record_a_decision(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    flow.submit("contributor", hid, key)
    msg = db.refused(people["contributor2"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256) "
                     f"values ({lit(new_id(hid))}, '{hid}', 'approved', '{key}', '{flow.version_sha(key)}')")
    assert "only an Editor or the owner" in msg or "row-level security" in msg
    assert db.one(f"select count(*) from public.decisions where household_id = '{hid}'") == "0"


def test_a_versions_author_is_the_caller_whatever_the_client_sends(db, people, flow):
    hid = fresh_household(db)
    plan = plan_for(hid)
    vid = new_id(hid)
    db.as_(people["contributor"], f"insert into public.versions (id, author, household_id, source, plan, screen, sha256) values "
           f"({lit(vid)}, '{people['editor']}', '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, "
           f"'{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, '{sha(plan)}')")
    assert db.one(f"select author from public.versions where id = {lit(vid)}") == people["contributor"]
    assert db.one(f"select key from public.versions where id = {lit(vid)}") == f"{people['contributor']}/{vid}"
    # The same for a decision: the caller, never the author the client names.
    key = f"{people['contributor']}/{vid}"
    flow.submit("contributor", hid, key)
    did = new_id(hid)
    db.as_(people["editor"], f"insert into public.decisions (id, author, household_id, decision, version_id, plan_sha256) values "
           f"({lit(did)}, '{people['owner']}', '{hid}', 'approved', '{key}', '{sha(plan)}')")
    assert db.one(f"select author from public.decisions where id = {lit(did)}") == people["editor"]


def test_every_timestamp_comes_from_the_server(db, people, flow):
    hid = fresh_household(db)
    plan = plan_for(hid)
    vid = new_id(hid)
    old = "'2001-02-03T04:05:06Z'"
    db.as_(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256, created_at, version) values "
           f"({lit(vid)}, '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, "
           f"'{{\"passed\": true, \"spec_version\": \"1\", \"checked_at\": \"2001-02-03\"}}'::jsonb, '{sha(plan)}', {old}, 42)")
    key = f"{people['contributor']}/{vid}"
    db.as_(people["contributor"], f"insert into public.files (household_id, status, version_id, updated_at, updated_by, assignee, assigned_at) values "
           f"('{hid}', 'submitted', '{key}', {old}, '{people['owner']}', '{people['contributor']}', {old})")
    db.as_(people["contributor"], f"insert into public.checks (household_id, check_id, state, updated_by, updated_at) values "
           f"('{hid}', 'general.duty', 'done', '{people['owner']}', {old})")
    db.as_(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256, decided_at, four_eyes) values "
           f"({lit(new_id(hid))}, '{hid}', 'approved', '{key}', '{sha(plan)}', {old}, false)")
    db.as_(people["contributor"], f"insert into public.moves (household_id, stage, note, updated_by, updated_at) values "
           f"('{hid}', 'referral', '', '{people['owner']}', {old})")
    db.as_(people["viewer"], f"insert into public.events (household_id, action, detail, actor, at) values "
           f"('{hid}', 'pack_exported', 'plan pack (.md)', '{people['owner']}', {old})")
    recent = "> now() - interval '10 minutes'"
    for q in [f"select created_at {recent} and version = 1 and (screen ->> 'checked_at')::timestamptz {recent} from public.versions where id = {lit(vid)}",
              f"select updated_at {recent} and assigned_at {recent} and updated_by = '{people['contributor']}' from public.files where household_id = '{hid}'",
              f"select updated_at {recent} and updated_by = '{people['contributor']}' from public.checks where household_id = '{hid}'",
              f"select decided_at {recent} and four_eyes from public.decisions where household_id = '{hid}'",
              f"select updated_at {recent} and updated_by = '{people['contributor']}' from public.moves where household_id = '{hid}'",
              f"select at {recent} and actor = '{people['viewer']}' from public.events where household_id = '{hid}'",
              f"select bool_and(at {recent}) from public.audit where household_id = '{hid}'"]:
        assert db.one(q) == "t", q


# ============================================================== fingerprints and four-eyes

def test_a_version_must_carry_its_plans_sha256(db, people, flow):
    hid = fresh_household(db)
    plan = plan_for(hid)
    msg = db.refused(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256) values "
                     f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, "
                     f"'{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, '{sha(plan_for(hid, 'Another plan.'))}')")
    assert "SHA-256 does not match the plan" in msg
    # A plan for another household, a record that is not synthetic, or one the screen did not pass.
    other = plan_for("SYN-9999")
    assert "not for this synthetic household" in db.refused(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256) values "
        f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(other))}::jsonb, '{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, '{sha(other)}')")
    real = dict(plan, record_is_synthetic=False)
    assert "not for this synthetic household" in db.refused(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256) values "
        f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(real))}::jsonb, '{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, '{sha(real)}')")
    assert "passed the screen" in db.refused(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256) values "
        f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, '{{\"passed\": false, \"spec_version\": \"1\"}}'::jsonb, '{sha(plan)}')")
    # Household ids are synthetic on every table.
    for t, cols, vals in [("files", "household_id", "'HH-0001'"), ("checks", "household_id, check_id, state", "'HH-0001', 'general.duty', 'done'"),
                          ("events", "household_id, action", "'HH-0001', 'pack_exported'")]:
        assert "check constraint" in db.refused(people["contributor"], f"insert into public.{t} ({cols}) values ({vals})"), t


def test_a_version_lists_the_reviewer_notes_its_plan_answers(db, people, flow):
    hid = fresh_household(db)
    note = {"id": "review-1", "kind": "returned", "text": "Add the risks of a move out of the district."}
    answered = plan_for(hid)
    answered["responds_to_review"] = [{"note": "review-1", "change": "The risks now include a move out of the district.", "confidence": "Likely"}]
    key = flow.save("contributor", hid, answered, extra=", review", extra_vals=f", {lit(json.dumps([note]))}::jsonb")
    assert json.loads(db.one(f"select review from public.versions where key = '{key}'")) == [note]
    assert db.one(f"select review from public.versions where key = '{flow.save('contributor', hid)}'") == "[]"

    def insert(plan: dict, review: str) -> str:
        return db.refused(people["contributor"], f"insert into public.versions (id, household_id, source, plan, screen, sha256, review) values "
                          f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, '{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, "
                          f"'{sha(plan)}', {review})")
    notes = lambda v: f"{lit(json.dumps(v))}::jsonb"  # noqa: E731
    answer_twice = dict(answered, responds_to_review=answered["responds_to_review"] * 2)
    for plan, review, words in [
        (answered, notes([]), "answer each reviewer note"),                            # an answer to a note it does not list
        (plan_for(hid), notes([note]), "answer each reviewer note"),                   # a note it does not answer
        (answer_twice, notes([note]), "answer each reviewer note"),                    # a note answered twice
        (answered, notes([note, note]), "its own id"),
        (answered, notes([dict(note, id="note-1")]), "its own id"),
        (answered, notes([dict(note, kind="approved")]), "its own id"),
        (answered, notes([{"id": "review-1", "kind": "returned"}]), "its own id"),
        (answered, notes(["review-1"]), "its own id"),
        (answered, notes({"review-1": note}), "must be a list"),
        (answered, notes([dict(note, id=f"review-{i}") for i in range(1, 7)]), "at most five"),
        (answered, notes([dict(note, text="x" * 9000)]), "check constraint"),
    ]:
        assert words in insert(plan, review), (plan.get("responds_to_review"), review)


def test_an_editors_own_version_cannot_be_approved_with_four_eyes_on(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("editor", hid)
    flow.submit("editor", hid, key)
    msg = db.refused(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256) "
                     f"values ({lit(new_id(hid))}, '{hid}', 'approved', '{key}', '{flow.version_sha(key)}')")
    assert "four-eyes is on" in msg
    # The four-eyes flag a client sends is ignored: the database reads the setting.
    assert "four-eyes is on" in db.refused(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256, four_eyes) "
                                           f"values ({lit(new_id(hid))}, '{hid}', 'approved', '{key}', '{flow.version_sha(key)}', false)")
    # Another editor can approve it; with four-eyes off the author can, and the decision says it was off.
    flow.decide("editor2", hid, "approved", key, flow.version_sha(key))
    assert db.one(f"select four_eyes from public.decisions where household_id = '{hid}'") == "t"
    hid2 = fresh_household(db)
    key2 = flow.save("editor", hid2)
    flow.submit("editor", hid2, key2)
    db.as_(people["editor2"], "update public.config set four_eyes = false where key = 'workflow'")
    try:
        flow.decide("editor", hid2, "approved", key2, flow.version_sha(key2))
        assert db.one(f"select four_eyes from public.decisions where household_id = '{hid2}'") == "f"
    finally:
        db.as_(people["editor2"], "update public.config set four_eyes = true where key = 'workflow'")


def test_an_approval_naming_the_wrong_sha256_is_refused(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    flow.submit("contributor", hid, key)
    wrong = sha(plan_for(hid, "A different plan from the one saved."))
    msg = db.refused(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256) "
                     f"values ({lit(new_id(hid))}, '{hid}', 'approved', '{key}', '{wrong}')")
    assert "SHA-256 does not match the version" in msg
    assert "SHA-256 does not match the version" in db.refused(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id) "
                                                             f"values ({lit(new_id(hid))}, '{hid}', 'approved', '{key}')")
    flow.decide("editor", hid, "approved", key, flow.version_sha(key))


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_databases_canonical_json_gives_the_pages_sha256(db, tmp_path):
    """The page's own canon() (from app/src/page.js) and its template, for all 200 records, plus
    awkward strings: the database's SHA-256 of each plan must equal the page's."""
    from tamarket import moveon as M
    patterns = tmp_path / "fdcore_patterns.json"
    patterns.write_text(json.dumps(M.fdcore_patterns()), encoding="utf-8")
    out = subprocess.run([NODE, str(ROOT / "tests" / "hosted_js_run.mjs"), "canon", str(ROOT), str(patterns)], capture_output=True, text=True, check=True)
    rows = json.loads(out.stdout)
    assert len(rows) >= 200
    got = db.sql(f"select x ->> 'id', private.plan_sha256(x -> 'plan'), private.canon_json(x -> 'plan') = x ->> 'canon' "
                 f"from jsonb_array_elements({lit(json.dumps(rows))}::jsonb) as x")
    want = {r["id"]: r["sha256"] for r in rows}
    assert len(got) == len(rows)
    for line in got:
        rid, h, same = line.split("|")
        assert (h, same) == (want[rid], "t"), rid


# ============================================================== insert-only

def test_nobody_updates_or_deletes_versions_decisions_or_the_audit_log(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    flow.submit("contributor", hid, key)
    flow.decide("editor", hid, "approved", key, flow.version_sha(key))
    db.as_(people["viewer"], f"insert into public.events (household_id, action, detail) values ('{hid}', 'pack_exported', 'data (.json)')")
    db.as_(None, f"insert into public.drafts (requested_by, household_id, passed) values ('{people['contributor']}', '{hid}', true)", role="service_role")
    where = f"where household_id = '{hid}'"
    stmts = {
        "versions": [f"update public.versions set plan = plan {where}", f"delete from public.versions {where}"],
        "decisions": [f"update public.decisions set note = 'changed' {where}", f"delete from public.decisions {where}"],
        "audit": [f"update public.audit set detail = 'changed' {where}", f"delete from public.audit {where}"],
        "events": [f"update public.events set detail = 'changed' {where}", f"delete from public.events {where}"],
        "drafts": [f"update public.drafts set passed = false {where}", f"delete from public.drafts {where}"],
    }
    for table, qs in stmts.items():
        for q in qs:
            for who in ["contributor", "editor", "owner"]:
                msg = db.refused(people[who], q)
                assert "permission denied" in msg or "insert-only" in msg, (table, who, q, msg)
            # The service role (the function's key) and the dashboard are refused too.
            msg = db.refused(None, q, role="service_role")
            assert "permission denied" in msg or "insert-only" in msg, (table, q, msg)
            with pytest.raises(Refused, match="insert-only"):
                db.sql(q)
    for table in ["members", "versions", "decisions", "files", "checks", "moves", "config", "events", "drafts", "audit"]:
        with pytest.raises(Refused, match="cannot be truncated"):
            db.sql(f"truncate public.{table} cascade")
        assert "permission denied" in db.refused(people["owner"], f"truncate public.{table}"), table
    assert db.one(f"select count(*) from public.versions where household_id = '{hid}'") == "1"
    assert db.one(f"select count(*) from public.decisions where household_id = '{hid}'") == "1"


def test_people_cannot_write_the_audit_log_or_take_delete_or_truncate_rights(db, people):
    assert "permission denied" in db.refused(people["owner"], "insert into public.audit (actor_role, table_name, op, row_key, action, change) "
                                             "values ('authenticated', 'files', 'INSERT', 'x', 'plan_approved', '{}')")
    tables = ["members", "versions", "decisions", "files", "checks", "moves", "config", "events", "drafts", "private_drafts", "deny_terms", "audit"]
    for t in tables:
        for role in ["anon", "authenticated", "service_role"]:
            for priv in ["DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]:
                assert db.one(f"select has_table_privilege('{role}', 'public.{t}', '{priv}')") == "f", (t, role, priv)
        assert db.one(f"select has_table_privilege('anon', 'public.{t}', 'SELECT')") == "f", t
    for t in ["versions", "decisions", "events", "drafts", "audit"]:
        assert db.one(f"select has_table_privilege('authenticated', 'public.{t}', 'UPDATE')") == "f", t


# ============================================================== the audit log

def test_every_action_leaves_an_audit_row_with_the_right_actor(db, people, flow):
    hid = fresh_household(db)
    start = db.one("select coalesce(max(id), 0) from public.audit")
    key = flow.save("contributor", hid)                                                    # plan_saved + plan_pointer_set
    db.as_(people["contributor"], f"update public.files set assignee = '{people['contributor']}' where household_id = '{hid}'")   # assigned
    db.as_(people["contributor"], f"insert into public.checks (household_id, check_id, state) values ('{hid}', 'general.duty', 'done')")  # check_updated
    flow.submit("contributor", hid, key)                                                    # plan_submitted
    flow.decide("editor", hid, "returned", key, flow.version_sha(key))                      # plan_returned
    key2 = flow.save("contributor2", hid)                                                   # plan_saved + plan_pointer_set
    flow.submit("contributor2", hid, key2)                                                  # plan_submitted
    flow.decide("editor2", hid, "approved", key2, flow.version_sha(key2))                   # plan_approved
    db.as_(people["contributor2"], f"insert into public.moves (household_id, stage, pathway_id, note) values ('{hid}', 'referral', 'social-housing', '')")  # progress_updated
    db.as_(people["viewer"], f"insert into public.events (household_id, action, detail) values ('{hid}', 'pack_exported', 'plan pack (.md)')")  # pack_exported
    db.as_(None, f"insert into public.drafts (requested_by, household_id, passed, rules, problem_count) values "
           f"('{people['contributor']}', '{hid}', false, '{{decision,person}}', 3)", role="service_role")   # draft_failed_screen
    db.as_(people["editor"], f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256) values "
           f"({lit(new_id(hid))}, '{hid}', 'reopened', '{key2}', '{flow.version_sha(key2)}')")                # reopened
    rows = [r.split("|") for r in db.sql(f"select action, actor, table_name, detail, actor_role from public.audit "
                                          f"where id > {start} and household_id = '{hid}' order by id")]
    p = people
    want = [
        ("plan_saved", p["contributor"], "versions", "version 1, from the template"),
        ("plan_pointer_set", p["contributor"], "files", "drafting, version 1"),
        ("assigned", p["contributor"], "files", ""),
        ("check_updated", p["contributor"], "checks", "general.duty: checked"),
        ("plan_submitted", p["contributor"], "files", "version 1"),
        ("plan_returned", p["editor"], "decisions", "with a note"),
        ("plan_saved", p["contributor2"], "versions", "version 2, from the template"),
        ("plan_pointer_set", p["contributor2"], "files", "drafting, version 2"),
        ("plan_submitted", p["contributor2"], "files", "version 2"),
        ("plan_approved", p["editor2"], "decisions", "version 2, four-eyes on"),
        ("progress_updated", p["contributor2"], "moves", "Referral or application made, Social housing"),
        ("pack_exported", p["viewer"], "events", "plan pack (.md)"),
        ("draft_failed_screen", p["contributor"], "drafts", "3 problems: decision, person"),
        ("reopened", p["editor"], "decisions", ""),
    ]
    assert [tuple(r[:4]) for r in rows] == want
    assert {r[4] for r in rows} == {"authenticated", "service_role"}
    # A change from the dashboard is logged too, with no person and the database role.
    db.sql(f"update public.members set display_name = 'Officer viewer, renamed' where user_id = '{p['viewer']}'")
    last = db.one("select action || '|' || coalesce(actor::text, '') || '|' || actor_role || '|' || detail from public.audit order by id desc limit 1")
    assert last == "member_changed||database|name changed"
    # An update that changes nothing leaves no row.
    n = db.one("select count(*) from public.audit")
    db.as_(p["contributor"], f"update public.checks set state = 'done' where household_id = '{hid}' and check_id = 'general.duty'")
    assert db.one("select count(*) from public.audit") == n


def test_the_audit_row_holds_the_change(db, people, flow):
    hid = fresh_household(db)
    flow.save("contributor", hid)
    db.as_(people["contributor"], f"insert into public.checks (household_id, check_id, state) values ('{hid}', 'general.wishes', 'done')")
    db.as_(people["contributor2"], f"update public.checks set state = 'na' where household_id = '{hid}' and check_id = 'general.wishes'")
    change = json.loads(db.one(f"select change from public.audit where household_id = '{hid}' and table_name = 'checks' order by id desc limit 1"))
    assert change["old"]["state"] == "done" and change["new"]["state"] == "na"
    assert change["new"]["updated_by"] == people["contributor2"] and change["old"]["updated_by"] == people["contributor"]
    assert set(change["new"]) == {"state", "updated_by", "updated_at"}


# ============================================================== the workflow

def test_a_decision_needs_the_submitted_version_once_per_submission(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    s = flow.version_sha(key)
    ins = lambda decision: (f"insert into public.decisions (id, household_id, decision, version_id, plan_sha256, note, reason) values "  # noqa: E731
                            f"({lit(new_id(hid))}, '{hid}', '{decision}', '{key}', '{s}', 'What needs to change.', 'changed')")
    assert "not the one submitted" in db.refused(people["editor"], ins("approved"))
    flow.submit("contributor", hid, key)
    flow.decide("editor", hid, "returned", key, s)
    assert "not been submitted again" in db.refused(people["editor"], ins("approved"))
    flow.submit("contributor", hid, key)
    flow.decide("editor", hid, "approved", key, s)
    assert "not been submitted again" in db.refused(people["editor2"], ins("rejected"))
    # A decided plan is locked: no new version and no pointer move until an Editor reopens it.
    with pytest.raises(Refused, match="reopen it first"):
        flow.save("contributor", hid)
    with pytest.raises(Refused, match="reopen it first"):
        flow.submit("contributor", hid, key)
    flow.decide("editor", hid, "reopened", key, s)
    assert "only an approved or rejected plan can be reopened" in db.refused(
        people["editor"], f"insert into public.decisions (id, household_id, decision) values ({lit(new_id(hid))}, '{hid}', 'reopened')")
    key2 = flow.save("contributor", hid)
    assert db.one(f"select version from public.versions where key = '{key2}'") == "2"   # the refused save took no number
    # A version of another household cannot be pointed at or decided.
    other = fresh_household(db)
    key_other = flow.save("contributor", other)
    assert "another household" in db.refused(people["contributor"], f"update public.files set version_id = '{key_other}' where household_id = '{hid}'")


def test_progress_needs_an_approved_plan_and_a_rejected_plan_locks_the_checks(db, people, flow):
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    move = f"insert into public.moves (household_id, stage, note) values ('{hid}', 'referral', '') on conflict (household_id) do update set stage = excluded.stage"
    assert "approved plan" in db.refused(people["contributor"], move)
    flow.submit("contributor", hid, key)
    flow.decide("editor", hid, "rejected", key, flow.version_sha(key))
    assert "approved plan" in db.refused(people["contributor"], move)
    assert "rejected" in db.refused(people["contributor"], f"insert into public.checks (household_id, check_id, state) values ('{hid}', 'general.duty', 'done')")
    flow.decide("editor", hid, "reopened", key, flow.version_sha(key))
    db.as_(people["contributor"], f"insert into public.checks (household_id, check_id, state) values ('{hid}', 'general.duty', 'done')")
    flow.submit("contributor", hid, key)
    flow.decide("editor2", hid, "approved", key, flow.version_sha(key))
    db.as_(people["contributor"], move)
    assert db.one(f"select stage from public.moves where household_id = '{hid}'") == "referral"


def test_the_pointers_time_moves_only_with_the_pointer(db, people, flow):
    """The page works out "returned" by comparing the pointer's time with the last decision's, so
    taking a household must not look like a new submission."""
    hid = fresh_household(db)
    key = flow.save("contributor", hid)
    flow.submit("contributor", hid, key)
    before = db.one(f"select updated_at from public.files where household_id = '{hid}'")
    db.as_(people["contributor2"], f"update public.files set assignee = '{people['contributor2']}', updated_at = now() + interval '1 day' where household_id = '{hid}'")
    assert db.one(f"select updated_at from public.files where household_id = '{hid}'") == before
    assert db.one(f"select updated_by from public.files where household_id = '{hid}'") == people["contributor"]
    # A person takes a household only for themselves.
    assert "only for themselves" in db.refused(people["contributor"], f"update public.files set assignee = '{people['viewer']}' where household_id = '{hid}'")


# ============================================================== roles

def test_a_viewer_reads_but_writes_nothing(db, people, flow):
    hid = fresh_household(db)
    flow.save("contributor", hid)
    v = people["viewer"]
    plan = plan_for(hid)
    assert "needs a signed-in Contributor" in db.refused(v, f"insert into public.versions (id, household_id, source, plan, screen, sha256) values "
        f"({lit(new_id(hid))}, '{hid}', 'template', {lit(json.dumps(plan))}::jsonb, '{{\"passed\": true, \"spec_version\": \"1\"}}'::jsonb, '{sha(plan)}')")
    for q in [f"insert into public.checks (household_id, check_id, state) values ('{hid}', 'general.duty', 'done')",
              f"insert into public.files (household_id, assignee) values ('{fresh_household(db)}', '{v}')",
              "insert into public.config (key, four_eyes) values ('workflow', false) on conflict (key) do update set four_eyes = excluded.four_eyes"]:
        assert "row-level security" in db.refused(v, q), q
    # An update that row-level security does not let them make changes no row.
    db.as_(v, f"update public.files set status = 'submitted' where household_id = '{hid}'")
    db.as_(v, "update public.config set four_eyes = false")
    assert db.one(f"select status from public.files where household_id = '{hid}'") == "drafting"
    assert db.one("select four_eyes from public.config") == "t"
    assert db.one(f"select count(*) from public.versions where household_id = '{hid}'") == "1"


def test_only_the_owner_manages_members(db, people):
    new = str(uuid.uuid4())
    db.sql(f"insert into auth.users (id, email) values ('{new}', '{'@'.join(['new', 'planner.test'])}')")
    assert "row-level security" in db.refused(people["editor"], f"insert into public.members (user_id, role) values ('{new}', 'viewer')")
    db.as_(people["owner"], f"insert into public.members (user_id, role, display_name) values ('{new}', 'viewer', 'Officer new')")
    assert db.one(f"select invited_by from public.members where user_id = '{new}'") == people["owner"]
    db.as_(people["editor"], f"update public.members set role = 'owner' where user_id = '{people['editor']}'")   # RLS: no row changes
    assert db.one(f"select role from public.members where user_id = '{people['editor']}'") == "editor"
    assert "your own role" in db.refused(people["owner"], f"update public.members set role = 'viewer' where user_id = '{people['owner']}'")
    with pytest.raises(Refused, match="active owner"):
        db.sql(f"update public.members set active = false where user_id = '{people['owner']}'")
    db.as_(people["owner"], f"update public.members set role = 'contributor' where user_id = '{new}'")
    assert db.one(f"select detail from public.audit where table_name = 'members' and row_key = '{new}' order by id desc limit 1") == "role viewer to contributor"
    # A member's account cannot be deleted from under their records: access is removed with active.
    with pytest.raises(Refused, match="foreign key"):
        db.sql(f"delete from auth.users where id = '{people['contributor']}'")


def test_private_drafts_are_private(db, people):
    hid = fresh_household(db)
    db.as_(people["contributor"], f"insert into public.private_drafts (household_id, working) values ('{hid}', '{{\"plan\": {{}}}}'::jsonb) "
           f"on conflict (user_id, household_id) do update set working = excluded.working")
    assert db.as_(people["contributor"], f"select count(*) from public.private_drafts where household_id = '{hid}'") == ["1"]
    for who in ["contributor2", "editor", "owner", "viewer"]:
        assert db.as_(people[who], f"select count(*) from public.private_drafts where household_id = '{hid}'") == ["0"], who
    # Nobody can write a draft as someone else, and private drafts never reach the audit log.
    db.as_(people["editor"], f"insert into public.private_drafts (user_id, household_id, working) values ('{people['contributor']}', '{hid}', null)")
    assert db.one(f"select count(*) from public.private_drafts where household_id = '{hid}' and user_id = '{people['editor']}'") == "1"
    assert db.one("select count(*) from public.audit where table_name = 'private_drafts'") == "0"


def test_drafts_are_written_by_the_function_only_and_the_deny_list_is_hidden(db, people):
    hid = fresh_household(db)
    assert "permission denied" in db.refused(people["owner"], f"insert into public.drafts (requested_by, household_id, passed) values ('{people['owner']}', '{hid}', true)")
    db.as_(None, f"insert into public.drafts (requested_by, household_id, passed, rules, problem_count, plan_sha256) values "
           f"('{people['contributor']}', '{hid}', true, '{{}}', 0, '{'0' * 64}')", role="service_role")
    assert db.one(f"select action || '|' || actor || '|' || detail from public.audit where table_name = 'drafts' and household_id = '{hid}'") \
        == f"draft_created|{people['contributor']}|passed the screen"
    db.sql("insert into public.deny_terms (term) values ('zzq' || 'placeholder')")
    assert "permission denied" in db.refused(people["owner"], "select count(*) from public.deny_terms")
    assert db.as_(None, "select count(*) from public.deny_terms", role="service_role") == ["1"]
    assert db.one("select count(*) from public.audit where table_name = 'deny_terms'") == "0"
    # Page events: only the listed actions, and the actor is the caller.
    assert "check constraint" in db.refused(people["viewer"], "insert into public.events (action) values ('plan_approved')")
    assert "signed-in member" in db.refused(people["outsider"], "insert into public.events (action) values ('audit_exported')")


# ============================================================== follow-ups (phase 6)

def new_task_id() -> str:
    return "task~" + "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=8)) + "~" + "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=4))


def add_task(tid: str, hid: str, text: str = "Arrange a viewing of the offered home", assignee: str | None = None) -> str:
    return (f"insert into public.tasks (id, household_id, text, kind, due, assignee) values ({lit(tid)}, '{hid}', {lit(text)}, 'viewing', '2026-11-12', "
            f"{lit(assignee) if assignee else 'null'})")


def test_follow_ups_record_who_and_when_and_are_audited(db, people):
    hid, c, e, tid = fresh_household(db), people["contributor"], people["editor"], new_task_id()
    db.as_(c, add_task(tid, hid, assignee=c))
    assert db.sql(f"select created_by, done, coalesce(done_by::text, '-') from public.tasks where id = {lit(tid)}") == [f"{c}|f|-"]
    assert "permission denied" in db.refused(c, f"insert into public.tasks (id, household_id, text, created_by) values ({lit(new_task_id())}, '{hid}', 'x', '{e}')")
    db.as_(e, f"update public.tasks set done = true where id = {lit(tid)}")
    assert db.one(f"select done_by from public.tasks where id = {lit(tid)}") == e
    db.as_(c, f"update public.tasks set done = false where id = {lit(tid)}")
    db.as_(c, f"update public.tasks set due = '2026-11-20' where id = {lit(tid)}")
    db.as_(c, f"update public.tasks set due = '2026-11-20' where id = {lit(tid)}")   # nothing changed: no entry
    rows = db.sql(f"select action || '|' || actor || '|' || detail from public.audit where table_name = 'tasks' and row_key = {lit(tid)} order by id")
    t = "Arrange a viewing of the offered home"
    assert rows == [f"task_added|{c}|{t}", f"task_done|{e}|{t}", f"task_reopened|{c}|{t}", f"task_changed|{c}|{t} (due date)"]


def test_a_follow_ups_owner_is_an_active_member_and_nobody_deletes_one(db, people):
    hid, c, tid = fresh_household(db), people["contributor"], new_task_id()
    assert "active member" in db.refused(c, add_task(tid, hid, assignee=people["removed"]))
    assert "active member" in db.refused(c, add_task(tid, hid, assignee=people["outsider"]))
    db.as_(c, add_task(tid, hid, assignee=people["contributor2"]))
    assert "permission denied" in db.refused(c, f"delete from public.tasks where id = {lit(tid)}")
    assert "permission denied" in db.refused(c, f"update public.tasks set household_id = 'SYN-9999' where id = {lit(tid)}")
    assert "permission denied" in db.refused(people["owner"], "truncate public.tasks")
    # An owner who has since left does not block ticking the follow-up off.
    db.sql(f"update public.members set active = false where user_id = '{people['contributor2']}'")
    try:
        db.as_(c, f"update public.tasks set done = true where id = {lit(tid)}")
        assert db.one(f"select done from public.tasks where id = {lit(tid)}") == "t"
    finally:
        db.sql(f"update public.members set active = true where user_id = '{people['contributor2']}'")


def test_a_viewer_reads_follow_ups_but_cannot_add_or_tick_them(db, people):
    hid, c, v, tid = fresh_household(db), people["contributor"], people["viewer"], new_task_id()
    db.as_(c, add_task(tid, hid))
    assert db.as_(v, f"select count(*) from public.tasks where id = {lit(tid)}") == ["1"]
    assert "row-level security" in db.refused(v, add_task(new_task_id(), hid))
    db.as_(v, f"update public.tasks set done = true where id = {lit(tid)}")
    assert db.one(f"select done from public.tasks where id = {lit(tid)}") == "f"
    assert db.as_(people["outsider"], f"select count(*) from public.tasks where id = {lit(tid)}") == ["0"]
    assert db.as_(people["removed"], f"select count(*) from public.tasks where id = {lit(tid)}") == ["0"]


# ============================================================== notices and review clocks (phase 6.5)

def note(hid: str, kind: str, cols: str, vals: str, n: int = 1) -> str:
    """An officer's notice row, recorded again if it is there. s.213AA rows are for child n."""
    key, child = (f"{hid}~{kind}", "null") if kind == "s208" else (f"{hid}~c{n}~{kind}", str(n))
    return (f"insert into public.notices (id, household_id, kind, child_no, {cols}) values ('{key}', '{hid}', '{kind}', {child}, {vals}) "
            f"on conflict (id) do update set status = excluded.status, sent_on = excluded.sent_on, method = excluded.method, "
            f"asked_on = excluded.asked_on, agreed_on = excluded.agreed_on, info_on = excluded.info_on, refused_on = excluded.refused_on, "
            f"agreed_bodies = excluded.agreed_bodies, declined_bodies = excluded.declined_bodies")


def test_notices_record_who_and_when_refuse_the_future_and_are_audited(db, people):
    hid, c, e = fresh_household(db), people["contributor"], people["editor"]
    db.as_(c, note(hid, "s208", "status, sent_on, method", "'sent', current_date - 3, 'Email'"))
    assert db.one(f"select recorded_by from public.notices where id = '{hid}~s208'") == c
    assert "future" in db.refused(c, note(hid, "s208", "status, sent_on, method", "'sent', current_date + 1, 'Letter'"))
    assert "check constraint" in db.refused(c, note(hid, "s208", "status", "'none'"))           # an s.208 notice is sent or not recorded
    assert "check constraint" in db.refused(c, note(fresh_household(db), "s208", "status, method", "'sent', 'Letter'"))   # sent needs its date
    assert "permission denied" in db.refused(c, f"insert into public.notices (id, household_id, kind, status, sent_on, method, recorded_by) values "
                                                f"('{hid}~s208', '{hid}', 's208', 'sent', current_date, 'Letter', '{e}')")
    db.as_(e, note(hid, "s208", "status, sent_on, method", "'sent', current_date - 2, 'Letter'"))
    assert db.one(f"select recorded_by from public.notices where id = '{hid}~s208'") == e
    rows = db.sql(f"select action || '|' || actor from public.audit where table_name = 'notices' and row_key = '{hid}~s208' order by id")
    assert rows == [f"notice_recorded|{c}", f"notice_changed|{e}"]


def test_a_childs_notices_need_the_agreement_on_record_for_that_child(db, people):
    hid, c = fresh_household(db), people["contributor"]
    assert "agreement" in db.refused(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 1, current_date, 'Letter'"))
    db.as_(c, note(hid, "child", "status, asked_on", "'asked', current_date - 5"))
    assert "agreement" in db.refused(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 1"))   # no information taken before agreement
    db.as_(c, note(hid, "child", "status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                   "'agreed', current_date - 5, current_date - 4, '{gp,education}', '{health_visiting}'"))
    db.as_(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 4"))
    db.as_(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 4, current_date, 'Letter'"))
    db.as_(c, note(hid, "child-education", "status", "'none'"))
    # The agreement for child 1 is not the agreement for child 2: each child has their own.
    assert "agreement" in db.refused(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 4", n=2))
    assert db.sql(f"select id || '|' || status from public.notices where household_id = '{hid}' order by id") == \
        [f"{hid}~c1~child|agreed", f"{hid}~c1~child-education|none", f"{hid}~c1~child-gp|sent"]
    acts = db.sql(f"select action from public.audit where table_name = 'notices' and household_id = '{hid}' order by id")
    assert acts == ["consent_recorded", "consent_recorded", "notice_info_recorded", "notice_recorded", "notice_recorded"]   # recorded when first sent
    assert "check constraint" in db.refused(c, f"insert into public.notices (id, household_id, kind, child_no, status, asked_on) values "
                                                f"('{hid}~child', '{hid}', 'child', null, 'asked', current_date)")      # a child's row names the child
    assert "check constraint" in db.refused(c, f"insert into public.notices (id, household_id, kind, child_no, status, asked_on) values "
                                                f"('{hid}~c3~child', '{hid}', 'child', 2, 'asked', current_date)")      # and its id says which


def test_the_agreement_is_per_body_and_a_notice_follows_that_bodys_information(db, people):
    """s.213AA: the answer is recorded body by body; a notice goes only to a body agreed to, needs the
    information about that body on record, is never dated before the agreement or that information
    (s.213AA(4)), and once one is sent the agreement can neither drop that body nor move after it."""
    hid, c = fresh_household(db), people["contributor"]
    child = lambda cols, vals: note(hid, "child", cols, vals)
    assert "check constraint" in db.refused(c, child("status, asked_on, agreed_on", "'agreed', current_date - 9, current_date - 8"))   # agreed to no body
    assert "check constraint" in db.refused(c, child("status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                                                     "'agreed', current_date - 9, current_date - 8, '{gp}', '{gp}'"))                     # agreed and not
    assert "check constraint" in db.refused(c, child("status, asked_on, agreed_on, agreed_bodies", "'agreed', current_date - 9, current_date - 8, '{dentist}'"))
    assert "check constraint" in db.refused(c, note(hid, "s208", "status, sent_on, method, agreed_bodies", "'sent', current_date, 'Letter', '{gp}'"))
    assert "check constraint" in db.refused(c, child("status, asked_on, info_on", "'asked', current_date - 9, current_date - 9"))      # information sits on a body's row
    db.as_(c, child("status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                    "'agreed', current_date - 9, current_date - 8, '{gp,health_visiting}', '{education}'"))
    assert "agreement to that body" in db.refused(c, note(hid, "child-education", "status, info_on, sent_on, method", "'sent', current_date - 7, current_date, 'Letter'"))
    # No information on record: refused (greatest() alone would pass over the missing date).
    assert "check constraint" in db.refused(c, note(hid, "child-gp", "status, sent_on, method", "'sent', current_date - 7, 'Letter'"))
    # Each body's information has its own date, and the notice follows it.
    db.as_(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 7"))
    db.as_(c, note(hid, "child-health_visiting", "status, info_on", "'info', current_date - 2"))
    assert "before the agreement and the information" in db.refused(c, note(hid, "child-health_visiting", "status, info_on, sent_on, method", "'sent', current_date - 2, current_date - 3, 'Letter'"))
    db.as_(c, note(hid, "child-health_visiting", "status, info_on, sent_on, method", "'sent', current_date - 2, current_date - 2, 'Letter'"))
    assert "before the agreement and the information" in db.refused(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 7, current_date - 9, 'Letter'"))
    db.as_(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 7, current_date - 6, 'Letter'"))
    # A sent notice is locked: its information date, its own date and its status stay.
    gp = f"update public.notices set {{}} where id = '{hid}~c1~child-gp'"
    assert "once sent" in db.refused(c, gp.format("info_on = current_date - 6"))
    assert "once sent" in db.refused(c, gp.format("sent_on = current_date - 5"))
    assert "once sent" in db.refused(c, gp.format("status = 'none', sent_on = null, method = null"))   # so the agreement's locks cannot be lifted
    db.as_(c, gp.format("method = 'Email'"))                                                          # how it was sent may be corrected
    # An answer is not dated before the asking.
    assert "check constraint" in db.refused(c, child("status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                                                     "'agreed', current_date - 8, current_date - 9, '{gp,health_visiting}', '{education}'"))
    assert "check constraint" in db.refused(c, note(hid, "child", "status, asked_on, refused_on, declined_bodies", "'refused', current_date - 2, current_date - 3, '{gp}'", n=2))
    # The agreement keeps a notified body, and cannot be dated after a notice sent on it.
    assert "stay among the bodies agreed" in db.refused(c, child("status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                                                                 "'agreed', current_date - 9, current_date - 8, '{health_visiting}', '{gp,education}'"))
    assert "stay among the bodies agreed" in db.refused(c, child("status, asked_on, refused_on, declined_bodies", "'refused', current_date - 9, current_date - 8, '{gp,health_visiting,education}'"))
    assert "dated after a notice already sent" in db.refused(c, child("status, asked_on, agreed_on, agreed_bodies, declined_bodies",
                                                                      "'agreed', current_date - 9, current_date - 4, '{gp,health_visiting}', '{education}'"))
    detail = db.one(f"select detail from public.audit where table_name = 'notices' and row_key = '{hid}~c1~child' order by id desc limit 1")
    assert detail.startswith("child 1 child: agreed") and detail.endswith("(gp, health_visiting; not education)"), detail


def test_only_the_owner_corrects_a_sent_notice_with_a_listed_reason_and_it_is_audited(db, people):
    """A sent s.213AA notice is locked; public.correct_notice is the owner's way past the lock, with a
    reason from a fixed list, and the audit says it was a correction."""
    hid, c, e, o = fresh_household(db), people["contributor"], people["editor"], people["owner"]
    db.as_(c, note(hid, "child", "status, asked_on, agreed_on, agreed_bodies", "'agreed', current_date - 9, current_date - 8, '{gp}'"))
    db.as_(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 7"))
    db.as_(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 7, current_date - 2, 'Letter'"))
    gp = f"{hid}~c1~child-gp"
    fix = lambda status, sent, info, method, reason: f"select public.correct_notice('{gp}', '{status}', {sent}, {info}, {method}, '{reason}')"
    assert "only the owner" in db.refused(c, fix("sent", "current_date - 6", "current_date - 7", "'Letter'", "wrong_date"))
    assert "only the owner" in db.refused(e, fix("sent", "current_date - 6", "current_date - 7", "'Letter'", "wrong_date"))
    assert "needs its reason" in db.refused(o, fix("sent", "current_date - 6", "current_date - 7", "'Letter'", "the officer said so"))
    assert "before the agreement and the information" in db.refused(o, fix("sent", "current_date - 9", "current_date - 7", "'Letter'", "wrong_date"))   # every other check holds
    db.as_(o, fix("sent", "current_date - 6", "current_date - 7", "'Letter'", "wrong_date"))
    assert db.one(f"select (current_date - sent_on)::text || '|' || recorded_by from public.notices where id = '{gp}'") == f"6|{o}"
    detail = db.one(f"select action || '|' || detail from public.audit where table_name = 'notices' and row_key = '{gp}' order by id desc limit 1")
    assert detail.startswith("notice_corrected|") and detail.endswith("(corrected by the owner: wrong_date)"), detail
    db.as_(o, fix("none", "null", "null", "null", "not_sent"))
    assert db.one(f"select status from public.notices where id = '{gp}'") == "none"
    assert "only a sent s.213AA notice" in db.refused(o, fix("sent", "current_date", "current_date - 7", "'Letter'", "wrong_date"))   # no longer sent
    db.as_(c, note(hid, "s208", "status, sent_on, method", "'sent', current_date - 1, 'Letter'"))
    assert "only a sent s.213AA notice" in db.refused(o, f"select public.correct_notice('{hid}~s208', 'sent', current_date, null, 'Letter', 'wrong_date')")
    # Outside the function the lock holds, for the owner too.
    db.as_(c, note(hid, "child-gp", "status, info_on", "'info', current_date - 7"))
    db.as_(c, note(hid, "child-gp", "status, info_on, sent_on, method", "'sent', current_date - 7, current_date - 1, 'Letter'"))
    assert "once sent" in db.refused(o, f"update public.notices set sent_on = current_date where id = '{gp}'")


def test_a_postgrest_style_upsert_of_a_notice_is_refused_so_the_client_inserts_then_updates(db, people):
    """An upsert through PostgREST sets every column it sends on a conflict, the key included; the
    table grants update on its value columns only, so app/src/hosted.js inserts and, on a taken id,
    updates the value columns (tests/hosted_js_run.mjs checks the client)."""
    hid, c = fresh_household(db), people["contributor"]
    upsert = (f"insert into public.notices (id, household_id, kind, status, sent_on, method) values ('{hid}~s208', '{hid}', 's208', 'sent', current_date, 'Letter') "
              f"on conflict (id) do update set id = excluded.id, household_id = excluded.household_id, kind = excluded.kind, status = excluded.status, "
              f"sent_on = excluded.sent_on, method = excluded.method")
    assert "permission denied" in db.refused(c, upsert)
    db.as_(c, f"insert into public.notices (id, household_id, kind, status, sent_on, method) values ('{hid}~s208', '{hid}', 's208', 'sent', current_date - 1, 'Letter')")
    db.as_(c, f"update public.notices set sent_on = current_date, method = 'Email' where id = '{hid}~s208'")
    assert db.one(f"select method from public.notices where id = '{hid}~s208'") == "Email"


def test_notices_cannot_be_deleted_or_moved_and_a_viewer_writes_none(db, people):
    hid, c, v = fresh_household(db), people["contributor"], people["viewer"]
    db.as_(c, note(hid, "s208", "status, sent_on, method", "'sent', current_date, 'Letter'"))
    assert "permission denied" in db.refused(c, f"delete from public.notices where id = '{hid}~s208'")
    assert "permission denied" in db.refused(c, f"update public.notices set household_id = 'SYN-9999' where id = '{hid}~s208'")
    assert "permission denied" in db.refused(people["owner"], "truncate public.notices")
    assert "row-level security" in db.refused(v, note(fresh_household(db), "s208", "status, sent_on, method", "'sent', current_date, 'Letter'"))
    assert db.as_(v, f"select count(*) from public.notices where id = '{hid}~s208'") == ["1"]
    assert db.as_(people["outsider"], f"select count(*) from public.notices where id = '{hid}~s208'") == ["0"]


def new_review_id() -> str:
    return "review~" + "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=8)) + "~" + "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=4))


def test_reviews_record_who_decided_refuse_bad_dates_and_are_audited(db, people):
    hid, c, e, rid = fresh_household(db), people["contributor"], people["editor"], new_review_id()
    db.as_(c, f"insert into public.reviews (id, household_id, requested_on, assignee) values ('{rid}', '{hid}', current_date - 60, '{c}')")
    assert db.one(f"select created_by from public.reviews where id = '{rid}'") == c
    assert "future" in db.refused(c, f"insert into public.reviews (id, household_id, requested_on) values ('{new_review_id()}', '{hid}', current_date + 1)")
    assert "active member" in db.refused(c, f"insert into public.reviews (id, household_id, requested_on, assignee) values ('{new_review_id()}', '{hid}', current_date, '{people['removed']}')")
    assert "check constraint" in db.refused(c, f"update public.reviews set decided_on = current_date - 61 where id = '{rid}'")
    assert "permission denied" in db.refused(c, f"update public.reviews set requested_on = current_date where id = '{rid}'")
    assert "check constraint" in db.refused(c, f"update public.reviews set agreed_to = current_date - 6 where id = '{rid}'")   # before the statutory date (request + 55)
    db.as_(c, f"update public.reviews set agreed_to = current_date - 5 where id = '{rid}'")                                       # on it
    db.as_(c, f"update public.reviews set agreed_to = current_date + 10 where id = '{rid}'")
    db.as_(e, f"update public.reviews set decided_on = current_date - 1 where id = '{rid}'")
    assert db.one(f"select decided_by from public.reviews where id = '{rid}'") == e
    assert "permission denied" in db.refused(c, f"delete from public.reviews where id = '{rid}'")
    rows = db.sql(f"select action || '|' || actor from public.audit where table_name = 'reviews' and row_key = '{rid}' order by id")
    assert rows == [f"review_requested|{c}", f"review_extended|{c}", f"review_extended|{c}", f"review_decided|{e}"]


def test_a_saved_handover_is_a_page_event(db, people):
    hid, c = fresh_household(db), people["contributor"]
    db.as_(c, f"insert into public.events (household_id, action, detail) values ('{hid}', 'handover_exported', 'since 2026-10-08')")
    assert db.one(f"select actor from public.events where household_id = '{hid}' and action = 'handover_exported'") == c
    assert "check constraint" in db.refused(c, f"insert into public.events (household_id, action) values ('{hid}', 'notice_sent')")


# ============================================================== monitoring decisions (phase 7)

def mon_id() -> str:
    return "mon-" + "".join(random.choices("0123456789abcdef", k=12))


def test_a_monitoring_decision_records_who_and_when_and_is_audited(db, people):
    c, e, mid = people["contributor"], people["editor"], mon_id()
    db.as_(c, f"insert into public.monitor_decisions (id, decision, grade, note) values ('{mid}', 'accepted', 'A2', 'Read with the team.')")
    assert db.one(f"select decided_by from public.monitor_decisions where id = '{mid}'") == c
    assert "permission denied" in db.refused(c, f"insert into public.monitor_decisions (id, decision, grade, decided_by) values ('{mon_id()}', 'accepted', 'A1', '{e}')")
    db.as_(e, f"update public.monitor_decisions set decision = 'rejected', grade = null, reason = 'superseded' where id = '{mid}'")
    db.as_(e, f"update public.monitor_decisions set reason = 'superseded' where id = '{mid}'")   # nothing changed: no entry
    assert db.one(f"select decided_by from public.monitor_decisions where id = '{mid}'") == e
    rows = db.sql(f"select action || '|' || actor from public.audit where table_name = 'monitor_decisions' and row_key = '{mid}' order by id")
    assert rows == [f"monitor_accepted|{c}", f"monitor_changed|{e}"]
    # The change keeps what was decided before and what is decided now, without who or when.
    old, new = db.sql(f"select change -> 'old' ->> 'decision' || '|' || (change -> 'old' ->> 'grade') || '|' || (change -> 'new' ->> 'decision') || '|' || "
                      f"(change -> 'new' ->> 'reason') || '|' || (change -> 'new' ? 'decided_by')::text from public.audit "
                      f"where table_name = 'monitor_decisions' and row_key = '{mid}' and action = 'monitor_changed'")[0].split("|", 1)
    assert [old, new] == ["accepted", "A2|rejected|superseded|false"]


def test_a_monitoring_decision_needs_its_grade_or_reason_and_nobody_deletes_one(db, people):
    c, v, mid = people["contributor"], people["viewer"], mon_id()
    assert "check constraint" in db.refused(c, f"insert into public.monitor_decisions (id, decision) values ('{mon_id()}', 'accepted')")
    assert "check constraint" in db.refused(c, f"insert into public.monitor_decisions (id, decision, grade) values ('{mon_id()}', 'accepted', 'G7')")
    assert "check constraint" in db.refused(c, f"insert into public.monitor_decisions (id, decision) values ('{mon_id()}', 'rejected')")
    assert "check constraint" in db.refused(c, f"insert into public.monitor_decisions (id, decision, reason) values ('{mon_id()}', 'rejected', 'other')")
    assert "check constraint" in db.refused(c, "insert into public.monitor_decisions (id, decision, grade) values ('mon-x', 'accepted', 'A1')")
    db.as_(c, f"insert into public.monitor_decisions (id, decision, reason) values ('{mid}', 'rejected', 'duplicate')")
    assert "permission denied" in db.refused(c, f"delete from public.monitor_decisions where id = '{mid}'")
    assert "permission denied" in db.refused(c, f"update public.monitor_decisions set id = '{mon_id()}' where id = '{mid}'")
    assert "permission denied" in db.refused(people["owner"], "truncate public.monitor_decisions")
    assert "row-level security" in db.refused(v, f"insert into public.monitor_decisions (id, decision, grade) values ('{mon_id()}', 'accepted', 'A1')")
    assert db.as_(v, f"select count(*) from public.monitor_decisions where id = '{mid}'") == ["1"]
    assert db.as_(people["outsider"], f"select count(*) from public.monitor_decisions where id = '{mid}'") == ["0"]
