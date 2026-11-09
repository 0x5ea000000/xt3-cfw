'use strict';
// Palette front end. No libraries: h() builds elements, every value goes in as text, never as HTML.
const $ = s => document.querySelector(s);
const app = $('#app');
let S = null;            // last /api/state
let timer = null;
let view = null;         // current view's refresh function

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k === 'value') e.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') e[k] = !!v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    e.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return e;
}

async function api(path, opts) {
  const o = Object.assign({}, opts);
  if (o.json !== undefined) { o.method = o.method || 'POST'; o.headers = { 'Content-Type': 'application/json' }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch(path, o);
  const t = await r.text();
  let d; try { d = JSON.parse(t); } catch { d = { error: t.slice(0, 200) }; }
  if (!r.ok) throw new Error(d.error || `Request failed (${r.status})`);
  return d;
}

let toastT = null;
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 4000); }
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message); } };

const STOCK = ['Provia', 'Velvia', 'Astia', 'Classic Chrome', 'PRO Neg. Hi', 'PRO Neg. Std', 'Classic Negative', 'Eterna', 'Eterna Bleach Bypass', 'Acros', 'Monochrome', 'Sepia'];
const GRADE = { great: 'Great match', good: 'Good match', fair: 'Fair match', poor: 'Poor match' };
const CAMERA = { passed: 'Passed on camera', failed: 'Failed on camera', 'not-tested': 'Not tested on camera' };
const lookBy = slug => S.looks.find(k => k.slug === slug);
const score = v => (v === null || v === undefined) ? '–' : Number(v).toFixed(2);
const when = t => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
const statusText = k => ({ 'waiting-exports': 'Needs exports', fitting: 'Fitting', failed: 'Fit failed', fitted: k.fit ? GRADE[k.fit.grade] : 'Fitted' })[k.status];
const statusClass = k => k.status === 'fitted' && k.fit ? k.fit.grade : k.status === 'failed' ? 'failed' : 'not-tested';

function sharePath(folder) {
  return folder;
}

function copyBtn(text) {
  return h('button', { type: 'button', class: 'small', onclick: guard(async () => { await navigator.clipboard.writeText(text); toast('Copied'); }) }, 'Copy');
}

// ---- film list ----
async function filmList() {
  const shown = S.rows.filter(Boolean), built = S.current_build ? S.builds.find(b => b.id === S.current_build) : null;
  const ready = S.looks.filter(k => k.status === 'fitted');
  const free = ready.filter(k => !shown.includes(k.slug));
  const save = guard(async r => { await api('/api/rows', { json: { rows: r } }); await refresh(); });
  const move = (i, d) => { const r = shown.slice(); [r[i], r[i + d]] = [r[i + d], r[i]]; save(r); };
  const rowItem = (slug, i) => {
    const k = lookBy(slug);
    return h('li', { class: 'custom' },
      h('span', { class: 'tag' }, `Row ${i + 1}`),
      k ? h('a', { href: `#/look/${slug}`, title: 'Change this icon' }, h('img', { class: 'icon36', src: iconUrl(k.icon), alt: `${k.icon} icon` })) : null,
      h('div', { class: 'sel' }, h('select', { 'aria-label': `Look on row ${i + 1}`, onchange: e => { const r = shown.slice(); r[i] = e.target.value; save(r); } },
        ready.map(x => h('option', { value: x.slug, selected: x.slug === slug, disabled: x.slug !== slug && shown.includes(x.slug) }, `${x.name} (${x.menu_name})`)))),
      k ? h('a', { href: `#/look/${slug}`, title: 'Predicted score. Lower is closer to Lightroom.' }, h('span', { class: `badge ${statusClass(k)}` }, score(k.fit?.score))) : null,
      h('div', { class: 'row', style: 'gap:4px' },
        h('button', { type: 'button', class: 'icon', title: 'Move up', 'aria-label': `Move row ${i + 1} up`, disabled: i === 0, onclick: () => move(i, -1) }, '↑'),
        h('button', { type: 'button', class: 'icon', title: 'Move down', 'aria-label': `Move row ${i + 1} down`, disabled: i === shown.length - 1, onclick: () => move(i, 1) }, '↓'),
        h('button', { type: 'button', class: 'icon', title: 'Take off the camera', 'aria-label': `Remove row ${i + 1}`, disabled: shown.length === 1, onclick: () => save(shown.filter((_, n) => n !== i)) }, '×')));
  };
  const add = shown.length < S.engine.rows && free.length ? h('li', { class: 'custom' },
    h('span', { class: 'tag' }, 'Add'),
    h('div', { class: 'sel' }, h('select', { 'aria-label': 'Add a look to the camera', onchange: e => e.target.value && save([...shown, e.target.value]) },
      h('option', { value: '' }, 'Add a look to the camera...'), free.map(x => h('option', { value: x.slug }, `${x.name} (${x.menu_name})`))))) : null;
  const left = h('section', { class: 'panel' },
    h('div', { class: 'row spread' }, h('h2', { style: 'margin:0' }, 'Film list on the camera'), h('span', { class: 'muted small' }, `${shown.length} of ${S.engine.rows} rows`)),
    h('p', { class: 'muted small', style: 'margin-top:4px' }, 'SD boot. Stock films stay exactly as they are; your looks follow Sepia.'),
    h('ul', { class: 'film' }, STOCK.map(n => h('li', {}, n)), shown.map(rowItem), add));
  const side = [];
  const icons = shown.map(x => lookBy(x)?.icon); const twins = [...new Set(icons.filter((x, i) => x && icons.indexOf(x) !== i))];
  if (twins.length) side.push(h('p', { class: 'note warn' }, `More than one row uses the ${twins.join(', ')} icon. Pick different letters on a look's page to tell them apart.`));
  if (built) {
    side.push(h('section', { class: 'panel' }, h('h2', {}, 'Card files are ready'),
      h('p', {}, `Build ${built.id.split('-')[0]}: `, h('b', {}, built.label)),
      h('p', {}, h('span', { class: `badge ${built.camera.status}` }, CAMERA[built.camera.status])),
      built.notes.map(n => h('p', { class: 'note warn' }, n)),
      h('div', { class: 'row' }, ...downloads(built), h('a', { class: 'btn', href: '#/builds' }, 'All builds'))));
  } else {
    side.push(h('section', { class: 'panel' }, h('h2', {}, 'This film list is not built yet'),
      h('p', { class: 'muted' }, 'Building takes a few seconds. It checks that only look data differs from the firmware that passed on your camera.'),
      h('button', { class: 'primary', disabled: !S.engine.ok, onclick: guard(async () => { const r = await api('/api/builds', { json: {} }); toast(r.new ? 'Built and checked' : 'That build already exists'); await refresh(); }) }, 'Build card files')));
  }
  side.push(h('section', { class: 'panel' }, h('h2', {}, 'Good to know'),
    h('p', { class: 'small' }, h('b', {}, 'Row 1 is your home row.'), ' After power-off, the camera comes back on Row 1 whichever row you were using. Put your everyday look there.'),
    h('p', { class: 'small' }, 'Highlighting a row previews it in live view and selects it, as with stock films.'),
    h('p', { class: 'small muted' }, 'Tables were fitted at DR100 with Color Chrome Off. Other settings run before the table and shift the result.')));
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Your film list'), h('p', { class: 'muted' }, 'Choose which looks go on the camera, and their order.')),
    h('a', { class: 'btn', href: '#/add' }, 'Add a new look')), h('div', { class: 'grid2' }, left, h('div', {}, side)));
}

// ---- looks ----
function lookCard(k) {
  const img = k.samples ? `/media/look/${k.slug}/${S.frames0}.table.jpg` : null;
  const onRow = S.rows.indexOf(k.slug);
  return h('a', { class: 'card', href: `#/look/${k.slug}` },
    img ? h('img', { class: 'pic', src: img.replace('.table.jpg', '.t.jpg'), alt: '', loading: 'lazy' }) : h('div', { class: 'pic' }),
    h('div', { class: 'body' }, h('div', { class: 'row spread' }, h('b', {}, k.name), h('span', { class: `badge ${statusClass(k)}` }, statusText(k))),
      h('div', { class: 'muted small' }, k.fit ? `Score ${score(k.fit.score)}` : 'No table yet', onRow >= 0 ? ` · on Row ${onRow + 1}` : '')));
}

async function looks() {
  if (!S.frames0) { const f = await api('/api/frames'); S.frames0 = f.frames[0]?.name; }
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Looks'), h('p', { class: 'muted' }, `Every look you have fitted. Up to ${S.engine.rows} can be on the camera at once.`)),
    h('a', { class: 'btn primary', href: '#/add' }, 'Add a look')),
    h('div', { class: 'looks' }, S.looks.map(lookCard)));
}

// ---- add ----
const iconUrl = (pair, kind = 'list', scale = 2) => `/icon/${pair}.png?kind=${kind}&scale=${scale}`;

function suggestMenu(n) { return n.replace(/\s+(Normal\s+)?EXP\s*0\s*$/i, '').toUpperCase().slice(0, S.engine.name_max).trim(); }

async function addLook() {
  const f = { name: h('input', { required: true, placeholder: 'Portra 400' }), menu: h('input', { maxlength: S.engine.name_max, placeholder: 'PORTRA 400' }), look: h('input', { placeholder: 'Exactly as Lightroom shows it' }),
    l1: h('input', { maxlength: S.engine.line_max }), l2: h('input', { maxlength: S.engine.line_max, value: 'Custom film look' }), l3: h('input', { maxlength: S.engine.line_max, value: 'Use DR100, Color Chrome Off' }) };
  let preset = null;
  const info = h('div', {});
  const take = guard(async file => {
    const fd = new FormData(); fd.append('file', file);
    const p = await api('/api/preset', { method: 'POST', body: fd });
    preset = p.filename; f.name.value = f.name.value || p.name.replace(/\s+Normal\s+EXP\s*0\s*$/i, ''); f.look.value = p.name; f.menu.value = f.menu.value || suggestMenu(p.name); f.l1.value = f.l1.value || p.name.slice(0, S.engine.line_max);
    info.replaceChildren(h('p', { class: 'note ok' }, `Read ${p.type.toLowerCase()} "${p.name}"${p.group ? ` from ${p.group}` : ''}.`));
  });
  f.name.addEventListener('input', () => { if (!f.menu.value || f.menu.dataset.auto) { f.menu.value = suggestMenu(f.name.value); f.menu.dataset.auto = '1'; } if (!f.l1.value || f.l1.dataset.auto) { f.l1.value = f.name.value.slice(0, S.engine.line_max); f.l1.dataset.auto = '1'; } });
  f.menu.addEventListener('input', () => delete f.menu.dataset.auto);
  const drop = h('label', { class: 'drop' }, 'Drop the .xmp preset here, or click to choose it',
    h('input', { type: 'file', accept: '.xmp', onchange: e => e.target.files[0] && take(e.target.files[0]) }));
  dropZone(drop, files => files[0] && take(files[0]));
  const submit = guard(async e => {
    e.preventDefault();
    const k = await api('/api/looks', { json: { name: f.name.value, menu_name: f.menu.value, lightroom_look: f.look.value, preset, lines: [f.l1.value, f.l2.value, f.l3.value] } });
    await refresh(); location.hash = `#/look/${k.slug}`;
  });
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Add a look'), h('p', { class: 'muted' }, 'Start with the Lightroom preset. Nothing reaches the camera until you build and copy it.'))),
    h('form', { class: 'panel', onsubmit: submit, style: 'max-width:620px' }, drop, info,
      h('label', {}, 'Name in this app', f.name),
      h('label', {}, 'Lightroom Look name ', h('span', { class: 'hint' }, 'used to check your exports'), f.look),
      h('label', {}, `Name on the camera `, h('span', { class: 'hint' }, `up to ${S.engine.name_max} characters`), f.menu),
      h('label', {}, 'Description on the camera, line 1', f.l1), h('label', {}, 'Line 2', f.l2), h('label', {}, 'Line 3', f.l3),
      h('button', { class: 'primary' }, 'Continue')));
}

function dropZone(el, cb) {
  el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('over'); });
  el.addEventListener('dragleave', () => el.classList.remove('over'));
  el.addEventListener('drop', e => { e.preventDefault(); el.classList.remove('over'); cb([...e.dataTransfer.files]); });
}

// ---- one look ----
function jobPanel(j) {
  const pct = j.total ? Math.min(100, Math.round(j.done / j.total * 100)) : 0;
  return h('div', {}, h('div', { class: 'row spread' }, h('b', {}, j.step), j.total ? h('span', { class: 'muted small' }, `${Math.min(j.done, j.total)} of ${j.total}`) : null),
    h('div', { class: `bar ${j.total ? '' : 'busy'}` }, h('i', { style: `width:${pct}%` })));
}

function checkPanel(c) {
  const kids = [];
  if (c.found) kids.push(h('p', { class: 'small muted' }, `${c.found} of ${c.expected} found.`));
  if (c.ok && !c.problems.length) kids.push(h('p', { class: 'note ok' }, `All ${c.expected} photos are in and the settings are correct.`));
  for (const p of c.problems) kids.push(h('div', { class: `note ${p.level}` }, p.text, p.frames.length ? h('div', { class: 'small muted' }, p.frames.join(', ') + (p.count > p.frames.length ? ` and ${p.count - p.frames.length} more` : '')) : null));
  return kids;
}

function uploader(label, url, after) {
  const st = h('div', { class: 'small muted' });
  const send = guard(async files => {
    files = files.filter(f => /\.(jpe?g|raf)$/i.test(f.name));
    let n = 0;
    const next = async () => { while (files.length) { const f = files.shift(); await api(url(f.name), { method: 'PUT', body: f }); n++; st.textContent = `Uploaded ${n}, ${files.length} to go`; } };
    await Promise.all([next(), next(), next()]);
    st.textContent = `Uploaded ${n} file${n === 1 ? '' : 's'}.`; if (after) await after();
  });
  const d = h('label', { class: 'drop' }, label, h('input', { type: 'file', multiple: true, onchange: e => send([...e.target.files]) }));
  dropZone(d, send);
  return h('div', {}, d, st);
}

async function look(slug) {
  const k = await api(`/api/looks/${slug}`);
  const running = k.job && (k.job.state === 'queued' || k.job.state === 'running');
  const fitted = k.status === 'fitted';
  const head = h('div', { class: 'head' }, h('div', {}, h('h1', {}, k.name), h('p', { class: 'muted' }, `${k.menu_name} on the camera · base ${k.base}`)),
    h('div', { class: 'row' }, h('span', { class: `badge ${statusClass(k)}` }, statusText(k)), fitted && k.samples ? h('a', { class: 'btn', href: `#/compare/${slug}` }, 'Compare') : null));
  const out = [head];
  if (running) out.push(h('section', { class: 'panel' }, jobPanel(k.job)));
  if (k.error) out.push(h('p', { class: 'note error' }, k.error));
  if (k.job && k.job.state === 'failed' && k.job.error && !k.error) out.push(h('p', { class: 'note error' }, k.job.error));
  if (fitted && k.fit) {
    out.push(h('section', { class: 'panel' }, h('h2', {}, GRADE[k.fit.grade]), h('p', {}, k.fit.text),
      h('div', { class: 'stats' },
        h('div', { class: 'stat' }, h('b', {}, score(k.fit.score)), h('span', {}, 'Score with the table')),
        h('div', { class: 'stat' }, h('b', {}, score(k.fit.before)), h('span', {}, 'Plain PRO Neg. Std')),
        h('div', { class: 'stat' }, h('b', {}, score(k.fit.p95)), h('span', {}, 'Worst 5% of pixels')),
        k.camera_score?.mean != null ? h('div', { class: 'stat' }, h('b', {}, score(k.camera_score.mean)), h('span', {}, 'Measured on camera')) : null),
      h('p', { class: 'small muted' }, 'Lower is closer to Lightroom. These are colour differences on photos left out of the fit, predicted in software, not yet measured on the camera.'),
      k.fit.notes.map(n => h('p', { class: `note ${n.level === 'warn' ? 'warn' : ''}` }, n.text)),
      !k.samples && !running ? h('button', { onclick: guard(async () => { await api(`/api/looks/${slug}/samples`, { method: 'POST' }); await refresh(); }) }, 'Make comparison images') : null));
    out.push(cameraPanel(k, slug));
  }
  if (!fitted || k.status === 'failed') out.push(stepsPanel(k, slug, running));
  out.push(iconPanel(k, slug));
  out.push(textPanel(k, slug));
  if (fitted) out.push(redoPanel(k, slug, running));
  app.replaceChildren(...out);
}

function stepsPanel(k, slug, running) {
  const c = k.check || { ok: false, problems: [], found: 0, expected: S.photos, folder: '' };
  return h('section', { class: 'panel' }, h('h2', {}, 'What this look needs'),
    h('ol', { class: 'steps' },
      h('li', { 'data-n': '1', class: c.ok ? 'done' : 'now' }, h('h3', {}, `Export the ${S.photos} photos from Lightroom`),
        h('p', { class: 'small' }, 'Select the same RAFs in Lightroom and apply the Look with nothing else changed.'),
        h('dl', { class: 'settings' },
          h('dt', {}, 'Profile'), h('dd', {}, 'Adobe Standard v2'),
          h('dt', {}, 'Look'), h('dd', {}, `${k.lightroom_look}, Amount 100`),
          h('dt', {}, 'Develop'), h('dd', {}, 'As Shot white balance, all sliders 0, lens corrections off, no crop, grain or vignette'),
          h('dt', {}, 'Export'), h('dd', {}, 'sRGB JPEG, quality 100, long edge 3240, metadata All, filename unchanged')),
        h('p', { class: 'small' }, 'Save them to this folder, or drop them below.'),
        h('div', { class: 'path' }, h('code', {}, sharePath(c.folder)), copyBtn(sharePath(c.folder))),
        uploader('Drop the exported JPEGs here', n => `/api/looks/${slug}/exports/${encodeURIComponent(n)}`, () => look(slug))),
      h('li', { 'data-n': '2', class: c.ok ? 'done' : '' }, h('h3', {}, 'Check the exports'), checkPanel(c), h('button', { type: 'button', onclick: guard(() => look(slug)) }, 'Check again')),
      h('li', { 'data-n': '3', class: c.ok ? 'now' : '' }, h('h3', {}, 'Fit the table'), h('p', { class: 'small muted' }, 'About 3 minutes, then comparison images. You can leave this page.'),
        h('button', { class: 'primary', disabled: !c.ok || running, onclick: guard(async () => { await api(`/api/looks/${slug}/fit`, { method: 'POST' }); await refresh(); await look(slug); }) }, 'Fit this look'))));
}

function iconPanel(k, slug) {
  const ok = c => /^[A-Z0-9]$/.test(c);
  const big = h('input', { value: k.icon[0], maxlength: 1, 'aria-label': 'Big character', class: 'letter' });
  const small = h('input', { value: k.icon[1], maxlength: 1, 'aria-label': 'Small character', class: 'letter' });
  const views = [['list', 'Film list', 3], ['q', 'Q menu', 2], ['caption', 'I.Q. menu', 2], ['pb60', 'Shooting info', 2]];
  const imgs = views.map(([kind, , scale]) => h('img', { src: iconUrl(k.icon, kind, scale), alt: '' }));
  const msg = h('p', { class: 'small muted', style: 'margin:0' }, k.icon_chosen ? '' : 'Suggested from the camera name. Change it, or save to keep it.');
  const save = h('button', { type: 'button', disabled: true, onclick: guard(async () => {
    await api(`/api/looks/${slug}/icon`, { method: 'PATCH', json: { icon: big.value + small.value } });
    await refresh(); toast('Icon saved. Build again to put it on the card.');
  }) }, 'Save icon');
  const show = () => {
    big.value = big.value.toUpperCase(); small.value = small.value.toUpperCase();
    const good = ok(big.value) && ok(small.value); const pair = big.value + small.value;
    save.disabled = !good || (pair === k.icon && k.icon_chosen);
    msg.textContent = good ? (k.icon_chosen || pair !== k.icon ? '' : 'Suggested from the camera name. Change it, or save to keep it.') : 'Use A to Z or 0 to 9.';
    if (good) views.forEach(([kind, , scale], i) => { imgs[i].src = iconUrl(pair, kind, scale); });
  };
  big.addEventListener('input', show); small.addEventListener('input', show);
  show();
  return h('section', { class: 'panel' }, h('h2', {}, 'Icon on the camera'),
    h('div', { class: 'row', style: 'align-items:flex-end;gap:14px' },
      h('label', { style: 'margin:0' }, 'Big', big), h('label', { style: 'margin:0' }, 'Small', small), save, msg),
    h('div', { class: 'previews' }, views.map(([, name], i) => h('figure', {}, imgs[i], h('figcaption', {}, name)))));
}

function textPanel(k, slug) {
  const name = h('input', { value: k.menu_name, maxlength: S.engine.name_max });
  const ls = k.lines.map(t => h('input', { value: t, maxlength: S.engine.line_max }));
  const inRow = S.rows.includes(slug);
  return h('details', { class: 'panel' }, h('summary', {}, 'Name, description and removal'), h('div', { style: 'margin-top:14px;max-width:560px' },
    h('label', {}, 'Name on the camera', name), ls.map((l, i) => h('label', {}, `Description line ${i + 1}`, l)),
    h('div', { class: 'row spread' }, h('button', { onclick: guard(async () => { await api(`/api/looks/${slug}`, { method: 'PATCH', json: { menu_name: name.value, lines: ls.map(l => l.value) } }); await refresh(); toast('Saved. Build again to put it on the card.'); }) }, 'Save'),
      h('button', { class: 'danger', disabled: inRow, title: inRow ? 'Take it off its row first' : null, onclick: guard(async () => {
        if (!confirm(`Remove ${k.name} and its table from the library?`)) return;
        await api(`/api/looks/${slug}`, { method: 'DELETE' }); view = looks; location.hash = '#/looks'; await refresh(); }) }, 'Remove look'))));
}

function redoPanel(k, slug, running) {
  return h('details', { class: 'panel' }, h('summary', {}, 'Fit again'), h('div', { style: 'margin-top:12px' },
    h('p', { class: 'small muted' }, 'Replaces this look\'s table. Any build already made keeps its own copy.'),
    h('button', { disabled: running, onclick: guard(async () => { if (!confirm('Replace the table with a new fit?')) return; await api(`/api/looks/${slug}/fit`, { method: 'POST' }); await refresh(); await look(slug); }) }, 'Fit again')));
}

function cameraPanel(k, slug) {
  const cs = k.camera_score;
  return h('section', { class: 'panel' }, h('h2', {}, 'Score it on the camera'),
    h('p', { class: 'small' }, 'This is the real test. Shoot 5 or so scenes on this row, then export those RAFs from Lightroom with the settings above.'),
    h('div', { class: 'grid2' },
      uploader('Photos from the camera (JPEG or RAF)', n => `/api/looks/${slug}/camera/camera/${encodeURIComponent(n)}`),
      uploader('Lightroom exports of the same frames', n => `/api/looks/${slug}/camera/camera-lightroom/${encodeURIComponent(n)}`)),
    h('button', { onclick: guard(async () => { await api(`/api/looks/${slug}/score`, { method: 'POST' }); await refresh(); await look(slug); }) }, 'Score these photos'),
    cs ? h('div', { class: 'tablewrap', style: 'margin-top:12px' }, h('table', {}, h('thead', {}, h('tr', {}, ['Frame', 'Score', 'Worst 5%', 'Brightness'].map(t => h('th', {}, t)))),
      h('tbody', {}, cs.frames.map(f => h('tr', {}, h('td', {}, f.frame), h('td', {}, score(f.mean)), h('td', {}, score(f.p95)), h('td', {}, (f.mean_L_error > 0 ? '+' : '') + f.mean_L_error)))))) : null,
    cs && cs.skipped.length ? h('p', { class: 'small muted' }, `Skipped, no matching Lightroom file or different size: ${cs.skipped.join(', ')}`) : null);
}

// ---- compare ----
let cmp = { frame: null, left: 'base', right: null, sort: 'worst' };

function sources() {
  const out = [['base', 'Plain PRO Neg. Std']];
  for (const k of S.looks) if (k.samples) { out.push([`table:${k.slug}`, `${k.name}: table`]); out.push([`lr:${k.slug}`, `${k.name}: Lightroom`]); }
  return out;
}
function srcUrl(s, frame) {
  if (s === 'base') return `/media/base/${frame}.jpg`;
  const [t, slug] = s.split(':');
  return `/media/look/${slug}/${frame}.${t === 'lr' ? 'lightroom' : 'table'}.jpg`;
}
const srcName = s => sources().find(x => x[0] === s)?.[1] || s;

function wipe(a, b, la, lb) {
  const top = h('img', { src: a, alt: la }), base = h('img', { src: b, alt: lb });
  const over = h('div', { class: 'over' }, top), hd = h('div', { class: 'handle' });
  const box = h('div', { class: 'wipe' }, base, over, hd, h('span', { class: 'lab l' }, la), h('span', { class: 'lab r' }, lb));
  const set = p => { p = Math.max(0, Math.min(1, p)); over.style.clipPath = `inset(0 ${100 - p * 100}% 0 0)`; hd.style.left = `${p * 100}%`; box.setAttribute('aria-valuenow', Math.round(p * 100)); box._p = p; };
  set(.5);
  const mv = e => { const r = box.getBoundingClientRect(); set((e.clientX - r.left) / r.width); };
  box.addEventListener('pointerdown', e => { box.setPointerCapture(e.pointerId); mv(e); box.addEventListener('pointermove', mv); });
  box.addEventListener('pointerup', () => box.removeEventListener('pointermove', mv));
  box.tabIndex = 0; box.setAttribute('role', 'slider'); box.setAttribute('aria-label', 'Comparison position');
  box.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') set(box._p - .05); if (e.key === 'ArrowRight') set(box._p + .05); });
  return box;
}

async function compare(slug) {
  const with_ = S.looks.filter(k => k.samples);
  if (!with_.length) { app.replaceChildren(h('h1', {}, 'Compare'), h('p', { class: 'note' }, 'No comparison images yet. Open a look and make them.')); return; }
  if (slug && lookBy(slug)?.samples) { cmp.right = `lr:${slug}`; cmp.left = `table:${slug}`; }
  if (!cmp.right) { cmp.left = `table:${with_[0].slug}`; cmp.right = `lr:${with_[0].slug}`; }
  const { frames } = await api('/api/frames');
  const key = cmp.left.includes(':') ? cmp.left.split(':')[1] : cmp.right.split(':')[1];
  const val = f => f.scores[key]?.table ?? 0;
  const list = frames.filter(f => f.scores[key]).sort((a, b) => cmp.sort === 'worst' ? val(b) - val(a) : a.name.localeCompare(b.name));
  if (!cmp.frame || !list.some(f => f.name === cmp.frame)) cmp.frame = list[0]?.name;
  const sel = (side) => h('select', { 'aria-label': `${side} image`, onchange: e => { cmp[side] = e.target.value; compare(); } }, sources().map(([v, n]) => h('option', { value: v, selected: cmp[side] === v }, n)));
  const f = list.find(x => x.name === cmp.frame);
  const thumb = n => `/media/look/${key}/${n}.t.jpg`;
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Compare'), h('p', { class: 'muted' }, 'Drag across the photo. "Table" is the predicted camera result; "Lightroom" is the target.'))),
    h('section', { class: 'panel' },
      h('div', { class: 'row', style: 'margin-bottom:10px' }, h('div', { style: 'flex:1 1 220px;min-width:0' }, sel('left')), h('div', { style: 'flex:1 1 220px;min-width:0' }, sel('right'))),
      wipe(srcUrl(cmp.left, cmp.frame), srcUrl(cmp.right, cmp.frame), srcName(cmp.left), srcName(cmp.right)),
      h('div', { class: 'row spread', style: 'margin-top:10px' }, h('span', { class: 'small muted' }, `${cmp.frame}${f ? ` · score ${score(val(f))}, plain PRO Neg. Std ${score(f.scores[key].before)}` : ''}`),
        h('select', { style: 'width:auto', 'aria-label': 'Sort photos', onchange: e => { cmp.sort = e.target.value; compare(); } }, h('option', { value: 'worst', selected: cmp.sort === 'worst' }, 'Worst match first'), h('option', { value: 'name', selected: cmp.sort === 'name' }, 'By filename'))),
      h('div', { class: 'thumbs' }, list.map(x => h('button', { class: `thumb ${x.name === cmp.frame ? 'on' : ''}`, title: x.name, onclick: () => { cmp.frame = x.name; compare(); } }, h('img', { src: thumb(x.name), alt: x.name, loading: 'lazy' }), h('span', {}, score(val(x))))))));
}

// ---- card ----
const CRC_T = (() => { const t = new Uint32Array(256); for (let i = 0; i < 256; i++) { let c = i; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[i] = c >>> 0; } return t; })();

// The loader's checks: the CRC of older ffinit files, test 31's word check (r = word + rotl(r, 1)), and the same sum on one word in 16 for a small ffboot.
async function fileChecks(file, progress) {
  let c = 0xFFFFFFFF, pos = 0, sum = 0, word = 0, n = 0, index = 0, sampled = 0;
  const reader = file.stream().getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (let i = 0; i < value.length; i++) {
      const b = value[i];
      c = CRC_T[(c ^ b) & 255] ^ (c >>> 8);
      word = (word | (b << (n * 8))) >>> 0;
      if (++n === 4) {
        sum = (word + (((sum << 1) | (sum >>> 31)) >>> 0)) >>> 0;
        if (index++ % 16 === 0) sampled = (word + (((sampled << 1) | (sampled >>> 31)) >>> 0)) >>> 0;
        word = 0; n = 0;
      }
    }
    pos += value.length; progress(pos / file.size);
  }
  return { crc: (c ^ 0xFFFFFFFF) >>> 0, word: sum, sampled };
}

// A small ffboot leaves out the zero runs. ffinit's table says where each piece belongs, so the looks can be read at their usual addresses.
function segmentTable(view, from, to) {
  // Its place depends on the loader, so find it: it always starts with the 4 KiB the ROM reads, then the piece that follows.
  let start = -1;
  for (let at = from; at + 16 <= to && start < 0; at += 16) if (view.getUint32(at, true) === 0 && view.getUint32(at + 4, true) === 0x1000 && view.getUint32(at + 8, true) === 0x1000) start = at;
  if (start < 0) return null;
  const out = []; let pos = 0;
  for (let at = start; at + 8 <= to; at += 8) {
    const a = view.getUint32(at, true), n = view.getUint32(at + 4, true);
    if (!n) return out;
    out.push({ a, n, pos }); pos += n;
  }
  return null;
}

async function readAt(boot, segs, a, n) {
  if (!segs) return new Uint8Array(await boot.slice(a, a + n).arrayBuffer());
  const out = new Uint8Array(n);
  for (const s of segs) {
    const from = Math.max(a, s.a), to = Math.min(a + n, s.a + s.n);
    if (from < to) out.set(new Uint8Array(await boot.slice(s.pos + from - s.a, s.pos + to - s.a).arrayBuffer()), from - a);
  }
  return out;
}

async function inspectCard(files, out) {
  const find = n => files.find(f => f.name.toLowerCase() === n);
  const boot = find('ffboot.bin'), init = find('ffinit.bin');
  if (!boot) { out.replaceChildren(h('p', { class: 'note error' }, 'ffboot.bin was not found. Choose the card, or both files.')); return; }
  const bar = h('i', { style: 'width:0' });
  out.replaceChildren(h('p', {}, 'Reading the whole file from the card. Nothing is uploaded or written.'), h('div', { class: 'bar' }, bar));
  const { crc, word, sampled } = await fileChecks(boot, p => { bar.style.width = `${Math.round(p * 100)}%`; });
  const spec = await api('/api/card/spec');
  let fields = null, segs = null;
  if (init) {
    const d = new DataView(await init.arrayBuffer());
    if (d.byteLength >= spec.init_offset + 12) fields = [0, 4, 8].map(o => d.getUint32(spec.init_offset + o, true));
    if (spec.table && boot.size < spec.image_size && fields && fields[0] === boot.size && d.byteLength >= spec.table[1]) segs = segmentTable(d, spec.table[0], spec.table[1]);
  }
  const compact = !!(segs && segs.length && segs.reduce((t, s) => t + s.n, 0) === boot.size);
  const slices = {};
  if (compact || boot.size === spec.image_size) for (const [a, n] of spec.slices) {
    const b = await readAt(boot, compact ? segs : null, a, n);
    slices[a] = btoa(Array.from(b, c => String.fromCharCode(c)).join(''));
  }
  const r = await api('/api/card/inspect', { json: { size: boot.size, crc, word, sampled, compact, init: fields, slices } });
  const kids = [];
  kids.push(h('p', { class: `note ${r.files_match ? 'ok' : 'error'}` }, r.files_match ? 'The two files are complete and belong together.' : 'The two files do not match.'));
  for (const p of r.problems) kids.push(h('p', { class: `note ${p.level}` }, p.text));
  if (r.known) kids.push(h('p', {}, 'This is ', h('b', {}, r.known.name), '. ', h('span', { class: 'muted small' }, CAMERA[r.known.status] || r.known.status || '')));
  if (r.rows) kids.push(h('ul', { class: 'film' }, r.rows.map((x, i) => h('li', { class: 'custom' }, h('span', { class: 'tag' }, `Row ${i + 1}`),
    [x.icon_png ? h('img', { class: 'icon36', src: `data:image/png;base64,${x.icon_png}`, alt: '' }) : null, h('b', {}, x.name), h('span', { class: 'muted small' }, x.lines.join(' · ')), x.look ? h('a', { href: `#/look/${x.look}` }, h('span', { class: 'badge fitted' }, x.look_name)) : h('span', { class: 'badge not-tested' }, 'Table not in library')]))));
  out.replaceChildren(...kids);
}

async function card() {
  const out = h('div', {});
  const take = guard(files => inspectCard(files, out));
  const pick = h('label', { class: 'drop', style: 'padding:30px' }, 'Drop ffboot.bin and ffinit.bin here, or click to choose them',
    h('input', { type: 'file', multiple: true, onchange: e => take([...e.target.files]) }));
  dropZone(pick, take);
  const dir = h('input', { type: 'file', webkitdirectory: true, style: 'display:none', onchange: e => take([...e.target.files]) });
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'What\'s on the card'), h('p', { class: 'muted' }, 'Reads the files in your browser, and shows the looks inside and whether the copy is good.'))),
    h('section', { class: 'panel', style: 'max-width:760px' }, pick, h('div', { class: 'row' }, dir, h('button', { onclick: () => dir.click() }, 'Choose the card folder')), h('div', { style: 'margin-top:14px' }, out)));
}

// ---- builds ----
// Fast SD boot (about 5 s) when the build has the fast files; standard SD boot (FujiMod's loader, about 95 s) always works. Same looks either way.
function downloads(b) {
  return b.card
    ? [h('a', { class: 'btn primary', href: `/download/${b.id}/zip?speed=fast` }, 'Download: fast SD boot'),
       h('a', { class: 'btn', href: `/download/${b.id}/zip?speed=standard`, title: 'The original loader and full image. About 95 s to boot.' }, 'Standard SD boot')]
    : [h('a', { class: 'btn primary', href: `/download/${b.id}/zip?speed=standard` }, 'Download card files')];
}

function buildRow(b) {
  const note = h('input', { value: b.camera.note || '', placeholder: 'Notes from the camera test', 'aria-label': 'Camera notes' });
  const mark = s => guard(async () => { await api(`/api/builds/${b.id}`, { method: 'PATCH', json: { status: s, note: note.value } }); await refresh(); });
  const isCurrent = b.id === S.current_build;
  return h('section', { class: 'panel' },
    h('div', { class: 'row spread' }, h('div', {}, h('b', {}, `Build ${b.id.split('-')[0]}: ${b.label}`), isCurrent ? h('span', { class: 'badge fitted', style: 'margin-left:8px' }, 'Matches your film list') : null),
      h('span', { class: `badge ${b.camera.status}` }, CAMERA[b.camera.status])),
    h('p', { class: 'small muted' }, `${when(b.created)} · ${b.row_names.filter(Boolean).join(', ')}`),
    b.row_icons ? h('div', { class: 'row', style: 'gap:4px;margin-bottom:8px' }, b.row_icons.map(p => h('img', { class: 'icon36', src: iconUrl(p), alt: p }))) : null,
    h('p', { class: 'small muted' }, b.engine === S.engine.id ? `Only look data differs from the approved firmware: ${b.changed_bytes.toLocaleString()} bytes, no code.` : `Built on older firmware (${b.engine}).`),
    b.engine !== S.engine.id && b.engine.startsWith('official') !== S.engine.id.startsWith('official')
      ? h('p', { class: 'note warn' }, b.engine.startsWith('official')
          ? `Made for other firmware (${b.engine}). Check it matches your camera before using it.`
          : `Made for other firmware (${b.engine}). Do not use it on official 5.11: build your film list again here instead.`) : null,
    b.notes.map(n => h('p', { class: 'note warn' }, n)),
    b.card ? h('p', { class: 'small muted' }, `Fast SD boot: ${(b.card.size / 1e6).toFixed(1)} MB on the card, about 5 s. Standard SD boot: the full image, about 95 s. Same looks.`) : null,
    h('p', { class: 'small mono muted', style: 'overflow-wrap:anywhere' }, b.card ? `ffboot fast ${b.card.ffboot_sha256} · standard ${b.ffboot_sha256}` : `ffboot ${b.ffboot_sha256}`),
    h('div', { class: 'row' }, ...downloads(b),
      !isCurrent ? h('button', { onclick: guard(async () => { await api(`/api/builds/${b.id}/restore`, { method: 'POST' }); await refresh(); toast('Film list restored from this build'); }) }, 'Go back to this build') : null),
    h('details', { style: 'margin-top:12px' }, h('summary', {}, 'Copying it to the card and testing'),
      h('ol', { class: 'small', style: 'padding-left:20px;margin:10px 0' },
        h('li', {}, 'Use a FAT32 card. Delete the old ffboot.bin and ffinit.bin, then copy the new ffboot.bin and ffinit.bin to the top folder of the card, in that order.'),
        h('li', {}, 'Open What\'s on the card here and check the copy.'),
        h('li', {}, 'Hold Fn1 and press the rear dial while powering on. If it hangs with the lamp on, remove the battery and use your last good card.'),
        b.card ? h('li', {}, 'Fast SD boot: it should boot in about 5 or 6 seconds. About 24 seconds or more means ffboot.bin is in pieces on the card, so the boot took the slow route. Delete both files and copy them again. Standard SD boot takes about 95 seconds; that is normal.') : h('li', {}, 'It takes about 95 seconds to boot; that is normal.'),
        h('li', {}, 'Open FILM SIMULATION. Scroll past your rows both ways, select each one and reopen the list.'),
        h('li', {}, 'Check live view, half-press and playback, then shoot a few frames.'),
        h('li', {}, 'Boot once without the card to confirm normal boot is fine.'))),
    h('div', { class: 'row', style: 'margin-top:10px' }, h('div', { style: 'flex:1 1 220px;min-width:0' }, note), h('button', { onclick: mark('passed') }, 'Passed'), h('button', { class: 'danger', onclick: mark('failed') }, 'Failed')));
}

async function buildsPage() {
  app.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Builds'), h('p', { class: 'muted' }, 'Every set of card files. Each is kept, so you can always go back.'))),
    ...(S.builds.length ? S.builds.map(buildRow) : [h('p', { class: 'note' }, 'No builds yet. Build from the film list page.')]));
}

// ---- shell ----
const NAV = [['#/', 'Film list'], ['#/looks', 'Looks'], ['#/compare', 'Compare'], ['#/card', 'Card'], ['#/builds', 'Builds']];

function shell() {
  const r = location.hash || '#/';
  $('#nav').replaceChildren(...NAV.map(([href, t]) => h('a', { href, class: (r === href || (href !== '#/' && r.startsWith(href))) ? 'on' : null, 'aria-current': r === href ? 'page' : null }, t)));
  $('#engine').replaceChildren(h('span', { class: `pip ${S.engine.ok ? '' : 'bad'}` }), S.engine.ok ? 'Firmware verified' : `Firmware check failed: ${S.engine.error}`);
}

async function refresh() {
  const f0 = S?.frames0;
  S = await api('/api/state'); S.frames0 = f0;
  shell();
  if (view) await view();
}

function route() {
  const p = (location.hash || '#/').slice(2).split('/');
  const r = { '': () => filmList(), looks: () => looks(), add: () => addLook(), look: () => look(p[1]), compare: () => compare(p[1]), card: () => card(), builds: () => buildsPage() }[p[0]];
  view = r || filmList;
  if (S) { shell(); guard(view)(); }
}

// While a job runs, keep the current page live. Forms on these pages are not rebuilt unless a job is active.
async function tick() {
  try {
    const was = S?.active?.length || 0;
    const st = await api('/api/state'); st.frames0 = S?.frames0;
    const now = st.active.length;
    S = st; shell();
    if ((was || now) && (location.hash.startsWith('#/look/') || location.hash === '#/looks' || location.hash === '#/' || location.hash === '')) await view();
  } catch { /* the server may be restarting */ }
  timer = setTimeout(tick, 2000);
}

window.addEventListener('hashchange', route);
(async () => {
  try { S = await api('/api/state'); route(); tick(); }
  catch (e) { app.replaceChildren(h('p', { class: 'note error' }, `Cannot reach the app: ${e.message}`)); }
})();
