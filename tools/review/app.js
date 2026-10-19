// Reel review page. Plain JavaScript, no libraries.
// Everything the customer does is collected in `fb` (feedback), autosaved as a
// draft, and saved with "Save feedback". Claude applies it afterwards.
'use strict';

const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k.nodeType ? k : String(k));
  return e;
};
const fmt = t => { t = Math.max(0, t || 0); const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`; };
const LABEL = { text_callouts: 'Headline / callout', headline_bar: 'Headline bar', sticky_notes: 'Sticky note',
  lists: 'Checklist', emoji: 'Emoji', arrows: 'Arrow', keyword_cards: 'Key-phrase card', cta_card: 'Call to action',
  lower_third: 'Name tag', progress_bar: 'Progress bar', carousel: 'Image carousel', image: 'Image', calendar: 'Calendar (pages flip)', custom: 'Custom graphic' };
// carousel options (scripts/laine_reel/carousel.py)
const CAROUSEL = {
  place: { auto: 'Best spot for this video', top: 'Top', upper: 'Upper third', middle: 'Middle', lower: 'Lower third',
           left: 'Left side', right: 'Right side', top_left: 'Top-left corner', top_right: 'Top-right corner',
           near_subject: 'Beside me' },
  size: { small: 'Small', medium: 'Medium', large: 'Large' },
  speed: { slow: 'Slow', normal: 'Normal', fast: 'Fast' },
  direction: { clockwise: 'Clockwise', counterclockwise: 'Counter-clockwise' },
  motion: { subtle: 'Subtle', noticeable: 'More noticeable' } };
const CAROUSEL_DEFAULT = { place: 'auto', size: 'medium', speed: 'normal', direction: 'clockwise', motion: 'subtle' };
const CAROUSEL_LABEL = { place: 'Placement', size: 'Size', speed: 'Speed', direction: 'Direction', motion: 'Motion' };
const ANIM = { pop: 'Pop in', fade: 'Fade in', fade_scale: 'Soft grow', slide: 'Slide up', bounce: 'Bounce', none: 'Just appear' };

let D = null;                       // data from the server
const fb = { notes: [], cuts: { keep: [], remove: [], remove_words: [], cut_pauses: [] },
             captions: {}, headline: null, graphics: {}, add: { graphics: [], zooms: [], sfx: [] } };
const video = $('#video');
let selStart = null, selEnd = null;

// ---- loading -------------------------------------------------------------
let shownVersion = null;     // version number currently loaded as "newest"
let watching = null;         // version object being watched in the main player
async function load(keepTime) {
  const r = await fetch('/api/reel');
  D = await r.json();
  if (D.error) { toast('Could not load the reel: ' + D.error); return; }
  if (D.draft && !keepTime) Object.assign(fb, D.draft);
  document.documentElement.style.setProperty('--brand', D.brand.primary || '#ff3e8e');
  document.documentElement.style.setProperty('--accent', D.brand.accent || '#a3b18a');
  $('#reelName').textContent = `${D.name} · ${fmt(D.duration)} long` +
    (D.current_version ? ` · version ${D.current_version}` : '') + (D.approved ? ` · version ${D.approved} approved ✓` : '');
  $('#timeTotal').textContent = fmt(D.duration);
  shownVersion = D.current_version;
  // version picker: numbered versions newest first, then older renders
  const vs = $('#versionSelect'), cs = $('#compareSelect');
  vs.innerHTML = ''; cs.innerHTML = '';
  const numbered = D.versions.filter(v => v.n).sort((a, b) => b.n - a.n);
  const legacy = D.versions.filter(v => !v.n);
  if (!numbered.length) vs.append(el('option', { value: '' }, 'Current video'));
  [...numbered, ...legacy].forEach((v, k) => {
    const label = v.label + (v.current ? ' (current)' : '');
    vs.append(el('option', { value: k }, label));
    cs.append(el('option', { value: k }, label));
  });
  const all = [...numbered, ...legacy];
  const pick = () => {
    watching = all[+vs.value] || null;
    const t = video.currentTime || 0;
    video.src = watching ? watching.url : D.video;
    video.addEventListener('loadedmetadata', () => { video.currentTime = Math.min(t, video.duration || t); }, { once: true });
    $('#vtagMain').textContent = watching && watching.n ? 'Version ' + watching.n : 'Current';
    $('#restoreBtn').classList.toggle('hidden', !(watching && watching.n && !watching.current));
    $('#finalizeBtn').textContent = watching && watching.n ? `Finalize & Download version ${watching.n}` : 'Finalize & Download';
    if (watching && watching.n && !watching.current)
      toast(`You're watching version ${watching.n}. Notes you add use its timing; changes are made to the newest version.`, 6000);
  };
  vs.onchange = pick;
  cs.onchange = () => { const v = all[+cs.value]; $('#video2').src = v.url; $('#vtagCmp').textContent = v.n ? 'Version ' + v.n : 'Older'; };
  vs.value = numbered.length ? String(numbered.findIndex(v => v.current) >= 0 ? numbered.findIndex(v => v.current) : 0) : '';
  if (all.length > 1) { cs.value = '1'; cs.onchange(); }
  pick();
  renderAll();
}

// ---- versions: compare, restore, finalize, live status ---------------------
const video2 = $('#video2');
$('#compareBtn').onclick = () => {
  const on = $('#comparePhone').classList.toggle('hidden') === false;
  $('#compareRow').classList.toggle('hidden', !on);
  document.querySelector('.layout').classList.toggle('comparing', on);
  $('#compareBtn').textContent = on ? 'Stop comparing' : 'Compare';
  if (on && !video2.src && $('#compareSelect').options.length) $('#compareSelect').onchange();
  video2.currentTime = video.currentTime;
};
$('#cmpSound').onchange = e => { video2.muted = !e.target.checked; video.muted = e.target.checked; };
video.addEventListener('play', () => { if (!$('#comparePhone').classList.contains('hidden')) { video2.currentTime = video.currentTime; video2.play(); } });
video.addEventListener('pause', () => video2.pause());
video.addEventListener('seeked', () => { if (!$('#comparePhone').classList.contains('hidden')) video2.currentTime = video.currentTime; });

function ask(title, text, okLabel) {
  return new Promise(res => {
    $('#modalTitle').textContent = title; $('#modalText').textContent = text; $('#modalOk').textContent = okLabel;
    $('#modal').classList.remove('hidden');
    $('#modalOk').onclick = () => { $('#modal').classList.add('hidden'); res(true); };
    $('#modalCancel').onclick = () => { $('#modal').classList.add('hidden'); res(false); };
  });
}
$('#restoreBtn').onclick = async () => {
  if (!watching || !watching.n) return;
  if (!(await ask(`Restore version ${watching.n}?`, `Version ${watching.n} becomes your current video again, with its edits. Nothing is deleted: every version stays in the list.`, 'Restore'))) return;
  const r = await (await fetch('/api/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: watching.n }) })).json();
  if (!r.ok) { toast('Could not restore: ' + r.error); return; }
  toast(`Version ${r.version} restored.`); await load(true);
};
$('#finalizeBtn').onclick = async () => {
  const v = (watching && watching.n) ? watching.n : D.current_version;
  if (!v) { toast('There is no finished version to approve yet.'); return; }
  if (count() && !(await ask('You have unsaved changes', 'Download anyway? Your unsaved changes stay on this page; save them if you want another version.', 'Download anyway'))) return;
  if (!(await ask(`Approve version ${v}?`, `Version ${v} is marked as approved and its MP4 downloads to your computer. You can still make more versions later.`, 'Approve & download'))) return;
  const r = await (await fetch('/api/finalize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: v }) })).json();
  if (!r.ok) { toast('Could not finalize: ' + r.error); return; }
  window.location.href = r.download;
  toast(`Version ${v} approved ✓  Your download has started.`, 8000);
  setTimeout(() => load(true), 1500);
};

let lastStatus = '';
async function poll() {
  try {
    const st = await (await fetch('/api/status')).json();
    const bar = $('#statusBar');
    let text = '', cls = '';
    if (st.state === 'working') { text = st.message || 'Claude is working on your video…'; cls = 'working'; }
    else if (st.state === 'error') { text = st.message; cls = 'error'; }
    else if ((st.pending_feedback && st.pending_feedback.length) || st.pending_settings) {
      text = st.pending_settings && !(st.pending_feedback || []).length ? 'Brand settings saved. Tell Claude “apply my review” to see them in a new version.'
                                                                     : 'Feedback saved. Tell Claude “apply my review” to get the next version.'; cls = 'waiting'; }
    if (st.latest_version && shownVersion !== null && st.latest_version > shownVersion && st.state !== 'working') {
      await load(true);
      text = `Version ${st.latest_version} is ready. Watch it, add more notes, or Finalize & Download.`; cls = 'ready';
      toast(text, 8000);
    } else if (st.current_version && shownVersion !== st.current_version && st.state !== 'working') {
      await load(true);
    }
    bar.className = 'status ' + cls + (text ? '' : ' hidden');
    $('#statusText').textContent = text;
    lastStatus = JSON.stringify(st);
  } catch (e) { /* server stopped: keep the page as it is */ }
}
setInterval(poll, 3000);

// "Remove the pause here": the gap between words nearest the playhead
$('#cutPauseHere').onclick = () => {
  const t = video.currentTime, w = D.words_out;
  let best = null;
  for (let k = 1; k < w.length; k++) {
    const a = w[k - 1], b = w[k], gap = b.start - a.end;
    if (gap < 0.12 || a.i === undefined || a.i === null) continue;
    const d = t < a.end ? a.end - t : t > b.start ? t - b.start : 0;
    if (d <= 0.6 && (!best || d < best.d)) best = { d, a, b, gap };
  }
  if (!best) { toast('No pause found near here. Pause the video right where the silence is.'); return; }
  if (!fb.cuts.cut_pauses.includes(best.a.i)) fb.cuts.cut_pauses.push(best.a.i);
  toast(`The ${best.gap.toFixed(2)}s pause after “${best.a.text}” will be removed.`);
  changed();
};

// ---- player --------------------------------------------------------------
const playBtn = $('#playBtn');
playBtn.onclick = () => video.paused ? video.play() : video.pause();
video.onplay = () => playBtn.textContent = '❚❚';
video.onpause = () => playBtn.textContent = '▶';
video.addEventListener('click', () => playBtn.click());
$('#back1').onclick = () => video.currentTime = Math.max(0, video.currentTime - 1);
$('#fwd1').onclick = () => video.currentTime = Math.min(D.duration, video.currentTime + 1);
let stopAt = null;
video.ontimeupdate = () => {
  const t = video.currentTime;
  $('#timeNow').textContent = fmt(t);
  document.querySelectorAll('.tnow').forEach(s => s.textContent = fmt(t));
  $('#playhead').style.left = (100 * t / D.duration) + '%';
  const cap = D.captions.find(c => t >= c.start && t < c.end);
  $('#captionNow').textContent = cap ? '“' + cap.text + '”' : '';
  if (stopAt !== null && t >= stopAt) { video.pause(); stopAt = null; }
};
function seek(t, playFor) {
  video.currentTime = Math.max(0, t);
  if (playFor) { stopAt = t + playFor; video.play(); }
}
$('#timeline').onclick = e => {
  const r = e.currentTarget.getBoundingClientRect();
  seek(D.duration * (e.clientX - r.left) / r.width);
};
document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea, select')) return;
  if (e.code === 'Space') { e.preventDefault(); playBtn.click(); }
  if (e.code === 'ArrowLeft') video.currentTime -= 0.1;
  if (e.code === 'ArrowRight') video.currentTime += 0.1;
});

function renderTimeline() {
  const lane = $('#laneMarks'); lane.innerHTML = '';
  const pct = t => (100 * t / D.duration) + '%';
  const add = (cls, a, b, title) => lane.append(el('div', { class: 'mark ' + cls, title,
    style: `left:${pct(a)};${b !== undefined ? `width:calc(${pct(b - a)} + 2px)` : ''}` }));
  let off = 0; // cut points on the output timeline = where kept segments join
  D.graphics.forEach(g => g.type !== 'progress_bar' && add('g', g.start, g.end, LABEL[g.type] || g.type));
  D.zooms.forEach(z => add('z', z.start, z.end, 'zoom'));
  D.sfx.forEach(s => add('s', s.at, undefined, s.kind));
  joins().forEach(t => add('c', t, undefined, 'cut'));
  fb.notes.forEach(n => add('n', n.t, undefined, n.text));
  fb.add.graphics.forEach(g => add('g', g.t, g.t + (+g.duration || 2.5), 'new ' + g.type));
  fb.add.zooms.forEach(z => add('z', z.t, z.t + (+z.duration || 2), 'new zoom'));
  fb.add.sfx.forEach(s => add('s', s.t, undefined, 'new ' + s.kind));
}
function joins() {
  // output times where a cut happened: gaps between consecutive kept words' source times
  const out = [];
  const w = D.words_out;
  for (let k = 1; k < w.length; k++) {
    if (w[k].source_start - w[k - 1].source_end > (w[k].start - w[k - 1].end) + 0.15) out.push(w[k].start);
  }
  return out;
}

// ---- tabs ----------------------------------------------------------------
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('active', x === b));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + b.dataset.tab));
});

// ---- notes ---------------------------------------------------------------
$('#addNote').onclick = () => {
  const text = $('#noteText').value.trim();
  if (!text) { toast('Type what you would like changed first.'); return; }
  video.pause();
  fb.notes.push({ t: +video.currentTime.toFixed(2), text });
  $('#noteText').value = '';
  changed();
};
function renderNotes() {
  const ul = $('#notesList'); ul.innerHTML = '';
  if (!fb.notes.length) ul.append(el('li', { class: 'dim' }, 'No notes yet.'));
  [...fb.notes].sort((a, b) => a.t - b.t).forEach(n => ul.append(el('li', {},
    el('span', { class: 't', onclick: () => seek(n.t - 1, 2) }, fmt(n.t)),
    el('span', { class: 'what' }, n.text),
    el('button', { class: 'ghost', onclick: () => { fb.notes.splice(fb.notes.indexOf(n), 1); changed(); } }, 'Delete'))));
}

// ---- cuts ----------------------------------------------------------------
function toggle(list, v) { const i = list.indexOf(v); i < 0 ? list.push(v) : list.splice(i, 1); }
function renderCuts() {
  const ul = $('#candList'); ul.innerHTML = '';
  const cands = D.candidates.filter(c => c.type !== 'soft_filler');
  if (!cands.length) ul.append(el('li', { class: 'dim' }, 'Nothing found.'));
  cands.forEach(c => {
    const removed = c.decision && c.decision.applied;
    const pendingKeep = fb.cuts.keep.includes(c.id), pendingRemove = fb.cuts.remove.includes(c.id);
    const w0 = D.words_src[c.words[0]];
    ul.append(el('li', { class: (pendingKeep || pendingRemove) ? 'changed' : '' },
      el('span', { class: 'what' },
        el('span', { class: 'tag ' + (removed ? 'cut' : 'kept') }, removed ? 'cut' : 'left in'), ' “', c.text, '”',
        !removed && c.decision && c.decision.why ? el('div', { class: 'small' }, c.decision.why) : null),
      removed
        ? el('button', { class: 'ghost', onclick: () => { toggle(fb.cuts.keep, c.id); changed(); } }, pendingKeep ? 'Undo' : 'Put it back')
        : el('button', { class: 'ghost', onclick: () => { toggle(fb.cuts.remove, c.id); changed(); } }, pendingRemove ? 'Undo' : 'Remove it')));
  });
  const pl = $('#pauseList'); pl.innerHTML = '';
  if (!D.pauses.length) pl.append(el('li', { class: 'dim' }, 'No pauses longer than a natural breath.'));
  fb.cuts.cut_pauses.filter(i => !D.pauses.some(p => p.after_word === i)).forEach(i => {
    const w = D.words_src[i];
    pl.append(el('li', { class: 'changed' }, el('span', { class: 'what' }, `Pause after “${w ? w.text : i}” will be removed`),
      el('button', { class: 'ghost', onclick: () => { toggle(fb.cuts.cut_pauses, i); changed(); } }, 'Undo')));
  });
  D.pauses.forEach(p => {
    const on = fb.cuts.cut_pauses.includes(p.after_word);
    pl.append(el('li', { class: on ? 'changed' : '' },
      el('span', { class: 't', onclick: () => seek(p.at - 1.2, 2.6) }, fmt(p.at)),
      el('span', { class: 'what' }, `${p.length}s pause after “${p.before}”`),
      el('button', { class: 'ghost', onclick: () => seek(p.at - 1.2, 2.6) }, 'Listen'),
      el('button', { class: 'ghost', onclick: () => { toggle(fb.cuts.cut_pauses, p.after_word); changed(); } }, on ? 'Undo' : 'Remove')));
  });
  const box = $('#srcWords'); box.innerHTML = '';
  const pending = new Set(); fb.cuts.remove_words.forEach(([a, b]) => { for (let i = a; i <= b; i++) pending.add(i); });
  D.words_src.forEach(w => {
    const inSel = selStart !== null && w.i >= Math.min(selStart, selEnd ?? selStart) && w.i <= Math.max(selStart, selEnd ?? selStart);
    const cls = w.removed ? 'cut' : pending.has(w.i) ? 'pending' : inSel ? 'sel' : '';
    box.append(el('span', { class: cls, title: w.removed ? 'already cut' : (w.out !== null ? fmt(w.out) : ''),
      onclick: () => {
        if (w.removed) return;
        if (pending.has(w.i)) { fb.cuts.remove_words = fb.cuts.remove_words.filter(([a, b]) => w.i < a || w.i > b); changed(); return; }
        if (selStart === null || selEnd !== null) { selStart = w.i; selEnd = null; } else selEnd = w.i;
        if (w.out !== null) seek(w.out - 0.3);
        renderCuts();
      } }, w.text), ' ');
  });
  $('#removeSel').disabled = selStart === null;
}
$('#removeSel').onclick = () => {
  const a = Math.min(selStart, selEnd ?? selStart), b = Math.max(selStart, selEnd ?? selStart);
  fb.cuts.remove_words.push([a, b]); selStart = selEnd = null; changed();
};
$('#clearSel').onclick = () => { selStart = selEnd = null; renderCuts(); };

// ---- captions ------------------------------------------------------------
function renderCaptions() {
  const ul = $('#capList'); ul.innerHTML = '';
  D.captions.forEach(c => {
    const li = el('li', {});
    const words = el('div', { class: 'capwords' });
    c.words.forEach(w => {
      const fix = fb.captions[w.i] || {};
      const start = fix.start_out ?? w.start;
      const input = el('input', { type: 'text', value: fix.text ?? w.text,
        oninput: e => { setFix(w, { text: e.target.value === w.text ? undefined : e.target.value }); } });
      words.append(el('div', { class: 'w' + (w.emphasis ? ' em' : '') }, input,
        el('span', { class: 'wt' }, 'starts ' + fmt(start)),
        el('div', { class: 'row' },
          el('button', { class: 'ghost', title: 'Earlier', onclick: () => { setFix(w, { start_out: +(start - 0.05).toFixed(3) }); renderCaptions(); } }, '◀'),
          el('button', { class: 'ghost', onclick: () => { setFix(w, { start_out: +video.currentTime.toFixed(3) }); renderCaptions(); } }, 'Starts now'),
          el('button', { class: 'ghost', title: 'Later', onclick: () => { setFix(w, { start_out: +(start + 0.05).toFixed(3) }); renderCaptions(); } }, '▶'))));
    });
    const changedHere = c.words.some(w => fb.captions[w.i]);
    li.className = changedHere ? 'changed' : '';
    li.append(el('div', { class: 'row' },
      el('span', { class: 't', onclick: () => seek(c.start - 0.4, (c.end - c.start) + 0.8) }, '▶ ' + fmt(c.start)),
      changedHere ? el('button', { class: 'ghost', onclick: () => { c.words.forEach(w => delete fb.captions[w.i]); changed(); } }, 'Undo changes') : null), words);
    ul.append(li);
  });
}
function setFix(w, patch) {
  if (w.i === null || w.i === undefined) { toast('This word can’t be edited here; add a note instead.'); return; }
  const cur = Object.assign({}, fb.captions[w.i] || {}, patch);
  Object.keys(cur).forEach(k => cur[k] === undefined && delete cur[k]);
  if (Object.keys(cur).length) fb.captions[w.i] = cur; else delete fb.captions[w.i];
  changed(false);
}

// ---- headline ------------------------------------------------------------
function renderHeadline() {
  const box = $('#headOptions'); box.innerHTML = '';
  if (D.headline.style === 'none' || !D.headline.id) {
    box.append(el('p', { class: 'hint' }, 'Your brand profile has no headline. Add a note if you want one on this reel.'));
  }
  const opts = [];
  if (D.headline.text) opts.push({ text: D.headline.text, current: true });
  (D.headline.suggestions || []).forEach(s => s !== D.headline.text && opts.push({ text: s }));
  const chosen = fb.headline ? fb.headline.text : D.headline.text;
  opts.forEach(o => box.append(el('label', { class: 'opt' + (o.current ? ' current' : '') },
    el('input', { type: 'radio', name: 'headline', value: o.text, checked: chosen === o.text,
      onchange: () => { fb.headline = o.current ? null : { text: o.text }; changed(); } }),
    el('span', {}, o.text, o.current ? el('span', { class: 'small' }, '  (current)') : null,
      !o.current ? el('span', { class: 'small' }, '  (AI suggestion)') : null))));
  box.append(el('label', { class: 'opt' },
    el('input', { type: 'radio', name: 'headline', value: '__auto', checked: !!(fb.headline && fb.headline.choose_for_me),
      onchange: () => { fb.headline = { choose_for_me: true }; changed(); } }),
    el('span', {}, '✨ Choose for me', el('span', { class: 'small' }, '  (Claude picks the strongest)'))));
  const custom = document.querySelector('input[name=headline][value="__custom"]');
  const isCustom = fb.headline && !fb.headline.choose_for_me && !opts.some(o => o.text === fb.headline.text);
  custom.checked = !!isCustom;
  if (isCustom) $('#headCustom').value = fb.headline.text;
  custom.onchange = () => { if ($('#headCustom').value.trim()) { fb.headline = { text: $('#headCustom').value.trim() }; changed(); } else $('#headCustom').focus(); };
  $('#headCustom').oninput = e => { custom.checked = true; const v = e.target.value.trim(); fb.headline = v ? { text: v } : null; changed(false); };
}

// ---- graphics ------------------------------------------------------------
function renderGraphics() {
  const box = $('#gfxList'); box.innerHTML = '';
  // what the creative plan is going for, in one line, so every choice below has context
  if (D.creative && D.creative.used && D.creative.summary)
    box.append(el('p', { class: 'hint' }, '🎬 The plan: ' + D.creative.summary +
      (D.creative.tone ? ` (${D.creative.tone})` : '')));
  const swatchColors = [...new Set([...(D.brand.palette || []), '#FFFFFF', '#111111'])];
  D.graphics.filter(g => g.type !== 'progress_bar').forEach(g => {
    const ch = fb.graphics[g.id] || {};
    const set = patch => { fb.graphics[g.id] = Object.assign({}, fb.graphics[g.id] || {}, patch);
      Object.keys(fb.graphics[g.id]).forEach(k => (fb.graphics[g.id][k] === undefined) && delete fb.graphics[g.id][k]);
      if (!Object.keys(fb.graphics[g.id]).length) delete fb.graphics[g.id]; changed(); };
    const swatches = key => el('div', { class: 'swatches' },
      swatchColors.map(c => el('button', { class: 'sw' + (ch[key] === c ? ' on' : ''), style: `background:${c}`, title: c,
        onclick: () => set({ [key]: ch[key] === c ? undefined : c }) })),
      el('input', { type: 'color', value: ch[key] || '#ffffff', title: 'Any colour', onchange: e => set({ [key]: e.target.value }) }));
    const custom = Object.entries(g.style || {}).filter(([k, v]) => k.startsWith('custom_') && v).map(([k]) => k.replace('custom_', ''));
    const card = el('div', { class: 'card' + (Object.keys(ch).length ? ' changed' : '') },
      el('div', { class: 'gfx-head' },
        el('h3', {}, (g.role === 'headline' ? 'Headline' : LABEL[g.type] || g.type), ' ',
          el('span', { class: 'small' }, g.emoji || '')),
        el('span', { class: 't', onclick: () => seek(g.start - 0.5, Math.min(4, g.end - g.start + 1)) }, '▶ ' + fmt(g.start) + '–' + fmt(g.end))),
      g.why ? el('p', { class: 'small' }, 'Why: ' + g.why) : null,
      ch.remove ? el('p', { class: 'small' }, 'Will be removed.') : null,
      ch.reset_style ? el('p', { class: 'small' }, 'Will go back to your brand style.') : null,
      custom.length && !ch.reset_style ? el('p', { class: 'small' }, 'Has its own ' + custom.join(', ') + ' (overrides your brand settings)') : null);
    if (!ch.remove && (g.variants || []).length > 1) {
      // "Try another design": cycles this graphic only through the style's other designs
      const ids = g.variants.map(v => v.id), cur = ids.indexOf(ch.design || g.variant);
      const nxt = ids[(cur + 1) % ids.length];
      card.append(el('div', { class: 'field' }, el('span', {}, 'Design'),
        el('span', { class: 'small' }, ch.design
          ? `Will change to: ${g.variants[cur].name} (${cur + 1} of ${ids.length})`
          : `${g.variant_name} (${cur + 1} of ${ids.length})`),
        el('button', { class: 'ghost', title: 'Only this graphic changes; the rest of your reel keeps its look',
          onclick: () => set({ design: nxt === g.variant ? undefined : nxt }) }, '✨ Try another design')));
    }
    if (!ch.remove) {
      if (g.type === 'emoji') {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Emoji'),
          el('input', { type: 'text', value: ch.emoji ?? g.emoji, maxlength: 4, onchange: e => set({ emoji: e.target.value === g.emoji ? undefined : e.target.value }) })));
      } else if (g.items) {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Lines'),
          el('textarea', { rows: Math.max(2, g.items.length), onchange: e => {
            const lines = e.target.value.split('\n').map(x => x.trim()).filter(Boolean);
            set({ items: JSON.stringify(lines) === JSON.stringify(g.items.map(i => i.text)) ? undefined : lines }); } },
            (ch.items || g.items.map(i => i.text)).join('\n'))));
      } else if (g.type === 'custom') {
        card.append(el('p', { class: 'small' }, g.label || 'Made for this reel'));
      } else if (g.type === 'calendar') {
        card.append(el('p', { class: 'small' }, `${(g.flips || []).length} page flips, on the words you say`));
      } else if (g.type === 'carousel') {
        card.append(el('p', { class: 'small' }, `${(g.assets || []).length} images from your library, orbiting`));
        Object.entries(CAROUSEL).forEach(([key, opts]) => {
          const planned = g[key] ?? CAROUSEL_DEFAULT[key], cur = ch[key] ?? planned;
          card.append(el('div', { class: 'field' }, el('span', {}, CAROUSEL_LABEL[key]),
            el('select', { onchange: e => set({ [key]: e.target.value === planned ? undefined : e.target.value }) },
              Object.entries(opts).map(([v, l]) => el('option', { value: v, selected: cur === v }, l)))));
        });
      } else if (g.type !== 'arrows') {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Words'),
          el('input', { type: 'text', value: ch.text ?? g.text ?? '', onchange: e => set({ text: e.target.value === g.text ? undefined : e.target.value }) }),
          g.role === 'headline' ? el('span', { class: 'small' }, 'or use the Headline tab') : null));
      }
      if (!['emoji', 'arrows', 'carousel', 'calendar', 'custom'].includes(g.type)) {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Background'), swatches('background'),
          el('button', { class: 'ghost' + (ch.background === 'none' ? ' on' : ''), onclick: () => set({ background: ch.background === 'none' ? undefined : 'none' }) }, 'No background')));
        card.append(el('div', { class: 'field' }, el('span', {}, 'Text colour'), swatches('color')));
        card.append(el('div', { class: 'field' }, el('span', {}, 'Font'),
          el('select', { onchange: e => set({ font: e.target.value || undefined }) },
            el('option', { value: '' }, 'As planned'),
            D.brand.fonts.map(f => el('option', { value: f.key, selected: ch.font === f.key }, f.name)),
            el('option', { value: 'bulky', selected: ch.font === 'bulky' }, 'Bulky (heavy display)'))));
      }
      if (g.items) {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Paper'),
          el('select', { onchange: e => set({ paper: e.target.value || undefined }) },
            el('option', { value: '' }, 'As planned'),
            el('option', { value: 'lined', selected: ch.paper === 'lined' }, 'Lined notebook paper'))));
        card.append(el('label', { class: 'field' }, el('span', {}, 'Tick boxes'),
          el('input', { type: 'checkbox', checked: !!ch.checks, onchange: e => set({ checks: e.target.checked || undefined }) }),
          'Tick each box as it appears, with a click'));
      }
      if (g.type === 'emoji') {
        card.append(el('div', { class: 'field' }, el('span', {}, 'Position'),
          el('select', { onchange: e => set({ place: e.target.value || undefined }) },
            el('option', { value: '' }, 'Automatic (beside my face)'),
            el('option', { value: 'above_head', selected: ch.place === 'above_head' }, 'Above my head'))));
      }
      card.append(el('div', { class: 'field' }, el('span', {}, 'Animation'),
        el('select', { onchange: e => set({ animation: e.target.value || undefined }) },
          el('option', { value: '' }, 'As planned'),
          Object.entries(ANIM).map(([k, v]) => el('option', { value: k, selected: ch.animation === k }, v)))));
      card.append(el('div', { class: 'field' }, el('span', {}, 'Timing'),
        el('button', { class: 'ghost', onclick: () => set({ start: +video.currentTime.toFixed(2) }) }, 'Start now'),
        el('button', { class: 'ghost', onclick: () => set({ end: +video.currentTime.toFixed(2) }) }, 'End now'),
        (ch.start !== undefined || ch.end !== undefined) ? el('span', { class: 'small' },
          `${fmt(ch.start ?? g.start)}–${fmt(ch.end ?? g.end)}`) : null));
    }
    card.append(el('div', { class: 'row' },
      el('button', { class: 'ghost', title: 'Undo colour / font / animation choices made for this graphic',
        onclick: () => { fb.graphics[g.id] = { reset_style: true }; changed(); } }, '↺ Reset to my brand style'),
      el('button', { class: 'ghost', onclick: () => set({ remove: ch.remove ? undefined : true }) }, ch.remove ? 'Keep it' : 'Remove this graphic'),
      Object.keys(ch).length ? el('button', { class: 'ghost', onclick: () => { delete fb.graphics[g.id]; changed(); } }, 'Undo changes') : null));
    box.append(card);
  });
  if (!box.querySelector('.card')) box.append(el('p', { class: 'hint' }, 'No graphics in this reel yet. Use the Add tab.'));
}

// ---- add -----------------------------------------------------------------
function renderAdd() {
  const sel = $('#addType');
  if (!sel.children.length) Object.entries(D.addable).forEach(([k, v]) => sel.append(el('option', { value: k }, v)));
  const ul = $('#addList'); ul.innerHTML = '';
  const items = [
    ...fb.add.graphics.map(g => ({ t: g.t, text: `${D.addable[g.type]}${g.name ? ': ' + g.name : g.text ? ': ' + g.text : g.emoji ? ': ' + g.emoji : ''}`, list: fb.add.graphics, it: g })),
    ...fb.add.zooms.map(z => ({ t: z.t, text: (z.type === 'push' ? 'Slow push' : 'Snap zoom') + ` (${z.duration}s)`, list: fb.add.zooms, it: z })),
    ...fb.add.sfx.map(s => ({ t: s.t, text: 'Sound: ' + (s.name || s.kind), list: fb.add.sfx, it: s }))].sort((a, b) => a.t - b.t);
  if (!items.length) ul.append(el('li', { class: 'dim' }, 'Nothing added yet.'));
  items.forEach(x => ul.append(el('li', {},
    el('span', { class: 't', onclick: () => seek(x.t - 1, 2.5) }, fmt(x.t)), el('span', { class: 'what' }, x.text),
    el('button', { class: 'ghost', onclick: () => { x.list.splice(x.list.indexOf(x.it), 1); changed(); } }, 'Delete'))));
}
$('#addGfx').onclick = () => {
  const type = $('#addType').value, text = $('#addText').value.trim();
  if (type === 'image') {
    const id = $('#addImage').value;
    if (!id) { toast('Upload an image in the 📁 Library tab first.'); return; }
    const a = LIB.items.find(x => x.id === id);
    fb.add.graphics.push({ type: 'image', asset: id, name: a ? a.name : id, t: +video.currentTime.toFixed(2), duration: +$('#addDur').value || 2.5 });
    changed(); return;
  }
  if (type !== 'arrows' && type !== 'profile_card' && !text) { toast('Type the words (or an emoji) for the graphic.'); return; }
  fb.add.graphics.push({ type, t: +video.currentTime.toFixed(2), duration: +$('#addDur').value || 2.5,
    text: type === 'emoji' ? undefined : text, emoji: type === 'emoji' ? text : undefined });
  $('#addText').value = ''; changed();
};
$('#addZoom').onclick = () => { fb.add.zooms.push({ type: $('#zoomType').value, t: +video.currentTime.toFixed(2),
  duration: +$('#zoomDur').value || 2, scale: $('#zoomType').value === 'push' ? 1.1 : 1.18 }); changed(); };
$('#addSfx').onclick = () => { fb.add.sfx.push({ kind: $('#sfxKind').value, t: +video.currentTime.toFixed(2) }); changed(); };
$('#previewSfx').onclick = () => new Audio('/sfx/' + $('#sfxKind').value).play();

// ---- changes, autosave, save ----------------------------------------------
function count() {
  return fb.notes.length + fb.cuts.keep.length + fb.cuts.remove.length + fb.cuts.remove_words.length +
    fb.cuts.cut_pauses.length + Object.keys(fb.captions).length + (fb.headline ? 1 : 0) +
    Object.keys(fb.graphics).length + fb.add.graphics.length + fb.add.zooms.length + fb.add.sfx.length;
}
let draftTimer = null;
function changed(rerender = true) {
  if (rerender) renderAll(); else updateBadges();
  const n = count();
  $('#changeCount').textContent = n ? `${n} change${n > 1 ? 's' : ''} ready` : 'No changes yet';
  $('#saveBtn').disabled = !n;
  $('#draftState').textContent = 'Saving draft…';
  clearTimeout(draftTimer);
  draftTimer = setTimeout(async () => {
    await fetch('/api/draft', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fb) });
    $('#draftState').textContent = 'Draft saved';
  }, 700);
}
$('#saveBtn').onclick = async () => {
  // which version these timestamps belong to (so they land on the right words)
  const body = Object.assign({}, fb, { version: (watching && watching.n) || D.current_version || null });
  const r = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const res = await r.json();
  if (!res.ok) { toast('Could not save: ' + (res.error || r.status)); return; }
  toast('Saved! Tell Claude “apply my review”. The new version will appear right here when it’s ready.', 8000);
  poll();
  fb.notes = []; fb.cuts = { keep: [], remove: [], remove_words: [], cut_pauses: [] }; fb.captions = {};
  fb.headline = null; fb.graphics = {}; fb.add = { graphics: [], zooms: [], sfx: [] };
  clearTimeout(draftTimer);
  renderAll(); $('#changeCount').textContent = 'Feedback saved'; $('#saveBtn').disabled = true; $('#draftState').textContent = '';
};
function toast(msg, ms = 4000) {
  const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), ms);
}
function renderAll() {
  renderTimeline(); renderNotes(); renderCuts(); renderCaptions(); renderHeadline(); renderGraphics(); renderAdd();
  updateBadges();
}
function updateBadges() {
  const badges = { notes: fb.notes.length,
    cuts: fb.cuts.keep.length + fb.cuts.remove.length + fb.cuts.remove_words.length + fb.cuts.cut_pauses.length,
    captions: Object.keys(fb.captions).length, headline: fb.headline ? 1 : 0, graphics: Object.keys(fb.graphics).length,
    add: fb.add.graphics.length + fb.add.zooms.length + fb.add.sfx.length };
  document.querySelectorAll('#tabs button').forEach(b => {
    b.querySelector('.badge')?.remove();
    if (badges[b.dataset.tab]) b.append(el('span', { class: 'badge' }, badges[b.dataset.tab]));
  });
  const n = count();
  if (n) { $('#changeCount').textContent = `${n} change${n > 1 ? 's' : ''} ready`; $('#saveBtn').disabled = false; }
}

// ---- asset library ----------------------------------------------------------
let LIB = { items: [], sound_events: {}, image_categories: [], sound_categories: [] };
const KIND_ICON = { font: 'Aa', sound: '🔊', image: '🖼' };
async function loadLibrary() {
  LIB = await (await fetch('/api/library')).json();
  // fonts become usable on this page for previews
  for (const f of LIB.items.filter(x => x.kind === 'font' && !x.archived)) {
    try { const ff = new FontFace('lib-' + f.id, `url(/library/file/${f.id})`); await ff.load(); document.fonts.add(ff); } catch (e) {}
  }
  renderLibrary(); renderUploadCategories(); renderAddImages();
}
function renderUploadCategories() {
  const f = $('#upFile').files[0], sel = $('#upCategory');
  const ext = f ? f.name.split('.').pop().toLowerCase() : '';
  const cats = ['mp3', 'wav'].includes(ext) ? LIB.sound_categories : ['png', 'jpg', 'jpeg'].includes(ext) ? LIB.image_categories : [];
  sel.innerHTML = ''; sel.classList.toggle('hidden', !cats.length);
  sel.append(el('option', { value: '' }, 'Category: automatic'));
  cats.forEach(c => sel.append(el('option', { value: c }, c)));
}
$('#upFile').onchange = renderUploadCategories;
$('#upBtn').onclick = async () => {
  const f = $('#upFile').files[0];
  if (!f) { toast('Choose a file first.'); return; }
  const q = new URLSearchParams({ filename: f.name, name: $('#upName').value.trim() || f.name.replace(/\.[^.]+$/, ''), category: $('#upCategory').value || '' });
  $('#upBtn').disabled = true; $('#upBtn').textContent = 'Uploading…';
  try {
    const r = await (await fetch('/api/library/upload?' + q, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(f.name) }, body: f })).json();
    if (!r.ok) { toast('Not added: ' + r.error, 7000); return; }
    toast(`Added “${r.asset.name}” to your library.`);
    $('#upFile').value = ''; $('#upName').value = ''; await loadLibrary();
  } finally { $('#upBtn').disabled = false; $('#upBtn').textContent = 'Add to my library'; }
};
$('#libFilter').onchange = renderLibrary; $('#libArchived').onchange = renderLibrary;
async function libUpdate(id, patch) {
  const r = await (await fetch('/api/library/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ id }, patch)) })).json();
  if (!r.ok) toast('Not saved: ' + r.error); else await loadLibrary();
}
function renderLibrary() {
  const box = $('#libList'); box.innerHTML = '';
  const kind = $('#libFilter').value, arch = $('#libArchived').checked;
  const list = LIB.items.filter(x => (!kind || x.kind === kind) && (arch || !x.archived))
    .sort((a, b) => a.kind.localeCompare(b.kind) || (a.category || '').localeCompare(b.category || '') || a.name.localeCompare(b.name));
  if (!list.length) box.append(el('p', { class: 'hint' }, 'Nothing here yet. Upload a font, sound or image above.'));
  list.forEach(x => {
    const thumb = x.kind === 'image' ? el('img', { class: 'thumb', src: `/library/file/${x.id}` })
      : x.kind === 'font' ? el('div', { class: 'thumb fontsample', style: `font-family:'lib-${x.id}'` }, 'Aa')
      : el('div', { class: 'thumb' }, '🔊');
    const cats = x.kind === 'sound' ? LIB.sound_categories : x.kind === 'image' ? LIB.image_categories : null;
    const meta = el('div', { class: 'meta' },
      el('input', { type: 'text', value: x.name, onchange: e => libUpdate(x.id, { name: e.target.value }) }),
      el('span', { class: 'small' }, x.kind === 'font' ? `Font · ${x.family}` : x.kind === 'sound' ? `Sound · ${x.duration}s` : `Image · ${x.width}×${x.height}${x.transparent ? ' · transparent' : ''}`),
      cats ? el('select', { onchange: e => libUpdate(x.id, { category: e.target.value }) },
        cats.map(c => el('option', { value: c, selected: x.category === c }, c))) : null,
      x.kind === 'font' ? el('span', { class: 'fontsample', style: `font-family:'lib-${x.id}'` }, 'Your content needs a purpose') : null);
    const acts = el('div', { class: 'acts' },
      x.kind === 'sound' ? el('button', { class: 'ghost', onclick: () => new Audio(`/library/file/${x.id}`).play() }, '▶ Hear it') : null,
      x.kind === 'sound' ? el('button', { class: 'primary', onclick: () => { fb.add.sfx.push({ kind: 'library:' + x.id, name: x.name, t: +video.currentTime.toFixed(2) }); changed(); toast(`“${x.name}” will play at ${fmt(video.currentTime)}.`); } }, 'Use at ' + fmt(video.currentTime)) : null,
      x.kind === 'image' ? el('button', { class: 'primary', onclick: () => { fb.add.graphics.push({ type: 'image', asset: x.id, name: x.name, t: +video.currentTime.toFixed(2), duration: 2.5 }); changed(); toast(`“${x.name}” will show at ${fmt(video.currentTime)}.`); } }, 'Use at ' + fmt(video.currentTime)) : null,
      x.kind === 'font' ? el('button', { class: 'primary', onclick: openBrand }, 'Use in Brand settings') : null,
      el('button', { class: 'ghost', onclick: () => libUpdate(x.id, { archived: !x.archived }) }, x.archived ? 'Restore' : 'Archive'));
    box.append(el('div', { class: 'lib' + (x.archived ? ' archived' : '') }, thumb, meta, acts));
  });
}
function renderAddImages() {
  const sel = $('#addImage'); sel.innerHTML = '';
  LIB.items.filter(x => x.kind === 'image' && !x.archived).forEach(x => sel.append(el('option', { value: x.id }, x.name)));
}
$('#addType').addEventListener('change', () => $('#addImage').classList.toggle('hidden', $('#addType').value !== 'image'));
video.addEventListener('pause', () => { if (!$('#tab-library').classList.contains('hidden')) renderLibrary(); });

// ---- brand settings ---------------------------------------------------------
let BS = null, bchanges = {};
const PRESET_FONTS = ['Playfair Display', 'Lato', 'Montserrat', 'Inter', 'Bebas Neue', 'Poppins'];
async function openBrand() {
  BS = await (await fetch('/api/brand')).json();
  await loadLibrary();
  bchanges = {};
  renderBrand();
  $('#brandModal').classList.remove('hidden');
}
$('#brandBtn').onclick = openBrand;
$('#brandClose').onclick = () => $('#brandModal').classList.add('hidden');
function cur(key) { return key in bchanges ? bchanges[key] : BS.effective[key]; }
function setB(key, value) {
  if (JSON.stringify(value) === JSON.stringify(BS.effective[key])) delete bchanges[key]; else bchanges[key] = value;
  $('#brandSave').disabled = !Object.keys(bchanges).length;
  $('#brandChanged').textContent = Object.keys(bchanges).length ? `${Object.keys(bchanges).length} change(s)` : '';
  renderBrand();
}
function field(label, key, control) {
  return el('div', { class: 'bfield' + (key in bchanges ? ' changed' : '') },
    el('span', {}, label, key in (BS.reel || {}) ? el('span', { class: 'reelonly' }, 'this reel') : null), control);
}
const when = iso => iso ? new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
const diffList = d => el('ul', { class: 'small' }, d.slice(0, 6).map(x => el('li', {}, `${x.label}: ${x.before} → ${x.after}`)),
  d.length > 6 ? el('li', {}, `and ${d.length - 6} more`) : null);
function renderSnapshotNote() {
  const s = BS.snapshot || {}, d = s.differs || [];
  if (!s.pinned_at) return null;
  return el('div', { class: 'bsec' }, el('h3', {}, 'This reel’s brand'),
    el('p', { class: 'small' }, `This reel keeps the brand it was made with (${when(s.pinned_at)}), so changing your saved defaults never changes it. ` +
      (d.length ? `${d.length} setting(s) differ from your current saved defaults:` : 'It matches your current saved defaults.')),
    d.length ? diffList(d) : null,
    d.length ? el('button', { class: 'ghost', onclick: async () => {
      if (!(await ask('Use your current saved defaults here?', `${d.length} setting(s) on this reel will change to match your saved defaults. Changes you made for this reel only stay.`, 'Use them'))) return;
      const r = await (await fetch('/api/brand/use-defaults', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json();
      if (!r.ok) { toast('Not changed: ' + r.error, 7000); return; }
      $('#brandModal').classList.add('hidden');
      toast('Done. Tell Claude “apply my review” to see it in a new version.', 8000); poll();
    } }, 'Use my current saved defaults for this reel') : null);
}
function outlineField() {
  const o = Object.assign({}, BS.outline_default, cur('caption_outline') || {});
  const set = patch => setB('caption_outline', Object.assign({}, o, patch));
  const hex = o.color, a = o.opacity;
  const rgba = `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;
  const cc = BS.caption_colors || {};
  const stroke = o.enabled ? `${BS.outline_widths[o.thickness]}em ${rgba}` : '0';
  const sample = el('span', { class: 'outline-sample', style: `-webkit-text-stroke:${stroke};paint-order:stroke fill;color:${cc.caption_text || '#fff'}` },
    'your ', el('span', { style: `color:${cc.caption_keyword || cc.accent || '#fff'};-webkit-text-stroke:${stroke};paint-order:stroke fill` }, 'captions'));
  return field('Outline', 'caption_outline', el('div', { class: 'row' },
    el('label', { class: 'small' }, el('input', { type: 'checkbox', checked: o.enabled, onchange: e => set({ enabled: e.target.checked }) }), ' On'),
    o.enabled ? el('input', { type: 'color', value: o.color, title: 'Outline colour', onchange: e => set({ color: e.target.value.toUpperCase() }) }) : null,
    o.enabled ? el('select', { onchange: e => set({ thickness: e.target.value }) },
      ['thin', 'medium', 'thick'].map(v => el('option', { value: v, selected: o.thickness === v }, v[0].toUpperCase() + v.slice(1)))) : null,
    o.enabled ? el('label', { class: 'small' }, 'opacity ', el('input', { type: 'range', min: 10, max: 100, value: Math.round(o.opacity * 100),
      onchange: e => set({ opacity: +e.target.value / 100 }) }), ` ${Math.round(o.opacity * 100)}%`) : null,
    sample));
}
function referenceSection() {
  const rp = Object.assign({ use: [], avoid: [], notes: '' }, cur('reference_prefs') || {});
  const set = patch => setB('reference_prefs', Object.assign({}, rp, patch));
  const label = { captions: 'Captions', typography: 'Lettering', animation: 'Transitions / motion', graphics: 'Graphics',
                  zooms: 'Zooms', pacing: 'Pacing', colour: 'Colour mood' };
  return el('div', { class: 'bsec' }, el('h3', {}, 'Your reference reel'),
    el('p', { class: 'small' }, 'Inspiration only: Claude learns the feel of the parts you like. Their words, logos and artwork are never reused, and your own settings always come first.'),
    el('ul', { class: 'small' }, Object.entries(BS.reference.seen).map(([k, s]) => el('li', {}, `${label[k] || k}: ${s}`))),
    field('What I like', 'reference_prefs', el('div', { class: 'swatches' }, BS.reference.categories.map(c => {
      const state = rp.use.includes(c) ? 'use' : rp.avoid.includes(c) ? 'avoid' : '';
      return el('select', { title: label[c] || c, onchange: e => set({
          use: e.target.value === 'use' ? [...rp.use.filter(x => x !== c), c] : rp.use.filter(x => x !== c),
          avoid: e.target.value === 'avoid' ? [...rp.avoid.filter(x => x !== c), c] : rp.avoid.filter(x => x !== c) }) },
        el('option', { value: '', selected: state === '' }, `${label[c] || c}: no preference`),
        el('option', { value: 'use', selected: state === 'use' }, `${label[c] || c}: I like it`),
        el('option', { value: 'avoid', selected: state === 'avoid' }, `${label[c] || c}: not for me`));
    }))),
    field('In your words', 'reference_prefs', el('textarea', { rows: 2, placeholder: 'e.g. I love the captions and transitions, but not the graphics',
      onchange: e => set({ notes: e.target.value }) }, rp.notes || '')));
}
function renderHistory() {
  const H = BS.history || [];
  return el('div', { class: 'bsec' }, el('h3', {}, 'Earlier saved defaults'),
    H.length ? el('p', { class: 'small' }, 'Every time your saved defaults change, the earlier set is kept here. Restoring one changes your saved defaults for future reels (the set you have now is kept too, so you can switch back). Reels you already made keep their own brand.')
      : el('p', { class: 'small' }, 'No earlier versions yet. Each time you change your saved defaults, the earlier set is kept here.'),
    H.slice(0, 12).map(e => el('div', { class: 'card' },
      el('div', { class: 'gfx-head' }, el('b', {}, `Until ${when(e.saved_at)}`),
        e.differs_from_now.length ? el('button', { class: 'ghost', onclick: async () => {
          if (!(await ask('Restore these saved defaults?', `Future reels will use your saved defaults from before ${when(e.saved_at)}. Your current set is kept in this list.`, 'Restore'))) return;
          const r = await (await fetch('/api/brand/history/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: e.id }) })).json();
          if (!r.ok) { toast('Not restored: ' + r.error, 7000); return; }
          toast('Earlier saved defaults restored for future reels.', 6000); openBrand();
        } }, 'Restore') : el('span', { class: 'tag' }, 'same as now')),
      e.differs_from_now.length ? el('div', {}, el('span', { class: 'small' }, 'Compared with now:'), diffList(e.differs_from_now)) : null)));
}
// ---- your style (Stage 4) ----------------------------------------------------
const HEX = /^#?[0-9a-fA-F]{6}$/;
const hexBox = (value, onset, title) => el('input', { type: 'text', class: 'hex', value: (value || '').toUpperCase(),
  placeholder: '#FF3E8E', title, maxlength: 7, onchange: e => {
    const v = e.target.value.trim(); if (!HEX.test(v)) { toast('Use a HEX code like #FF3E8E'); e.target.value = value || ''; return; }
    onset('#' + v.replace('#', '').toUpperCase()); } });
function curStyle() {
  const s = Object.assign({ pack: BS.current_style.pack, mix: [], direction: BS.current_style.direction || '',
                            decorations: {}, keep: BS.current_style.keep || [] }, cur('style') || {});
  s.mix = s.mix || []; s.decorations = s.decorations || {}; s.keep = s.keep || [];
  return s;
}
const setStyle = patch => setB('style', Object.assign(curStyle(), patch));
function styleSection() {
  const st = curStyle(), cards = BS.styles.filter(s => !s.legacy || s.id === st.pack);
  const pick = el('div', { class: 'stylecards' }, cards.map(s => el('button', {
      class: 'stylecard' + (st.pack === s.id ? ' on' : ''), type: 'button',
      onclick: () => setStyle({ pack: s.id, decorations: {} }) },
    el('b', {}, s.legacy ? `${s.name} (your current look)` : s.name), el('span', {}, s.description))));
  const pack = BS.styles.find(s => s.id === st.pack) || {};
  const deco = Object.assign({}, pack.decorations || {}, st.decorations);
  const rules = cur('creative_rules') || BS.current_style.rules || { flags: [], notes: '' };
  const blocked = new Set(rules.flags || []);
  const keepBox = (k, label) => el('label', { class: 'small' }, el('input', { type: 'checkbox', checked: st.keep.includes(k),
    onchange: e => setStyle({ keep: e.target.checked ? [...st.keep, k] : st.keep.filter(x => x !== k) }) }), ' ' + label);
  const mixRow = el('div', { class: 'row' }, el('span', { class: 'small' }, 'Borrow'),
    el('select', { id: 'mixAspect' }, BS.aspects.map(a => el('option', { value: a }, { captions: 'captions', motion: 'motion',
      sound: 'sound effects', components: 'graphics' }[a]))),
    el('span', { class: 'small' }, 'from'),
    el('select', { id: 'mixPack' }, BS.styles.filter(s => !s.legacy && s.id !== st.pack).map(s => el('option', { value: s.id }, s.name))),
    el('button', { class: 'ghost', type: 'button', onclick: () => {
      const asp = $('#mixAspect').value, pk = $('#mixPack').value;
      setStyle({ mix: [...st.mix.filter(m => !m.aspects.includes(asp)), { pack: pk, aspects: [asp] }] }); } }, 'Add'));
  return el('div', { class: 'bsec' }, el('h3', {}, 'Your style'),
    el('p', { class: 'small' }, 'A starting point, not a template. Your colours, fonts and own words below always come first.'),
    pick,
    st.pack !== 'classic' ? el('div', { class: 'row' }, el('span', { class: 'small' }, 'Keep my own:'),
      keepBox('caption_style', 'caption style'), keepBox('caption_animation', 'caption animation'),
      keepBox('caption_emphasis', 'key-word look'), keepBox('zooms', 'zooms')) : null,
    st.pack !== 'classic' ? mixRow : null,
    st.mix.length ? el('div', { class: 'small' }, 'Borrowing: ', st.mix.map(m => el('span', { class: 'tag' },
      `${m.aspects.join(', ')} from ${m.pack} `, el('a', { href: '#', onclick: ev => { ev.preventDefault();
        setStyle({ mix: st.mix.filter(x => x !== m) }); } }, '×')))) : null,
    field('In your own words', 'style', el('textarea', { rows: 3, id: 'styleWords',
      placeholder: 'e.g. hot pink headlines, clean captions, no outlines or glows',
      onchange: e => setStyle({ direction: e.target.value }) }, st.direction || '')),
    el('p', { class: 'small' }, 'Claude reads this for every reel and turns it into exact settings, which you can check below.'),
    field('Always / never', 'creative_rules', el('div', { class: 'swatches' }, Object.entries(BS.rules).map(([k, label]) =>
      el('label', { class: 'small' }, el('input', { type: 'checkbox', checked: blocked.has(k), onchange: e => {
        const fl = new Set(rules.flags || []); e.target.checked ? fl.add(k) : fl.delete(k);
        setB('creative_rules', { flags: [...fl], notes: rules.notes || '' }); } }), ' ' + label)))),
    field('Decorations', 'style', el('div', { class: 'swatches' }, Object.entries(BS.decoration_labels).map(([d, label]) => {
      const off = (d === 'caption_outline' && blocked.has('no_outlines')) || (d === 'caption_glow' && blocked.has('no_glow')) ||
                  (['caption_shadow', 'graphic_shadow', 'emoji_shadow'].includes(d) && blocked.has('no_shadows')) ||
                  (['graphic_box', 'graphic_border'].includes(d) && blocked.has('no_boxes'));
      return el('label', { class: 'small' + (off ? ' dim' : '') }, el('input', { type: 'checkbox', checked: !!deco[d] && !off, disabled: off,
        onchange: e => setStyle({ decorations: Object.assign({}, st.decorations, { [d]: e.target.checked }) }) }), ' ' + label);
    }))),
    el('p', { class: 'small' }, 'Nothing decorative is added unless it is ticked here. Your "Always / never" choices win.'));
}
// Fonts included with the editor (free to use in your videos): a preview of each, and one tap
// to use it for headlines, captions or graphics. Nothing to download.
function fontLibrary(fontsAns) {
  const inc = BS.included_fonts || { categories: [], fonts: [] };
  if (!inc.fonts.length) return null;
  if (!document.getElementById('incFontFaces')) {
    const st = document.createElement('style'); st.id = 'incFontFaces';
    st.textContent = inc.fonts.map(x => `@font-face { font-family: "inc-${x.family}"; src: url("${x.url}"); font-weight: 100 900; }`).join('\n');
    document.head.append(st);
  }
  const using = BS.fonts_in_use || {};
  const assign = (role, fam) => {
    if (role === 'graphics') { setB('graphics_font', 'font:' + fam); }
    else { const ff = Object.assign({}, cur('font_files') || {}); ff[role] = null; setB('font_files', ff);
           setB('fonts', Object.assign({}, cur('fonts') || fontsAns, { [role]: fam })); }
    toast(`${fam} for your ${role === 'body' ? 'captions' : role === 'headline' ? 'headlines' : 'graphics'}.`);
  };
  return el('details', { class: 'fontlib' }, el('summary', {}, 'Font library (24 fonts included, ready to use)'),
    inc.categories.map(cat => el('div', {}, el('h4', {}, cat), el('div', { class: 'fontcards' },
      inc.fonts.filter(x => x.category === cat).map(x => el('div', { class: 'fontcard' },
        el('div', { class: 'fsample', style: `font-family:"inc-${x.family}",sans-serif` }, 'Your next reel'),
        el('div', { class: 'small' }, x.family,
          [['headline', 'H'], ['body', 'C'], ['graphics', 'G']].filter(([r]) => using[r] === x.family)
            .map(([, t]) => el('span', { class: 'tag' }, t))),
        el('div', { class: 'row' },
          el('button', { class: 'ghost', onclick: () => assign('headline', x.family) }, 'Headlines'),
          el('button', { class: 'ghost', onclick: () => assign('body', x.family) }, 'Captions'),
          el('button', { class: 'ghost', onclick: () => assign('graphics', x.family) }, 'Graphics'))))))),
    el('p', { class: 'small' }, 'H / C / G = in use for headlines, captions, graphics. Your own uploaded fonts stay available in the lists above.'));
}
function renderBrand() {
  const f = $('#brandForm'); f.innerHTML = '';
  f.append(styleSection());
  const def = document.querySelector('input[name=scope][value=default]');
  def.disabled = !!BS.neutral;
  if (BS.neutral) {
    document.querySelector('input[name=scope][value=reel]').checked = true;
    f.append(el('div', { class: 'bsec' }, el('h3', {}, 'No brand yet'),
      el('p', { class: 'small' }, 'This reel uses the clean neutral look. Say “Start my brand onboarding” to Claude to set up your own brand; after that you can save defaults here. Until then, changes apply to this reel only.')));
  }
  const note = renderSnapshotNote(); if (note) f.append(note);
  const Q = Object.fromEntries(BS.questions.map(q => [q.id, q]));
  const choice = (key, label) => Q[key] && cur(key) !== undefined ? field(label, key,
    el('select', { onchange: e => setB(key, e.target.value) }, Q[key].options.map(([v, l]) => el('option', { value: v, selected: cur(key) === v }, l)))) : null;
  const libFonts = LIB.items.filter(x => x.kind === 'font' && !x.archived);
  const fontsAns = cur('fonts') || {}, files = Object.assign({}, cur('font_files') || {});
  const fontSelect = role => {
    const val = files[role] ? 'lib:' + files[role] : (role === 'graphics' ? (cur('graphics_font') || 'headline') : fontsAns[role]);
    const inc = (BS.included_fonts || {}).fonts || [];
    const incNames = new Set(inc.map(x => x.family));
    const opts = role === 'graphics'
      ? [['headline', 'Same as headline'], ['body', 'Same as text']]
      : [...new Set([fontsAns[role], ...PRESET_FONTS])].filter(n => n && !incNames.has(n)).map(n => [n, n]);
    const incGroups = ((BS.included_fonts || {}).categories || []).map(cat => el('optgroup', { label: 'Included · ' + cat },
      inc.filter(x => x.category === cat).map(x => {
        const v = role === 'graphics' ? 'font:' + x.family : x.family;
        return el('option', { value: v, selected: val === v }, x.family); })));
    return el('select', { onchange: e => {
        const v = e.target.value, ff = Object.assign({}, cur('font_files') || {});
        if (v.startsWith('lib:')) { ff[role] = v.slice(4); setB('font_files', ff); if (role === 'graphics') setB('graphics_font', 'library'); }
        else { ff[role] = null; setB('font_files', ff);
               if (role === 'graphics') setB('graphics_font', v); else setB('fonts', Object.assign({}, fontsAns, { [role]: v })); }
      } },
      opts.map(([v, l]) => el('option', { value: v, selected: val === v }, l)),
      ...incGroups,
      libFonts.length ? el('optgroup', { label: 'My uploaded fonts' }, libFonts.map(x => el('option', { value: 'lib:' + x.id, selected: val === 'lib:' + x.id }, `${x.name} (${x.family})`))) : null);
  };
  const colors = (cur('colors') || []).slice();
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Colours'),
    field('Brand colours', 'colors', el('div', { class: 'swatches' },
      colors.map((c, i) => el('input', { type: 'color', value: c, title: i === 0 ? 'Main colour' : i === 1 ? 'Highlight colour' : '',
        onchange: e => { const n = colors.slice(); n[i] = e.target.value.toUpperCase(); setB('colors', n); } })),
      colors.map((c, i) => hexBox(c, v => { const n = colors.slice(); n[i] = v; setB('colors', n); }, i === 0 ? 'Main colour' : 'Colour ' + (i + 1))),
      colors.length < 4 ? el('button', { class: 'ghost', onclick: () => setB('colors', [...colors, '#FFFFFF']) }, '+ colour') : null,
      colors.length > 1 ? el('button', { class: 'ghost', onclick: () => setB('colors', colors.slice(0, -1)) }, '− last') : null,
      el('span', { class: 'small' }, '1st = main · 2nd = highlight'))),
    ...Object.entries(BS.color_roles).map(([role, label]) => {
      const roles = Object.assign({}, cur('color_roles') || {}), v = roles[role];
      const set = val => { const r = Object.assign({}, cur('color_roles') || {}); if (val) r[role] = val; else delete r[role]; setB('color_roles', r); };
      return field(label + ' colour', 'color_roles', el('div', { class: 'row' },
        el('label', { class: 'small' }, el('input', { type: 'checkbox', checked: !!v, onchange: e => set(e.target.checked ? (colors[0] || '#FF3E8E') : null) }), ' exact colour'),
        v ? el('input', { type: 'color', value: v, onchange: e => set(e.target.value.toUpperCase()) }) : null,
        v ? hexBox(v, set, label) : el('span', { class: 'small dim' }, 'from my palette')));
    })));
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Fonts'),
    field('Headline font', 'fonts', fontSelect('headline')),
    field('Caption / text font', 'font_files', fontSelect('body')),
    field('Graphics font', 'graphics_font', fontSelect('graphics')),
    fontLibrary(fontsAns),
    el('div', { class: 'row' }, el('button', { class: 'ghost', type: 'button', onclick: () => {
        $('#brandModal').classList.add('hidden'); document.querySelector('.tabs button[data-tab=library]').click();
        toast('Choose your TTF/OTF font file here, then come back to Brand settings and pick it.', 7000); } }, '＋ Upload a font file (TTF/OTF)'),
      el('span', { class: 'small' }, 'Uploaded fonts appear in these lists under “My uploaded fonts”.'))));
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Captions'),
    choice('caption_style', 'Style'), choice('caption_position', 'Position'), choice('caption_size', 'Size'),
    choice('caption_animation', 'Animation'), choice('caption_emphasis', 'Key words'), choice('caption_case', 'Lettering'),
    choice('caption_color', 'Colour'), outlineField()));
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Headline'), choice('headline', 'Headline')));
  const elems = cur('graphics_elements') || [];
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Graphics'), choice('graphics_density', 'How much'),
    field('Elements', 'graphics_elements', el('div', { class: 'swatches' }, Q.graphics_elements.options.map(([v, l]) =>
      el('label', { class: 'small' }, el('input', { type: 'checkbox', checked: elems.includes(v),
        onchange: e => setB('graphics_elements', e.target.checked ? [...elems, v] : elems.filter(x => x !== v)) }), ' ' + l)))),
    choice('sticky_font', 'Sticky-note font'), choice('aesthetic', 'Look')));
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Pace and zooms'), choice('pacing', 'Pacing'), choice('zoom_style', 'Zooms'), choice('zoom_frequency', 'How often')));
  const sounds = LIB.items.filter(x => x.kind === 'sound' && !x.archived);
  const smap = Object.assign({}, cur('sound_map') || {});
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Sound'), choice('sfx', 'Sound effects'), choice('music', 'Music'),
    ...Object.entries(BS.sound_events).map(([ev, label]) => field(label, 'sound_map', el('div', { class: 'row' },
      el('select', { onchange: e => { const m = Object.assign({}, cur('sound_map') || {}); m[ev] = e.target.value || null; setB('sound_map', m); } },
        el('option', { value: '' }, 'Editor default'), sounds.map(x => el('option', { value: x.id, selected: smap[ev] === x.id }, `${x.name} (${x.category})`))),
      smap[ev] ? el('button', { class: 'ghost', onclick: () => new Audio('/library/file/' + smap[ev]).play() }, '▶') : null))),
    el('p', { class: 'small' }, 'When you choose your own sound for a moment, exactly that sound is used. The editor never swaps in a default.')));
  const imgs = LIB.items.filter(x => x.kind === 'image' && !x.archived);
  const logo = cur('logo') || null;
  const setLogo = patch => setB('logo', patch === null ? null : Object.assign({ position: 'top_right', opacity: 0.9, size: 180 }, logo || {}, patch));
  f.append(el('div', { class: 'bsec' }, el('h3', {}, 'Logo'),
    field('Logo on every reel', 'logo', el('div', { class: 'row' },
      el('select', { onchange: e => setLogo(e.target.value ? { id: e.target.value } : null) },
        el('option', { value: '' }, 'No logo'), imgs.map(x => el('option', { value: x.id, selected: logo && logo.id === x.id }, `${x.name} (${x.category})`))),
      logo ? el('select', { onchange: e => setLogo({ position: e.target.value }) }, BS.logo_positions.map(p => el('option', { value: p, selected: logo.position === p }, p.replace('_', ' ')))) : null,
      logo ? el('label', { class: 'small' }, 'size ', el('input', { type: 'range', min: 80, max: 400, value: logo.size || 180, onchange: e => setLogo({ size: +e.target.value }) })) : null,
      logo ? el('label', { class: 'small' }, 'opacity ', el('input', { type: 'range', min: 20, max: 100, value: Math.round((logo.opacity || 0.9) * 100), onchange: e => setLogo({ opacity: +e.target.value / 100 }) })) : null))));
  if (BS.reference) f.append(referenceSection());
  f.append(renderHistory());
}
$('#brandSave').onclick = async () => {
  const scope = document.querySelector('input[name=scope]:checked').value;
  const what = scope === 'default' ? 'your saved defaults (future reels and this one; reels you already made keep their look)' : 'this reel only';
  if (!(await ask('Save brand settings?', `${Object.keys(bchanges).length} change(s) will apply to ${what}.`, 'Save'))) return;
  const r = await (await fetch('/api/brand', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes: bchanges, scope }) })).json();
  if (!r.ok) { toast('Not saved: ' + r.error, 7000); return; }
  $('#brandModal').classList.add('hidden');
  toast('Settings saved. Tell Claude “apply my review” to see them in a new version.', 8000);
  poll();
};
loadLibrary();
load().then(poll);
