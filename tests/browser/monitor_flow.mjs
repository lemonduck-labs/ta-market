// Phase 7 flow of the Move forward planner: the Monitor page and its count, an item accepted with
// a grade the officer sets, one rejected with a reason, a note that names someone refused, the
// accepted item on each household it touches and beside the reference it touches, a viewer who
// reads and decides nothing, and the audit entries. Synthetic records only; the items are the
// published monitoring items (data/monitor.json).
// Usage: node monitor_flow.mjs http://localhost:8766 shots/monitor
import { chromium } from 'playwright';
import assert from 'assert';
import fs from 'fs';
const base = process.argv[2] || 'http://localhost:8766';
const out = process.argv[3] || 'shots/monitor';
const records = JSON.parse(fs.readFileSync(new URL('../../demo/ta/synthetic_caseload.json', import.meta.url), 'utf8')).records;
const items = fs.readFileSync(new URL('../../monitor/items.jsonl', import.meta.url), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
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
const OWNER = 'role=owner&uid=u_owner';
const card = (id) => page.locator(`article[data-item="${id}"]`);

const bnb = items.find((i) => (i.tags.checks || []).includes('bnb-family-limit') && i.source === 'lgsco');
const ch17 = items.find((i) => i.url.endsWith('/chapter-17-suitability-of-accommodation'));
assert(ch17 && ch17.updated, 'chapter 17 keeps its updated date');
assert(bnb && ch17, 'the seed items are missing');
const bnbHomes = records.filter((r) => r.suitability_checks.includes('bnb-family-limit'));
assert(bnbHomes.length > 0);

step('reset');
await open(OWNER, 'monitor');
await page.evaluate(() => localStorage.clear());
await open(OWNER, 'monitor');

step('the Monitor page lists every item as waiting, with its count in the sidebar');
await page.waitForSelector('#view-monitor article.mon-item');
assert.equal(await page.locator('#view-monitor article.mon-item').count(), items.length);
assert.equal(await navCount('Monitor'), items.length);
const text = await page.locator('#view-monitor').innerText();
assert(!text.includes('—'), 'em dash on the Monitor page');
assert((await card(bnb.id).innerText()).includes(`${bnbHomes.length} on this caseload`), 'households touched not counted');
assert((await card(bnb.id).innerText()).includes('A2: completely reliable source; probably true'), 'proposed grade not in words');
assert.equal(await page.locator('#view-monitor article.mon-item h2').count(), items.length, 'each item title is an h2 under the page h1');
assert((await card(bnb.id).locator('.mon-terms').innerText()).startsWith('Terms: Not the Open Government Licence'), 'the ombudsman terms line');
assert((await card(ch17.id).locator('.mon-terms').innerText()).startsWith('Terms: Open Government Licence v3.0'), 'the GOV.UK terms line');
assert((await card(ch17.id).locator('.mon-meta').innerText()).includes('published 22 Feb 2018 · updated 15 Oct 2026'), 'both dates on the card');

step('a note that names someone is refused; accepting sets the grade the officer chooses');
await card(bnb.id).locator('textarea').fill(['Read with', 'Zzqel', 'Vantor', 'from the team'].join(' '));   // a made-up name, put together here
await card(bnb.id).locator('button:has-text("Accept")').click();
await page.waitForSelector(`article[data-item="${bnb.id}"] .task-msg`);
await card(bnb.id).locator('textarea').fill('Read with the team; the six-week clock covers this.');
await card(bnb.id).locator('select').first().selectOption('A3');
await card(bnb.id).locator('button:has-text("Accept")').click();
await page.waitForTimeout(400);
assert.equal(await navCount('Monitor'), items.length - 1);
let d = (await db())[`monitor/${bnb.id}`];
assert(d && d.decision === 'accepted' && d.grade === 'A3' && d.by === 'u_owner', 'decision not recorded: ' + JSON.stringify(d));
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), 'mon-st-' + bnb.id.slice(4), 'the keyboard is not on the item\'s status');
assert.equal(await page.locator('#mon-st-' + bnb.id.slice(4)).innerText(), 'Accepted · A3', 'the decided item left the list under the keyboard');

step('rejecting needs a reason');
await card(ch17.id).locator('button:has-text("Reject")').click();
await page.waitForSelector(`article[data-item="${ch17.id}"] .task-msg`);
await card(ch17.id).locator('select').nth(1).selectOption('superseded');
await card(ch17.id).locator('button:has-text("Reject")').click();
await page.waitForTimeout(400);
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), 'mon-st-' + ch17.id.slice(4), 'the keyboard is not on the rejected item\'s status');
d = (await db())[`monitor/${ch17.id}`];
assert(d && d.decision === 'rejected' && d.reason === 'superseded' && !d.grade);
await page.click('#view-monitor .seg >> text=Accepted');
assert.equal(await page.locator('#view-monitor article.mon-item').count(), 1);
await page.screenshot({ path: out + '-1-monitor.png', fullPage: true });

step('the accepted item is on the rail of a household it touches, and beside its reference');
await open(OWNER, 'file-' + bnbHomes[0].id);
await page.waitForSelector('#rail-monitor');
assert((await page.locator('#rail-monitor').innerText()).includes(bnb.title));
assert((await page.locator('#rail-monitor').innerText()).includes('A3'));
assert((await page.locator('#rail-refs').innerText()).includes(`Monitoring: ${bnb.title} (A3)`));
const other = records.find((r) => !r.suitability_checks.includes('bnb-family-limit'));
await open(OWNER, 'file-' + other.id);
await page.waitForSelector('#slot-refs');
assert.equal(await page.locator('#rail-monitor').count(), 0, 'a household the item does not touch shows it');

step('a viewer reads the decisions and decides nothing');
await open('role=viewer&uid=u_viewer', 'monitor');
await page.waitForSelector('#view-monitor article.mon-item');
assert.equal(await page.locator('#view-monitor .mon-form').count(), 0, 'a viewer was offered the decision');

step('the audit log holds both decisions');
await open(OWNER, 'audit');
await page.waitForTimeout(400);
const audit = await page.locator('#view-audit').innerText();
assert(audit.includes('accepted a monitoring item') && audit.includes('rejected a monitoring item'), 'audit entries missing');

step('a site copy says how many items it leaves off, on the Monitor page and in Method');
await page.route('**/data/manifest.json', async (route) => {
  const res = await route.fetch();
  const m = await res.json();
  m.site_copy = { changed: ['data/monitor.json'], monitor_items_left_off: 3, why: 'their sources have no open licence, so they stay internal' };   // the site build's own words
  await route.fulfill({ response: res, json: m });
});
await open(OWNER, 'monitor');
await page.waitForSelector('#mon-site-copy');
assert.equal(await page.locator('#mon-site-copy').innerText(), 'This copy of the build was changed for the site (data/monitor.json). It leaves off 3 monitoring items: their sources have no open licence, so they stay internal.');
await open(OWNER, 'method');
assert((await page.locator('#view-method').innerText()).includes('It leaves off 3 monitoring items'), 'Method does not say what the copy leaves off');
await page.unroute('**/data/manifest.json');
await open(OWNER, 'monitor');
assert.equal(await page.locator('#mon-site-copy').count(), 0, 'a build that is not a site copy says it is one');

assert.deepEqual(logs, [], 'console errors: ' + logs.join(' | '));
console.log('monitor flow passed');
await browser.close();
