// A stand-in for the claude.ai viewer's capabilities, for local runs only. Configured by
// window.__MOCK (set before this script by the test runner) or by query string.
(function () {
  const qs = new URLSearchParams(location.search);
  const M = Object.assign({ db: true, role: 'owner', uid: 'u_owner', name: 'Owner A', sample: 'ok', downloads: true, delay: 30 }, window.__MOCK || {});
  for (const [k, v] of qs) M[k] = v === 'true' ? true : v === 'false' ? false : v;
  if (M.claude === false) return;
  window.__downloads = [];
  window.__samples = [];
  const LEVEL = { view: 0, interact: 1, admin: 2, owner: 3 };
  const level = M.role === 'owner' ? 3 : M.role === 'editor' ? 2 : M.role === 'contributor' ? 1 : 0;
  const KEY = 'mockdb';
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { return {}; } };
  const save = (o) => localStorage.setItem(KEY, JSON.stringify(o));
  const err = (code, message) => ({ code, message });
  const listeners = new Set();
  const segs = (p) => p.split('/');
  // The planner's declared rules: author-bound records under <kind>/<own id>/..., decisions at
  // editor level, config at editor level, data/users private, everything else Contributor.
  // The owner meets every level; only {self} privacy limits the owner.
  function canWritePath(path) {
    const s = segs(path);
    if (s[0] === 'data' && s[1] === 'users') return s[2] === M.uid && level >= LEVEL.interact;
    if (level === LEVEL.owner) return true;
    const own = { members: LEVEL.interact, versions: LEVEL.interact, decisions: LEVEL.admin, audit: LEVEL.interact };
    if (s[0] in own) return s[1] === M.uid && level >= own[s[0]];
    if (s[0] === 'config') return level >= LEVEL.admin;
    return level >= LEVEL.interact;
  }
  function snapDoc(path, data) {
    const id = segs(path).pop();
    return { id, exists: data !== undefined, data: () => (data === undefined ? undefined : JSON.parse(JSON.stringify(data))), metadata: { fromCache: false, hasPendingWrites: false } };
  }
  function runQuery(q) {
    const all = load();
    let docs = Object.keys(all).filter((p) => p.startsWith(q.path + '/') && segs(p).length === segs(q.path).length + 1).map((p) => ({ p, d: all[p] }));
    for (const [f, op, v] of q.wh) docs = docs.filter((x) => { const a = x.d[f]; return op === '==' ? a === v : op === '!=' ? a !== v : op === '<' ? a < v : op === '<=' ? a <= v : op === '>' ? a > v : op === '>=' ? a >= v : true; });
    if (q.ob) { const [f, dir] = q.ob; docs.sort((x, y) => (x.d[f] > y.d[f] ? 1 : x.d[f] < y.d[f] ? -1 : 0) * (dir === 'desc' ? -1 : 1)); }
    else docs.sort((x, y) => (x.p < y.p ? -1 : 1));
    if (q.lim) docs = docs.slice(0, q.lim);
    const ds = docs.map((x) => snapDoc(x.p, x.d));
    return { docs: ds, size: ds.length, empty: !ds.length, docChanges: () => ds.map((d, i) => ({ type: 'added', doc: d, oldIndex: -1, newIndex: i })), metadata: { fromCache: false, hasPendingWrites: false } };
  }
  function deliver(l) {
    if (l.kind === 'doc') l.next(snapDoc(l.path, load()[l.path]));
    else l.next(runQuery(l.q));
  }
  const notify = () => { for (const l of listeners) setTimeout(() => deliver(l), M.delay); };
  window.addEventListener('storage', (e) => { if (e.key === KEY) notify(); });
  const merge = (a, b) => { const o = Object.assign({}, a); for (const k in b) o[k] = b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k]) ? merge(a[k], b[k]) : b[k]; return o; };
  let n = 0;
  function docRef(path) {
    if (segs(path).length % 2) throw new TypeError('document path needs an even number of segments: ' + path);
    return {
      id: segs(path).pop(), path,
      async get() { await new Promise((r) => setTimeout(r, M.delay)); return snapDoc(path, load()[path]); },
      async set(data) {
        if (!canWritePath(path)) throw err('invalid_argument', 'write below the minimum level');
        const all = load(); all[path] = JSON.parse(JSON.stringify(data)); save(all); notify();
      },
      async update(data) {
        if (!canWritePath(path)) throw err('invalid_argument', 'write below the minimum level');
        const all = load(); if (!all[path]) throw err('invalid_argument', 'update needs an existing document');
        all[path] = merge(all[path], JSON.parse(JSON.stringify(data))); save(all); notify();
      },
      async delete() { if (!canWritePath(path)) throw err('invalid_argument', 'write below the minimum level'); const all = load(); delete all[path]; save(all); notify(); },
      onSnapshot(next, error) { const l = { kind: 'doc', path, next, error }; listeners.add(l); setTimeout(() => deliver(l), M.delay); return () => listeners.delete(l); },
      collection(p) { return collRef(path + '/' + p); },
    };
  }
  function query(path, q) {
    return {
      where(f, op, v) { return query(path, Object.assign({}, q, { wh: q.wh.concat([[f, op, v]]) })); },
      orderBy(f, dir) { return query(path, Object.assign({}, q, { ob: [f, dir || 'asc'] })); },
      limit(k) { return query(path, Object.assign({}, q, { lim: k })); },
      async get() { return runQuery(Object.assign({ path }, q)); },
      onSnapshot(next, error) { const l = { kind: 'query', q: Object.assign({ path }, q), next, error }; listeners.add(l); setTimeout(() => deliver(l), M.delay); return () => listeners.delete(l); },
    };
  }
  function collRef(path) {
    if (segs(path).length % 2 === 0) throw new TypeError('collection path needs an odd number of segments: ' + path);
    const base = query(path, { wh: [], ob: null, lim: null });
    return Object.assign(base, {
      path,
      doc(id) { return docRef(path + '/' + (id || ('d' + Date.now().toString(36) + (n++).toString(36) + Math.random().toString(36).slice(2, 6)))); },
      async add(data) { const r = this.doc(); await r.set(data); return r; },
    });
  }
  const db = Object.freeze({ doc: docRef, collection: collRef });
  const people = { u_owner: 'Owner A', u_editor: 'Editor B', u_contrib: 'Contributor C', u_viewer: 'Viewer D' };
  const avatar = (id) => 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" rx="20" fill="#7a8f99"/><text x="20" y="26" font-size="16" text-anchor="middle" fill="#fff" font-family="sans-serif">${(people[id] || '?')[0]}</text></svg>`);
  const user = Object.freeze({
    async isOwner() { return M.role === 'owner'; },
    async canEdit() { return level >= 2; },
    async can(name) { if (M.canNull) return null; return name === 'data.write' ? level >= 1 : false; },
    async id() { return M.uid; },
    async me() { return { id: M.uid, name: people[M.uid] || M.name, avatarUrl: avatar(M.uid), color: '#7a8f99', email: null, isOwner: M.role === 'owner', canEdit: level >= 2 }; },
    async profiles(ids) { const o = {}; for (const id of [].concat(ids)) o[id] = { id, name: people[id] || '', avatarUrl: avatar(id), color: '#7a8f99', email: null, isMe: id === M.uid, guest: false }; return o; },
  });
  async function sampleFn(input, opts) {
    opts = opts || {};
    window.__samples.push({ input, opts: Object.keys(opts) });
    if (M.sample === 'not_granted') throw { code: 'not_granted', message: 'declined' };
    if (M.sample === 'rate') throw { code: 'rate_limited', message: 'slow down' };
    await new Promise((r, j) => { const t = setTimeout(r, 400); if (opts.signal) opts.signal.addEventListener('abort', () => { clearTimeout(t); j({ code: 'cancelled', message: 'stopped' }); }); });
    const text = (window.__mockAnswer && window.__mockAnswer(input)) || '{}';
    if (opts.onText) opts.onText({ text, delta: text });
    return { text, truncated: false, modelTierApplied: opts.modelTier || 'default' };
  }
  sampleFn.json = async (input, opts) => { const r = await sampleFn(input, opts); try { return JSON.parse(r.text); } catch { throw { code: 'invalid_json', message: 'no json', text: r.text }; } };
  sampleFn.limits = async () => ({ maxPromptBytes: 262144 });
  const downloads = Object.freeze({ async save(req) { window.__downloads.push({ filename: req.filename, data: typeof req.data === 'string' ? req.data : '[binary]' }); return { status: 'saved' }; } });
  const caps = { db: M.db ? db : null, user, sample: M.sample === 'none' ? null : sampleFn, downloads: M.downloads ? downloads : null };
  window.claude = Object.freeze({ use: (name) => new Promise((r) => setTimeout(() => r(caps[name] === undefined ? null : caps[name]), M.delay)) });
})();
