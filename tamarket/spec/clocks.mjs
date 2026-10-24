// JavaScript port of tamarket/clocks.py: statutory clocks on synthetic records. Must give the
// answers in clocks.json's cases (tests/test_spec_js.py checks it with node). Dates are ISO
// strings (YYYY-MM-DD), compared as text and moved by whole days in UTC, so no time zone moves
// a date. A period of N days "beginning with" a day ends on that day plus N - 1.

export function addDays(iso, n) {
  const [y, m, d] = String(iso).split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
}
export const lastDay = (start, days) => addDays(start, days - 1);

function stateOf(due, today, doneOn, soonDays, doneWords) {
  if (doneOn) return doneOn <= due ? doneWords[0] : doneWords[1];
  if (today > due) return "overdue";
  return today >= addDays(due, -soonDays) ? "due" : "later";
}

export function s208(record, today, sentOn, rules) {
  if (!record.placed_in_another_district) return { applies: false, due: null, state: "not_applicable" };
  const due = lastDay(record.placed_on, rules.s208.days);
  return { applies: true, due, state: stateOf(due, today, sentOn || null, rules.soon_days, ["sent_on_time", "sent_late"]) };
}

// A 16 or 17 year old applicant is a child under the section, and is asked instead of a parent.
export const YOUNG_APPLICANT = "applicant aged 16 or 17";
export function childScope(record, rules) {
  const young = record.priority_need === YOUNG_APPLICANT;
  const n = Number(record.children || 0) + (young ? 1 : 0);
  if (!n) return { applies: false, reason: "no_child", children: 0, young_applicant: false };
  if (record.placed_on < rules.child.in_force) return { applies: false, reason: "before_commencement", children: n, young_applicant: young };
  return { applies: true, reason: "check_application_date", children: n, young_applicant: young };
}

export function childDue(placedOn, agreedOn, infoOn, rules) {
  if (!agreedOn || !infoOn) return null;
  const latest = [placedOn, agreedOn, infoOn].sort().at(-1);
  return lastDay(latest, rules.child.days);
}

export function bnb(record, today, rules) {
  if (!(record.suitability_checks || []).includes("bnb-family-limit")) return { applies: false, limit: null, state: "not_applicable" };
  // The day to move by: the last day of 6 weeks beginning with the placement. Past from the next day.
  const limit = lastDay(record.placed_on, rules.bnb_family.days);
  const state = today > limit ? "past" : today >= addDays(limit, -rules.soon_days) ? "soon" : "later";
  return { applies: true, limit, state };
}

export function review(requestedOn, today, decidedOn, agreedTo, rules) {
  const due = agreedTo || lastDay(requestedOn, rules.review.days);
  return { due, state: stateOf(due, today, decidedOn || null, rules.soon_days, ["decided", "decided_late"]) };
}

export function runClockCase(c, rules) {
  if (c.fn === "s208") return s208(c.record, c.today, c.sent_on, rules);
  if (c.fn === "child_scope") return childScope(c.record, rules);
  if (c.fn === "child_due") return { due: childDue(c.placed_on, c.agreed_on, c.info_on, rules) };
  if (c.fn === "bnb") return bnb(c.record, c.today, rules);
  if (c.fn === "review") return review(c.requested_on, c.today, c.decided_on, c.agreed_to, rules);
  throw new Error("no such clock: " + c.fn);
}
