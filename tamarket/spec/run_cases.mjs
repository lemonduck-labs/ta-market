// Runs the shared cases through the JavaScript ports and prints the results as JSON, for
// tests/test_spec_js.py to compare with Python. Works under node or Deno (node: imports).
//   node tamarket/spec/run_cases.mjs [corpus.json]
// corpus.json, if given, is a list of strings to run through the fd-core part of the screen.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { screenPlan, fdcoreScan, usableNotes } from "./screen.mjs";
import { evaluateScenario } from "./scenario.mjs";
import { reviewNotesFrom } from "./prompt.mjs";
import { runClockCase } from "./clocks.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
const spec = { rules: load("screen_rules.json"), schema: load("moveon.schema.json"), pathways: load("pathways.json"),
  fdcore: load("fdcore_patterns.json") };
const clone = (v) => JSON.parse(JSON.stringify(v));

function walkTo(node, keys) {
  for (const k of keys) node = Array.isArray(node) ? node[Number(k)] : node[k];
  return node;
}

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

const cases = load("screen_cases.json");
const screen = cases.cases.map((c) => {
  const [plan, hh] = applyCase(cases.base_plan, cases.base_household, c);
  const r = screenPlan(plan, hh, spec, { deny: [], review: c.review });
  return { id: c.id, passed: r.passed, rules: [...new Set(r.problems.map((p) => p.rule))].sort() };
});
const notes = cases.note_cases.map((c) => {
  const text = c.text !== undefined ? c.text : (c.text_parts || []).join("");
  const out = usableNotes([{ id: "review-1", kind: "returned", text }], cases.base_household, spec, { deny: [] });
  return { id: c.id, usable: out.usable.length === 1, rules: [...new Set(out.held.flatMap((h) => h.problems.map((p) => p.rule)))].sort() };
});
const notesFrom = cases.notes_from_cases.map((c) => {
  const skip = new Set(c.not_counting || []);
  return { id: c.id, got: reviewNotesFrom(c.decisions, (d) => !skip.has(d.id), spec.rules) };
});
const scenario = load("scenario_cases.json").cases.map((c) => ({ id: c.id, got: evaluateScenario(c.inputs) }));
const clockDoc = load("clocks.json");
const clocks = clockDoc.cases.map((c) => ({ id: c.id, got: runClockCase(c, clockDoc.rules) }));
let corpus = null;
if (process.argv[2]) corpus = JSON.parse(readFileSync(process.argv[2], "utf8")).map((s) => fdcoreScan(s, spec.fdcore, []).map((f) => f.kind));
process.stdout.write(JSON.stringify({ screen, notes, notesFrom, scenario, clocks, corpus }));
