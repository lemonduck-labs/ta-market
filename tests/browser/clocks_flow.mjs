// Phase 6.5 flow of the Move forward planner, on a fixed day (22 October 2026) so the clocks give
// the same answers on any day: the Compliance at risk page and its count, the s.208 notice (draft,
// dates refused, recorded), the s.213AA steps (asked, agreed, each body, a refusal), 6 weeks in
// B&B (the day to move by), a review's eight weeks and a longer period, the handover summary, the
// pilot timings, what a viewer sees, where the keyboard goes after a button, and alerts announced
// once.
// Synthetic records only.
// Usage: node clocks_flow.mjs http://localhost:8766 shots/clocks
import { chromium } from 'playwright';
import assert from 'assert';
import fs from 'fs';
const base = process.argv[2] || 'http://localhost:8766';
const out = process.argv[3] || 'shots/clocks';
const records = JSON.parse(fs.readFileSync(new URL('../../demo/ta/synthetic_caseload.json', import.meta.url), 'utf8')).records;
const byId = new Map(records.map((r) => [r.id, r]));
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch());
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
await page.clock.setFixedTime(new Date('2026-10-22T10:00:00Z'));
const logs = [];
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|404/.test(m.text())) logs.push(m.text()); });
page.on('pageerror', (e) => logs.push('pageerror: ' + e.message));
const open = async (q, hash) => { await page.goto('about:blank'); await page.goto(`${base}/index.html?${q}#${hash}`); await page.waitForTimeout(700); };
const step = (name) => console.log('step:', name);
const db = () => page.evaluate(() => JSON.parse(localStorage.getItem('mockdb') || '{}'));
const navCount = (label) => page.evaluate((l) => { const it = [...document.querySelectorAll('.fs-item')].find((e) => e.querySelector('.fs-label') && e.querySelector('.fs-label').textContent.trim() === l); const c = it && it.querySelector('.fs-count'); return c ? Number(c.textContent) : null; }, label);
const panel = () => page.locator('#notices-panel').innerText();
const OWNER = 'role=owner&uid=u_owner';

// What the records say on 22 October 2026: the out-of-district notices with none on record are
// overdue; the families in B&B are past 6 weeks, or within 14 days of it; households with a child
// placed since 1 September 2026 are to start.
const lastDay = (iso, n) => { const [y, m, d] = iso.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d + n - 1)).toISOString().slice(0, 10); };
const plus = (iso, n) => lastDay(iso, n + 1);
const today = '2026-10-22';
const CLOCKS = JSON.parse(fs.readFileSync(new URL('../../tamarket/spec/clocks.json', import.meta.url), 'utf8'));
const fill = (line) => line.replace(/\{([^}]+)\}/g, (m, what) => `[${what}: added in a council deployment]`);
const s208Overdue = records.filter((r) => r.placed_in_another_district && !r.s208_notice_sent_on && lastDay(r.placed_on, 14) < today);
const bnb = records.filter((r) => r.suitability_checks.includes('bnb-family-limit'));
// 6 weeks beginning with the placement end on the placement day plus 41, the day to move by; from the
// next day 6 weeks are reached.
const bnbPast = bnb.filter((r) => lastDay(r.placed_on, 42) < today), bnbSoon = bnb.filter((r) => lastDay(r.placed_on, 42) >= today && plus(r.placed_on, 27) <= today);
// s.213AA is for each child: one item to start for every child placed since 1 September 2026.
const toStart = records.filter((r) => r.children > 0 && r.placed_on >= '2026-09-01');
const childrenToStart = toStart.reduce((n, r) => n + r.children, 0);
assert(s208Overdue.length && bnbPast.length && bnbSoon.length && toStart.length, 'the caseload no longer gives each clock something to show');

step('reset');
await open(OWNER, 'overview');
await page.evaluate(() => localStorage.clear());
await open(OWNER, 'overview');

step('Compliance at risk: a page in the Work group, its count the overdue and due items');
const risk = s208Overdue.length + bnbPast.length + bnbSoon.length;
assert.equal(await navCount('Compliance at risk'), risk, 'the sidebar count');
await open(OWNER, 'compliance');
const groupCount = async (title) => { const g = page.locator('#view-compliance section.card', { has: page.locator('h2', { hasText: new RegExp('^' + title + '$') }) }); return (await g.count()) ? g.locator('li.task').count() : 0; };
assert.equal(await groupCount('Overdue'), s208Overdue.length + bnbPast.length);
assert.equal(await groupCount('Due in the next 14 days'), bnbSoon.length);
assert.equal(await groupCount('To start'), childrenToStart, 'one item for each child');
const ctext = await page.locator('#view-compliance').innerText();
assert(ctext.includes('No time limit in the section'), 'the ask step shows no invented deadline');
assert(ctext.includes('made up for the demo'), 'the s.208 history is labelled');
await page.screenshot({ path: out + '-1-compliance.png', fullPage: true });

step('s.208: the notice is overdue, the draft carries placeholders, dates are checked');
const hh = records.find((r) => r.placed_in_another_district && !r.s208_notice_sent_on && r.children > 0 && r.placed_on >= '2026-09-01');
assert(hh, 'no record for the notice steps');
await page.locator('#view-compliance button', { hasText: hh.id }).first().click();
await page.waitForFunction((id) => location.hash === '#file-' + id, hh.id);
await page.waitForSelector('#clock-s208');
assert((await page.locator('#clock-s208').innerText()).includes('Overdue · ' + new Date(lastDay(hh.placed_on, 14) + 'T00:00:00Z').getUTCDate()), 'the last day');
assert((await page.locator('#clock-s208').innerText()).includes('No notice on record: the placement date and the history before the planner are synthetic, made up for the demo.'), 'the made-up label');
await page.click('#clock-s208 >> text=Draft the notice');
const draft = await page.locator('#clock-s208 pre').innerText();
assert(draft.includes('[applicant’s name: added in a council deployment]') && draft.includes('[address: added in a council deployment]'), 'placeholders');
assert(draft.includes('within 14 days beginning with the day the accommodation was made available'), 'the time limit in the draft');
assert(!draft.includes('—'), 'em dash in the draft');
await page.click('#clock-s208 >> text=Save the draft as a file');
await page.waitForTimeout(300);
let dls = await page.evaluate(() => window.__downloads);
assert(dls.some((d) => d.filename === `${hh.id}-s208-notice-draft.txt`), 'the draft was not saved');
await page.fill('#clock-s208 input[type=date]', '2026-10-30');
await page.click('#clock-s208 >> text=Record as sent');
await page.waitForTimeout(300);
assert((await page.locator('#clock-s208').innerText()).includes('cannot be in the future'), 'a future date was accepted');
assert.equal(await page.locator('#clock-s208 [role=alert]', { hasText: 'cannot be in the future' }).count(), 1, 'the message is not in a live region');
// A store refresh redraws the page: the message stays on screen and is not announced again.
await page.evaluate(() => window.dispatchEvent(new StorageEvent('storage', { key: 'mockdb' })));   // the mock store tells every watch
await page.waitForTimeout(300);
await page.evaluate(() => window.dispatchEvent(new StorageEvent('storage', { key: 'mockdb' })));
await page.waitForTimeout(300);
assert((await page.locator('#clock-s208').innerText()).includes('cannot be in the future'), 'the message went with the redraw');
assert.equal(await page.locator('#clock-s208 [role=alert]', { hasText: 'cannot be in the future' }).count(), 0, 'a redraw announces the message again');
await page.fill('#clock-s208 input[type=date]', '2026-10-21');
await page.selectOption('#clock-s208 select', 'Email');
await page.click('#clock-s208 >> text=Record as sent');
await page.waitForTimeout(500);
const s208Text = await page.locator('#clock-s208').innerText();
assert(s208Text.includes('Sent late · 21 Oct 2026') && s208Text.includes('by email'), 'the notice was not recorded: ' + s208Text);
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), 'clock-s208-h', 'the keyboard did not go back to the clock');
let d = await db();
assert(d[`notices/${hh.id}~s208`] && d[`notices/${hh.id}~s208`].status === 'sent' && d[`notices/${hh.id}~s208`].recorded_by === 'u_owner', 'the notice record');

step('s.213AA: asked, the answer body by body, each body’s own information and clock, drafts by body');
assert.equal(hh.children, 1, 'the flow expects a household with one child here');
const sec = page.locator('#clock-child');
const kid = page.locator('#clock-child-1');
const st = await sec.innerText();
assert(st.includes('Check the application date') && st.includes('A notification will be issued for each child'), 'the per-child rule');
assert(st.includes('the section speaks of one agreement') && st.includes('[Likely]'), 'the per-body agreement is a default');
// Asking before the placement is allowed: the 14 days run from the latest of the three dates.
await kid.locator('input[type=date]').first().fill(lastDay(hh.placed_on, -1));
await kid.locator('button', { hasText: 'Record that the parent was asked' }).click();
await page.waitForTimeout(400);
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), 'clock-child-h1', 'the keyboard did not go back to the child');
assert(!(await kid.innerText()).includes('cannot be before'), 'a date before the placement was refused');
await kid.locator('input[aria-label^="Answer on"]').fill(lastDay(hh.placed_on, -3));
await kid.locator('button', { hasText: /^Record the answer$/ }).click();
await page.waitForTimeout(300);
assert((await kid.innerText()).includes('The answer cannot be dated before the asking'), 'an answer dated before the asking was accepted');
await kid.locator('input[aria-label^="Answer on"]').fill('2026-10-01');
await kid.locator('button', { hasText: /^Record the answer$/ }).click();
await page.waitForTimeout(300);
assert((await kid.innerText()).includes('Give the answer for each body'), 'an answer was recorded without one for each body');
// The parent agrees to the GP practice and the school, not the health visiting service.
await kid.locator('select[aria-label^="Answer for the GP practice"]').selectOption('yes');
await kid.locator('select[aria-label^="Answer for the health visiting service"]').selectOption('no');
await kid.locator('select[aria-label^="Answer for the school"]').selectOption('yes');
await kid.locator('button', { hasText: /^Record the answer$/ }).click();
await page.waitForTimeout(400);
assert((await kid.innerText()).includes('take reasonable steps to notify it within 14 days'), 'the statute’s words');
d = await db();
const cKey = `notices/${hh.id}~c1~child`;
assert(d[cKey] && d[cKey].child_no === 1, 'the answer is for child 1');
assert.deepEqual([d[cKey].agreed_bodies, d[cKey].declined_bodies], [['gp', 'education'], ['health_visiting']], 'the answer body by body');
const bodyRow = (label) => kid.locator('li.body-row', { has: page.locator('b', { hasText: label }) });
assert((await bodyRow('Health visiting').innerText()).includes('Not agreed: no notice'), 'a body not agreed is not due');
assert.equal(await bodyRow('Health visiting').locator('text=Record as sent').count(), 0, 'a notice offered to a body not agreed');
assert((await bodyRow('GP practice').innerText()).includes('Waits on the information about this body'), 'no clock before the information');
assert((await bodyRow('GP practice').innerText()).includes('No GP practice? The guidance says the council will give the family information on how to register with one'), 'the prompt for a child with no GP practice');
assert((await sec.innerText()).includes('One recorded under another priority need'), 'young applicants under another priority need');
// The GP practice's information arrives first: its 14 days run from it, not from the school's.
await bodyRow('GP practice').locator('input[type=date]').fill('2026-10-02');
await bodyRow('GP practice').locator('button', { hasText: 'Record the information' }).click();
await page.waitForTimeout(400);
await bodyRow('School or other').locator('input[type=date]').fill('2026-10-12');
await bodyRow('School or other').locator('button', { hasText: 'Record the information' }).click();
await page.waitForTimeout(400);
assert((await bodyRow('GP practice').innerText()).includes('Overdue · 15 Oct 2026'), '14 days beginning with 2 October end on 15 October');
assert((await bodyRow('School or other').innerText()).includes('Due · 25 Oct 2026'), '14 days beginning with 12 October end on 25 October');
// Each body's draft carries what the guidance lists for it: no address to the GP practice.
await bodyRow('GP practice').locator('text=Draft the notice').click();
const gpDraft = await bodyRow('GP practice').locator('pre').innerText();
const [gpNotice, gpNotes] = gpDraft.split('Notes for the officer (not part of the notice):');
// Every line of the notice comes from spec/clocks.json child.contents, and nothing else of the planner's is in it.
for (const x of CLOCKS.rules.child.contents.gp.notice) assert(gpNotice.includes(fill(x.draft)), 'the GP practice draft lacks: ' + x.draft);
assert(!gpNotice.includes('[address') && !gpNotice.includes('No address') && !gpNotice.includes('child 1 of') && !gpNotice.includes(hh.id), 'the GP practice notice: ' + gpNotice);
assert(gpNotes && gpNotes.includes('will not include the new temporary address') && gpNotes.includes('how to register with a GP'), 'the notes for the officer: ' + gpNotes);
// Each line's basis reaches the officer: the GP practice's child line is the planner's reading, not the guidance's.
assert(gpNotes.includes('- Child: the planner\'s reading [Likely]') && gpNotes.includes('- Council reference: the planner\'s reading [Likely]'), 'the lines’ basis: ' + gpNotes);
assert(!gpDraft.includes('—'), 'em dash in the draft');
await bodyRow('GP practice').locator('text=Hide the draft').click();
assert.equal(await bodyRow('School or other').locator('input[aria-label^="Date sent"]').getAttribute('min'), '2026-10-12', 'the earliest date is the information’s');
await bodyRow('School or other').locator('input[aria-label^="Date sent"]').fill('2026-10-10');
await bodyRow('School or other').locator('text=Record as sent').click();
await page.waitForTimeout(300);
assert((await bodyRow('School or other').innerText()).includes('cannot be before 12 Oct 2026'), 'a notice dated before the information was accepted');
await bodyRow('School or other').locator('input[aria-label^="Date sent"]').fill('2026-10-21');
await bodyRow('School or other').locator('text=Record as sent').click();
await page.waitForTimeout(400);
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), 'clock-child-h1', 'the keyboard did not go back to the child');
await bodyRow('GP practice').locator('input[aria-label^="Date sent"]').fill('2026-10-20');
await bodyRow('GP practice').locator('text=Record as sent').click();
await page.waitForTimeout(500);
const s213 = await kid.innerText();
// Sent on 20 October: late against the GP practice's own date (15 October), whatever the school's.
assert(s213.includes('Sent late · 20 Oct 2026') && s213.includes('Sent on time · 21 Oct 2026') && s213.includes('so no notice goes to this body'), s213);
await page.screenshot({ path: out + '-2-notices.png', fullPage: true });
await open(OWNER, 'compliance');
assert.equal(await navCount('Compliance at risk'), risk - 1, 'the recorded s.208 notice left the count');
assert.equal(await groupCount('To start'), childrenToStart - 1, 'the child with their notices done left the list');

step('s.213AA for two children: each has their own agreement and notices; the household stays until both are done');
const two = toStart.find((r) => r.children === 2 && r.id !== hh.id);
await open(OWNER, 'file-' + two.id);
await page.waitForSelector('#clock-child-2');
await page.locator('#clock-child-1 button', { hasText: 'Record it for all 2 children not yet asked' }).click();
await page.waitForTimeout(500);
const c1 = page.locator('#clock-child-1');
for (const b of ['GP practice', 'health visiting service', 'school']) await c1.locator(`select[aria-label^="Answer for the ${b}"]`).selectOption('yes');
await c1.locator('button', { hasText: /^Record the answer$/ }).click();
await page.waitForTimeout(400);
const hvRow = c1.locator('li.body-row', { has: page.locator('b', { hasText: 'Health visiting' }) });
await hvRow.locator('input[type=date]').fill('2026-10-20');
await hvRow.locator('button', { hasText: 'Record the information' }).click();
await page.waitForTimeout(400);
await hvRow.locator('text=Draft the notice').click();
const hvDraft = await hvRow.locator('pre').innerText();
const [hvNotice, hvNotes] = hvDraft.split('Notes for the officer (not part of the notice):');
for (const x of CLOCKS.rules.child.contents.health_visiting.notice) assert(hvNotice.includes(fill(x.draft)), 'the health visiting draft lacks: ' + x.draft);
assert(!hvNotice.includes('child 1 of') && hvNotes.includes('If the child is pregnant, change the last two lines of the notice to the child’s own contact number and name'), 'the health visiting draft: ' + hvDraft);
d = await db();
assert(d[`notices/${two.id}~c1~child`].status === 'agreed' && d[`notices/${two.id}~c2~child`].status === 'asked', 'each child has their own agreement');
assert.equal(d[`notices/${two.id}~c1~child-health_visiting`].info_on, '2026-10-20', 'the information date sits on the body');
await open(OWNER, 'compliance');
const ctext2 = await page.locator('#view-compliance').innerText();
assert(ctext2.includes('Child 1: notice to the health visiting service for the area') && ctext2.includes(two.id), 'child 1’s body is due');
assert.equal(await groupCount('To start'), childrenToStart - 3, 'both children asked');
// The household stays on the page until both children are done: what waits on it is listed apart.
assert.equal(await groupCount('Waiting on the household'), 3, 'child 1’s GP practice and school wait on their information, child 2 on the answer');
assert(ctext2.includes('Child 2: waiting for the answer'), 'child 2 waits on the answer');

step('s.213AA: a parent who does not agree means no notice');
const other = toStart.find((r) => r.id !== hh.id && r.children === 1);   // one child, so the refusal finishes the household
await open(OWNER, 'file-' + other.id);
await page.waitForSelector('#clock-child');
await page.locator('#clock-child-1 button', { hasText: 'Record that the parent was asked' }).click();
await page.waitForTimeout(400);
await page.click('#clock-child-1 >> text=Did not agree to any body');
await page.waitForTimeout(400);
assert((await page.locator('#clock-child').innerText()).includes('no notice is sent'));
assert.equal(await page.locator('#clock-child li.body-row').count(), 0, 'bodies shown after a refusal');

step('before 1 September 2026 the s.213AA duty does not apply; a family in B&B shows its 6 weeks');
const early = records.find((r) => r.children > 0 && r.placed_on < '2026-09-01' && !r.placed_in_another_district);
await open(OWNER, 'file-' + early.id);
await page.waitForSelector('#notices-panel');
assert((await panel()).includes('the duty does not apply'));
const soon = bnbSoon[0];
await open(OWNER, 'file-' + soon.id);
await page.waitForSelector('#clock-bnb');
const lim = lastDay(soon.placed_on, 42), [ly, lm, ld] = lim.split('-').map(Number);
assert((await page.locator('#clock-bnb').innerText()).includes(`Within 14 days · move by ${ld} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][lm - 1]} ${ly}`), 'the day to move by');
await open(OWNER, 'file-' + bnbPast[0].id);
await page.waitForSelector('#clock-bnb');
assert((await page.locator('#clock-bnb').innerText()).includes('6 weeks reached · move by'), 'past 6 weeks');
await open(OWNER, 'file-' + soon.id);
await page.waitForSelector('#clock-bnb');
assert((await page.locator('#clock-bnb').innerText()).includes('a total of periods'), 'the Order’s words');
const bnbText = await page.locator('#clock-bnb').innerText();
assert(bnbText.includes('a day on the safe side') && bnbText.includes('Code 17.40') && bnbText.includes('only as a last resort'), 'what the clock leaves out');

step('a review: eight weeks beginning with the request; overdue ones reach the page; a decision clears it');
const long = bnbPast[0];
await open(OWNER, 'file-' + long.id);
await page.waitForSelector('#reviews-panel');
await page.click('#reviews-panel >> text=+ Record a review request');
await page.fill('#reviews-panel input[aria-label="Review requested on"]', '2026-08-20');
await page.click('#reviews-panel >> text=Record the request');
await page.waitForTimeout(400);
assert((await page.locator('#reviews-panel').innerText()).includes('Overdue · 14 Oct 2026'), 'eight weeks beginning with 20 August end on 14 October');
assert((await page.locator('#reviews-panel').innerText()).includes('It does not track a review decided in three weeks'), 'what the clock covers');
const revText = await page.locator('#reviews-panel').innerText();
assert(revText.includes('although this right does not apply in the case of interim accommodation secured under sections 188, 190, 200(1), 204(4)'), 'interim accommodation');
assert(!revText.includes('the same eight weeks') && revText.includes('(s.202(1)(ba)(i) or (bc)) is decided in three weeks (reg. 9(1)(a)) and is not'), 'other reviews and their periods: ' + revText);
await page.click('#reviews-panel >> text=Record the decision or a longer period');
assert.equal(await page.locator('#reviews-panel input[aria-label="Longer period agreed in writing, to"]').getAttribute('min'), '2026-10-14', 'a longer period starts at the statutory date');
await page.fill('#reviews-panel input[aria-label="Longer period agreed in writing, to"]', '2026-10-01');
await page.waitForTimeout(400);
d = await db();
assert(!Object.entries(d).find(([k, v]) => k.startsWith('reviews/') && v.agreed_to), 'a longer period before the statutory date was recorded');
await page.click('#reviews-panel >> text=Close');
await open(OWNER, 'compliance');
assert((await page.locator('#view-compliance').innerText()).includes('Decision on the review'));
await open(OWNER, 'file-' + long.id);
await page.click('#reviews-panel >> text=Record the decision or a longer period');
await page.fill('#reviews-panel input[aria-label="Decision notified on"]', '2026-10-15');
await page.waitForTimeout(500);
assert((await page.locator('#reviews-panel').innerText()).includes('Decided late · 15 Oct 2026'));
d = await db();
const rv = Object.entries(d).find(([k]) => k.startsWith('reviews/'));
assert(rv && rv[1].decided_on === '2026-10-15' && rv[1].decided_by === 'u_owner', 'the review record');

step('the handover summary: what changed since a date, saved as a file');
await open(OWNER, 'file-' + hh.id);
await page.waitForSelector('#handover-panel');
const hv = await page.locator('#handover-panel').innerText();
assert(hv.includes('Changes since') && hv.includes('recorded a notice'), 'the changes since');
await page.click('#handover-panel >> text=Prepare a handover');
await page.click('#handover-panel >> text=Save the handover (.md)');
await page.waitForTimeout(400);
dls = await page.evaluate(() => window.__downloads);
const ho = dls.find((x) => x.filename === `${hh.id}-handover.md`);
assert(ho && ho.data.includes(`# Handover: ${hh.id} (synthetic record)`) && ho.data.includes('recorded the answer on a child’s notices'), 'the handover file');
assert(!ho.data.includes('—'), 'em dash in the handover');

step('a plan started from the template and submitted is one timed task');
const fresh = records.find((r) => ![hh.id, other.id, soon.id].includes(r.id) && r.children === 0);
await open(OWNER, 'file-' + fresh.id);
await page.click('text=Start from the template');
await page.click('text=Save draft');
await page.waitForSelector('text=Submit for approval');
await page.click('text=Submit for approval');
await page.waitForTimeout(500);
step('pilot timings: this browser’s log, no household or person in it, exported as CSV');
await open(OWNER, 'timings');
const row = (k) => page.locator(`#view-timings tr[data-task="${k}"] td`);
assert.equal(await row('notices').nth(1).innerText(), '2', 'the two placements whose notices were finished (one sent, one refused)');
assert.equal(await row('handover').nth(1).innerText(), '1', 'the handover task was not logged');
assert.equal(await row('plan').nth(1).innerText(), '1', 'the plan task was not logged');
const log = await page.evaluate(() => JSON.parse(localStorage.getItem('mop.pilot_steps') || '[]'));
const raw = JSON.stringify(await page.evaluate(() => ({ ...localStorage })));
assert(!/SYN-\d{4}/.test(JSON.stringify(log)) && !raw.match(/pilot_steps[^}]*SYN-/), 'the timing log holds a household id');
await page.click('#view-timings >> text=Export .csv');
await page.waitForTimeout(300);
dls = await page.evaluate(() => window.__downloads);
const csv = dls.find((x) => x.filename === 'move-forward-pilot-timings.csv');
assert(csv && csv.data.startsWith('task,started_at,ended_at,minutes,steps') && !/SYN-/.test(csv.data), 'the CSV');
await page.screenshot({ path: out + '-3-timings.png', fullPage: true });

step('a viewer sees the clocks and records nothing');
await open('role=viewer&uid=u_viewer', 'file-' + toStart.find((r) => ![hh.id, other.id, two.id].includes(r.id)).id);
await page.waitForSelector('#clock-child');
assert.equal(await page.locator('#notices-panel button', { hasText: 'Record' }).count(), 0, 'a viewer can record');
assert.equal(await page.locator('#reviews-panel button', { hasText: 'Record a review request' }).count(), 0);

step('a 16 or 17 year old applicant is asked themselves, and the health visiting draft gives their own name and number');
const young = records.find((r) => r.priority_need === 'applicant aged 16 or 17');
const { createHash } = await import('node:crypto');
let caseBody = null;
await page.route('**/data/caseload.json', async (route) => {
  const res = await route.fetch();
  const doc = await res.json();
  for (const r of doc.records) if (r.id === young.id) r.placed_on = '2026-09-10';   // placed after the section came into force, for this step only
  caseBody = JSON.stringify(doc);
  await route.fulfill({ response: res, body: caseBody, headers: { 'content-type': 'application/json' } });
});
await page.route('**/data/manifest.json', async (route) => {
  const res = await route.fetch();
  const m = await res.json();
  const cr = await (await page.context().request.get(base + '/data/caseload.json')).json();
  for (const r of cr.records) if (r.id === young.id) r.placed_on = '2026-09-10';
  m.files['data/caseload.json'] = createHash('sha256').update(JSON.stringify(cr)).digest('hex');
  await route.fulfill({ response: res, json: m });
});
await open(OWNER, 'file-' + young.id);
await page.waitForSelector('#clock-child-1');
const yk = page.locator('#clock-child-1');
assert((await yk.innerText()).includes('The applicant (16 or 17)') && (await yk.innerText()).includes('s.213AA(3)'), 'the applicant is asked');
await yk.locator('button', { hasText: 'Record that the applicant was asked' }).click();
await page.waitForTimeout(400);
await yk.locator('select[aria-label^="Answer for the GP practice"]').selectOption('no');
await yk.locator('select[aria-label^="Answer for the health visiting service"]').selectOption('yes');
await yk.locator('select[aria-label^="Answer for the school"]').selectOption('no');
await yk.locator('button', { hasText: /^Record the answer$/ }).click();
await page.waitForTimeout(400);
const yhv = yk.locator('li.body-row', { has: page.locator('b', { hasText: 'Health visiting' }) });
await yhv.locator('input[type=date]').fill('2026-10-20');
await yhv.locator('button', { hasText: 'Record the information' }).click();
await page.waitForTimeout(400);
await yhv.locator('text=Draft the notice').click();
const yDraft = await yhv.locator('pre').innerText();
const [yNotice] = yDraft.split('Notes for the officer (not part of the notice):');
assert(yNotice.includes('The applicant’s own contact number: [the applicant’s contact number') && yNotice.includes('The applicant’s own name: [the applicant’s name'), 'the young applicant’s own details: ' + yNotice);
assert(!yNotice.includes('contact number for the child’s parent') && !yNotice.includes('The name of the person reachable'), 'a relative’s details asked for a young applicant: ' + yNotice);
await page.unroute('**/data/caseload.json');
await page.unroute('**/data/manifest.json');

step('narrow screen: no horizontal overflow on a household or the compliance page');
await page.setViewportSize({ width: 390, height: 860 });
for (const hash of ['file-' + hh.id, 'compliance', 'timings']) {
  await open(OWNER, hash);
  assert(!(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), 'horizontal overflow on ' + hash);
}

assert.deepEqual(logs, [], 'console errors: ' + logs.join(' | '));
console.log('clocks flow passed');
await browser.close();
