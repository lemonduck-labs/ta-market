/* The hosted planner's stand-in for window.claude, over Supabase.
 *
 * The planner page (app/src/page.js) reaches its store, sign-in, drafting and downloads through
 * claude.use('db' | 'user' | 'sample' | 'downloads'). Inside Claude those are the artifact's
 * capabilities. For the hosted version, `python scripts/build_app.py --target hosted` writes a page
 * that loads the Supabase client (supabase-js, its UMD build, pinned and checked by its SHA-384),
 * then the project's URL and publishable key, then this file, then the page unchanged.
 *
 * The page's record paths map to tables (supabase/migrations):
 *   members                   public.members (id = user_id)
 *   versions/<id>/v           public.versions where author = <id> (the page's "from" is from_source)
 *   decisions/<id>/d          public.decisions where author = <id>
 *   audit/<id>/e              public.audit where actor = <id>, read only: the database writes it.
 *                             The page's own entries are dropped, except exports, which go to
 *                             public.events, since no table change records them.
 *   files, moves              public.files, public.moves (id = household_id)
 *   checks                    public.checks, one row per check, read back as {items: {id: {state, by, at}}}
 *   tasks                     public.tasks, the follow-ups (id = id); the database sets who added and finished each
 *   notices                   public.notices (id = <household>~s208, or ~c<n>~child[-<body>] for child n): notices recorded
 *   monitor                   public.monitor_decisions (id = the item's id): an officer's decision on a monitoring item;
 *                             the items themselves are published with the page (data/monitor.json)
 *   reviews                   public.reviews (id = id): review requests and their decisions
 *   config/workflow           public.config
 *   data/users/<id>/draft_<h> public.private_drafts (id = household_id)
 * The database sets every author, actor and time and writes the audit log itself, so this file
 * never sends a time, an author or an audit entry; whatever the page puts in those fields is left out.
 *
 * Drafting goes to the draft-plan function (supabase/functions/draft-plan), which builds the
 * prompt from its own copy of the record and the reviewer notes in the database, drafts with the
 * owner's key, screens the reply with the private deny list and returns the plan only if it passed. A draft that fails comes back as a
 * list of the rules it broke, shown in this file's own notice; the page then says the draft did
 * not arrive.
 *
 * Synthetic records only. Suggestions for an officer to approve, never decisions.
 */
(function (root) {
'use strict';

const RANK = { viewer: 1, contributor: 2, editor: 3, owner: 4 };
const atLeast = (role, r) => (RANK[role] || 0) >= RANK[r];
const PAGE_EVENTS = new Set(['pack_exported', 'audit_exported', 'handover_exported']);
// Audit actions only the database writes, in words, since the page shows an action it has no label
// for as it is.
const DB_ACTIONS = {
  plan_pointer_set: 'set the version being drafted', file_updated: 'updated the household file',
  member_added: 'added a member', member_changed: 'changed a member', row_deleted: 'deleted a record from the dashboard',
};
// Short words for the screen's rules, after the page's RULE_TEXT (app/src/page.js), for the notice.
const RULE_TEXT = {
  style: 'plain characters and no em dashes', schema: 'the plan format', record: 'the synthetic record',
  pathway: 'a pathway not listed for this record', decision: 'a sentence stating a decision',
  person: 'a word that may name a person, place or provider', figure: 'a figure that is not in the record',
  reply: 'a reply that could not be read as a plan', not_ready: 'the screen rules',
  'fdcore:company name': 'the name of a firm', 'fdcore:email address': 'an email address', 'fdcore:UK postcode': 'a postcode',
  'fdcore:phone number': 'a phone number', 'fdcore:deny-list name': 'a name on the deny list', 'fdcore:accusing language': 'judging or accusing wording',
};
const PAGE_SIZE = 1000;

const clone = (o) => (o === undefined ? undefined : JSON.parse(JSON.stringify(o)));
const fail = (code, message) => { const e = new Error(message || code); e.code = code; return e; };
const autoId = () => 'h' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

// Times as the page writes them (Date.toISOString: milliseconds, Z), so its string comparisons
// and its date parsing work unchanged. Microseconds are cut, never rounded, so order is kept.
function toIso(v) {
  if (v === null || v === undefined || v === '') return v === undefined ? null : v;
  const s = String(v);
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]00(?::?00)?)$/.exec(s);
  if (m) return `${m[1]}T${m[2]}.${(m[3] || '').padEnd(3, '0').slice(0, 3)}Z`;
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toISOString();
}

// PostgREST and supabase-js errors as the codes the page knows (app/src/page.js, writeFailed and
// withRetry): invalid_argument for "not allowed", unavailable for "try again".
function storeError(error, status) {
  const code = (error && error.code) || '';
  const message = (error && error.message) || '';
  if (code === '42501' || status === 403) return fail('invalid_argument', 'not allowed: ' + message);
  if (status === 401 || /^PGRST30/.test(code)) return fail('unavailable', 'the session needs renewing');
  if (!status || status >= 500 || /fetch|network|timed? ?out/i.test(message)) return fail('unavailable', message || 'the store did not answer');
  return fail('failed_precondition', message || 'refused');
}
async function run(builder) {
  let res;
  try { res = await builder; } catch (e) { throw storeError(e, 0); }
  if (res.error) throw storeError(res.error, res.status);
  return res;
}
// Insert a row; if its key is taken (23505), update only the columns the table lets a member
// update. A PostgREST upsert would set every column sent, the key included, and a table whose
// grants cover only its value columns refuses that.
async function insertOrUpdate(c, table, key, id, row, change) {
  let res;
  try { res = await c.from(table).insert(row); } catch (e) { throw storeError(e, 0); }
  if (!res.error) return res;
  if (res.error.code !== '23505') throw storeError(res.error, res.status);
  const upd = await run(c.from(table).update(pick(row, change)).eq(key, id).select(key));
  if (!upd.data || !upd.data.length) throw fail('invalid_argument', 'no such row, or no access to it');
  return upd;
}

/* ------------------------------------------------------------ paths and tables */
const pick = (obj, keys) => { const out = {}; for (const k of keys) if (obj && obj[k] !== undefined) out[k] = obj[k]; return out; };
const KINDS = {
  members: {
    table: 'members', key: 'user_id', columns: 'user_id, role, display_name, active, invited_at',
    fields: { role: 'role', display_name: 'display_name', active: 'active', joined_at: 'invited_at' },
    toData: (r) => ({ role: r.role, display_name: r.display_name || '', active: r.active !== false, joined_at: toIso(r.invited_at) }),
  },
  versions: {
    table: 'versions', key: 'id', owner: 'author',
    columns: 'id, author, household_id, version, source, from_source, plan, screen, sha256, prompt_sha256, review, created_at',
    fields: { household_id: 'household_id', version: 'version', source: 'source', from: 'from_source', sha256: 'sha256', prompt_sha256: 'prompt_sha256', created_at: 'created_at' },
    toData: (r) => ({ household_id: r.household_id, version: r.version, source: r.source, from: r.from_source || null, plan: r.plan,
      screen: r.screen ? Object.assign({}, r.screen, { checked_at: toIso(r.screen.checked_at) }) : r.screen,
      sha256: r.sha256, prompt_sha256: r.prompt_sha256 || null, review: Array.isArray(r.review) ? r.review : [], created_at: toIso(r.created_at) }),
  },
  decisions: {
    table: 'decisions', key: 'id', owner: 'author',
    columns: 'id, author, household_id, decision, version_id, plan_sha256, four_eyes, note, reason, decided_at',
    fields: { household_id: 'household_id', decision: 'decision', version_id: 'version_id', plan_sha256: 'plan_sha256', four_eyes: 'four_eyes', decided_at: 'decided_at' },
    toData: (r) => {
      const d = { household_id: r.household_id, decision: r.decision, version_id: r.version_id, plan_sha256: r.plan_sha256, four_eyes: r.four_eyes, decided_at: toIso(r.decided_at) };
      if (r.note) d.note = r.note;
      if (r.reason) d.reason = r.reason;
      return d;
    },
  },
  audit: {
    table: 'audit', key: 'id', owner: 'actor', columns: 'id, actor, at, household_id, action, detail, spec_version',
    fields: { at: 'at', household_id: 'household_id', action: 'action' },
    toData: (r) => ({ at: toIso(r.at), household_id: r.household_id || null, action: DB_ACTIONS[r.action] || r.action, detail: r.detail || '', spec_version: r.spec_version || null }),
  },
  files: {
    table: 'files', key: 'household_id', columns: 'household_id, status, version_id, updated_at, updated_by, assignee, assigned_at',
    fields: { household_id: 'household_id', status: 'status', version_id: 'version_id', updated_at: 'updated_at', assignee: 'assignee' },
    write: ['household_id', 'status', 'version_id', 'assignee'],
    toData: (r) => ({ household_id: r.household_id, status: r.status, version_id: r.version_id, updated_at: toIso(r.updated_at), updated_by: r.updated_by,
      assignee: r.assignee, assigned_at: toIso(r.assigned_at) }),
  },
  moves: {
    table: 'moves', key: 'household_id', columns: 'household_id, stage, pathway_id, note, plan_version, updated_by, updated_at',
    fields: { household_id: 'household_id', stage: 'stage', updated_at: 'updated_at' },
    write: ['household_id', 'stage', 'pathway_id', 'note', 'plan_version'],
    toData: (r) => ({ household_id: r.household_id, stage: r.stage, pathway_id: r.pathway_id, note: r.note || '', plan_version: r.plan_version, updated_by: r.updated_by, updated_at: toIso(r.updated_at) }),
  },
  checks: {
    table: 'checks', key: 'household_id', columns: 'household_id, check_id, state, updated_by, updated_at', grouped: true,
    fields: { household_id: 'household_id' }, order: ['household_id', 'check_id'],
  },
  tasks: {
    table: 'tasks', key: 'id', columns: 'id, household_id, text, kind, due, assignee, done, done_by, done_at, created_by, created_at',
    fields: { household_id: 'household_id', due: 'due', done: 'done', created_at: 'created_at' },
    insert: ['household_id', 'text', 'kind', 'due', 'assignee', 'done'], change: ['text', 'due', 'assignee', 'done'],
    toData: (r) => ({ household_id: r.household_id, text: r.text, kind: r.kind, due: r.due || null, assignee: r.assignee || null, done: r.done === true,
      done_by: r.done_by || null, done_at: toIso(r.done_at), created_by: r.created_by || null, created_at: toIso(r.created_at) }),
  },
  notices: {
    table: 'notices', key: 'id', columns: 'id, household_id, kind, child_no, status, sent_on, method, asked_on, agreed_on, info_on, refused_on, agreed_bodies, declined_bodies, recorded_by, recorded_at',
    fields: { household_id: 'household_id', kind: 'kind', status: 'status' },
    // The migration grants update on the value columns only (change), never on id, household_id or kind.
    insert: ['household_id', 'kind', 'child_no', 'status', 'sent_on', 'method', 'asked_on', 'agreed_on', 'info_on', 'refused_on', 'agreed_bodies', 'declined_bodies'],
    change: ['status', 'sent_on', 'method', 'asked_on', 'agreed_on', 'info_on', 'refused_on', 'agreed_bodies', 'declined_bodies'],
    toData: (r) => ({ household_id: r.household_id, kind: r.kind, child_no: r.child_no || null, status: r.status, sent_on: r.sent_on || null, method: r.method || null, asked_on: r.asked_on || null,
      agreed_on: r.agreed_on || null, info_on: r.info_on || null, refused_on: r.refused_on || null,
      agreed_bodies: Array.isArray(r.agreed_bodies) ? r.agreed_bodies : [], declined_bodies: Array.isArray(r.declined_bodies) ? r.declined_bodies : [],
      recorded_by: r.recorded_by || null, recorded_at: toIso(r.recorded_at) }),
  },
  monitor: {
    table: 'monitor_decisions', key: 'id', columns: 'id, decision, grade, reason, note, decided_by, decided_at',
    fields: { decision: 'decision' },
    insert: ['decision', 'grade', 'reason', 'note'], change: ['decision', 'grade', 'reason', 'note'],
    toData: (r) => ({ item_id: r.id, decision: r.decision, grade: r.grade || null, reason: r.reason || null, note: r.note || '', by: r.decided_by || null, at: toIso(r.decided_at) }),
  },
  reviews: {
    table: 'reviews', key: 'id', columns: 'id, household_id, requested_on, assignee, agreed_to, decided_on, decided_by, created_by, created_at',
    fields: { household_id: 'household_id', requested_on: 'requested_on' },
    insert: ['household_id', 'requested_on', 'assignee', 'agreed_to', 'decided_on'], change: ['assignee', 'agreed_to', 'decided_on'],
    toData: (r) => ({ household_id: r.household_id, requested_on: r.requested_on, assignee: r.assignee || null, agreed_to: r.agreed_to || null, decided_on: r.decided_on || null,
      decided_by: r.decided_by || null, created_by: r.created_by || null, created_at: toIso(r.created_at) }),
  },
  config: {
    table: 'config', key: 'key', columns: 'key, four_eyes, updated_at, updated_by',
    fields: { four_eyes: 'four_eyes', updated_at: 'updated_at' },
    toData: (r) => ({ four_eyes: r.four_eyes !== false, updated_at: toIso(r.updated_at), updated_by: r.updated_by }),
  },
  private: {
    table: 'private_drafts', key: 'household_id', owner: 'user_id', columns: 'user_id, household_id, working, at',
    fields: { household_id: 'household_id', at: 'at' },
    docId: (r) => 'draft_' + r.household_id, keyOf: (id) => (/^draft_(SYN-\d{4})$/.exec(id) || [])[1] || null,
    toData: (r) => ({ household_id: r.household_id, working: r.working, at: toIso(r.at) }),
  },
};
const OWN = { versions: 'v', decisions: 'd', audit: 'e' };

function parsePath(path) {
  const p = String(path).split('/');
  if (p.length === 1 && ['members', 'files', 'moves', 'checks', 'tasks', 'notices', 'reviews', 'monitor', 'config'].includes(p[0])) return { kind: p[0], owner: null };
  if (p.length === 3 && OWN[p[0]] && p[2] === OWN[p[0]] && p[1]) return { kind: p[0], owner: p[1] };
  if (p.length === 3 && p[0] === 'data' && p[1] === 'users' && p[2]) return { kind: 'private', owner: p[2] };
  throw fail('invalid_argument', 'no table for the path ' + path);
}
const docIdOf = (spec, row) => (spec.docId ? spec.docId(row) : String(row[spec.key]));
const keyOf = (spec, id) => (spec.keyOf ? spec.keyOf(id) : id);

function groupChecks(rows) {
  const by = new Map();
  for (const r of rows) {
    if (!by.has(r.household_id)) by.set(r.household_id, { household_id: r.household_id, items: {} });
    by.get(r.household_id).items[r.check_id] = { state: r.state, by: r.updated_by, at: toIso(r.updated_at) };
  }
  return [...by.entries()].map(([id, data]) => ({ id, data }));
}

/* ------------------------------------------------------------ reads */
// Rows for a collection or a document, paged past PostgREST's 1,000-row default.
async function readRows(ctx, at, q) {
  const spec = KINDS[at.kind];
  const filters = [];
  if (spec.owner) filters.push([spec.owner, at.owner]);
  if (q.docId !== undefined) {
    if (at.kind === 'checks') filters.push(['household_id', q.docId]);
    else { const k = keyOf(spec, q.docId); if (k === null) return []; filters.push([spec.key, k]); }
  }
  for (const [field, value] of q.where || []) {
    const col = spec.fields[field];
    if (!col) throw fail('invalid_argument', `cannot filter ${at.kind} on ${field}`);
    filters.push([col, value]);
  }
  const order = [];
  if (q.orderBy) {
    const col = spec.fields[q.orderBy];
    if (!col) throw fail('invalid_argument', `cannot order ${at.kind} by ${q.orderBy}`);
    order.push([col, q.dir !== 'desc']);
  }
  for (const col of spec.order || [spec.key]) order.push([col, q.dir !== 'desc' || !q.orderBy]);
  const want = q.limit || Infinity;
  const out = [];
  for (let from = 0; out.length < want; from += PAGE_SIZE) {
    let b = ctx.client.from(spec.table).select(spec.columns);
    for (const [col, value] of filters) b = b.eq(col, value);
    for (const [col, asc] of order) b = b.order(col, { ascending: asc });
    const n = Math.min(PAGE_SIZE, want - out.length);
    b = b.range(from, from + n - 1);
    const res = await run(b);
    const rows = res.data || [];
    out.push(...rows);
    if (rows.length < n) break;
  }
  return out;
}
async function readDocs(ctx, at, q) {
  const rows = await readRows(ctx, at, q);
  const spec = KINDS[at.kind];
  if (spec.grouped) return groupChecks(rows);
  return rows.map((r) => ({ id: docIdOf(spec, r), data: spec.toData(r) }));
}
const docSnap = (id, data) => ({ id, exists: data !== null && data !== undefined, data: () => clone(data) });
const collSnap = (docs) => ({ docs: docs.map((d) => docSnap(d.id, d.data)), size: docs.length, empty: !docs.length });

/* ------------------------------------------------------------ writes */
async function writeDoc(ctx, at, id, data, mode) {
  const spec = KINDS[at.kind];
  if (spec.owner && at.owner !== ctx.uid) throw fail('invalid_argument', 'a person writes only their own records');
  const touched = [spec.table, 'audit'];
  const c = ctx.client;
  switch (at.kind) {
    case 'members':
      // Membership is the owner's (public.members); the page only registers itself on its first change.
      if (id === ctx.uid && ctx.member) return;
      throw fail('invalid_argument', 'members are managed by the owner');
    case 'versions':
      if (mode !== 'set') throw fail('invalid_argument', 'versions are insert-only');
      await run(c.from('versions').insert({ id, household_id: data.household_id, source: data.source, from_source: data.from || null, plan: data.plan,
        screen: data.screen, sha256: data.sha256, prompt_sha256: data.prompt_sha256 || null, review: Array.isArray(data.review) ? data.review : [] }));
      break;
    case 'decisions': {
      if (mode !== 'set') throw fail('invalid_argument', 'decisions are insert-only');
      const row = { id, household_id: data.household_id, decision: data.decision, version_id: data.version_id || null, plan_sha256: data.plan_sha256 || null };
      if (data.note !== undefined && data.note !== null) row.note = String(data.note);
      if (data.reason) row.reason = data.reason;
      await run(c.from('decisions').insert(row));
      break;
    }
    case 'audit':
      // The database writes the audit log from its own triggers. Only what changes no table, an
      // export, is recorded, as a page event whose who and when the database sets.
      if (!PAGE_EVENTS.has(data && data.action)) return;
      await run(c.from('events').insert({ household_id: data.household_id || null, action: data.action,
        detail: String(data.detail || '').slice(0, 200), spec_version: data.spec_version ? String(data.spec_version) : null }));
      touched.push('events');
      break;
    case 'files':
    case 'moves': {
      const row = Object.assign(pick(data, spec.write), { household_id: id });
      if (mode === 'set') await run(c.from(spec.table).upsert(row, { onConflict: 'household_id' }));
      else {
        const res = await run(c.from(spec.table).update(row).eq('household_id', id).select('household_id'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no such document, or no access to it');
      }
      break;
    }
    case 'tasks': {
      if (mode === 'set') await run(c.from('tasks').insert(Object.assign(pick(data, spec.insert), { id })));
      else {
        const row = pick(data, spec.change);
        if (!Object.keys(row).length) return;
        const res = await run(c.from('tasks').update(row).eq('id', id).select('id'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no such follow-up, or no access to it');
      }
      break;
    }
    case 'notices': {
      // One row per notice; a set replaces what the officer recorded, the database sets who and when.
      const row = Object.assign(pick(data, spec.insert), { id });
      for (const k of ['sent_on', 'method', 'asked_on', 'agreed_on', 'info_on', 'refused_on']) if (!(k in row)) row[k] = null;
      for (const k of ['agreed_bodies', 'declined_bodies']) if (!Array.isArray(row[k])) row[k] = [];
      if (mode === 'set') await insertOrUpdate(c, 'notices', 'id', id, row, spec.change);
      else {
        const res = await run(c.from('notices').update(pick(data, spec.change)).eq('id', id).select('id'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no such notice, or no access to it');
      }
      break;
    }
    case 'monitor': {
      if (!/^mon-[0-9a-f]{12}$/.test(String(id))) throw fail('invalid_argument', 'a monitoring decision is keyed by its item id');
      if (mode === 'set') await run(c.from('monitor_decisions').insert(Object.assign(pick(data, spec.insert), { id })));
      else {
        const row = pick(data, spec.change);
        if (!Object.keys(row).length) return;
        const res = await run(c.from('monitor_decisions').update(row).eq('id', id).select('id'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no such decision, or no access to it');
      }
      break;
    }
    case 'reviews': {
      if (mode === 'set') await run(c.from('reviews').insert(Object.assign(pick(data, spec.insert), { id })));
      else {
        const row = pick(data, spec.change);
        if (!Object.keys(row).length) return;
        const res = await run(c.from('reviews').update(row).eq('id', id).select('id'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no such review, or no access to it');
      }
      break;
    }
    case 'checks': {
      const items = Object.entries((data && data.items) || {});
      for (const [checkId, item] of items) {
        await run(c.from('checks').upsert({ household_id: id, check_id: checkId, state: item && item.state }, { onConflict: 'household_id,check_id' }));
      }
      break;
    }
    case 'config': {
      if (id !== 'workflow') throw fail('invalid_argument', 'the only setting is workflow');
      const row = { key: 'workflow', four_eyes: data.four_eyes !== false };
      if (mode === 'set') await run(c.from('config').upsert(row, { onConflict: 'key' }));
      else {
        const res = await run(c.from('config').update({ four_eyes: row.four_eyes }).eq('key', 'workflow').select('key'));
        if (!res.data || !res.data.length) throw fail('invalid_argument', 'no access to the setting');
      }
      break;
    }
    case 'private': {
      const hid = keyOf(spec, id);
      if (!hid) throw fail('invalid_argument', 'a private draft is draft_<household>');
      await run(c.from('private_drafts').upsert({ household_id: hid, working: data && data.working !== undefined ? data.working : null }, { onConflict: 'user_id,household_id' }));
      touched.length = 0;
      touched.push('private_drafts');
      break;
    }
    default:
      throw fail('invalid_argument', 'no table for ' + at.kind);
  }
  ctx.live.touch(touched);
}

/* ------------------------------------------------------------ live updates */
// One realtime channel for every table the page watches. A change refreshes only the watches it
// can affect; while the channel is down, every watch is polled instead.
const LIVE_TABLES = ['members', 'versions', 'decisions', 'audit', 'files', 'checks', 'moves', 'tasks', 'notices', 'reviews', 'monitor_decisions', 'config'];
function makeLive(ctx, opts) {
  const watches = new Set();
  const pollMs = opts.pollMs || 20000, debounceMs = opts.debounceMs === undefined ? 120 : opts.debounceMs;
  let channel = null, polling = null, up = false;
  const setTimer = opts.setTimeout || setTimeout, clearTimer = opts.clearTimeout || clearTimeout;
  const startPolling = () => { if (!polling && !opts.noPolling) polling = setInterval(() => watches.forEach((w) => w.schedule()), pollMs); };
  const stopPolling = () => { if (polling) { clearInterval(polling); polling = null; } };
  function ensureChannel() {
    if (channel || typeof ctx.client.channel !== 'function') { if (!channel) startPolling(); return; }
    channel = ctx.client.channel('ta-planner-live');
    for (const t of LIVE_TABLES) channel.on('postgres_changes', { event: '*', schema: 'public', table: t }, (payload) => changed(t, payload));
    channel.subscribe((status) => {
      if (status === 'SUBSCRIBED') { const was = up; up = true; stopPolling(); if (was === false) watches.forEach((w) => w.schedule()); }
      else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') { up = false; startPolling(); }
    });
  }
  function changed(table, payload) {
    for (const w of watches) if (w.table === table && w.affects(payload)) w.schedule();
  }
  function add(at, q, emit, onErr) {
    const spec = KINDS[at.kind];
    let last = null, timer = null, closed = false, busy = false, again = false, failed = false;
    const w = {
      table: spec.table,
      affects(payload) {
        if (!spec.owner) return true;
        const row = (payload && (payload.new && Object.keys(payload.new).length ? payload.new : payload.old)) || {};
        return row[spec.owner] === undefined || row[spec.owner] === at.owner;
      },
      schedule() {
        if (closed || timer) return;
        timer = setTimer(() => { timer = null; w.refresh(); }, debounceMs);
      },
      async refresh() {
        if (closed) return;
        if (busy) { again = true; return; }
        busy = true;
        try {
          const docs = await readDocs(ctx, at, q);
          const text = JSON.stringify(docs);
          if (!closed && text !== last) { last = text; emit(docs); }
          failed = false;
        } catch (e) {
          if (!failed && e && e.code === 'invalid_argument' && onErr) onErr(Object.assign(e, { code: 'revoked' }));
          failed = true;
        } finally {
          busy = false;
          if (again) { again = false; w.schedule(); }
        }
      },
    };
    watches.add(w);
    ensureChannel();
    w.refresh();
    return () => { closed = true; watches.delete(w); if (timer) clearTimer(timer); };
  }
  return {
    add,
    touch(tables) { for (const w of watches) if (tables.includes(w.table)) w.schedule(); },
    size: () => watches.size,
  };
}

/* ------------------------------------------------------------ the db capability */
function makeDb(ctx) {
  class Query {
    constructor(path, q) { this.path = path; this.at = parsePath(path); this.q = q || {}; }
    where(field, op, value) {
      if (op !== '==') throw fail('invalid_argument', 'only == filters are mapped');
      return new Query(this.path, Object.assign({}, this.q, { where: [...(this.q.where || []), [field, value]] }));
    }
    orderBy(field, dir) { return new Query(this.path, Object.assign({}, this.q, { orderBy: field, dir: dir === 'desc' ? 'desc' : 'asc' })); }
    limit(n) { return new Query(this.path, Object.assign({}, this.q, { limit: n })); }
    async get() { return collSnap(await readDocs(ctx, this.at, this.q)); }
    onSnapshot(cb, onErr) { return ctx.live.add(this.at, this.q, (docs) => cb(collSnap(docs)), onErr); }
  }
  class Coll extends Query {
    doc(id) { return new Doc(this.path, id === undefined ? autoId() : String(id)); }
  }
  class Doc {
    constructor(path, id) { this.path = path; this.at = parsePath(path); this.id = id; }
    async get() { const docs = await readDocs(ctx, this.at, { docId: this.id }); return docSnap(this.id, docs.length ? docs[0].data : null); }
    set(data) { return writeDoc(ctx, this.at, this.id, clone(data), 'set'); }
    update(data) { return writeDoc(ctx, this.at, this.id, clone(data), 'update'); }
    onSnapshot(cb, onErr) { return ctx.live.add(this.at, { docId: this.id }, (docs) => cb(docSnap(this.id, docs.length ? docs[0].data : null)), onErr); }
  }
  return { collection: (path) => new Coll(path) };
}

/* ------------------------------------------------------------ user, sample, downloads */
function makeUser(ctx) {
  return {
    async me() {
      return { id: ctx.uid, name: ctx.member.display_name || '', avatarUrl: '', isOwner: ctx.role === 'owner', canEdit: atLeast(ctx.role, 'editor') };
    },
    async can(what) { return what === 'data.write' ? atLeast(ctx.role, 'contributor') : false; },
    async profiles(ids) {
      const want = [...new Set((ids || []).filter((x) => typeof x === 'string' && /^[0-9a-f-]{36}$/i.test(x)))];
      if (!want.length) return {};
      const res = await run(ctx.client.from('members').select('user_id, display_name').in('user_id', want));
      const out = {};
      for (const r of res.data || []) out[r.user_id] = { name: r.display_name || '', avatarUrl: '' };
      return out;
    },
  };
}

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
async function sha256Hex(text, cryptoImpl) {
  const subtle = (cryptoImpl || root.crypto).subtle;
  return hex(await subtle.digest('SHA-256', new TextEncoder().encode(text)));
}
const ERROR_CODES = {
  not_signed_in: 'session_expired', not_allowed: 'not_granted', not_configured: 'capability_disabled',
  too_many_drafts: 'rate_limited', busy: 'rate_limited', deny_list_unavailable: 'capability_disabled', note_blocked: 'note_blocked',
};
function describeProblems(problems) {
  const words = [...new Set((problems || []).map((p) => RULE_TEXT[p.rule] || p.rule))];
  return words.length ? words.join('; ') : 'the screen';
}

// sample(promptText) as the page calls it. The function builds the prompt itself from its copy of
// the record and the reviewer notes in the database; the page's prompt only names the record and,
// by its SHA-256, proves that both built the same prompt. The record's id is the one in the
// household record's JSON ("id": "SYN-0001"), since a reviewer note may mention another.
const RECORD_ID = /"id": "(SYN-\d{4})"/;
function makeSample(ctx) {
  return async function sample(text, opts) {
    const found = RECORD_ID.exec(String(text || ''));
    if (!found) throw fail('prompt_too_large', 'the prompt does not name a synthetic record');
    const ids = [found[1]];
    const promptSha = await sha256Hex(String(text), ctx.crypto);
    const s = await ctx.client.auth.getSession();
    const token = s && s.data && s.data.session && s.data.session.access_token;
    if (!token) throw fail('session_expired', 'not signed in');
    let res;
    try {
      res = await ctx.fetch(ctx.config.url.replace(/\/+$/, '') + '/functions/v1/draft-plan', {
        method: 'POST',
        headers: { authorization: 'Bearer ' + token, apikey: ctx.config.anonKey, 'content-type': 'application/json' },
        body: JSON.stringify({ household_id: ids[0], prompt_sha256: promptSha }),
        signal: opts && opts.signal,
      });
    } catch (e) {
      if (e && (e.name === 'AbortError' || (opts && opts.signal && opts.signal.aborted))) throw fail('cancelled', 'stopped');
      throw fail('unavailable', 'the drafting function did not answer');
    }
    let body = null;
    try { body = await res.json(); } catch { body = null; }
    if (!res.ok) {
      const err = (body && body.error) || '';
      if (err === 'build_mismatch') ctx.notice('The drafting function built a different prompt from this page, so it did not draft. If the plan was returned or rejected a moment ago, reload the page and draft again; if not, the function and the page come from different builds: ask the owner to deploy both from the same build.');
      if (err === 'note_blocked') ctx.notice('A reviewer’s note on this plan could not be sent to Claude, so it did not draft. Start from the template, which shows the note to answer.');
      if (err === 'deny_list_unavailable') ctx.notice('The drafting function could not read the deny list, so it did not draft. Tell the owner.');
      throw fail(ERROR_CODES[err] || (res.status === 401 ? 'session_expired' : res.status === 403 ? 'not_granted' : res.status === 429 ? 'rate_limited' : 'unavailable'), err || 'HTTP ' + res.status);
    }
    if (!body || body.passed !== true || !body.plan || typeof body.plan !== 'object') {
      ctx.notice(`The draft was stopped by the screen and is not shown. It had ${describeProblems(body && body.problems)}. Draft again, or start from the template.`);
      throw fail('draft_failed_screen', 'the draft did not pass the screen');
    }
    return { text: JSON.stringify(body.plan), truncated: false };
  };
}

function makeDownloads(save) {
  return { async save(file) { if (!file || typeof file.filename !== 'string') throw fail('invalid_argument', 'no file'); await save(file.filename, String(file.data === undefined ? '' : file.data)); } };
}

/* ------------------------------------------------------------ the stand-in */
function createHosted(opts) {
  const ctx = {
    client: opts.client, config: opts.config, fetch: opts.fetch || ((...a) => root.fetch(...a)), crypto: opts.crypto,
    notice: opts.notice || (() => {}), uid: null, email: '', role: null, member: null, live: null,
  };
  let resolveReady, pending = null;
  const ready = new Promise((r) => { resolveReady = r; });
  async function establish(session) {
    if (!session || !session.user) return { state: 'signed-out' };
    if (ctx.uid) return { state: ctx.uid === session.user.id ? 'signed-in' : 'switched', role: ctx.role, name: ctx.member && ctx.member.display_name, email: ctx.email };
    if (pending && pending.id === session.user.id) return pending.result;
    pending = { id: session.user.id, result: lookUp(session) };
    try { return await pending.result; } finally { pending = null; }
  }
  async function lookUp(session) {
    let res;
    try { res = await run(ctx.client.from('members').select('user_id, role, display_name, active').eq('user_id', session.user.id).maybeSingle()); }
    catch (e) { return { state: 'error', error: e }; }
    const m = res.data;
    if (!m || m.active === false || !RANK[m.role]) return { state: 'no-access', email: session.user.email || '' };
    ctx.uid = session.user.id; ctx.email = session.user.email || ''; ctx.member = m; ctx.role = m.role;
    ctx.live = makeLive(ctx, opts);
    resolveReady({
      db: makeDb(ctx), user: makeUser(ctx), sample: atLeast(ctx.role, 'contributor') ? makeSample(ctx) : null,
      downloads: opts.save ? makeDownloads(opts.save) : null,
    });
    return { state: 'signed-in', role: ctx.role, name: m.display_name || '', email: ctx.email };
  }
  const claude = {
    hosted: true,
    async use(name) {
      if (!['db', 'user', 'sample', 'downloads'].includes(name)) throw fail('not_declared', 'no capability ' + name);
      return (await ready)[name];
    },
  };
  return { claude, ctx, establish, ready };
}

/* ------------------------------------------------------------ the sign-in bar (browser only) */
function browserSave(doc, win) {
  return async (filename, text) => {
    const type = /\.json$/i.test(filename) ? 'application/json' : /\.csv$/i.test(filename) ? 'text/csv' : 'text/markdown';
    const url = win.URL.createObjectURL(new win.Blob([text], { type: type + ';charset=utf-8' }));
    const a = doc.createElement('a');
    a.href = url; a.download = filename; a.rel = 'noopener';
    doc.body.append(a); a.click(); a.remove();
    win.setTimeout(() => win.URL.revokeObjectURL(url), 30000);
  };
}

function shellBar(doc) {
  const el = (tag, props, ...kids) => {
    const n = doc.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else if (k === 'hidden') n.hidden = !!v; else n.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids) if (kid) n.append(kid);
    return n;
  };
  const status = el('span', { class: 'hs-status', 'aria-live': 'polite' });
  const email = el('input', { type: 'email', autocomplete: 'email', required: true, 'aria-label': 'Work email', placeholder: 'Work email' });
  const sendBtn = el('button', { class: 'btn primary small', type: 'submit', text: 'Email me a code' });
  const emailForm = el('form', { class: 'hs-form', hidden: true }, email, sendBtn);
  const code = el('input', { type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', required: true, pattern: '[0-9]{6,10}', 'aria-label': 'Code from the email', placeholder: 'Code from the email' });
  const verifyBtn = el('button', { class: 'btn primary small', type: 'submit', text: 'Sign in' });
  const backBtn = el('button', { class: 'btn quiet small', type: 'button', text: 'Use another email' });
  const codeForm = el('form', { class: 'hs-form', hidden: true }, code, verifyBtn, backBtn);
  const outBtn = el('button', { class: 'btn small', type: 'button', text: 'Sign out', hidden: true });
  const noticeText = el('span');
  const closeBtn = el('button', { class: 'btn quiet small', type: 'button', text: 'Close' });
  const notice = el('div', { class: 'wrap hs-notice', role: 'alert', hidden: true }, el('div', { class: 'banner warn hs-notice-in' }, noticeText, closeBtn));
  const bar = el('div', { class: 'hs-bar', role: 'region', 'aria-label': 'Sign-in' },
    el('div', { class: 'wrap hs-row' }, status, emailForm, codeForm, el('span', { class: 'spacer' }), outBtn), notice);
  doc.body.prepend(bar);
  closeBtn.addEventListener('click', () => { notice.hidden = true; });
  const api = {
    onSend: null, onVerify: null, onSignOut: null,
    show(state, info) {
      info = info || {};
      emailForm.hidden = state !== 'signed-out';
      codeForm.hidden = state !== 'code';
      outBtn.hidden = !['signed-in', 'no-access', 'error'].includes(state);
      status.textContent = {
        config: 'This hosted build has no project settings. Build it again with the project URL and publishable key (hosted/README.md).',
        nolib: 'The Supabase client did not load, so the planner cannot sign in. Check the browser console and hosted/README.md.',
        'signed-out': 'Sign in with your work email to use the planner.',
        code: `A code was sent to ${info.email || 'your email'}. Enter it to sign in.`,
        checking: 'Signing in…',
        'no-access': `Signed in as ${info.email || 'this account'}, which has not been given access to this planner. Ask the owner.`,
        'signed-in': `Signed in${info.name ? ' as ' + info.name : ''}${info.role ? ', ' + info.role : ''}.`,
        error: 'Could not reach the planner’s store. Reload the page in a moment.',
      }[state] || '';
    },
    notice(text) { noticeText.textContent = text; notice.hidden = false; },
  };
  emailForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    sendBtn.disabled = true;
    try { await api.onSend(email.value.trim()); api.show('code', { email: email.value.trim() }); code.value = ''; code.focus(); }
    catch { status.textContent = 'The code could not be sent. Check the address, or wait a minute and try again.'; }
    finally { sendBtn.disabled = false; }
  });
  codeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    verifyBtn.disabled = true;
    try { await api.onVerify(email.value.trim(), code.value.trim()); api.show('checking'); }
    catch { status.textContent = 'That code did not work. Check it, or ask for a new one.'; }
    finally { verifyBtn.disabled = false; }
  });
  backBtn.addEventListener('click', () => { api.show('signed-out'); email.focus(); });
  outBtn.addEventListener('click', () => { if (api.onSignOut) api.onSignOut(); });
  return api;
}

function configured(cfg) {
  return !!cfg && typeof cfg.url === 'string' && /^https:\/\/[^/\s]+$/.test(cfg.url.replace(/\/+$/, '')) && !/YOUR-PROJECT/.test(cfg.url)
    && typeof cfg.anonKey === 'string' && cfg.anonKey.length > 20 && !/YOUR-/.test(cfg.anonKey);
}

function boot(win) {
  const doc = win.document, cfg = win.TA_HOSTED_CONFIG;
  const bar = shellBar(doc);
  const never = { hosted: true, use: () => new Promise(() => {}) };   // the page waits, read-only
  if (!configured(cfg)) { bar.show('config'); win.claude = never; return; }
  if (!win.supabase || typeof win.supabase.createClient !== 'function') { bar.show('nolib'); win.claude = never; return; }
  const client = win.supabase.createClient(cfg.url, cfg.anonKey, { auth: { flowType: 'pkce', persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
  const hosted = createHosted({ client, config: cfg, notice: bar.notice, save: browserSave(doc, win) });
  win.claude = hosted.claude;
  const settle = async (session) => {
    const r = await hosted.establish(session);
    if (r.state === 'switched') { win.location.reload(); return; }
    bar.show(r.state, r);
  };
  bar.onSend = async (email) => {
    const { error } = await client.auth.signInWithOtp({ email, options: { shouldCreateUser: false, emailRedirectTo: win.location.origin + win.location.pathname } });
    if (error) throw error;
  };
  bar.onVerify = async (email, token) => {
    const { error } = await client.auth.verifyOtp({ email, token, type: 'email' });
    if (error) throw error;
  };
  bar.onSignOut = async () => { try { await client.auth.signOut(); } finally { win.location.reload(); } };
  // supabase-js asks for its callbacks to return quickly and not call the client themselves.
  client.auth.onAuthStateChange((event, session) => {
    win.setTimeout(() => {
      if (event === 'SIGNED_OUT') { if (hosted.ctx.uid) win.location.reload(); else bar.show('signed-out'); }
      else if (event === 'SIGNED_IN' && session) settle(session);
    }, 0);
  });
  bar.show('checking');
  client.auth.getSession().then(({ data }) => (data && data.session ? settle(data.session) : bar.show('signed-out')), () => bar.show('error'));
}

root.TaHosted = { createHosted, parsePath, toIso, storeError, KINDS, groupChecks, configured };
if (root.TA_HOSTED_CONFIG && root.document) boot(root);
})(typeof window !== 'undefined' ? window : globalThis);
