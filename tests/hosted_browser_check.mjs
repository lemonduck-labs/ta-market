// The hosted page in a real browser (Chromium through Playwright), run by tests/test_hosted_js.py
// when Playwright, its Chromium and a copy of the pinned Supabase client are on the machine.
//
//   node tests/hosted_browser_check.mjs <playwright module> <site folder> <supabase.js> <reply plans.json>
//
// The site folder is a hosted build (scripts/build_app.py --target hosted) for the made-up project
// https://abcdefghijklmnopqrst.supabase.co. The browser fetches the site with the headers its
// _headers file sets (so the Content-Security-Policy applies), the Supabase client from its CDN URL
// (answered with the local copy, so the page's SHA-384 check runs), and the project's Auth, REST and
// function endpoints, answered by a small fake of the project in this file; nothing leaves the
// machine. Two people sign in with an emailed code, a Contributor and an Editor, and take a plan
// through the workflow. Prints {steps, csp, errors, requests} as JSON. Synthetic records only.
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

const [, , playwrightPath, siteDir, umdPath, repliesPath] = process.argv;
const { chromium } = await import(playwrightPath);
const SITE = "https://planner.test";
const PROJECT = "https://abcdefghijklmnopqrst.supabase.co";
const CDN = /^https:\/\/cdn\.jsdelivr\.net\/npm\/@supabase\/supabase-js@[\d.]+\/dist\/umd\/supabase\.js$/;
const replies = JSON.parse(readFileSync(repliesPath, "utf8"));   // {household_id: screened template plan}
const PEOPLE = {
  contributor: { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", role: "contributor", name: "Officer contributor" },
  editor: { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", role: "editor", name: "Officer editor" },
};
const emailOf = (who) => [who, "planner.test"].join("@");

/* ------------------------------------------------------------ the site, with its _headers */
function siteHeaders() {
  const lines = readFileSync(path.join(siteDir, "_headers"), "utf8").split("\n");
  const blocks = [];
  for (const line of lines) {
    if (!line.trim() || line.startsWith("#")) continue;
    if (!/^\s/.test(line)) blocks.push({ path: line.trim(), headers: {} });
    else { const i = line.indexOf(":"); blocks[blocks.length - 1].headers[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim(); }
  }
  return (p) => Object.assign({}, ...blocks.filter((b) => b.path === "/*" || (b.path.endsWith("/*") && p.startsWith(b.path.slice(0, -1)))).map((b) => b.headers));
}
const headersFor = siteHeaders();
const TYPES = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".md": "text/markdown; charset=utf-8", ".txt": "text/plain" };

/* ------------------------------------------------------------ a fake of the project */
const tables = { members: [], versions: [], decisions: [], files: [], checks: [], moves: [], tasks: [], notices: [], reviews: [], monitor_decisions: [], config: [{ key: "workflow", four_eyes: true, updated_at: null, updated_by: null }],
  events: [], audit: [], private_drafts: [] };
for (const p of Object.values(PEOPLE)) tables.members.push({ user_id: p.id, role: p.role, display_name: p.name, active: true, invited_at: "2026-10-01T09:00:00+00:00" });
const requests = [];
const keys = { members: ["user_id"], versions: ["id"], decisions: ["id"], files: ["household_id"], moves: ["household_id"], config: ["key"], tasks: ["id"], notices: ["id"], reviews: ["id"], monitor_decisions: ["id"],
  checks: ["household_id", "check_id"], private_drafts: ["user_id", "household_id"], events: ["id"] };
const nowIso = () => new Date().toISOString().replace("Z", "000+00:00");
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const token = (p) => `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub: p.id, role: "authenticated", aud: "authenticated", email: emailOf(p.role), exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;
const callerOf = (headers) => {
  const m = /^Bearer (.+)$/.exec(headers.authorization || "");
  try { return JSON.parse(Buffer.from(m[1].split(".")[1], "base64url").toString()).sub; } catch { return null; }
};
function serverSet(table, row, old, uid) {
  const t = nowIso();
  if (table === "versions") Object.assign(row, { author: uid, created_at: t, version: tables.versions.filter((v) => v.household_id === row.household_id).length + 1, key: uid + "/" + row.id });
  if (table === "decisions") Object.assign(row, { author: uid, decided_at: t, four_eyes: tables.config[0].four_eyes, note: row.note || "" });
  if (table === "files") { if (!old || "status" in row || "version_id" in row) Object.assign(row, { updated_at: t, updated_by: uid }); if ("assignee" in row) row.assigned_at = row.assignee ? t : null; }
  if (table === "checks" || table === "moves" || table === "config") Object.assign(row, { updated_by: uid, updated_at: t });
  if (table === "tasks") { if (!old) Object.assign(row, { created_by: uid, created_at: t }); if ("done" in row) Object.assign(row, { done_by: row.done ? uid : null, done_at: row.done ? t : null }); }
  if (table === "notices") Object.assign(row, { recorded_by: uid, recorded_at: t });
  if (table === "reviews") { if (!old) Object.assign(row, { created_by: uid, created_at: t }); if ("decided_on" in row) row.decided_by = row.decided_on ? uid : null; }
  if (table === "events") Object.assign(row, { id: tables.events.length + 1, actor: uid, at: t });
  if (table === "private_drafts") Object.assign(row, { user_id: uid, at: t });
  return row;
}
function matches(row, params) {
  for (const [k, v] of params) {
    if (["select", "order", "limit", "offset", "on_conflict", "columns"].includes(k)) continue;
    const [op, ...rest] = v.split(".");
    const val = rest.join(".");
    if (op === "eq" && String(row[k]) !== val) return false;
    if (op === "gte" && !(String(row[k]) >= val)) return false;
    if (op === "in" && !val.replace(/^\(|\)$/g, "").split(",").map((s) => s.replace(/^"|"$/g, "")).includes(String(row[k]))) return false;
  }
  return true;
}
function rest(method, table, url, headers, body, uid) {
  const rows = tables[table];
  if (!rows) return [404, { message: "no table " + table }];
  const params = [...url.searchParams.entries()];
  const prefer = headers.prefer || "";
  if (method === "GET" || method === "HEAD") {
    let out = rows.filter((r) => matches(r, params));
    if (table === "private_drafts") out = out.filter((r) => r.user_id === uid);
    const order = url.searchParams.get("order");
    if (order) for (const part of order.split(",").reverse()) { const [c, d] = part.split("."); out = out.slice().sort((x, y) => (x[c] < y[c] ? -1 : x[c] > y[c] ? 1 : 0) * (d === "desc" ? -1 : 1)); }
    const off = Number(url.searchParams.get("offset") || 0), lim = url.searchParams.get("limit");
    out = out.slice(off, lim ? off + Number(lim) : undefined);
    return [200, out];
  }
  const payload = body ? JSON.parse(body) : null;
  if (method === "POST") {
    const list = Array.isArray(payload) ? payload : [payload];
    const conflict = (url.searchParams.get("on_conflict") || "").split(",").filter(Boolean);
    const changed = [];
    for (const r of list) {
      const row = JSON.parse(JSON.stringify(r));
      if (table === "private_drafts") row.user_id = uid;
      const ks = conflict.length ? conflict : keys[table];
      const old = prefer.includes("resolution=merge-duplicates") ? rows.find((x) => ks.every((k) => x[k] === row[k])) : null;
      if (old) { Object.assign(old, serverSet(table, row, old, uid)); changed.push(old); } else { const n = serverSet(table, row, null, uid); rows.push(n); changed.push(n); }
    }
    return [201, prefer.includes("return=representation") ? changed : null];
  }
  if (method === "PATCH") {
    const hit = rows.filter((r) => matches(r, params));
    for (const r of hit) Object.assign(r, serverSet(table, JSON.parse(body), r, uid));
    return [prefer.includes("return=representation") ? 200 : 204, prefer.includes("return=representation") ? hit : null];
  }
  return [405, { message: "method" }];
}
let draftAnswer = "pass";
async function project(route) {
  const req = route.request();
  const url = new URL(req.url());
  const headers = req.headers();
  const body = req.postData();
  const uid = callerOf(headers);
  requests.push({ method: req.method(), path: url.pathname, query: url.search, apikey: headers.apikey || null, caller: uid, body: body ? JSON.parse(body) : null });
  const send = (status, data, extra = {}) => route.fulfill({ status, contentType: "application/json",
    headers: Object.assign({ "access-control-allow-origin": SITE, "access-control-allow-headers": "*", "access-control-allow-methods": "*", "access-control-expose-headers": "content-range" }, extra),
    body: data === null ? "" : JSON.stringify(data) });
  if (req.method() === "OPTIONS") return send(204, null);
  if (url.pathname === "/auth/v1/otp") return send(200, {});
  if (url.pathname === "/auth/v1/verify") {
    const { email } = JSON.parse(body);
    const p = Object.values(PEOPLE).find((x) => emailOf(x.role) === email);
    if (!p) return send(403, { code: 403, error_code: "otp_expired", msg: "Token has expired or is invalid" });
    const exp = Math.floor(Date.now() / 1000) + 3600;
    return send(200, { access_token: token(p), token_type: "bearer", expires_in: 3600, expires_at: exp, refresh_token: "refresh-" + p.role,
      user: { id: p.id, aud: "authenticated", role: "authenticated", email, app_metadata: {}, user_metadata: {}, created_at: "2026-10-01T09:00:00Z" } });
  }
  if (url.pathname === "/auth/v1/logout") return send(204, null);
  if (url.pathname === "/auth/v1/user") { const p = Object.values(PEOPLE).find((x) => x.id === uid); return p ? send(200, { id: p.id, email: emailOf(p.role) }) : send(401, {}); }
  if (url.pathname.startsWith("/rest/v1/")) {
    const [status, data] = rest(req.method(), url.pathname.slice("/rest/v1/".length), url, headers, body, uid);
    return send(status, data, status === 200 && Array.isArray(data) ? { "content-range": `0-${Math.max(0, data.length - 1)}/${data.length}` } : {});
  }
  if (url.pathname === "/functions/v1/draft-plan") {
    const b = JSON.parse(body);
    if (draftAnswer === "fail") return send(200, { passed: false, plan: null, problems: [{ path: "summary.text", rule: "decision", detail: "has ended" }] });
    return send(200, { passed: true, problems: [], plan: replies[b.household_id], prompt_sha256: b.prompt_sha256, build: {} });
  }
  return send(404, { message: "not in the fake" });
}

/* ------------------------------------------------------------ the browser */
const steps = [], errors = [];
const step = (name, ok, detail) => steps.push({ name, ok: !!ok, detail: detail === undefined ? null : detail });
let browser;
// A Chromium named by TA_CHROMIUM (or the one this workspace keeps at /opt/pw-browsers/chromium)
// when it exists, as tests/browser/flow.mjs does; otherwise Playwright's own.
const executablePath = [process.env.TA_CHROMIUM, "/opt/pw-browsers/chromium"].find((x) => x && existsSync(x));
try { browser = await chromium.launch(executablePath ? { executablePath } : {}); } catch (err) {
  process.stdout.write(JSON.stringify({ steps, csp: [], errors: ["browserType.launch: " + String(err && err.message).slice(0, 300)], requests: 0 }));
  process.exit(0);
}
async function personPage(who) {
  const context = await browser.newContext({ acceptDownloads: true });
  await context.routeWebSocket(/\/realtime\/v1\//, (ws) => ws.close());   // live updates down, so the page polls
  await context.route("**/*", async (route) => {
    const u = route.request().url();
    if (u.startsWith(SITE + "/")) {
      let p = new URL(u).pathname;
      if (p === "/") p = "/index.html";
      const f = path.join(siteDir, p);
      if (!existsSync(f)) return route.fulfill({ status: 404, body: "" });
      return route.fulfill({ status: 200, contentType: TYPES[path.extname(f)] || "application/octet-stream", headers: headersFor(p), body: readFileSync(f) });
    }
    if (CDN.test(u)) return route.fulfill({ status: 200, contentType: "application/javascript; charset=utf-8", headers: { "access-control-allow-origin": "*" }, body: readFileSync(umdPath) });
    if (u.startsWith(PROJECT + "/")) return project(route);
    return route.abort();
  });
  const page = await context.newPage();
  await page.addInitScript(() => { window.__csp = []; document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`)); });
  page.on("pageerror", (e) => errors.push(`${who}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${who} console: ${m.text()}`); });
  await page.goto(SITE + "/");
  return { context, page };
}
async function signIn(page, who) {
  await page.locator(".hs-status", { hasText: "Sign in with your work email" }).waitFor({ timeout: 15000 });
  await page.getByPlaceholder("Work email").fill(emailOf(who));
  await page.getByRole("button", { name: "Email me a code", exact: true }).click();
  await page.getByPlaceholder("Code from the email").fill("123456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator(".hs-status", { hasText: `Signed in as ${PEOPLE[who].name}, ${PEOPLE[who].role}.` }).waitFor({ timeout: 15000 });
  await page.locator("#store-chip", { hasText: "Shared store" }).waitFor({ timeout: 15000 });
}
const openFile = async (page, hid) => { await page.evaluate((h) => { location.hash = "#file-" + h; }, hid); await page.locator(".rec-id", { hasText: hid }).waitFor({ timeout: 10000 }); };

try {
  const c = await personPage("contributor");
  step("the Supabase client loaded past its integrity check", await c.page.evaluate(() => typeof window.supabase === "object" && typeof window.supabase.createClient === "function"));
  step("the page waits for sign-in before it has a store", (await c.page.locator("#store-chip").innerText()).includes("Connecting"));
  await signIn(c.page, "contributor");
  step("a Contributor signs in with an emailed code", true);
  const verify = requests.find((r) => r.path === "/auth/v1/verify");
  const otp = requests.find((r) => r.path === "/auth/v1/otp");
  step("sign-in never creates an account", otp && otp.body && otp.body.create_user === false, otp && otp.body);
  step("the code is checked as an email code", verify && verify.body && verify.body.type === "email" && verify.body.token === "123456");

  await openFile(c.page, "SYN-0001");
  await c.page.getByRole("button", { name: "Start from the template", exact: true }).click();
  await c.page.getByRole("button", { name: "Save draft", exact: true }).click();
  await c.page.getByRole("button", { name: "Submit for approval", exact: true }).waitFor({ timeout: 10000 });
  const vIns = requests.find((r) => r.path === "/rest/v1/versions" && r.method === "POST");
  step("a saved version goes to versions with no author, time or number from the page",
    vIns && !("author" in vIns.body) && !("created_at" in vIns.body) && !("version" in vIns.body) && vIns.caller === PEOPLE.contributor.id, vIns && Object.keys(vIns.body).sort());
  await c.page.getByRole("button", { name: "Submit for approval", exact: true }).click();
  await c.page.locator(".st", { hasText: "Awaiting approval" }).first().waitFor({ timeout: 10000 });
  const f = tables.files.find((r) => r.household_id === "SYN-0001");
  step("the pointer says submitted, set by the Contributor", f && f.status === "submitted" && f.updated_by === PEOPLE.contributor.id, f);
  step("the Contributor is not offered Approve", (await c.page.getByRole("button", { name: "Approve", exact: true }).count()) === 0);

  // Drafting with Claude: through the function, the plan saved as a Claude draft.
  await openFile(c.page, "SYN-0002");
  await c.page.getByRole("button", { name: "Draft with Claude", exact: true }).click();
  await c.page.getByRole("button", { name: "Save draft", exact: true }).waitFor({ timeout: 15000 });
  const fn = requests.find((r) => r.path === "/functions/v1/draft-plan");
  step("drafting sends the record id and the prompt's SHA-256 to the function", fn && fn.body.household_id === "SYN-0002" && /^[0-9a-f]{64}$/.test(fn.body.prompt_sha256) && fn.caller === PEOPLE.contributor.id, fn && fn.body);
  await c.page.getByRole("button", { name: "Save draft", exact: true }).click();
  await c.page.getByRole("button", { name: "Submit for approval", exact: true }).waitFor({ timeout: 10000 });
  const claude = tables.versions.find((v) => v.household_id === "SYN-0002");
  step("a Claude draft is saved as one, with the prompt's SHA-256", claude && claude.source === "claude" && claude.prompt_sha256 === fn.body.prompt_sha256);
  draftAnswer = "fail";
  await openFile(c.page, "SYN-0003");
  await c.page.getByRole("button", { name: "Draft with Claude", exact: true }).click();
  await c.page.locator(".hs-notice", { hasText: "stopped by the screen" }).waitFor({ timeout: 10000 });
  step("a draft that fails the screen is not shown; the bar names the rule", (await c.page.getByRole("button", { name: "Save draft", exact: true }).count()) === 0
    && (await c.page.locator(".hs-notice").innerText()).includes("a sentence stating a decision"));

  const e = await personPage("editor");
  await signIn(e.page, "editor");
  step("an Editor signs in", true);
  await openFile(e.page, "SYN-0001");
  await e.page.getByRole("button", { name: "Approve", exact: true }).click();
  await e.page.locator(".st", { hasText: "Approved" }).first().waitFor({ timeout: 10000 });
  const dIns = requests.find((r) => r.path === "/rest/v1/decisions" && r.method === "POST");
  step("the approval goes to decisions with no author, time or four-eyes flag from the page",
    dIns && !("author" in dIns.body) && !("decided_at" in dIns.body) && !("four_eyes" in dIns.body) && dIns.body.plan_sha256 === tables.versions[0].sha256 && dIns.caller === PEOPLE.editor.id, dIns && dIns.body);
  const ev = requests.filter((r) => r.path === "/rest/v1/events");
  step("the page wrote no audit entry of its own", !requests.some((r) => r.path === "/rest/v1/audit" && r.method !== "GET") && ev.length === 0);

  await e.page.click("#tab-method");
  const method = await e.page.locator("#view-method").innerText();
  step("the Method view describes the hosted version, not the pilot",
    method.includes("this is the hosted version") && method.includes("checked by its SHA-384") && method.includes("by the drafting function, on the owner") && !method.includes("runs inside Claude for the pilot"));

  const csp = [...(await c.page.evaluate(() => window.__csp)), ...(await e.page.evaluate(() => window.__csp))];
  step("the Content-Security-Policy blocked nothing", csp.length === 0, csp);
  await c.page.getByRole("button", { name: "Sign out", exact: true }).click();
  await c.page.locator(".hs-status", { hasText: "Sign in with your work email" }).waitFor({ timeout: 15000 });
  step("signing out leaves the page signed out", true);
  process.stdout.write(JSON.stringify({ steps, csp, errors, requests: requests.length }));
} catch (err) {
  process.stdout.write(JSON.stringify({ steps, csp: [], errors: [...errors, "check stopped: " + String(err && err.message).slice(0, 500)], requests: requests.length }));
} finally {
  await browser.close();
}
