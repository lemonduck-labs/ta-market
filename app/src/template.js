/* The template move-forward plan, for when Claude drafting is not available or not wanted.
 *
 * Built only from Python's suggestions for one synthetic record (the ids in eligible_pathways
 * and suitability_checks, resolved by the caseload's meta.moveon texts): it copies the general
 * checks, the suitability checks and every officer check word for word, uses each pathway's
 * first reason as the reason to consider it, and adds a few fixed sentences. It evaluates no
 * rule of its own. tests/test_app.py checks that it passes the screen, Python's and the
 * JavaScript port, for every record in the caseload. An officer edits it from there.
 *
 * With reviewer notes (screen_rules.json, review), each note gets the placeholder answer, which
 * the screen refuses until a person writes what changed: the page opens the editor on them.
 *
 * Suggestions for an officer to approve, never decisions.
 *
 * Loads as a CommonJS module (Node tests), or sets globalThis.TaTemplate (the page).
 */
(function (root, factory) {
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.TaTemplate = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const PLACE = {
    bed_and_breakfast: 'bed and breakfast accommodation',
    nightly_paid_self_contained: 'nightly-paid, self-contained accommodation',
    hostels: 'a hostel',
    private_sector_leased: 'private sector leased accommodation',
    la_ha_stock: 'council or housing association stock',
    other: 'other temporary accommodation',
  };
  const NAME = {
    'social-housing': 'social housing through the allocation scheme',
    'prs-offer': 'a private rented sector offer',
    'supported-housing': 'supported housing',
  };
  const STEP = {
    'social-housing': { text: "Check the household's position under the allocation scheme, and check any offer against the checks for this pathway.", confidence: 'Certain' },
    'prs-offer': { text: 'If a private rented sector offer is considered, check each condition for this pathway before the offer is made, and tell the household in writing what accepting or refusing it would mean.', confidence: 'Certain' },
    'supported-housing': { text: 'If the household wants supported housing, check that its support and housing needs have been assessed before any referral.', confidence: 'Likely' },
  };
  const RISKS = [
    [(r, ids) => ids.has('prs-offer.n-children'), { text: "A move could disrupt the children's education.", confidence: 'Likely' }],
    [(r, ids) => ids.has('prs-offer.n-support'), { text: 'A move could put the support and medical services the household relies on out of reach.', confidence: 'Likely' }],
    [(r) => r.suitability_checks.includes('out-of-district'), { text: 'A placement outside the district can put work, schooling, care or support further away, and a move back could change them again.', confidence: 'Likely' }],
    [(r, ids, has) => has('social-housing'), { text: 'Waiting for a suitable offer under the allocation scheme could mean a longer stay in TA.', confidence: 'Likely' }],
    [(r, ids, has) => has('prs-offer'), { text: 'A private tenancy could cost more than the household can afford over time.', confidence: 'Guessing' }],
    [(r, ids) => ids.has('supported-housing.n-family'), { text: 'Supported housing with shared facilities will not normally suit a family for a longer stay (Code 2.52).', confidence: 'Certain' }],
  ];
  const LIMITS = { steps: 12, officer_checks: 20, risks: 10, pathway_suggestions: 3 };

  const plural = (n, one, many) => (n === 1 ? one : many);
  const listWords = (xs) => (xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]);

  function text(moveon, id) {
    const t = moveon.texts[id];
    if (!t) throw new Error('unknown text id: ' + id);
    return t;
  }

  function summary(r) {
    const who = `${r.adults} ${plural(r.adults, 'adult', 'adults')}` +
      (r.children > 0 ? ` and ${r.children} ${plural(r.children, 'child', 'children')}` : ', no children');
    const where = PLACE[r.accommodation_type] || r.accommodation;
    const placed = r.placed_in_another_district ? ", placed outside the council's district" : '';
    const names = listWords(r.eligible_pathways.map((p) => NAME[p.pathway_id] || p.pathway_id));
    return `A household of ${who}, in temporary accommodation for ${r.weeks_in_ta} ${plural(r.weeks_in_ta, 'week', 'weeks')}, now in ${where}${placed}. ` +
      `The pathways listed for this record are ${names}. Each could be considered after the officer confirms the duty owed; none of this is a decision.`;
  }

  function templatePlan(record, moveon, review, placeholder) {
    if (!record || record.synthetic !== true) throw new Error('plans are drafted on synthetic records only');
    const r = record;
    const pids = r.eligible_pathways.map((p) => p.pathway_id);
    const has = (pid) => pids.includes(pid);
    const ids = new Set(r.eligible_pathways.flatMap((p) => p.officer_checks));
    const steps = [];
    for (const id of moveon.general_checks) { const t = text(moveon, id); steps.push({ text: t.text, owner: 'officer', confidence: t.confidence }); }
    for (const id of r.suitability_checks) { const t = text(moveon, id); steps.push({ text: t.text, owner: 'officer', confidence: t.confidence }); }
    for (const pid of pids) if (STEP[pid]) steps.push({ text: STEP[pid].text, owner: 'officer', confidence: STEP[pid].confidence });
    const checks = [];
    for (const p of r.eligible_pathways) for (const id of p.officer_checks) {
      const t = text(moveon, id);
      checks.push({ text: t.text, pathway_id: p.pathway_id, confidence: t.confidence });
    }
    const suggestions = r.eligible_pathways.map((p) => {
      const first = p.reasons.find((id) => id !== p.pathway_id + '.when');
      return { pathway_id: p.pathway_id, why: text(moveon, first).text, confidence: 'Likely' };
    });
    const risks = RISKS.filter(([when]) => when(r, ids, has)).map(([, claim]) => ({ text: claim.text, confidence: claim.confidence }));
    const plan = {
      schema_version: '1',
      household_id: r.id,
      record_is_synthetic: true,
      status: 'draft for officer review',
      summary: { text: summary(r), confidence: 'Certain' },
      pathway_suggestions: suggestions.slice(0, LIMITS.pathway_suggestions),
      steps: steps.slice(0, LIMITS.steps),
      officer_checks: checks.slice(0, LIMITS.officer_checks),
      risks: risks.slice(0, LIMITS.risks),
    };
    if (Array.isArray(review) && review.length) {
      if (typeof placeholder !== 'string' || !placeholder) throw new Error('the placeholder answer is needed with reviewer notes');
      plan.responds_to_review = review.map((n) => ({ note: n.id, change: placeholder, confidence: 'Certain' }));
    }
    return plan;
  }

  return { templatePlan, PLACE, NAME };
});
