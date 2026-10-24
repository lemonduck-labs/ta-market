// The draft-plan function's logic. Every outside call (the session check, the database, Claude,
// the clock) is passed in, so node can test it without the network (tests/hosted_js_run.mjs)
// and Deno runs it unchanged (index.ts).
//
// POST {household_id, prompt_sha256} with the caller's session token in Authorization. The
// function checks the session and the caller's role, reads the household's reviewer notes from
// the decisions in the database (never from the caller), builds the drafting prompt from its own
// copy of the synthetic record and those notes (tamarket/spec/prompt.mjs), refuses if the page
// built a different prompt, asks Claude through the Messages API with the owner's key, reads the
// reply with parseReply, screens it against the same notes (tamarket/spec/screen.mjs, with the
// fd-core patterns and the private deny list), records the draft in public.drafts and returns
// {passed, problems, plan}.
//
// A draft that fails is never returned: the caller learns which rules it broke and where, and
// what matched only for rules whose match cannot itself be a name or personal data (the page's
// own list). The reply's text is never logged.
//
// Synthetic records only. Plans are suggestions for an officer to approve, never decisions.

export const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
export const ANTHROPIC_VERSION = "2023-06-01";
export const DEFAULT_MODEL = "claude-sonnet-5-5";
export const DEFAULT_MAX_TOKENS = 8000;
export const DEFAULT_DRAFTS_PER_HOUR = 30;
// What matched is returned only for these rules (app/src/page.js, SAFE_DETAIL).
export const SAFE_DETAIL = new Set(["style", "schema", "record", "pathway", "decision", "figure", "review", "length", "fdcore:accusing language"]);
const RANK = { viewer: 1, contributor: 2, editor: 3, owner: 4 };
const HOUSEHOLD = /^SYN-\d{4}$/;
const HEX64 = /^[0-9a-f]{64}$/;

// The page's canonical JSON (app/src/page.js, canon): keys sorted at every level.
export function canon(v) {
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  if (v && typeof v === "object") return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
  return JSON.stringify(v);
}

export function safeProblems(problems) {
  return problems.slice(0, 50).map((p) => ({
    path: String((p && p.path) || ""),
    rule: String((p && p.rule) || ""),
    detail: p && SAFE_DETAIL.has(p.rule) ? String(p.detail || "").slice(0, 200) : "",
  }));
}

// Deny-list lines from a secret: one term per line, blank lines and # comments ignored.
export function denyLines(text) {
  return String(text || "").split(/\r?\n/).map((s) => s.trim()).filter((s) => s && !s.startsWith("#"));
}

// Times as the page holds them (app/src/hosted.js, toIso): milliseconds and Z, so decisions sort
// here exactly as they sort in the page.
export function toIso(v) {
  if (v === null || v === undefined || v === "") return v === undefined ? null : v;
  const s = String(v);
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]00(?::?00)?)$/.exec(s);
  if (m) return `${m[1]}T${m[2]}.${(m[3] || "").padEnd(3, "0").slice(0, 3)}Z`;
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toISOString();
}

// Whether an approval counts, as the page's approvalCheck decides it (app/src/page.js): the
// version it names is this household's and has the SHA-256 it names, and the person who saved
// the version did not approve it unless four-eyes is off, both now and in the decision. The
// database already refuses an approval that breaks these when it is made, and keeps each
// version's SHA-256 true to its plan; the setting can change later, so it is read each time.
export function approvalCounts(d, fourEyes) {
  const v = d && d.version;
  if (!v || v.household_id !== d.household_id || v.sha256 !== d.plan_sha256) return false;
  if (v.author === d.author && (fourEyes !== false || d.four_eyes !== false)) return false;
  return true;
}

// The household's reviewer notes from its decisions, as the page builds them (prompt.mjs,
// reviewNotesFrom). inputs = {decisions: [{id, author, household_id, decision, version_id,
// plan_sha256, four_eyes, note, reason, decided_at, version: {author, sha256, household_id} or
// null}], four_eyes}.
export function notesFromInputs(inputs, rules, reviewNotesFrom) {
  const ds = (inputs && Array.isArray(inputs.decisions) ? inputs.decisions : []).map((d) => Object.assign({}, d, { decided_at: toIso(d.decided_at) }));
  return reviewNotesFrom(ds, (d) => approvalCounts(d, inputs.four_eyes), rules);
}

const posInt = (v, d) => { const n = Number.parseInt(String(v || ""), 10); return Number.isFinite(n) && n > 0 ? n : d; };
const intOrNull = (v) => (Number.isInteger(v) ? v : null);

function corsHeaders(origin, allowed) {
  const allow = !allowed.length ? "*" : allowed.includes(origin) ? origin : allowed[0];
  return {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    vary: "Origin",
    "access-control-allow-origin": allow,
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-max-age": "600",
  };
}

/**
 * @param {Request} req
 * @param {{env: (name: string) => string, data: object,
 *          lib: {fillPrompt: Function, parseReply: Function, screenPlan: Function, reviewNotesFrom: Function, usableNotes: Function},
 *          fetch: Function, now: () => Date, sha256Hex: (text: string) => Promise<string>,
 *          getUser: (jwt: string) => Promise<{id: string}|null>, memberRole: (id: string) => Promise<string|null>,
 *          recentDrafts: (id: string, sinceIso: string) => Promise<number>, denyTerms: () => Promise<string[]>,
 *          reviewInputs: (householdId: string) => Promise<{decisions: unknown[], four_eyes: boolean}>,
 *          recordDraft: (row: Record<string, unknown>) => Promise<void>, log?: (msg: string) => void}} deps
 * @returns {Promise<Response>}
 */
export async function handleRequest(req, deps) {
  const env = (name) => String(deps.env(name) || "");
  const log = deps.log || (() => {});
  const origin = req.headers.get("origin") || "";
  const allowed = env("ALLOWED_ORIGINS").split(",").map((s) => s.trim()).filter(Boolean);
  const headers = corsHeaders(origin, allowed);
  const reply = (status, body) => new Response(body === null ? null : JSON.stringify(body), { status, headers });
  if (allowed.length && origin && !allowed.includes(origin)) return reply(403, { error: "origin_not_allowed" });
  if (req.method === "OPTIONS") return reply(204, null);
  if (req.method !== "POST") return reply(405, { error: "method_not_allowed" });
  try {
    return await draft(req, deps, env, log, reply);
  } catch (e) {
    log("draft-plan: unexpected " + ((e && e.name) || "error"));
    return reply(500, { error: "internal" });
  }
}

async function draft(req, deps, env, log, reply) {
  const raw = await req.text();
  if (raw.length > 4096) return reply(413, { error: "request_too_large" });
  let body;
  try { body = JSON.parse(raw); } catch { return reply(400, { error: "bad_request" }); }
  if (!body || typeof body !== "object" || Array.isArray(body) || typeof body.household_id !== "string" || !HOUSEHOLD.test(body.household_id)) {
    return reply(400, { error: "bad_request" });
  }
  if (body.prompt_sha256 !== undefined && body.prompt_sha256 !== null && !(typeof body.prompt_sha256 === "string" && HEX64.test(body.prompt_sha256))) {
    return reply(400, { error: "bad_request" });
  }
  const hid = body.household_id;

  // Who is asking: a signed-in member at Contributor or above.
  const m = /^Bearer\s+(\S+)$/i.exec(req.headers.get("authorization") || "");
  if (!m) return reply(401, { error: "not_signed_in" });
  let user = null;
  try { user = await deps.getUser(m[1]); } catch { user = null; }
  if (!user || typeof user.id !== "string") return reply(401, { error: "not_signed_in" });
  const role = await deps.memberRole(user.id);
  if ((RANK[role] || 0) < RANK.contributor) return reply(403, { error: "not_allowed" });

  // The record, from the function's own copy of the synthetic caseload.
  const data = deps.data;
  const rec = data.caseload.records.find((r) => r && r.id === hid);
  if (!rec || rec.synthetic !== true) return reply(404, { error: "no_such_record" });
  const build = { source_commit: (data.manifest && data.manifest.source_commit) || null, spec_version: data.spec.rules.spec_version };

  const key = env("ANTHROPIC_API_KEY");
  if (!key) return reply(503, { error: "not_configured" });

  const limit = posInt(env("DRAFTS_PER_HOUR"), DEFAULT_DRAFTS_PER_HOUR);
  const since = new Date(deps.now().getTime() - 3600 * 1000).toISOString();
  if ((await deps.recentDrafts(user.id, since)) >= limit) return reply(429, { error: "too_many_drafts", limit });

  // The deny list: the secret and the private table. Without it the screen cannot check names,
  // so no draft is made.
  let deny;
  try { deny = [...denyLines(env("DENY_LIST")), ...(await deps.denyTerms())]; } catch { return reply(503, { error: "deny_list_unavailable" }); }

  // The reviewer notes, from the decisions editors recorded. The page builds them the same way
  // from what it has loaded and without the deny list, which it never sees; a note the deny list
  // would hold back is not sent, and the page is told so instead of being sent a different prompt.
  let notes;
  try { notes = notesFromInputs(await deps.reviewInputs(hid), data.spec.rules, deps.lib.reviewNotesFrom); } catch { return reply(503, { error: "notes_unavailable" }); }
  const open = deps.lib.usableNotes(notes, rec, data.spec, { deny: [] });
  if (deps.lib.usableNotes(open.usable, rec, data.spec, { deny }).held.length) return reply(422, { error: "note_blocked" });
  const review = open.usable;

  const prompt = deps.lib.fillPrompt(rec, data.caseload.meta.moveon, data.prompt, data.spec.schema, review);
  const promptSha = await deps.sha256Hex(prompt);
  if (body.prompt_sha256 && body.prompt_sha256 !== promptSha) return reply(409, { error: "build_mismatch", build, notes: review.length });

  const model = env("ANTHROPIC_MODEL") || DEFAULT_MODEL;
  let res;
  try {
    res = await deps.fetch(ANTHROPIC_URL, {
      method: "POST",
      headers: { "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json" },
      body: JSON.stringify({ model, max_tokens: posInt(env("ANTHROPIC_MAX_TOKENS"), DEFAULT_MAX_TOKENS), messages: [{ role: "user", content: prompt }] }),
      signal: AbortSignal.timeout(posInt(env("ANTHROPIC_TIMEOUT_MS"), 120000)),
    });
  } catch {
    return reply(504, { error: "draft_timed_out" });
  }
  if (res.status === 429 || res.status === 529 || res.status >= 500) return reply(503, { error: "busy" });
  if (res.status === 401 || res.status === 403) { log("draft-plan: the API key was refused"); return reply(503, { error: "not_configured" }); }
  if (!res.ok) { log("draft-plan: the API answered " + res.status); return reply(502, { error: "draft_failed" }); }
  let msg;
  try { msg = await res.json(); } catch { return reply(502, { error: "draft_failed" }); }
  const text = (Array.isArray(msg && msg.content) ? msg.content : []).filter((b) => b && b.type === "text" && typeof b.text === "string").map((b) => b.text).join("");

  let problems, plan = null, passed = false;
  if (msg.stop_reason === "max_tokens") problems = [{ path: "(reply)", rule: "reply", detail: "the reply was cut off" }];
  else if (msg.stop_reason === "refusal") problems = [{ path: "(reply)", rule: "reply", detail: "Claude declined to draft this plan" }];
  else {
    const parsed = deps.lib.parseReply(text);
    if (!parsed.ok) problems = [parsed.problem];
    else {
      let scr;
      try { scr = deps.lib.screenPlan(parsed.plan, rec, data.spec, { deny, review }); } catch { scr = { passed: false, problems: [{ path: "", rule: "not_ready", detail: "" }] }; }
      passed = scr.passed === true;
      problems = scr.problems;
      if (passed) plan = scr.plan;
    }
  }

  // Every draft is recorded before anyone sees it; a draft that cannot be recorded is not returned.
  const rules = [...new Set(problems.map((p) => String(p.rule)))].sort();
  try {
    await deps.recordDraft({
      requested_by: user.id, household_id: hid, passed, rules, problem_count: problems.length,
      prompt_sha256: promptSha, plan_sha256: passed ? await deps.sha256Hex(canon(plan)) : null,
      model: String(msg.model || model).slice(0, 80), stop_reason: msg.stop_reason ? String(msg.stop_reason).slice(0, 40) : null,
      input_tokens: intOrNull(msg.usage && msg.usage.input_tokens), output_tokens: intOrNull(msg.usage && msg.usage.output_tokens),
      spec_version: build.spec_version,
    });
  } catch {
    log("draft-plan: the draft could not be recorded");
    return reply(500, { error: "not_recorded" });
  }
  log(`draft-plan: ${hid} ${passed ? "passed" : "failed: " + rules.join(", ")}`);
  return reply(200, { passed, problems: safeProblems(problems), plan, prompt_sha256: promptSha, build });
}
