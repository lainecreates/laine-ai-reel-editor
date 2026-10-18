"""Build the overlay page: every caption and graphic as HTML/CSS on a
transparent 1080x1920 canvas, with a deterministic timeline (window.__seek).

tools/render_overlay.mjs steps through it frame by frame in headless Chrome
and saves transparent PNGs. This replaces ffmpeg's drawtext/subtitles, which
this ffmpeg doesn't have, and gives real fonts, emoji, shadows and animation.
"""

import json
from pathlib import Path

from . import config

SERIF = '"Didot", "Bodoni 72", "Georgia", serif'
SANS = '"Avenir Next", "Helvetica Neue", "Arial", sans-serif'
CONDENSED = '"Avenir Next Condensed", "Impact", sans-serif'
HAND = '"Noteworthy", "Marker Felt", "Bradley Hand", cursive'
BULKY = '"Futura Condensed ExtraBold", "Futura", "Impact", "Arial Black", sans-serif'
FALLBACK = {
    "playfair display": SERIF, "didot": SERIF, "bodoni": SERIF, "lora": SERIF,
    "cormorant": SERIF, "dm serif display": SERIF, "libre baskerville": SERIF,
    "bebas neue": CONDENSED, "oswald": CONDENSED, "anton": CONDENSED,
}


def font_stack(name):
    if not name:
        return SANS
    return f'"{name}", ' + FALLBACK.get(name.lower(), SANS)


def font_faces(brand):
    """@font-face rules for brand fonts that exist as files."""
    css = []
    f = brand.get("fonts", {})
    candidates = {f.get("headline"): f.get("headline_file"), f.get("body"): f.get("body_file")}
    if f.get("graphics"):
        candidates.setdefault(f.get("graphics"), f.get("graphics_file"))
    fonts_dir = config.ASSETS_DIR / "fonts"
    for name, path in candidates.items():
        if not name:
            continue
        files = [Path(path)] if path else []
        if fonts_dir.is_dir():
            key = name.lower().replace(" ", "")
            files += [p for p in sorted(fonts_dir.iterdir())
                      if p.suffix.lower() in (".ttf", ".otf", ".woff2")
                      and p.stem.lower().replace(" ", "").replace("-", "").startswith(key)]
        for p in files:
            # one face for every weight: an uploaded font is used as-is, never faked bold
            css.append(f'@font-face {{ font-family: "{name}"; src: url("{p.as_uri()}"); '
                       f'font-weight: 100 900; }}')
    return "\n".join(css)


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def page_data(edit, layout, brand, fps):
    c = brand.get("colors", {})
    tokens = brand.get("aesthetic", {}).get("tokens", {})
    cap = edit["captions"]
    graphics = []
    for g in edit["graphics"]:
        geo = layout["graphics"].get(g["id"])
        if geo:
            graphics.append(dict(g, **{"geo": geo}))
    return {
        "W": 1080, "H": 1920, "fps": fps,
        "colors": {
            "primary": c.get("primary", "#FF3E8E"), "accent": c.get("accent", "#A3B18A"),
            "card": c.get("card_background", "#FFFFFF"), "cardText": c.get("card_text", "#111111"),
            "onPrimary": c.get("on_primary", "#FFFFFF"), "onAccent": c.get("on_accent", "#111111"),
            "sticky": mix(c.get("accent", "#F7E26B"), "#FFFFFF", 0.62),
            "captionText": c.get("caption_text", "#FFFFFF"),
            "captionKeyword": c.get("caption_keyword"),
        },
        "stickyFont": brand.get("graphics", {}).get("sticky_font", "hand"),
        "handle": brand.get("name"),
        "tokens": {"radius": tokens.get("corner_radius", 18), "shadow": tokens.get("shadow", "soft"),
                   "stroke": tokens.get("stroke", 0)},
        "captions": {"style": cap["style"], "y": (layout.get("captions") or {}).get("y", 1300),
                     "items": cap["items"]},
        "graphics": graphics,
    }


def build_page(edit, layout, brand, fps):
    data = page_data(edit, layout, brand, fps)
    f = brand.get("fonts", {})
    css_vars = {
        "--headline": font_stack(f.get("headline")),
        "--body": font_stack(f.get("body")),
        "--graphics": font_stack(f.get("graphics") or f.get("headline")),
        "--hand": HAND,
        "--bulky": BULKY,
    }
    root = "; ".join(f"{k}: {v}" for k, v in css_vars.items())
    return TEMPLATE.replace("/*FONTFACES*/", font_faces(brand)) \
                   .replace("/*ROOTVARS*/", root) \
                   .replace("/*DATA*/", json.dumps(data, ensure_ascii=False))


TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
/*FONTFACES*/
:root { /*ROOTVARS*/ }
html, body { margin: 0; width: 1080px; height: 1920px; background: transparent; overflow: hidden;
             font-family: var(--body); }
.el { position: absolute; visibility: hidden; transform-origin: center center; will-change: transform, opacity; }
.cap { left: 0; width: 1080px; text-align: center; font-family: var(--body); font-weight: 700;
       line-height: 1.12; padding: 0 70px; box-sizing: border-box; }
.cap .w { display: inline-block; margin: 0 0.12em;
          /* solid outline behind the letters: readable on light clothes and walls */
          -webkit-text-stroke: 0.16em rgba(0,0,0,.82); paint-order: stroke fill; }
.cap .w.em-bigger { font-size: 1.38em; }
.card { box-sizing: border-box; display: flex; flex-direction: column; justify-content: center;
        padding: 26px 34px; font-family: var(--body); }
.sticky { font-family: var(--hand); color: #2b2b2b; padding: 34px 38px 30px; }
.sticky h4 { margin: 0 0 14px; font-family: var(--body); font-size: 30px; letter-spacing: .08em;
             text-transform: uppercase; opacity: .7; }
.item { display: flex; align-items: flex-start; gap: 16px; font-size: 46px; line-height: 1.18;
        margin: 10px 0; }
.box { flex: none; width: 30px; height: 30px; margin-top: 8px; border-radius: 6px; border: 4px solid; }
.paper-lined { background-color: #fffdf7 !important;
  background-image: linear-gradient(90deg, transparent 58px, #f08a8a 58px, #f08a8a 61px, transparent 61px),
                    repeating-linear-gradient(180deg, transparent 0 56px, #9cc3ee 56px 58px) !important;
  background-position: 0 0, 0 30px; padding: 30px 30px 30px 82px !important; }
.paper-lined .item { margin: 0; line-height: 58px; min-height: 58px; }
.paper-lined .box { margin-top: 13px; }
.box { display: inline-flex; align-items: center; justify-content: center; font-family: -apple-system, sans-serif;
       font-weight: 900; line-height: 1; overflow: visible; }
.emoji { font-size: 150px; line-height: 1; text-align: center;
         font-family: "Apple Color Emoji", "Noto Color Emoji", sans-serif;
         filter: drop-shadow(0 8px 14px rgba(0,0,0,.35)); }
.headline { font-family: var(--headline); }
.gfxfont { font-family: var(--graphics); }
</style></head>
<body>
<script>
const D = /*DATA*/;
const C = D.colors, T = D.tokens, FPS = D.fps;
const q = v => Math.round(v * 1000) / 1000;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const easeOut = p => 1 - Math.pow(1 - p, 3);
const easeBack = p => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); };
const shadow = T.shadow === 'hard' ? '10px 10px 0 rgba(0,0,0,.85)'
             : T.shadow === 'glow' ? `0 0 0 2px ${C.primary}55, 0 10px 40px ${C.primary}66`
             : T.shadow === 'none' ? 'none' : '0 16px 40px rgba(0,0,0,.28)';
const IN = { pop: .28, fade: .25, fade_scale: .35, slide: .32, bounce: .42, none: 0 };
const OUT = .2;

function mk(cls, css, html) {
  const e = document.createElement('div');
  e.className = 'el ' + cls; Object.assign(e.style, css); if (html !== undefined) e.innerHTML = html;
  document.body.appendChild(e); return e;
}
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// ---- captions -------------------------------------------------------------
const cs = D.captions.style || {};
const capSize = cs.size_px || 76;
const caps = D.captions.items.map(c => {
  const words = c.words.map((w, i) => {
    let cls = 'w', st = '';
    if (w.emphasis) {
      if (cs.emphasis === 'bigger') cls += ' em-bigger';
      if (C.captionKeyword) st = `color:${C.captionKeyword}`;
      if (cs.emphasis === 'accent_color') st = `color:${C.accent}`;
      if (cs.emphasis === 'accent_box') st = `background:${C.accent};color:${C.onAccent};padding:0 .18em;border-radius:.18em`;
    }
    return `<span class="${cls}" data-i="${i}" style="${st}">${esc(w.text)}</span>`;
  }).join(' ');
  const e = mk('cap', {
    top: (D.captions.y - capSize) + 'px', fontSize: capSize + 'px', color: C.captionText,
    textShadow: `0 4px 14px rgba(0,0,0,.55), 0 0 26px ${C.primary}66`,
  }, words);
  return { c, e, spans: [...e.querySelectorAll('.w')] };
});

// ---- graphics -------------------------------------------------------------
function card(g, bg, fg) {
  return { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', minHeight: g.geo.h + 'px',
           background: bg, color: fg, borderRadius: T.radius + 'px', boxShadow: shadow,
           border: T.stroke ? `${T.stroke}px solid ${fg}` : 'none' };
}
function arrowSVG(dir, color) {
  const paths = {
    down_right: 'M30 30 C 90 40, 150 90, 190 190',  up_left: 'M190 190 C 150 120, 90 60, 30 30',
    down: 'M120 20 C 100 80, 140 140, 120 210', right: 'M20 120 C 80 90, 150 150, 210 120',
    left: 'M210 120 C 150 90, 80 150, 20 120', up: 'M120 210 C 140 150, 100 80, 120 20',
  };
  const d = paths[dir] || paths.down_right;
  return `<svg width="240" height="240" viewBox="0 0 240 240"><path class="shaft" d="${d}" fill="none"
    stroke="${color}" stroke-width="12" stroke-linecap="round"/><path class="head" d="" fill="none"
    stroke="${color}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
const FONTVAR = { headline: 'var(--headline)', body: 'var(--body)', hand: 'var(--hand)', bulky: 'var(--bulky)' };
const gfx = D.graphics.map(g => {
  const s = g.style || {}, sc = g.geo.scale || 1;
  let e, parts = [];
  if (g.type === 'emoji') {
    e = mk('emoji', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px',
                      fontSize: Math.round(150 * sc) + 'px' }, g.emoji);
  } else if (g.type === 'sticky_notes' || g.type === 'lists') {
    const sticky = g.type === 'sticky_notes';
    const items = (g.items || []).map(it =>
      `<div class="item"><span class="box" style="border-color:${C.primary}"></span><span>${esc(it.text)}</span></div>`).join('');
    const stickyFont = { hand: 'var(--hand)', body: 'var(--body)', headline: 'var(--headline)' }[D.stickyFont] || 'var(--hand)';
    e = mk(sticky ? 'card sticky' : 'card', Object.assign(
      card(g, sticky ? C.sticky : C.card, sticky ? '#2b2b2b' : C.cardText),
      sticky ? { transform: 'rotate(-2deg)', borderRadius: Math.min(T.radius, 8) + 'px', fontFamily: stickyFont,
                 fontSize: Math.round(46 * sc) + 'px' } : { fontSize: Math.round(46 * sc) + 'px' }),
      (g.title ? `<h4>${esc(g.title)}</h4>` : '') + items);
    e.querySelectorAll('.item').forEach(i => i.style.fontSize = Math.round(46 * sc) + 'px');
    if (s.custom_paper === 'lined') e.classList.add('paper-lined');
    parts = [...e.querySelectorAll('.item')];
  } else if (g.type === 'full_overlay') {
    // full-screen colour wash at reduced opacity, big text centred
    e = mk('', { left: 0, top: 0, width: '1080px', height: '1920px', display: 'flex',
                 alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box', padding: '0 90px' });
    const wash = document.createElement('div');
    Object.assign(wash.style, { position: 'absolute', inset: 0, background: s.custom_background || C.primary,
                                opacity: String(g.opacity ?? 0.55) });
    const txt = document.createElement('div');
    Object.assign(txt.style, { position: 'relative', color: s.custom_text || '#FFFFFF', textAlign: 'center',
      fontFamily: 'var(--headline)', fontWeight: 800, fontSize: '104px', lineHeight: 1.05,
      textShadow: '0 6px 24px rgba(0,0,0,.45)' });
    txt.textContent = g.text || '';
    e.append(wash, txt);
  } else if (g.type === 'profile_card') {
    // social profile page mock-up: avatar ring, handle, placeholder stats, post grid
    const pal = [C.primary, C.accent, C.card, C.sticky];
    const tiles = Array.from({ length: 3 }, (_, k) => `<div style="aspect-ratio:1;border-radius:6px;background:${pal[k % pal.length]};opacity:${0.65 + (k % 3) * 0.12}"></div>`).join('');
    const bar = (w, o) => `<div style="height:14px;width:${w}px;border-radius:7px;background:#111;opacity:${o}"></div>`;
    const stat = lab => `<div style="display:flex;flex-direction:column;align-items:center;gap:8px">${bar(54, .85)}<div style="font-size:24px;opacity:.75">${lab}</div></div>`;
    const avatar = g.avatar ? `<img src="${g.avatar}" style="width:118px;height:118px;border-radius:50%;object-fit:cover;border:5px solid #fff">`
                            : `<div style="width:118px;height:118px;border-radius:50%;background:${C.accent};border:5px solid #fff"></div>`;
    e = mk('card', Object.assign(card(g, '#FFFFFF', '#111111'), { padding: '26px 30px', gap: '18px', justifyContent: 'flex-start',
           fontFamily: '-apple-system, "Helvetica Neue", sans-serif' }),
      `<div style="font-weight:800;font-size:34px">${esc(g.text || D.handle || '@yourhandle')}</div>
       <div style="display:flex;align-items:center;gap:28px">
         <div style="padding:5px;border-radius:50%;background:conic-gradient(#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5,#feda75)">${avatar}</div>
         <div style="display:flex;gap:30px">${stat('posts')}${stat('followers')}${stat('following')}</div>
       </div>
       <div style="display:flex;flex-direction:column;gap:9px">${bar(380, .55)}${bar(300, .35)}</div>
       <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px">${tiles}</div>`);
  } else if (g.type === 'image') {
    const framed = g.category === 'screenshot' || g.category === 'photo';
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      `<img src="${g.src}" style="width:100%;height:100%;object-fit:contain;display:block;${framed
        ? `border-radius:${Math.min(T.radius, 24)}px;box-shadow:${shadow};background:#fff;border:6px solid #fff` : ''}">`);
    if (g.opacity) e.querySelector('img').style.opacity = String(g.opacity);
  } else if (g.type === 'headline_bar') {
    e = mk('card headline', Object.assign(card(g, C.primary, C.onPrimary), {
      fontSize: Math.round(46 * sc) + 'px', fontWeight: 700, textAlign: 'center', lineHeight: 1.1,
      padding: '14px 28px' }), esc(g.text || ''));
  } else if (g.type === 'arrows') {
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
           arrowSVG(g.direction, C.primary));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
  } else {
    const isCta = g.type === 'cta_card', isHook = g.type === 'text_callouts';
    const bg = isCta ? C.accent : isHook ? C.primary : C.card;
    const fg = isCta ? C.onAccent : isHook ? C.onPrimary : C.cardText;
    const size = isHook ? 74 : isCta ? 68 : g.type === 'lower_third' ? 44 : 58;
    e = mk('card ' + (g.role === 'headline' ? 'headline' : 'gfxfont'), Object.assign(card(g, bg, fg), {
      fontSize: Math.round(size * sc) + 'px', fontWeight: 700, textAlign: 'center', lineHeight: 1.1,
      borderLeft: g.type === 'keyword_cards' ? `14px solid ${C.accent}` : undefined }),
      esc(g.text || ''));
  }
  // Never draw a graphic bigger than the box the layout engine approved (it
  // checked that box against the face): scale the whole thing down to fit.
  if (!['full_overlay', 'emoji', 'arrows', 'image'].includes(g.type) && g.geo.h) {
    e.style.visibility = 'hidden';
    const h = e.offsetHeight, w = e.offsetWidth;
    const k = Math.min(1, g.geo.h / Math.max(h, 1), g.geo.w / Math.max(w, 1));
    if (k < 0.99) {
      // CSS zoom also scales left/top: compensate so it stays where layout put it
      e.style.zoom = String(k); e.dataset.fit = String(k);
      e.style.left = (g.geo.x / k) + 'px'; e.style.top = (g.geo.y / k) + 'px';
    }
  }
  // Customer's own choices from the review page win over the brand defaults.
  if (s.custom_background) e.style.background = s.custom_background;
  if (s.custom_text) { e.style.color = s.custom_text; }
  if (s.custom_background === 'none') {
    // text only: no box; a dark outline keeps it readable on any background
    Object.assign(e.style, { background: 'transparent', boxShadow: 'none', border: 'none', borderLeft: 'none' });
    e.style.webkitTextStroke = '0.07em rgba(0,0,0,.8)'; e.style.paintOrder = 'stroke fill';
    e.style.textShadow = '0 6px 18px rgba(0,0,0,.45)';
  }
  if (s.custom_font === 'bulky') { e.style.fontWeight = 800; e.style.fontStretch = 'condensed'; e.style.letterSpacing = '0.01em'; }
  if (s.custom_font && FONTVAR[s.custom_font]) {
    e.style.fontFamily = FONTVAR[s.custom_font];
    e.querySelectorAll('.item span:last-child').forEach(x => x.style.fontFamily = FONTVAR[s.custom_font]);
  }
  return { g, e, parts };
});

// ---- timeline -------------------------------------------------------------
function phase(t, start, end, inDur) {
  if (t < start || t >= end) return null;
  const pin = inDur ? clamp((t - start) / inDur, 0, 1) : 1;
  const pout = clamp((end - t) / OUT, 0, 1);
  return { pin, pout };
}
function animate(e, kind, ph, extra = '') {
  const pi = ph.pin, po = ph.pout;
  let s = 1, y = 0, o = 1;
  if (kind === 'pop' || kind === 'bounce') s = 0.6 + 0.4 * easeBack(pi);
  else if (kind === 'fade_scale') { s = 0.92 + 0.08 * easeOut(pi); o = easeOut(pi); }
  else if (kind === 'fade') o = easeOut(pi);
  else if (kind === 'slide') { y = 40 * (1 - easeOut(pi)); o = easeOut(pi); }
  o *= po;
  e.style.visibility = 'visible';
  e.style.opacity = q(o);
  e.style.transform = `translateY(${q(y)}px) scale(${q(s)}) ${extra}`;
}

// Which font stack did each element really get? (checked against the profile)
window.__fonts = function () {
  const fam = e => getComputedStyle(e.querySelector('.w') || e.querySelector('.item span:last-child') || (e.children.length === 2 && e.children[1]) || e).fontFamily;
  const out = caps.slice(0, 3).map((c, n) => ({ id: 'cap' + (n + 1), role: 'caption', family: fam(c.e) }));
  for (const { g, e } of gfx) {
    if (g.type === 'progress_bar' || g.type === 'arrows') continue;
    if (g.type === 'profile_card' || g.type === 'image') continue;   // no text to check
    const role = g.type === 'emoji' ? 'emoji' : g.type === 'sticky_notes' ? 'sticky'
               : (g.type === 'lists') ? 'body' : g.role === 'headline' ? 'headline' : 'graphics';
    out.push({ id: g.id, role, family: fam(e) });
  }
  return JSON.stringify(out);
};

// Did each brand font really load (an uploaded file can fail silently)?
window.__fontsLoaded = async function () {
  await document.fonts.ready;
  const fams = new Set();
  const root = getComputedStyle(document.documentElement);
  for (const v of ['--headline', '--body', '--graphics']) fams.add(root.getPropertyValue(v).split(',')[0].trim().replace(/"/g, ''));
  const out = {};
  for (const f of fams) {
    if (!f) continue;
    try { await document.fonts.load(`40px "${f}"`); } catch (e) {}
    out[f] = [...document.fonts].some(ff => ff.family.replace(/"/g, '') === f && ff.status === 'loaded');
  }
  return JSON.stringify(out);
};

// Where is each graphic really drawn? (checked against the face after rendering)
window.__rects = function () {
  const out = [];
  for (const { g, e } of gfx) {
    if (g.type === 'progress_bar') continue;
    const vis = e.style.visibility, tr = e.style.transform;
    e.style.visibility = 'visible'; e.style.transform = 'none';
    const r = e.getBoundingClientRect();
    e.style.visibility = vis; e.style.transform = tr;
    out.push({ id: g.id, x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) });
  }
  return JSON.stringify(out);
};

window.__seek = function (t) {
  const key = [];
  // captions
  for (let n = 0; n < caps.length; n++) {
    const { c, e, spans } = caps[n];
    const anim = cs.animation || 'none';
    const ph = phase(t, c.start, c.end, IN[anim] !== undefined ? Math.min(IN[anim], .14) : 0);
    if (!ph) { e.style.visibility = 'hidden'; continue; }
    animate(e, anim === 'slide_up' ? 'slide' : anim, ph);
    let active = -1;
    if (cs.style === 'karaoke') {
      c.words.forEach((w, i) => { if (t >= w.start) active = i; });
      spans.forEach((sp, i) => sp.style.color = i === active ? C.accent : '');
    }
    if (anim === 'typewriter') {
      const shown = Math.floor(clamp((t - c.start) / .5, 0, 1) * c.text.length);
      let left = shown;
      spans.forEach(sp => { const full = sp.dataset.full || (sp.dataset.full = sp.textContent);
        sp.textContent = full.slice(0, Math.max(0, left)); left -= full.length + 1; });
      key.push('tw' + shown);
    }
    key.push(`c${n}:${q(ph.pin)}:${q(ph.pout)}:${active}`);
  }
  // graphics
  for (const { g, e, parts } of gfx) {
    if (g.type === 'progress_bar') continue;  // drawn by ffmpeg
    const kind = g.type === 'emoji' ? 'pop' : (g.style || {}).animation_in || 'fade';
    const ph = phase(t, g.start, g.end, IN[kind] || .25);
    if (!ph) { e.style.visibility = 'hidden'; continue; }
    const tilt = g.type === 'sticky_notes' ? 'rotate(-2deg)' : '';
    animate(e, kind, ph, tilt);
    let k = `g${g.id}:${q(ph.pin)}:${q(ph.pout)}`;
    parts.forEach((p, i) => {
      const at = (g.items[i] || {}).at ?? g.start;
      const pi = clamp((t - at) / .25, 0, 1);
      p.style.opacity = q(easeOut(pi));
      p.style.transform = `translateX(${q(-24 * (1 - easeOut(pi)))}px)`;
      k += ':' + q(pi);
      if ((g.style || {}).checks) {
        // the box ticks right after the line appears (with a click sound)
        const pc = clamp((t - at - .12) / .18, 0, 1);
        const box = p.querySelector('.box');
        box.textContent = pc > 0 ? '✓' : '';
        box.style.color = C.primary;
        box.style.fontSize = q(0.9 * easeBack(pc)) + 'em';
        k += ':c' + q(pc);
      }
    });
    if (g.type === 'arrows') {
      const pi = clamp((t - g.start) / .45, 0, 1);
      const shaft = e.querySelector('.shaft'), len = shaft.getTotalLength();
      shaft.style.strokeDasharray = len; shaft.style.strokeDashoffset = q(len * (1 - easeOut(pi)));
      const head = e.querySelector('.head');
      if (pi >= 1) {
        const p = shaft.getPointAtLength(len), b = shaft.getPointAtLength(len - 30);
        const a = Math.atan2(p.y - b.y, p.x - b.x), L = 34;
        const h1 = [p.x - L * Math.cos(a - .5), p.y - L * Math.sin(a - .5)];
        const h2 = [p.x - L * Math.cos(a + .5), p.y - L * Math.sin(a + .5)];
        head.setAttribute('d', `M${h1} L${p.x},${p.y} L${h2}`);
      } else head.setAttribute('d', '');
      k += ':' + q(pi);
    }
    key.push(k);
  }
  return key.join('|') || 'empty';
};
</script>
</body></html>
"""
