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


WEIGHT_WORDS = [("extralight", 200), ("ultralight", 200), ("semibold", 600), ("demibold", 600),
                ("extrabold", 800), ("ultrabold", 800), ("thin", 100), ("light", 300), ("regular", 400),
                ("book", 400), ("medium", 500), ("bold", 700), ("black", 900), ("heavy", 900)]


def _weight_range(path, n_files):
    stem = path.stem.lower().replace("_", "-")
    if n_files == 1 or "variable" in stem or "[" in stem:
        return "100 900"
    for word, w in WEIGHT_WORDS:
        if stem.endswith(word) or f"-{word}" in stem:
            return str(w)
    return "100 900"


def font_faces(brand):
    """@font-face rules for brand fonts that exist as files."""
    css = []
    f = brand.get("fonts", {})
    candidates = {f.get("headline"): f.get("headline_file"), f.get("body"): f.get("body_file")}
    if f.get("graphics"):
        candidates.setdefault(f.get("graphics"), f.get("graphics_file"))
    fonts_dir = config.ASSETS_DIR / "fonts"
    from . import fontlib
    for name, path in candidates.items():
        if not name:
            continue
        included = fontlib.files_for(name)
        if included:                       # a font included with the editor: all its weights
            files = list(included)
            if path and Path(path) not in files and not str(path).startswith(str(fontlib.INCLUDED_DIR)):
                files.append(Path(path))     # their own upload of the same family wins (declared last)
            for p in files:
                css.append(f'@font-face {{ font-family: "{name}"; src: url("{p.as_uri()}"); '
                           f'font-weight: {_weight_range(p, len(files))}; }}')
            continue
        files = [Path(path)] if path else []
        if fonts_dir.is_dir():
            key = name.lower().replace(" ", "")
            files += [p for p in sorted(fonts_dir.iterdir())
                      if p.suffix.lower() in (".ttf", ".otf", ".woff2")
                      and p.stem.lower().replace(" ", "").replace("-", "").startswith(key)]
        for p in files:
            # a file named for its weight (Lato-Bold) covers that weight; a variable or single
            # font covers them all (used as-is, never faked bold)
            css.append(f'@font-face {{ font-family: "{name}"; src: url("{p.as_uri()}"); '
                       f'font-weight: {_weight_range(p, len(files))}; }}')
    return "\n".join(css)


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def _readable(hex_color):
    if not hex_color:
        return None
    from .brand import readable_on
    return readable_on(hex_color)


def _outline(brand, st=None):
    """The outline the captions get: its look from the brand/pack, and whether
    it's drawn at all from the resolved decorations (rules can turn it off)."""
    from . import styles
    from .brand import DEFAULT_OUTLINE, OUTLINE_WIDTHS
    st = st or styles.resolve(brand)
    o = (brand.get("captions", {}) or {}).get("outline") or \
        dict(DEFAULT_OUTLINE, width_em=OUTLINE_WIDTHS[DEFAULT_OUTLINE["thickness"]])
    out = {k: o[k] for k in ("enabled", "color", "width_em", "opacity")}
    out["enabled"] = bool(st["decorations"]["caption_outline"]["on"])
    return out


def page_data(edit, layout, brand, fps):
    from . import styles
    c = brand.get("colors", {})
    st = styles.resolve(brand)
    preset = brand.get("aesthetic", {}).get("preset")
    tokens = st["aspects"]["shape"].get("tokens_by_aesthetic", {}).get(preset) or \
        brand.get("aesthetic", {}).get("tokens", {})
    typo = st["aspects"]["typography"]
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
            "headline": c.get("headline") or c.get("primary", "#FF3E8E"),
            "onHeadline": c.get("on_headline") or c.get("on_primary", "#FFFFFF"),
            "captionKeyword": c.get("caption_keyword"),
            "onKeyword": _readable(c.get("caption_keyword")) or c.get("on_primary", "#FFFFFF"),
        },
        "captionOutline": _outline(brand, st),
        "decorations": styles.decorations_on(st),
        # decorations the customer's rules forbid: a graphic may never turn these back on
        "decoBlocked": sorted({d for r in (st.get("rules") or {}).get("flags", [])
                               for d in styles.RULES.get(r, {}).get("decorations", [])}),
        "style": {"pack": st["pack"], "version": st["version"]},
        "pack": {"id": st["pack"], "legacy": st["legacy"], "typography": typo,
                 "captions": st["aspects"]["captions"], "motion": st["aspects"]["motion"],
                 "composition": st["aspects"].get("composition", {})},
        "cardPx": typo.get("card_text_px", {"hook": 74, "cta": 68, "lower_third": 44, "default": 58}),
        "weight": typo.get("weight", 700),
        "stickyFont": brand.get("graphics", {}).get("sticky_font", "hand"),
        "handle": brand.get("name"),
        "tokens": {"radius": tokens.get("corner_radius", 18), "shadow": tokens.get("shadow", "soft"),
                   "stroke": tokens.get("stroke", 0)},
        "captions": {"style": cap["style"], "y": (layout.get("captions") or {}).get("y", 1300),
                     "items": cap["items"]},
        "graphics": graphics,
    }


MOTION_JS = config.PROJECT_ROOT / "tools" / "motion.js"


def _component_js(brand):
    """The drawing components of every pack this reel uses (Classic has none:
    its graphics are drawn by the original code below)."""
    from . import styles
    st = styles.resolve(brand)
    out, seen = ["window.COMPONENTS = {};"], set()
    packs = [(st["pack"], st["version"])] + [(m["pack"], m.get("version")) for m in
                                              (brand.get("style") or {}).get("mix") or []]
    for pid, ver in packs:
        f = styles.styles_dir() / pid / (ver or styles.latest_version(pid)) / "components.js"
        if f.exists() and f not in seen:
            seen.add(f)
            out.append(f.read_text())
    return "\n".join(out)


def custom_js(edit):
    """Per-reel custom graphics (workspace/<reel>/custom/*.js): components written for
    one customer request ("custom.<name>"), loaded only for that reel. Each file is
    wrapped so a mistake in it is reported as a page error instead of breaking the page."""
    out = []
    for name, code in (edit.get("_custom_js") or {}).items():
        out.append(f"try {{\n{code}\n}} catch (e) {{ (window.__errors = window.__errors || [])"
                   f".push('custom/{name}: ' + e.message); }}")
    return "\n".join(out)


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
                   .replace("/*MOTION*/", MOTION_JS.read_text() + "\n" + _component_js(brand) + "\n"
                            + custom_js(edit)) \
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
.cap .w { display: inline-block; margin: 0 0.12em; paint-order: stroke fill; }
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
<script>window.__errors = []; window.addEventListener('error', ev => window.__errors.push(String(ev.message)));</script>
<script>
/*MOTION*/
const D = /*DATA*/;
const C = D.colors, T = D.tokens, FPS = D.fps, DECO = D.decorations || {};
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
const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

const FONTVAR = { headline: 'var(--headline)', body: 'var(--body)', hand: 'var(--hand)', bulky: 'var(--bulky)' };
// ---- captions -------------------------------------------------------------
const cs = D.captions.style || {};
const capSize = cs.size_px || 76;
const caps = D.captions.items.map(c => {
  const words = c.words.map((w, i) => {
    let cls = 'w', st = '';
    if (w.emphasis) {
      if (cs.emphasis === 'bigger') cls += ' em-bigger';
      if (C.captionKeyword) st = `color:${C.captionKeyword}`;
      // a key-word colour the customer set (Brand settings → colour roles) beats the generic highlight colour
      if (cs.emphasis === 'accent_color') st = `color:${C.captionKeyword || C.accent}`;
      if (cs.emphasis === 'accent_box') st = `background:${C.accent};color:${C.onAccent};padding:0 .18em;border-radius:.18em`;
      // style-pack treatments (brand colours by role, never a fixed colour)
      const kc = C.captionKeyword || C.accent;
      if (cs.emphasis === 'italic') st = `color:${kc};font-style:italic;font-family:var(--headline);font-weight:400`;
      if (cs.emphasis === 'underline') st = `color:${kc};text-decoration:underline;text-decoration-color:${C.accent};text-decoration-thickness:.09em;text-underline-offset:.16em`;
      // the block is the customer's key-word colour (their main colour unless they chose one)
      if (cs.emphasis === 'highlight_block') st = `background:${C.captionKeyword || C.primary};color:${C.captionKeyword ? C.onKeyword : C.onPrimary};padding:0 .14em`;
      if (cs.emphasis === 'color_fill') st = `color:${kc};transform:scale(1.14)`;
      if (cs.emphasis === 'bolder') st = `color:${kc};font-weight:900`;
      if (cs.emphasis === 'color_tilt') st = `color:${kc};transform:rotate(-7deg) scale(1.22)`;
    }
    if (w.emphasis) cls += ' kw';     // marks key words (no style of its own)
  return `<span class="${cls}" data-i="${i}" style="${st}">${esc(w.text)}</span>`;
  }).join(' ');
  const e = mk('cap', {
    top: (D.captions.y - capSize) + 'px', fontSize: capSize + 'px', color: C.captionText,
    textShadow: [DECO.caption_shadow ? '0 4px 14px rgba(0,0,0,.55)' : '',
                 DECO.caption_glow ? `0 0 26px ${C.primary}66` : ''].filter(Boolean).join(', ') || 'none',
  }, words);
  const PC = D.pack && !D.pack.legacy ? (D.pack.captions.treatment || {}) : null;
  if (PC) {
    if (PC.font) e.style.fontFamily = FONTVAR[PC.font] || e.style.fontFamily;
    if (PC.weight) e.style.fontWeight = PC.weight;
    if (PC.italic) e.style.fontStyle = 'italic';
    if (PC.letter_spacing) e.style.letterSpacing = PC.letter_spacing;
    if (PC.align) e.style.textAlign = PC.align;
    if (PC.line_height) e.style.lineHeight = PC.line_height;
  }
  const spans = [...e.querySelectorAll('.w')];
  const O = D.captionOutline;
  spans.forEach(sp => {
    sp.dataset.base = sp.style.color || '';   // keyword colour, restored after karaoke
    sp.style.webkitTextStroke = O && O.enabled ? `${O.width_em}em ${rgba(O.color, O.opacity)}` : '0';
  });
  return { c, e, spans };
});

// ---- graphics -------------------------------------------------------------
function card(g, bg, fg) {
  return { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', minHeight: g.geo.h + 'px',
           background: DECO.graphic_box ? bg : 'transparent', color: fg, borderRadius: T.radius + 'px',
           boxShadow: DECO.graphic_shadow ? shadow : 'none',
           border: DECO.graphic_border && T.stroke ? `${T.stroke}px solid ${fg}` : 'none' };
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
// Context handed to a pack's components: brand colours and fonts by role,
// decorations, the pack's typography, and small helpers. Components never
// hardcode a customer colour or font.
const X = { C, DECO, T, mk, esc, rgba, pack: D.pack, handle: D.handle, FONTVAR,
            arrowSVG: (dir, color) => arrowSVG(dir, color), MOTION, q, clamp, easeOut, easeBack,
            box: g => ({ left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', boxSizing: 'border-box' }),
            prog: (t, a, d) => clamp((t - a) / d, 0, 1),
            // the same shaft/head structure as the original arrow, so it draws on the same way
            arrow: (dir, color, width) => arrowSVG(dir, color).replace(/stroke-width="12"/g, `stroke-width="${width}"`) };
const gfx = D.graphics.map(g => {
  const s = g.style || {}, sc = g.geo.scale || 1;
  let e, parts = [], ms = null;
  const CP = (window.COMPONENTS || {})[g.component];
  if (CP) {
    // headlines use the customer's headline colour wherever a style uses its main colour
    const Cg = g.role === 'headline' ? Object.assign({}, C, { primary: C.headline, onPrimary: C.onHeadline }) : C;
    // Backing per graphic (plan or review): "none" = clean text over the footage,
    // "box" = the style's box/plaque - unless the customer's rules forbid it.
    const backing = s.custom_background === 'none' ? 'none' : g.backing;
    const Dg = Object.assign({}, DECO);
    if (backing === 'none') Object.assign(Dg, { graphic_box: false, graphic_border: false });
    if (backing === 'box' && !(D.decoBlocked || []).includes('graphic_box')) Dg.graphic_box = true;
    const r = CP(g, Object.assign({ sc }, X, { C: Cg, DECO: Dg }));
    e = r.e; parts = r.parts || []; ms = r.motion;
  } else if (g.type === 'emoji') {
    e = mk('emoji', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px',
                      fontSize: Math.round(150 * sc) + 'px' }, g.emoji);
    if (!DECO.emoji_shadow) e.style.filter = 'none';
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
  } else if (g.type === 'calendar') {
    // A wall calendar on request: a stack of pages in the brand's colours; on each beat
    // (g.flips: seconds after it appears) the top page swings up over the binding and
    // the next one shows. Drawn from time alone, so every render is identical.
    const flips = (g.flips || []).map(Number).filter(x => x >= 0).sort((a, b) => a - b);
    const n = flips.length + 1, gw = g.geo.w, gh = g.geo.h, head = Math.round(gh * .2);
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: gw + 'px', height: gh + 'px',
                 perspective: Math.round(gw * 3) + 'px' });
    const drop = DECO.graphic_shadow ? 'box-shadow:0 18px 40px rgba(0,0,0,.30);' : '';
    const days = k => {           // a plain month grid; each page starts on a different weekday
      const off = (k * 3) % 7, len = [31, 30, 31, 30][k % 4];
      let cells = '';
      for (let i = 0; i < 35; i++) {
        const d = i - off + 1;
        cells += `<span style="text-align:center;opacity:${d >= 1 && d <= len ? 1 : 0}">${d >= 1 && d <= len ? d : ''}</span>`;
      }
      return cells;
    };
    const page = (k, top) => {
      const p = document.createElement('div');
      p.setAttribute('style', `position:absolute;left:0;top:${head * .55}px;width:${gw}px;height:${gh - head * .55}px;` +
        `background:#FFFFFF;border-radius:${Math.min(T.radius, 18)}px;overflow:hidden;box-sizing:border-box;` +
        `transform-origin:50% 0;${top ? drop : ''}`);
      p.innerHTML = `<div style="height:${head}px;background:${C.primary}"></div>` +
        `<div style="display:grid;grid-template-columns:repeat(7,1fr);row-gap:${Math.round(gh * .028)}px;` +
        `padding:${Math.round(gh * .045)}px ${Math.round(gw * .06)}px;font-family:var(--body);font-weight:700;` +
        `font-size:${Math.round(gw * .062)}px;color:${C.cardText && C.cardText !== C.card ? C.cardText : '#111111'}">${days(k)}</div>`;
      return p;
    };
    // pages from the back (last) to the front (first); rings sit on top of everything
    const pages = [];
    for (let k = n - 1; k >= 0; k--) { const p = page(k, k === 0); e.appendChild(p); pages[k] = p; }
    const rings = document.createElement('div');
    rings.setAttribute('style', `position:absolute;left:0;top:0;width:${gw}px;height:${head}px;display:flex;` +
      `justify-content:space-around;align-items:flex-start;padding:0 ${Math.round(gw * .12)}px;box-sizing:border-box;z-index:50`);
    rings.innerHTML = Array.from({ length: 4 }, () => `<i style="display:block;width:${Math.round(gw * .045)}px;` +
      `height:${Math.round(head * .9)}px;border-radius:999px;background:#FFFFFF;border:${Math.max(2, Math.round(gw * .01))}px solid ` +
      `${C.cardText && C.cardText !== C.card ? C.cardText : '#111111'}"></i>`).join('');
    e.appendChild(rings);
    const flip = t => {
      const s = t - g.start;
      let key = '';
      flips.forEach((f, k) => {
        // the page swings up toward the viewer over the rings (ease in and out, ~0.75 s) and
        // fades as it turns edge-on, revealing the next page
        const p = clamp((s - f) / .75, 0, 1), a = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
        const deg = a * 100, pg = pages[k], back = deg > 90;
        pg.style.transform = `rotateX(${q(deg)}deg)`;
        pg.style.opacity = String(q(p >= 1 ? 0 : deg > 65 ? Math.max(0, 1 - (deg - 65) / 25) : 1));
        if (pg.dataset.back !== String(back)) {
          pg.dataset.back = String(back);
          [...pg.children].forEach(c => { c.style.visibility = back ? 'hidden' : ''; });
          pg.style.background = back ? '#EDEDED' : '#FFFFFF';
        }
        key += q(p) + ',';
      });
      return key;
    };
    ms = { in: 'pop', inDur: .35, out: 'fade', outDur: .3, tick: flip };
  } else if (g.type === 'carousel') {
    // The customer's images orbiting a tilted ring: front cards big and bright, back
    // cards smaller and dimmer, each turning a little as it passes the sides.
    // Position comes from time alone (frame-exact, identical on every render).
    const O = g.geo.orbit, n = g.srcs.length, gw = g.geo.w, gh = g.geo.h;
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: gw + 'px', height: gh + 'px',
                 perspective: Math.round(gw * 1.6) + 'px' });
    const frame = DECO.graphic_border ? `border:${Math.max(3, Math.round(O.card * .025))}px solid #FFFFFF;` : '';
    const drop = DECO.graphic_shadow ? 'box-shadow:0 18px 40px rgba(0,0,0,.35);' : '';
    const cards = g.srcs.map((src, i) => {
      const r = g.ratios[i] || .8;
      const w = r >= O.card / O.card_h ? O.card : O.card_h * r, h = w / r;
      const c = document.createElement('div');
      c.setAttribute('style', `position:absolute;left:0;top:0;width:${Math.round(w)}px;height:${Math.round(h)}px;` +
        `border-radius:${Math.min(T.radius, 20)}px;overflow:hidden;box-sizing:border-box;${frame}${drop}` +
        `background:#FFFFFF;will-change:transform`);
      c.innerHTML = `<img src="${src}" style="width:100%;height:100%;object-fit:contain;display:block">`;
      c.dataset.w = w; c.dataset.h = h;
      e.appendChild(c);
      return c;
    });
    const spin = t => {
      const base = O.dir * 2 * Math.PI * (t - g.start) / O.period;
      cards.forEach((c, i) => {
        const a = base + i * 2 * Math.PI / n, sn = Math.sin(a), cs = Math.cos(a);
        const k = (cs + 1) / 2;                                   // 1 = front, 0 = back
        const s = O.back + (1 - O.back) * k;
        const x = gw / 2 + O.radius * sn - c.dataset.w / 2, y = gh / 2 + O.tilt * cs - c.dataset.h / 2;
        c.style.transform = `translate(${q(x)}px,${q(y)}px) rotateY(${q(-sn * O.turn)}deg) scale(${q(s)})`;
        c.style.filter = `brightness(${q(O.dim + (1 - O.dim) * k)})`;
        c.style.zIndex = String(Math.round(k * 1000));
      });
      return q(base);
    };
    ms = { in: 'scale_in', inDur: .6, out: 'fade', outDur: .45, tick: spin };
  } else if (g.type === 'image') {
    const framed = g.category === 'screenshot' || g.category === 'photo';
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      `<img src="${g.src}" style="width:100%;height:100%;object-fit:contain;display:block;${framed
        ? `border-radius:${Math.min(T.radius, 24)}px;box-shadow:${DECO.graphic_shadow ? shadow : 'none'};background:#fff;border:6px solid #fff` : ''}">`);
    if (g.opacity) e.querySelector('img').style.opacity = String(g.opacity);
  } else if (g.type === 'headline_bar') {
    e = mk('card headline', Object.assign(card(g, C.headline, C.onHeadline), {
      fontSize: Math.round(46 * sc) + 'px', fontWeight: 700, textAlign: 'center', lineHeight: 1.1,
      padding: '14px 28px' }), esc(g.text || ''));
  } else if (g.type === 'arrows') {
    e = mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
           arrowSVG(g.direction, C.primary));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
  } else {
    const isCta = g.type === 'cta_card', isHook = g.type === 'text_callouts';
    const hl = g.role === 'headline';
    const bg = isCta ? C.accent : isHook ? (hl ? C.headline : C.primary) : C.card;
    const fg = isCta ? C.onAccent : isHook ? (hl ? C.onHeadline : C.onPrimary) : C.cardText;
    const P = D.cardPx;
    const size = isHook ? P.hook : isCta ? P.cta : g.type === 'lower_third' ? P.lower_third : P.default;
    e = mk('card ' + (g.role === 'headline' ? 'headline' : 'gfxfont'), Object.assign(card(g, bg, fg), {
      fontSize: Math.round(size * sc) + 'px', fontWeight: D.weight, textAlign: 'center', lineHeight: 1.1,
      borderLeft: g.type === 'keyword_cards' && DECO.graphic_border ? `14px solid ${C.accent}` : undefined }),
      esc(g.text || ''));
  }
  // Never draw a graphic bigger than the box the layout engine approved (it
  // checked that box against the face): scale the whole thing down to fit.
  if (g.geo.list_mode === 'sequence' && parts.length) {
    // one item at a time: measure with only the longest item showing
    e.querySelectorAll('br').forEach(b => b.remove());
    parts.forEach(p => { p.style.display = 'none'; });
    parts.reduce((a, b) => (b.textContent.length > a.textContent.length ? b : a)).style.display = '';
  }
  if (!['full_overlay', 'emoji', 'arrows', 'image', 'carousel', 'calendar'].includes(g.type) && g.geo.h) {
    e.style.visibility = 'hidden';
    if (ms) {
      // A word wider than its box (or more lines than a fixed-height shape) would spill
      // past the style's own background: grow the box around its text first, then the
      // whole graphic is scaled into the approved space below.
      const overW = e.scrollWidth - e.clientWidth, overH = e.scrollHeight - e.clientHeight;
      if (overW > 1) e.style.width = (e.offsetWidth + overW) + 'px';
      if (overH > 1 && e.style.height) e.style.height = (e.offsetHeight + overH) + 'px';
    }
    const h = e.offsetHeight, w = ms ? Math.max(e.offsetWidth, e.scrollWidth) : e.offsetWidth;
    const k = Math.min(1, g.geo.h / Math.max(h, 1), g.geo.w / Math.max(w, 1));
    if (k < 0.99) {
      // CSS zoom also scales left/top: compensate so it stays where layout put it
      e.style.zoom = String(k); e.dataset.fit = String(k);
      e.style.left = (g.geo.x / k) + 'px'; e.style.top = (g.geo.y / k) + 'px';
    }
  }
  // Customer's own choices from the review page win over the brand defaults.
  if (s.custom_background && !(CP && s.custom_background === 'none')) e.style.background = s.custom_background;
  if (s.custom_text) { e.style.color = s.custom_text; }
  if (s.custom_background === 'none' && !CP) {   // style components handle it as backing: none
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
  return { g, e, parts, ms };
});

// ---- timeline -------------------------------------------------------------
function phase(t, start, end, inDur, outDur = OUT) {
  if (t < start || t >= end) return null;
  const pin = inDur ? clamp((t - start) / inDur, 0, 1) : 1;
  const pout = outDur ? clamp((end - t) / outDur, 0, 1) : 1;
  return { pin, pout };
}
// Captions: "none" means no animation at all (no fade-out either). Short
// captions (one-word pops) never fade out and get only a tiny entrance, so
// keywords are shown solid, in their real colour, for (nearly) all their time.
const SHORT_CAPTION = .45;
function capTiming(anim, dur) {
  if (anim === 'none') return [0, 0];
  const short = dur < SHORT_CAPTION;
  const key = anim === 'slide_up' ? 'slide' : anim;   // "slide up" moves like slide
  const packIn = (D.pack && D.pack.captions.treatment || {}).in_s || .22;
  const base = IN[key] !== undefined ? IN[key] : MOTION.IN[key] ? packIn : 0;
  const inDur = Math.min(base, short ? .06 : (IN[key] !== undefined ? .14 : packIn));
  return [inDur, short ? 0 : Math.min(OUT, .2 * dur)];
}
// The original animations keep their exact original code (Classic must never
// change); every other name comes from the motion primitives (tools/motion.js).
const LEGACY_MOTION = new Set(['pop', 'bounce', 'fade_scale', 'fade', 'slide', 'none', 'typewriter']);
function animate(e, kind, ph, extra = '') {
  if (!LEGACY_MOTION.has(kind) && MOTION.IN[kind]) {
    const st = MOTION.css(MOTION.state(kind, ph.pin, ph.exit || kind, ph.pout));
    e.style.visibility = 'visible';
    Object.assign(e.style, { opacity: st.opacity, filter: st.filter, clipPath: st.clipPath,
                             transformOrigin: st.transformOrigin, transform: `${st.transform} ${extra}` });
    return;
  }
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
  const fam = e => getComputedStyle(e.querySelector('.w:not(.kw)') || e.querySelector('.w') || e.querySelector('.item span:last-child') || (e.children.length === 2 && e.children[1]) || e).fontFamily;
  const out = caps.slice(0, 3).map((c, n) => ({ id: 'cap' + (n + 1), role: 'caption', family: fam(c.e) }));
  for (const { g, e } of gfx) {
    if (g.type === 'progress_bar' || g.type === 'arrows') continue;
    if (['profile_card', 'image', 'carousel', 'calendar'].includes(g.type)) continue;   // no text to check
    const role = g.type === 'emoji' ? 'emoji' : g.type === 'sticky_notes' ? 'sticky'
               : (g.type === 'lists') ? 'body' : g.role === 'headline' ? 'headline' : 'graphics';
    out.push({ id: g.id, role, family: fam(e) });
  }
  return JSON.stringify(out);
};

// Computed look of every caption and graphic (used by the style comparison test).
window.__styleReport = function () {
  const pick = el => { const cs = getComputedStyle(el); return { family: cs.fontFamily.split(',')[0].replace(/"/g, '').trim(),
    weight: cs.fontWeight, style: cs.fontStyle, transform: cs.textTransform, spacing: cs.letterSpacing,
    size: cs.fontSize, align: cs.textAlign, bg: cs.backgroundColor, radius: cs.borderRadius }; };
  const out = caps.slice(0, 2).map((c, n) => Object.assign({ id: 'cap' + (n + 1), role: 'caption' }, pick(c.spans[0] || c.e)));
  for (const { g, e } of gfx) {
    if (g.type === 'progress_bar') continue;
    const inner = e.querySelector('.part, div, span') || e;
    const r = e.getBoundingClientRect();
    out.push(Object.assign({ id: g.id, role: g.intent || g.type, component: g.component || null,
      x: Math.round(g.geo.x), w: Math.round(g.geo.w) }, pick(e), { innerWeight: getComputedStyle(inner).fontWeight }));
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
    const [inDur, outDur] = capTiming(anim, c.end - c.start);
    const ph = phase(t, c.start, c.end, inDur, outDur);
    if (!ph) { e.style.visibility = 'hidden'; continue; }
    animate(e, anim === 'slide_up' ? 'slide' : anim, ph);
    let active = -1;
    if (cs.style === 'karaoke') {
      c.words.forEach((w, i) => { if (t >= w.start) active = i; });
      spans.forEach((sp, i) => sp.style.color = i === active ? C.accent : sp.dataset.base);
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
  for (const { g, e, parts, ms } of gfx) {
    if (g.type === 'progress_bar') continue;  // drawn by ffmpeg
    const asked = (g.style || {}).animation_in;   // a review choice beats the pack
    const kind = ms ? (asked || ms.in) : g.type === 'emoji' ? 'pop' : asked || 'fade';
    const ph = ms ? phase(t, g.start, g.end, ms.inDur, ms.outDur ?? OUT)
                  : phase(t, g.start, g.end, IN[kind] || .25);
    if (!ph) { e.style.visibility = 'hidden'; continue; }
    if (ms) ph.exit = ms.out;
    const tilt = ms ? (ms.extra || '') : g.type === 'sticky_notes' ? 'rotate(-2deg)' : '';
    animate(e, kind, ph, tilt);
    let k = `g${g.id}:${q(ph.pin)}:${q(ph.pout)}`;
    if (ms && ms.tick) k += ':' + ms.tick(t, ph);
    if (g.geo.list_mode === 'sequence' && parts.length) {
      let cur = 0;
      parts.forEach((p, i) => {
        const at = ms && ms.partAt ? ms.partAt(i) : (g.items && g.items[i] || {}).at ?? g.start;
        if (t >= at) cur = i;
      });
      parts.forEach((p, i) => { p.style.display = i === cur ? '' : 'none'; });
      k += ':s' + cur;
    }
    parts.forEach((p, i) => {
      const at = ms && ms.partAt ? ms.partAt(i) : (g.items && g.items[i] || {}).at ?? g.start;
      const pi = clamp((t - at) / (ms ? ms.partDur || .3 : .25), 0, 1);
      if (ms) {
        const st = MOTION.css(MOTION.state(ms.partIn || 'rise', pi, 'fade', 1));
        Object.assign(p.style, { opacity: st.opacity, transform: st.transform + (p.dataset.tf || ''),
                                 filter: st.filter, clipPath: st.clipPath });
      } else {
        p.style.opacity = q(easeOut(pi));
        p.style.transform = `translateX(${q(-24 * (1 - easeOut(pi)))}px)`;
      }
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
