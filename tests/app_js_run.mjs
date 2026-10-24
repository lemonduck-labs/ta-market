// Runs the code built into app/index.html (its MODULES block: TaScreen, TaScenario, TaPrompt and
// TaTemplate, as the page runs them) against the shared cases and every caseload record, and
// prints the results as JSON for tests/test_app.py to compare with Python.
//   node tests/app_js_run.mjs <app/index.html> <the page's spec dir> <caseload.json> <replies.json> <tamarket/spec, for the cases>
import { readFileSync } from "node:fs";
import vm from "node:vm";

const [, , pagePath, specDir, caseloadPath, repliesPath, casesDir] = process.argv;
const html = readFileSync(pagePath, "utf8");
const begin = html.indexOf("/* BEGIN MODULES"), end = html.indexOf("/* END MODULES */");
if (begin < 0 || end < begin) throw new Error("no MODULES block in the page");
const code = html.slice(html.indexOf("*/", begin) + 2, end);
const sandbox = { console };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "app/index.html#MODULES" });
const { TaScreen, TaScenario, TaPrompt, TaTemplate } = sandbox;

const load = (name) => JSON.parse(readFileSync(`${specDir}/${name}`, "utf8"));
const spec = { rules: load("screen_rules.json"), schema: load("moveon.schema.json"), pathways: load("pathways.json"), fdcore: load("fdcore_patterns.json") };
const clone = (v) => JSON.parse(JSON.stringify(v));
const walkTo = (node, keys) => { for (const k of keys) node = Array.isArray(node) ? node[Number(k)] : node[k]; return node; };
function applyCase(base, household, c) {
  const plan = clone(base), hh = clone(household);
  for (const path of c.delete || []) { const keys = path.split("."), last = keys.pop(); delete walkTo(plan, keys)[last]; }
  const sets = { ...(c.set || {}) };
  for (const [k, parts] of Object.entries(c.set_parts || {})) sets[k] = parts.join("");
  for (const [path, value] of Object.entries(sets)) {
    const keys = path.split("."), last = keys.pop(), node = walkTo(plan, keys);
    if (Array.isArray(node)) node[Number(last)] = clone(value); else node[last] = clone(value);
  }
  Object.assign(hh, clone(c.household_set || {}));
  return [plan, hh];
}

const loadCases = (name) => JSON.parse(readFileSync(`${casesDir}/${name}`, "utf8"));
const cases = loadCases("screen_cases.json");
const screen = cases.cases.map((c) => {
  const [plan, hh] = applyCase(cases.base_plan, cases.base_household, c);
  const r = TaScreen.screenPlan(plan, hh, spec, { deny: [], review: c.review });
  return { id: c.id, passed: r.passed, rules: [...new Set(r.problems.map((p) => p.rule))].sort() };
});
const notes = cases.note_cases.map((c) => {
  const text = c.text !== undefined ? c.text : (c.text_parts || []).join("");
  const out = TaScreen.usableNotes([{ id: "review-1", kind: "returned", text }], cases.base_household, spec, { deny: [] });
  return { id: c.id, usable: out.usable.length === 1, rules: [...new Set(out.held.flatMap((h) => h.problems.map((p) => p.rule)))].sort() };
});
const notesFrom = cases.notes_from_cases.map((c) => {
  const skip = new Set(c.not_counting || []);
  return { id: c.id, got: JSON.parse(JSON.stringify(TaPrompt.reviewNotesFrom(c.decisions, (d) => !skip.has(d.id), spec.rules))) };
});
const scenario = loadCases("scenario_cases.json").cases.map((c) => ({ id: c.id, got: TaScenario.evaluateScenario(c.inputs) }));

const caseload = JSON.parse(readFileSync(caseloadPath, "utf8"));
const prompt = readFileSync(`${specDir}/moveon_prompt.md`, "utf8");
// Every tenth record is also drafted against two reviewer notes: the prompt must carry them as
// Python's does, and the template must answer each with the placeholder, which the screen refuses.
const NOTES = [
  { id: "review-1", kind: "returned", text: "Start the steps with the duty owed, then the household's wishes." },
  { id: "review-2", kind: "rejected", text: "The record or the circumstances have changed: the household now has a medical need." },
];
// And every tenth record, offset by five, with two lessons, which the prompt must carry as Python's does.
const LESSONS = [
  { id: "lesson-1", applies_to: "private rented sector offer, every household", text: "Check the property's distance from the children's schools before an offer." },
  { id: "lesson-2", applies_to: "this household", text: "Ask about the household's wishes on the area before anything else." },
];
const records = caseload.records.map((r, i) => {
  const plan = TaTemplate.templatePlan(r, caseload.meta.moveon);
  const res = TaScreen.screenPlan(plan, r, spec, { deny: [] });
  const out = {
    id: r.id, plan: JSON.parse(JSON.stringify(res.plan)), passed: res.passed, rules: [...new Set(res.problems.map((p) => p.rule))].sort(),
    suggestions: JSON.parse(JSON.stringify(TaPrompt.suggestionsFor(r, caseload.meta.moveon))),
    prompt: TaPrompt.fillPrompt(r, caseload.meta.moveon, prompt, spec.schema),
  };
  if (i % 10 === 5) out.lessons = { lessons: LESSONS, prompt: TaPrompt.fillPrompt(r, caseload.meta.moveon, prompt, spec.schema, [], LESSONS) };
  if (i % 10 === 0) {
    const withNotes = TaTemplate.templatePlan(r, caseload.meta.moveon, NOTES, spec.rules.review.placeholder);
    const nres = TaScreen.screenPlan(withNotes, r, spec, { deny: [], review: NOTES });
    out.notes = { review: NOTES, prompt: TaPrompt.fillPrompt(r, caseload.meta.moveon, prompt, spec.schema, NOTES),
      template: JSON.parse(JSON.stringify(nres.plan)), problems: nres.problems.map((p) => [p.path, p.rule]) };
  }
  return out;
});
const replies = JSON.parse(readFileSync(repliesPath, "utf8")).map((t) => TaPrompt.parseReply(t).ok);
process.stdout.write(JSON.stringify({ screen, notes, notesFrom, scenario, records, replies }));
