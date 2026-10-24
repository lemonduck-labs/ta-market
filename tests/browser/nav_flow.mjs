// The planner's navigation (fd-core's shell), with the mock capabilities: the sidebar's queues and
// views with their counts and links, a household opened from a view with its place in it, j and k
// between households, Escape back to the row it came from, the search palette, the shortcuts
// sheet, g then a letter, and the drawer on a narrow screen. Synthetic records only.
// Usage: node nav_flow.mjs http://localhost:8766 shots/nav
import { chromium } from 'playwright';
import assert from 'assert';
import fs from 'fs';
const base = process.argv[2] || 'http://localhost:8766';
const out = process.argv[3] || 'shots/nav';
const records = JSON.parse(fs.readFileSync(new URL('../../demo/ta/synthetic_caseload.json', import.meta.url), 'utf8')).records;
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch());
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|404/.test(m.text())) logs.push(m.text()); });
page.on('pageerror', (e) => logs.push('pageerror: ' + e.message));
const open = async (q, hash) => { await page.goto('about:blank'); await page.goto(`${base}/index.html?${q}#${hash}`); await page.waitForTimeout(600); };
const step = (name) => console.log('step:', name);
const item = (label) => page.locator('.fs-item', { has: page.locator('.fs-label', { hasText: new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }) });
const count = async (label) => { const c = item(label).locator('.fs-count'); return (await c.count()) ? Number(await c.innerText()) : null; };
const rows = () => page.$$eval('#view-caseload button.crow', (els) => els.map((e) => e.getAttribute('title').replace('Open ', '')));
const ood = records.filter((r) => r.suitability_checks.includes('out-of-district'));
const long = records.filter((r) => r.weeks_in_ta >= 104);
const bnb = records.filter((r) => r.suitability_checks.includes('bnb-family-limit'));

step('reset');
await open('role=owner&uid=u_owner', 'caseload');
await page.evaluate(() => localStorage.clear());
await open('role=owner&uid=u_owner', 'caseload');

step('the sidebar: queues named for the job, views with their counts');
for (const label of ['Caseload', 'Plans to approve', 'Returned to me', 'My households', 'Family in B&B', 'Out of district', 'Two years or more in TA', 'Scenario', 'Lessons', 'Method', 'Audit log']) {
  assert.equal(await item(label).count(), 1, 'no sidebar item ' + label);
}
assert.equal(await count('Caseload'), records.length);
assert.equal(await count('Out of district'), ood.length);
assert.equal(await count('Two years or more in TA'), long.length);
assert.equal(await count('Family in B&B'), bnb.length);
assert.equal(await count('Plans to approve'), null, 'an empty work queue shows no count');
assert.equal(await page.getAttribute('#tab-caseload', 'aria-current'), 'page');
assert.equal((await rows()).length, records.length, 'the caseload lists every household');
assert.equal(await page.locator('#view-caseload .qgroup[data-group="new"]').count(), 1, 'no group for households with no plan');

step('a view: its own link, its households, longest in TA first');
await item('Out of district').click();
await page.waitForFunction(() => location.hash === '#ood');
let list = await rows();
assert.deepEqual([...list].sort(), ood.map((r) => r.id).sort(), 'out of district lists the wrong households');
const weeks = list.map((id) => records.find((r) => r.id === id).weeks_in_ta);
assert.deepEqual(weeks, [...weeks].sort((a, b) => b - a), 'not longest in TA first');
assert.equal(await page.getAttribute('#nav-ood', 'aria-current'), 'page');
assert((await page.locator('.fs-crumbs').innerText()).includes('Out of district'), 'the breadcrumb does not name the view');
await page.screenshot({ path: out + '-1-view.png' });

step('j and k move through the list; Enter opens the household with its place in the view');
await page.keyboard.press('j');
await page.keyboard.press('j');
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('title')), 'Open ' + list[1]);
await page.keyboard.press('Enter');
await page.waitForFunction((id) => location.hash === '#file-' + id, list[1]);
assert((await page.locator('#view-file .pane-nav').innerText()).includes(`2 of ${ood.length}`), 'no place in the view');
assert((await page.locator('#view-file .pane-nav .back').innerText()).includes(`Out of district (${ood.length})`));
assert((await page.locator('#view-file .rec-id').innerText()) === list[1]);
assert((await page.locator('#view-file .trail').innerText()).includes('No plan yet'), 'no trail');

step('j and k on a household go to the next and previous one in the view');
await page.keyboard.press('j');
await page.waitForFunction((id) => location.hash === '#file-' + id, list[2]);
await page.keyboard.press('k');
await page.waitForFunction((id) => location.hash === '#file-' + id, list[1]);

step('Escape goes back to the view, to the row it came from');
await page.keyboard.press('Escape');
await page.waitForFunction(() => location.hash === '#ood');
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('title')), 'Open ' + list[1], 'focus not back on the row');

step('the search palette finds a household by its id and opens it');
await page.keyboard.press('Control+k');
await page.waitForSelector('.fs-pal input');
await page.keyboard.type('SYN-0114');
await page.waitForSelector('.fs-opt[aria-selected="true"]');
assert((await page.locator('.fs-opt[aria-selected="true"]').innerText()).includes('SYN-0114'));
await page.screenshot({ path: out + '-2-palette.png' });
await page.keyboard.press('Enter');
await page.waitForFunction(() => location.hash === '#file-SYN-0114');
assert.equal(await page.locator('.fs-layer').count(), 0, 'the palette stayed open');

step('the palette finds pages too, and says when nothing matches');
await page.keyboard.press('/');
await page.keyboard.type('audit');
await page.waitForSelector('.fs-opt[aria-selected="true"]');
assert((await page.locator('.fs-opt[aria-selected="true"]').innerText()).includes('Audit log'));
await page.keyboard.press('Enter');
await page.waitForFunction(() => location.hash === '#audit');
await page.keyboard.press('Control+k');
await page.keyboard.type('zzzz nothing');
await page.waitForSelector('.fs-empty');
await page.keyboard.press('Escape');
assert.equal(await page.locator('.fs-layer').count(), 0);

step('the shortcuts sheet, and g then a letter');
await page.keyboard.press('?');
await page.waitForSelector('.fs-sheet');
assert((await page.locator('.fs-sheet').innerText()).includes('Go to the scenario'));
await page.keyboard.press('Escape');
assert.equal(await page.locator('.fs-sheet').count(), 0);
assert.equal(await page.evaluate(() => location.hash), '#audit', 'Escape on the sheet also left the page');
await page.keyboard.press('g');
await page.keyboard.press('s');
await page.waitForFunction(() => location.hash === '#scenario');
await page.keyboard.press('g');
await page.keyboard.press('c');
await page.waitForFunction(() => location.hash === '#caseload');

step('typing in a field does not trigger the keys');
await page.click('input[aria-label="Find a record id"]');
await page.keyboard.type('gs');
assert.equal(await page.evaluate(() => location.hash), '#caseload');
await page.fill('input[aria-label="Find a record id"]', '');

step('a view reloads from its link');
await open('role=owner&uid=u_owner', 'long');
assert.deepEqual((await rows()).sort(), long.map((r) => r.id).sort());
assert((await page.locator('#view-caseload .head-row').innerText()).includes(`${long.length} of ${records.length} households`));

step('How it works: from the sidebar, from its link, and the brand it carries');
await item('How it works').click();
await page.waitForFunction(() => location.hash === '#guide');
await page.waitForTimeout(300);
assert.equal((await page.locator('#view-guide h1').innerText()).trim(), 'How it works');
{
  const g = await page.locator('#view-guide').innerText();
  for (const want of ['Who uses it', 'A typical week', 'In this copy', 'What a deployment could add', 'Improving it']) assert(g.includes(want), 'the guide has no ' + want);
}
assert.equal(await page.getAttribute('#tab-guide', 'aria-current'), 'page');
await open('role=owner&uid=u_owner', 'guide');
assert(await page.locator('#view-guide').isVisible(), 'the guide does not open from its link');
assert.equal(await page.locator('.fs-brand b').innerText(), 'Move forward');
assert(await page.evaluate(() => getComputedStyle(document.querySelector('.fs-mark')).backgroundImage.startsWith('url("data:image/svg+xml')), 'no brand mark in the sidebar');
await page.evaluate(() => document.fonts.ready);
// document.fonts.check is true when no face matches, so look for the face itself and its status.
assert(await page.evaluate(() => [...document.fonts].some((f) => f.family.replace(/["']/g, '') === 'Poppins' && f.style === 'italic' && f.status === 'loaded')), 'the brand font is not loaded');

step('the overview: a fresh visit lands on it; the pipeline counts every household once');
await page.evaluate(() => localStorage.clear());
await page.goto('about:blank'); await page.goto(`${base}/index.html?role=owner&uid=u_owner`); await page.waitForTimeout(800);
assert.equal(await page.evaluate(() => location.hash), '#overview', 'a fresh visit does not land on the overview');
{
  const nums = await page.$$eval('#view-overview .pipe-k b', (els) => els.map((e) => Number(e.textContent.replace(/,/g, ''))));
  assert.equal(nums.reduce((a, b) => a + b, 0), records.length, 'the pipeline does not add up to the caseload');
  const ov = await page.locator('#view-overview').innerText();
  for (const want of ['Needs a decision', 'Time in temporary accommodation', 'Checks raised', 'Weekly cost of the caseload', 'synthetic']) assert(ov.includes(want), 'the overview has no ' + want);
  const low = records.reduce((t, r) => t + r.weekly_cost_from, 0);
  assert(ov.includes(`£${low.toLocaleString('en-GB')} to`), 'the weekly cost range does not start at the sum of the bands');
}
step('the board: a lane for each stage, every household in one lane');
await open('role=owner&uid=u_owner', 'board');
await page.waitForSelector('#view-board .lane');
{
  const ns = await page.$$eval('#view-board .lane-n', (els) => els.map((e) => Number(e.textContent.replace(/,/g, ''))));
  assert.equal(ns.reduce((a, b) => a + b, 0), records.length, 'the board does not add up to the caseload');
  await page.locator('#view-board .bcard').first().click();
  await page.waitForFunction(() => location.hash.startsWith('#file-'));
}
step('taking a household says so, and Undo puts it back');
await page.locator('button', { hasText: 'Take this household' }).first().click();
await page.waitForSelector('.fs-toast');
assert((await page.locator('.fs-toast').innerText()).includes('You have this household'));
await page.locator('.fs-toast button', { hasText: 'Undo' }).click();
await page.waitForSelector('button:has-text("Take this household")');
assert(await page.locator('.fs-secbar').count() === 1, 'no section bar on the household');

step('a household reads as one record: sections fold and stay folded, the next step opens its section');
const hh = records.find((r) => r.accommodation_type === 'bed_and_breakfast') || records[0];
await open('role=owner&uid=u_owner', 'file-' + hh.id);
await page.waitForSelector('#sec-checks .sec-toggle');
const tg = page.locator('#sec-checks .sec-toggle');
assert.equal(await tg.getAttribute('aria-expanded'), 'true', 'the checks section starts folded');
const ctl = await tg.getAttribute('aria-controls');
assert(ctl && await page.locator('#' + ctl).count() === 1, 'the toggle does not name the body it controls');
await tg.click();
await page.waitForTimeout(200);
assert.equal(await tg.getAttribute('aria-expanded'), 'false', 'the checks section did not fold');
assert(await page.locator('#' + ctl).isHidden(), 'the folded body still shows');
await open('role=owner&uid=u_owner', 'file-' + hh.id);
await page.waitForSelector('#sec-checks .sec-toggle');
assert.equal(await page.getAttribute('#sec-checks .sec-toggle', 'aria-expanded'), 'false', 'the fold was not kept');
await page.click('#sec-checks .sec-toggle');
await page.click('#sec-plan .sec-toggle');
await page.waitForTimeout(200);
assert.equal(await page.getAttribute('#sec-plan .sec-toggle', 'aria-expanded'), 'false');
await page.click('.rec-actions button.primary');
await page.waitForTimeout(300);
assert.equal(await page.getAttribute('#sec-plan .sec-toggle', 'aria-expanded'), 'true', 'the next step did not open the plan');
assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.closest('#sec-plan') !== null), true, 'focus did not move to the plan');

step('the rail: official references, each a link with the date it was read');
const refs = JSON.parse(fs.readFileSync(new URL('../../tamarket/spec/references.json', import.meta.url), 'utf8')).references;
const links = await page.$$eval('#rail-refs a', (as) => as.map((a) => [a.textContent, a.href, a.rel]));
assert.equal(links.length, refs.length, 'the references panel does not list every reference');
for (const [i, x] of refs.entries()) {
  assert.equal(links[i][0], x.title); assert.equal(links[i][1], x.url); assert(links[i][2].includes('noopener'));
}

step('drill-through: every household in a type of accommodation, and on a route out');
await page.click(`.rec-actions >> text=Everyone in`);
await page.waitForFunction((k) => location.hash === '#type-' + k, hh.accommodation_type);
const inType = records.filter((r) => r.accommodation_type === hh.accommodation_type);
assert.equal(await page.locator('#view-type .ov-row').count(), inType.length, 'the type page lists the wrong households');
assert((await page.locator('#view-type .statline').innerText()).includes(String(inType.length)));
assert((await page.locator('.fs-crumbs').innerText()).includes('Caseload'), 'no way back up from the type page');
const route = 'social-housing';
await open('role=owner&uid=u_owner', 'route-' + route);
const onRoute = records.filter((r) => r.eligible_pathways.some((x) => x.pathway_id === route));
assert.equal(await page.locator('#view-route .ov-row').count(), onRoute.length, 'the route page lists the wrong households');
await page.locator('#view-route .ov-row').first().click();
await page.waitForFunction(() => location.hash.startsWith('#file-'));
await open('role=owner&uid=u_owner', 'type-no_such_type');
await page.waitForTimeout(400);
const landed = await page.evaluate(() => location.hash);
assert(!landed.startsWith('#type-') && await page.locator('#view-type').isHidden(), 'an unknown type left a blank page at ' + landed);

step('team and access: the roles and what each can do');
await open('role=owner&uid=u_owner', 'team');
for (const role of ['Viewer', 'Contributor', 'Editor', 'Owner']) assert((await page.locator('#view-team').innerText()).includes(role), 'no ' + role + ' on the team page');

step('narrow screen: a drawer in place of the sidebar');
await page.setViewportSize({ width: 390, height: 860 });
await open('role=owner&uid=u_owner', 'caseload');
assert(!(await page.locator('.fs-side').isVisible()) || (await page.locator('.fs-side').boundingBox()).x < -100, 'the sidebar shows on a phone');
await page.click('.fs-menu');
await page.waitForTimeout(300);
assert((await page.locator('.fs-side').boundingBox()).x >= 0, 'the drawer did not open');
await page.screenshot({ path: out + '-3-drawer.png' });
await item('Family in B&B').click();
await page.waitForFunction(() => location.hash === '#bnb');
await page.waitForTimeout(300);
assert(!(await page.locator('.fs').getAttribute('class')).includes('fs-drawer'), 'the drawer stayed open');
assert.deepEqual((await rows()).sort(), bnb.map((r) => r.id).sort());
const over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
assert(!over, 'horizontal overflow on a phone');

assert.deepEqual(logs, [], 'console errors: ' + logs.join(' | '));
console.log('nav flow passed');
await browser.close();
