// JavaScript port of tamarket/moveon.py suggest_pathways, fill_prompt and review_notes_from,
// for an artifact page or a Deno function. It never evaluates the rules in pathways.json: it
// resolves the ids that Python wrote into each caseload record (eligible_pathways,
// suitability_checks) to their words in the caseload's meta.moveon block, so the suggestions a
// page shows and sends are Python's. tests/test_app.py checks, with node, that both outputs
// equal Python's for every record.
//
// moveon = the caseload file's meta.moveon (status, pathways, general_checks, texts,
//          statutory_figures, citations), written by scripts/build_caseload.py.
//
// Suggestions for an officer to approve, never decisions.

export const MARKER = "---PROMPT---";
const COMPACT = ["eligible_pathways", "suitability_checks"];

// The record as Python's generator wrote it, without the two lists of ids added for the page.
export function bareRecord(record) {
  const out = {};
  for (const [k, v] of Object.entries(record)) if (!COMPACT.includes(k)) out[k] = v;
  return out;
}

function item(moveon, id, used) {
  const t = moveon.texts[id];
  if (!t) throw new Error("unknown text id: " + id);
  for (const c of t.citations) used.add(c);
  return { id, text: t.text, citations: t.citations, confidence: t.confidence };
}

export function suggestionsFor(record, moveon) {
  if (!record || typeof record !== "object" || record.synthetic !== true) throw new Error("move-forward suggestions are made for synthetic records only");
  if (!Array.isArray(record.eligible_pathways) || !Array.isArray(record.suitability_checks)) {
    throw new Error("the record must carry eligible_pathways and suitability_checks from tamarket/moveon.py");
  }
  const used = new Set();
  const pathways = record.eligible_pathways.map((p) => {
    const meta = moveon.pathways[p.pathway_id], when = p.pathway_id + ".when";
    if (!meta || !moveon.texts[when]) throw new Error("unknown pathway: " + p.pathway_id);
    return {
      pathway_id: p.pathway_id, title: meta.title, summary: meta.summary, ends_main_duty: meta.ends_main_duty,
      why_listed: moveon.texts[when].text,
      reasons: p.reasons.filter((id) => id !== when).map((id) => item(moveon, id, used)),
      officer_checks: p.officer_checks.map((id) => item(moveon, id, used)),
    };
  });
  const checks = record.suitability_checks.map((id) => item(moveon, id, used));
  const general = moveon.general_checks.map((id) => item(moveon, id, used));
  const citations = {};
  for (const [k, v] of Object.entries(moveon.citations)) if (used.has(k)) citations[k] = v;
  return { household_id: record.id, synthetic: true, status: moveon.status, general_checks: general, pathways,
    suitability_checks: checks, statutory_figures: moveon.statutory_figures, citations };
}

// Python's json.dumps(v, indent=1), which escapes everything outside printable ASCII.
function asciiJson(v) {
  return JSON.stringify(v, null, 1).replace(/[\u007f-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

// The drafting prompt with its five placeholders filled in one pass, exactly as
// fill_prompt(bare record, review=..., lessons=...). review: the usable reviewer notes
// (screen.mjs, usableNotes), oldest first; lessons: the lessons recalled for the household,
// as {id, applies_to, text}; [] or left out when there are none.
const PLACEHOLDER = /\{\{(HOUSEHOLD_JSON|SUGGESTIONS_JSON|REVIEW_JSON|LESSONS_JSON|SCHEMA_JSON)\}\}/g;
export function fillPrompt(record, moveon, promptText, schema, review, lessons) {
  const i = promptText.indexOf(MARKER);
  if (i < 0) throw new Error("the prompt file has no " + MARKER + " line");
  if (review !== undefined && review !== null && !Array.isArray(review)) throw new Error("reviewer notes must be a list");
  if (lessons !== undefined && lessons !== null && !Array.isArray(lessons)) throw new Error("lessons must be a list");
  const body = promptText.slice(i + MARKER.length).replace(/^\n+/, "");
  const vals = {
    HOUSEHOLD_JSON: JSON.stringify(bareRecord(record), null, 1),
    SUGGESTIONS_JSON: JSON.stringify(suggestionsFor(record, moveon), null, 1),
    REVIEW_JSON: JSON.stringify((review || []).map((n) => ({ id: n.id, kind: n.kind, text: n.text })), null, 1),
    LESSONS_JSON: JSON.stringify((lessons || []).map((l) => ({ id: l.id, applies_to: l.applies_to, text: l.text })), null, 1),
    SCHEMA_JSON: asciiJson(schema),
  };
  return body.replace(PLACEHOLDER, (m, name) => vals[name]);
}

// The reviewer notes for a household's next draft (screen_rules.json, review), exactly as
// moveon.review_notes_from: the returns with a note and the rejections since the last approval
// that counts(d), oldest first, the latest max_notes of them, as [{id, kind, text}]. Decisions
// are ordered by decided_at, then id, compared as strings, as the page orders them; pass times
// in one format (the page's ISO form). Run usableNotes on the result before a prompt uses it.
export function reviewNotesFrom(decisions, counts, rules) {
  const R = rules.review, ok = counts || (() => true);
  const key = (d) => [String(d.decided_at || ""), String(d.id || "")];
  const ds = [...decisions].sort((a, b) => { const x = key(a), y = key(b); return x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0; });
  let from = 0;
  for (let i = ds.length - 1; i >= 0; i--) if (ds[i].decision === "approved" && ok(ds[i])) { from = i + 1; break; }
  const picked = ds.slice(from).filter((d) => (d.decision === "returned" && String(d.note || "").trim()) || d.decision === "rejected").slice(-R.max_notes);
  return picked.map((d, i) => {
    const note = String(d.note || "").trim();
    const label = Object.prototype.hasOwnProperty.call(R.reject_labels, d.reason) ? R.reject_labels[d.reason] : R.reject_label_unknown;
    return { id: `review-${i + 1}`, kind: d.decision, text: d.decision === "rejected" ? (note ? `${label}: ${note}` : label) : note };
  });
}

// A drafting reply must be one JSON object, nested at most MAX_DEPTH deep; a single code fence
// around it is allowed. Only ASCII white space is trimmed, as moveon.parse_reply does, so both
// read every reply the same way.
export const MAX_DEPTH = 32;
const trimAscii = (s) => s.replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, "");
function depth(v) {
  let max = 0;
  const stack = [[v, 1]];
  while (stack.length) {
    const [x, d] = stack.pop();
    if (x === null || typeof x !== "object") continue;
    if (d > max) max = d;
    if (max > MAX_DEPTH) return max;
    for (const y of Array.isArray(x) ? x : Object.values(x)) stack.push([y, d + 1]);
  }
  return max;
}
export function parseReply(text) {
  let t = trimAscii(typeof text === "string" ? text : "");
  const fence = /^```[A-Za-z]*\n([\s\S]*?)\n?```$/.exec(t);
  if (fence) t = trimAscii(fence[1]);
  try {
    const v = JSON.parse(t);
    if (v !== null && typeof v === "object" && !Array.isArray(v) && depth(v) <= MAX_DEPTH) return { ok: true, plan: v };
  } catch (e) { /* not JSON */ }
  return { ok: false, problem: { path: "(reply)", rule: "reply", detail: "the reply is not one JSON object" } };
}
