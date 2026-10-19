// Luxe: quiet, expensive, unhurried. Light serif display type with wide
// letter-spacing, fine rules that draw themselves on, no boxes, slow rises.
// Colours and fonts always come from the customer's brand (X.C, X.FONTVAR).
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['luxe.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  const shade = X => X.DECO.graphic_shadow ? '0 2px 22px rgba(0,0,0,.38)' : 'none';
  // a refined translucent plaque behind the text, for legibility on bright walls (switchable)
  const veil = X => X.DECO.graphic_box ? { background: 'rgba(18,18,20,.46)', borderRadius: '3px',
                                           padding: '30px 44px' } : {};
  const display = (X, size, extra) => Object.assign(X.box(X.g), {
    fontFamily: X.FONTVAR.headline, fontWeight: 400, fontSize: px(X, size), letterSpacing: '.04em',
    lineHeight: 1.18, color: '#FFFFFF', textAlign: 'center', textShadow: shade(X) }, veil(X), extra || {});
  const label = (X, size) => `font-family:${X.FONTVAR.body};font-size:${px(X, size)};letter-spacing:.42em;` +
    `text-transform:uppercase;font-weight:400`;
  const rule = (X, w, mt, mb) => `<div class="rule" style="height:1.5px;width:${Math.round(w * X.sc)}px;` +
    `margin:${mt}px auto ${mb}px;background:${X.C.accent};transform:scaleX(0)"></div>`;
  // fine lines draw on from the centre, after a short delay
  const drawLines = (e, g, delay, dur) => t => {
    const p = Math.max(0, Math.min(1, (t - g.start - delay) / dur));
    const k = Math.round((1 - Math.pow(1 - p, 3)) * 1000) / 1000;
    e.querySelectorAll('.rule').forEach(r => { r.style.transform = `scaleX(${k})`; });
    e.querySelectorAll('.vrule').forEach(r => { r.style.transform = `scaleY(${k})`; });
    return k;
  };
  const slow = (e, g, extra) => Object.assign({ in: 'rise', inDur: .9, out: 'fade', outDur: .5,
                                                tick: drawLines(e, g, .25, .9) }, extra || {});
  const withG = (g, X) => Object.assign({ g }, X);
  // a hairline frame is a border: it follows the "no outlines / no boxes" rules
  const frame = X => X.DECO.graphic_border ? `border:1px solid ${X.rgba(X.C.accent, .9)};padding:26px 34px;` : '';
  // "80% of creators quit" -> ["80%", "of creators quit"]
  const splitNum = t => { const m = String(t || '').match(/^(.*?)(\d[\d.,]*\s?%?)(.*)$/);
                          return m ? [m[2].trim(), (m[1] + ' ' + m[3]).trim()] : [String(t || ''), '']; };

  reg('hook', pick({
    rules: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 62),
        (X.handle ? `<div style="${label(X, 20)};opacity:.85">${X.esc(X.handle)}</div>` : '') +
        rule(X, 140, 18, 22) + `<div>${X.esc(g.text || '')}</div>` + rule(X, 140, 22, 0));
      return { e, motion: slow(e, g) };
    },
    frame: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 58, { fontStyle: 'italic' }),
        `<div style="${frame(X)}">${X.esc(g.text || '')}</div>`);
      return { e, motion: slow(e, g, { in: 'scale_in', inDur: 1.0 }) };
    },
    side: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 56, { textAlign: 'left' }),
        `<div style="display:flex;gap:26px;align-items:stretch">` +
        `<div class="vrule" style="width:1.5px;flex:none;background:${X.C.accent};transform-origin:top;transform:scaleY(0)"></div>` +
        `<div>${X.handle ? `<div style="${label(X, 18)};opacity:.85;margin-bottom:14px">${X.esc(X.handle)}</div>` : ''}` +
        `${X.esc(g.text || '')}</div></div>`);
      return { e, motion: slow(e, g, { in: 'wipe_right', inDur: .9 }) };
    },
  }));
  reg('headline_bar', (g, X0) => {
    const X = withG(g, X0);
    const e = X.mk('', display(X, 30, { letterSpacing: '.32em', textTransform: 'uppercase',
                                        fontFamily: X.FONTVAR.body }),
      `<div>${X.esc(g.text || '')}</div>` + rule(X, 90, 14, 0));
    return { e, motion: slow(e, g, { inDur: .7 }) };
  });
  reg('key_phrase', (g, X0) => {
    const X = withG(g, X0);
    const e = X.mk('', display(X, 54, { fontStyle: 'italic' }),
      `<div>${X.esc(g.text || '')}</div>` + rule(X, 90, 18, 0));
    return { e, motion: slow(e, g, { in: 'blur_in', inDur: .8 }) };
  });
  reg('stat', pick({
    numeral: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 150, { fontWeight: 300, letterSpacing: '.02em', lineHeight: 1 }),
        `<div>${X.esc(g.text || '')}</div>` + rule(X, 110, 16, 0));
      return { e, motion: slow(e, g, { in: 'scale_in', inDur: 1.0 }) };
    },
    numeral_words: (g, X0) => {
      const X = withG(g, X0);
      const [n, rest] = splitNum(g.text);
      const e = X.mk('', display(X, 140, { fontWeight: 300, lineHeight: 1 }),
        `<div>${X.esc(n)}</div>` + rule(X, 80, 18, 18) +
        (rest ? `<div style="${label(X, 24)};line-height:1.5">${X.esc(rest)}</div>` : ''));
      return { e, motion: slow(e, g, { in: 'scale_in', inDur: 1.0 }) };
    },
  }));
  const list = (numbered, roman) => (g, X0) => {
    const X = withG(g, X0);
    const R = ['I', 'II', 'III', 'IV', 'V', 'VI'];
    const mark = i => roman ? (R[i] || String(i + 1)) : numbered ? String(i + 1).padStart(2, '0') : '·';
    const items = (g.items || []).map((it, i) =>
      `<div class="part" style="display:flex;gap:22px;align-items:baseline;justify-content:${roman ? 'flex-start' : 'center'};opacity:0">` +
      `<span style="font-family:${X.FONTVAR.headline};font-size:${px(X, roman ? 30 : 26)};color:${X.C.accent};letter-spacing:.2em` +
      `${roman ? ';min-width:2.4em' : ''}">${mark(i)}</span>` +
      `<span style="font-size:${px(X, 44)}">${X.esc(it.text)}</span></div>` +
      (i < g.items.length - 1 ? (roman ? '<div style="height:18px"></div>' : rule(X, 60, 14, 14)) : '')).join('');
    const e = X.mk('', display(X, 38, { fontFamily: X.FONTVAR.body, fontWeight: 300, letterSpacing: '.03em' },
                               ), items);
    if (roman) e.style.textAlign = 'left';
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: slow(e, g, { in: 'fade', inDur: .4, partIn: roman ? 'wipe_right' : 'rise', partDur: .6 }) };
  };
  reg('list', pick({ centred: list(true, false), roman: list(true, true) }));
  reg('question_list', list(false, false));
  reg('cta', pick({
    rules: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 40, { fontFamily: X.FONTVAR.body, letterSpacing: '.26em',
                                          textTransform: 'uppercase' }),
        rule(X, 200, 0, 20) + `<div>${X.esc(g.text || '')}</div>` + rule(X, 200, 20, 0));
      return { e, motion: slow(e, g, { inDur: 1.0 }) };
    },
    signature: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 52, { fontStyle: 'italic' }),
        `<div style="display:inline-block">${X.esc(g.text || '')}<div class="rule" style="height:1.5px;width:100%;` +
        `margin-top:14px;background:${X.C.accent};transform-origin:left center;transform:scaleX(0)"></div></div>`);
      return { e, motion: slow(e, g, { in: 'blur_in', inDur: .9 }) };
    },
  }));
  reg('quote', pick({
    mark: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 50, { fontStyle: 'italic' }),
        `<div style="font-size:${px(X, 120)};line-height:.7;height:${px(X, 60)};color:${X.C.accent};font-style:normal">“</div>` +
        `<div>${X.esc(g.text || '')}</div>`);
      return { e, motion: slow(e, g, { in: 'blur_in', inDur: 1.0 }) };
    },
    frame: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 48, { fontStyle: 'italic' }),
        `<div style="${frame(X)}">“${X.esc(g.text || '')}”</div>`);
      return { e, motion: slow(e, g, { in: 'scale_in', inDur: 1.0 }) };
    },
  }));
  reg('contrast', pick({
    strike: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 50),
        `<div style="position:relative;display:inline-block;opacity:.65;font-size:${px(X, 40)}">${X.esc(g.before || '')}` +
        `<div class="rule" style="position:absolute;left:0;right:0;top:55%;margin:0;height:1.5px;background:${X.C.accent};` +
        `transform-origin:left center;transform:scaleX(0)"></div></div>` +
        `<div style="font-style:italic;margin-top:${px(X, 22)}">${X.esc(g.after || '')}</div>`);
      return { e, motion: slow(e, g, { inDur: 1.0, tick: drawLines(e, g, .5, .8) }) };
    },
    pair: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 42),
        `<div style="display:flex;align-items:center;justify-content:center;gap:28px">` +
        `<span style="opacity:.6">${X.esc(g.before || '')}</span>` +
        `<div class="vrule" style="width:1.5px;height:1.4em;flex:none;background:${X.C.accent};transform:scaleY(0)"></div>` +
        `<span style="font-style:italic">${X.esc(g.after || '')}</span></div>`);
      return { e, motion: slow(e, g) };
    },
  }));
  reg('tip', pick({
    note: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 46),
        `<div style="${label(X, 20)};opacity:.85">A note</div>` + rule(X, 60, 16, 18) +
        `<div>${X.esc(g.text || '')}</div>`);
      return { e, motion: slow(e, g) };
    },
    numbered: (g, X0) => {
      const X = withG(g, X0);
      const e = X.mk('', display(X, 46, { textAlign: 'left' }),
        `<div style="display:flex;gap:24px;align-items:baseline"><span style="font-size:${px(X, 60)};` +
        `color:${X.C.accent};flex:none">Nº</span><span>${X.esc(g.text || '')}</span></div>`);
      return { e, motion: slow(e, g, { in: 'wipe_right' }) };
    },
  }));
  reg('lower_third', (g, X0) => {
    const X = withG(g, X0);
    const e = X.mk('', display(X, 26, { fontFamily: X.FONTVAR.body, letterSpacing: '.38em',
                                        textTransform: 'uppercase', textAlign: 'left' }),
      `<div>${X.esc(g.text || '')}</div><div class="rule" style="height:1.5px;width:${px(X, 160)};` +
      `margin-top:12px;background:${X.C.accent};transform-origin:left center;transform:scaleX(0)"></div>`);
    return { e, motion: slow(e, g, { inDur: .8 }) };
  });
  reg('reaction', (g, X0) => {
    const X = withG(g, X0);
    const e = X.mk('', Object.assign(X.box(g), { fontSize: px(X, 96), lineHeight: 1, textAlign: 'center',
      fontFamily: '"Apple Color Emoji", sans-serif', filter: X.DECO.emoji_shadow ? 'drop-shadow(0 6px 10px rgba(0,0,0,.3))' : 'none' }),
      X.esc(g.emoji || ''));
    return { e, motion: { in: 'fade', inDur: .7, out: 'fade', outDur: .5 } };
  });
  reg('pointer', (g, X0) => {
    const X = withG(g, X0);
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, X.C.accent, 3));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: { in: 'fade', inDur: .5, out: 'fade', outDur: .4 } };
  });
})();
