// Bold: loud and certain, but still. Huge heavy upper-case type, solid colour
// slabs and full-width bands, hard edges, instant snaps and hard cuts out.
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['bold.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  const splitNum = t => { const m = String(t || '').match(/^(.*?)(\d[\d.,]*\s?%?)(.*)$/);
                          return m ? [m[2].trim(), (m[1] + ' ' + m[3]).trim()] : [String(t || ''), '']; };
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  const INK = '#111111';
  const slab = (X, g, bg, fg, extra) => Object.assign(X.box(g), {
    background: X.DECO.graphic_box ? bg : 'transparent', color: X.DECO.graphic_box ? fg : '#FFFFFF',
    padding: X.DECO.graphic_box ? '24px 40px' : '0', fontFamily: X.FONTVAR.headline, fontWeight: 900,
    textTransform: 'uppercase', letterSpacing: '-.02em', lineHeight: .92, textAlign: 'left',
    boxShadow: X.DECO.graphic_shadow && X.DECO.graphic_box ? `0 14px 0 ${INK}` : 'none',
    textShadow: X.DECO.graphic_box ? 'none' : '0 4px 18px rgba(0,0,0,.5)' }, extra || {},
    // text with no slab behind it still keeps the side margin when the layout gave it the full width
    !X.DECO.graphic_box && g.geo.x < 30 ? { padding: `0 ${Math.round(60 * X.sc)}px` } : {});
  const snap = extra => Object.assign({ in: 'slam', inDur: .14, out: 'none', outDur: 0 }, extra || {});
  const block = (X, bg, fg, html, extra) => X.DECO.graphic_box
    ? `<span style="display:inline-block;background:${bg};color:${fg};padding:4px 16px;margin:4px 6px 4px 0;${extra || ''}">${html}</span>`
    : `<span style="display:inline-block;margin:4px 12px 4px 0;${extra || ''}">${html}</span>`;

  const twotone = size => (g, X) => {
    // two-tone stacked words: alternating brand colour and ink blocks
    const words = String(g.text || '').split(/\s+/).filter(Boolean);
    const html = words.map((w, i) => block(X, i % 2 ? INK : X.C.primary, i % 2 ? '#FFFFFF' : X.C.onPrimary, X.esc(w))).join('');
    return { e: X.mk('', slab(X, g, 'transparent', '#FFFFFF', { fontSize: px(X, size), padding: 0, background: 'transparent',
      boxShadow: 'none' }), html), motion: snap() };
  };
  reg('hook', pick({
    slab: (g, X) => ({ e: X.mk('', slab(X, g, X.C.primary, X.C.onPrimary,
      { fontSize: px(X, 100), minHeight: g.geo.h + 'px', display: 'flex', alignItems: 'center', padding: X.DECO.graphic_box ? '30px 60px' : '0' }),
      X.esc(g.text || '')), motion: snap() }),
    twotone: twotone(92),
    giant: (g, X) => {
      // the first word huge, the rest in a band underneath
      const words = String(g.text || '').split(/\s+/).filter(Boolean);
      const first = words.shift() || '';
      const e = X.mk('', slab(X, g, 'transparent', '#FFFFFF', { padding: 0, background: 'transparent', boxShadow: 'none' }),
        `<div style="font-size:${px(X, 230)};line-height:.82;color:${X.C.primary};` +
        `${X.DECO.graphic_shadow ? `text-shadow:8px 8px 0 ${INK}` : ''}">${X.esc(first)}</div>` +
        (words.length ? block(X, INK, '#FFFFFF', X.esc(words.join(' ')), `font-size:${px(X, 66)};margin-top:12px`) : ''));
      return { e, motion: snap() };
    },
  }));
  reg('headline_bar', (g, X) => ({ e: X.mk('', slab(X, g, INK, '#FFFFFF',
    { fontSize: px(X, 40), padding: X.DECO.graphic_box ? '18px 60px' : '0', letterSpacing: '.02em' }), X.esc(g.text || '')),
    motion: snap() }));
  reg('key_phrase', twotone(82));
  reg('stat', pick({
    slab: (g, X) => ({ e: X.mk('', slab(X, g, INK, X.C.accent,
      { fontSize: px(X, 210), lineHeight: .85, padding: X.DECO.graphic_box ? '26px 44px 30px' : '0' }), X.esc(g.text || '')),
      motion: snap({ inDur: .1 }) }),
    fill: (g, X) => {
      // a thick bar that snaps full to the percentage, the number on top
      const [n, rest] = splitNum(g.text);
      const pct = Math.max(0, Math.min(100, parseFloat(n.replace(',', '.')) || 0));
      const e = X.mk('', slab(X, g, 'transparent', '#FFFFFF', { padding: 0, background: 'transparent', boxShadow: 'none' }),
        `<div style="font-size:${px(X, 170)};line-height:.85">${X.esc(n)}</div>` +
        (rest ? `<div style="font-size:${px(X, 46)};margin:10px 0 14px">${X.esc(rest)}</div>` : '') +
        `<div style="position:relative;height:${px(X, 46)};background:${X.DECO.graphic_box ? INK : 'rgba(255,255,255,.25)'}">` +
        `<div class="fill" style="position:absolute;left:0;top:0;bottom:0;width:${pct}%;background:${X.C.primary};` +
        `transform-origin:left center;transform:scaleX(0)"></div></div>`);
      return { e, motion: snap({ inDur: .1, tick: t => {
        const k = Math.round(Math.max(0, Math.min(1, (t - g.start - .25) / .35)) * 1000) / 1000;
        e.querySelector('.fill').style.transform = `scaleX(${k})`;
        return k; } }) };
    },
  }));
  const blocks = q => (g, X) => {
    const items = (g.items || []).map((it, i) =>
      `<div class="part" style="display:flex;align-items:stretch;margin:0 0 10px;opacity:0">` +
      block(X, X.C.primary, X.C.onPrimary, q ? '?' : String(i + 1), 'margin:0;min-width:1.1em;text-align:center') +
      block(X, INK, '#FFFFFF', X.esc(it.text), 'margin:0;flex:1') + '</div>').join('');
    const e = X.mk('', slab(X, g, 'transparent', '#FFFFFF', { fontSize: px(X, 52), padding: 0, background: 'transparent',
      boxShadow: 'none', lineHeight: 1 }), items);
    return { e, parts: [...e.querySelectorAll('.part')], motion: snap({ in: 'none', inDur: 0, partIn: 'slam', partDur: .12 }) };
  };
  const bignums = (g, X) => {
    const items = (g.items || []).map((it, i) =>
      `<div class="part" style="display:flex;align-items:center;gap:24px;margin:0 0 8px;opacity:0">` +
      `<span style="font-size:${px(X, 120)};line-height:.85;color:${X.C.primary};min-width:.8em">${i + 1}</span>` +
      `<span style="font-size:${px(X, 54)}">${X.esc(it.text)}</span></div>`).join('');
    const e = X.mk('', slab(X, g, 'transparent', '#FFFFFF', { padding: 0, background: 'transparent', boxShadow: 'none' }), items);
    return { e, parts: [...e.querySelectorAll('.part')], motion: snap({ in: 'none', inDur: 0, partIn: 'slam', partDur: .12 }) };
  };
  reg('list', pick({ blocks: blocks(false), bignums }));
  reg('question_list', blocks(true));
  reg('cta', pick({
    band: (g, X) => ({ e: X.mk('', slab(X, g, X.C.primary, X.C.onPrimary,
      { fontSize: px(X, 70), minHeight: g.geo.h + 'px', display: 'flex', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center' }), X.esc(g.text || '')), motion: snap() }),
    stamp: (g, X) => ({ e: X.mk('', slab(X, g, X.C.accent, X.C.onAccent,
      { fontSize: px(X, 64), textAlign: 'center', padding: '22px 36px',
        border: X.DECO.graphic_border ? `8px solid ${X.DECO.graphic_box ? INK : X.C.primary}` : 'none' }),
      X.esc(g.text || '')), motion: snap({ extra: 'rotate(-6deg)' }) }),
  }));
  reg('quote', pick({
    marks: (g, X) => ({ e: X.mk('', slab(X, g, 'transparent', '#FFFFFF', { fontSize: px(X, 70), padding: 0, background: 'transparent',
      boxShadow: 'none', lineHeight: .98 }),
      `<div style="font-size:${px(X, 260)};line-height:.62;height:${px(X, 120)};color:${X.C.primary}">“</div>` + X.esc(g.text || '')),
      motion: snap() }),
  }));
  reg('contrast', pick({
    crossed: (g, X) => {
      // the old idea in ink with a thick bar through it, then the answer slams in
      const e = X.mk('', slab(X, g, 'transparent', '#FFFFFF', { padding: 0, background: 'transparent', boxShadow: 'none' }),
        `<div class="part" style="opacity:0;position:relative;display:inline-block;font-size:${px(X, 54)}">` +
        block(X, INK, 'rgba(255,255,255,.75)', X.esc(g.before || ''), 'margin:0') +
        `<div style="position:absolute;left:-10px;right:-10px;top:46%;height:${px(X, 14)};background:${X.C.primary}"></div></div>` +
        `<div class="part" style="opacity:0;margin-top:14px;font-size:${px(X, 80)}">` +
        block(X, X.C.primary, X.C.onPrimary, X.esc(g.after || ''), 'margin:0') + '</div>');
      const d = Math.max(.5, (g.end - g.start) * .4);
      return { e, parts: [...e.querySelectorAll('.part')],
               motion: snap({ in: 'none', inDur: 0, partIn: 'slam', partDur: .12, partAt: i => g.start + i * d }) };
    },
  }));
  reg('tip', pick({
    dothis: (g, X) => ({ e: X.mk('', slab(X, g, 'transparent', '#FFFFFF', { padding: 0, background: 'transparent', boxShadow: 'none' }),
      block(X, X.C.accent, X.C.onAccent, 'Do this', `font-size:${px(X, 40)};transform:rotate(-4deg);margin-bottom:12px`) + '<br>' +
      block(X, INK, '#FFFFFF', X.esc(g.text || ''), `font-size:${px(X, 64)};margin:0`)), motion: snap() }),
  }));
  reg('lower_third', (g, X) => ({ e: X.mk('', slab(X, g, INK, '#FFFFFF',
    { fontSize: px(X, 36), padding: X.DECO.graphic_box ? '16px 26px' : '0', letterSpacing: '.04em',
      borderLeft: X.DECO.graphic_box ? `16px solid ${X.C.primary}` : 'none' }), X.esc(g.text || '')), motion: snap() }));
  reg('reaction', (g, X) => ({
    e: X.mk('', Object.assign(X.box(g), { height: g.geo.h + 'px', fontSize: px(X, 200), lineHeight: 1, textAlign: 'center',
      fontFamily: '"Apple Color Emoji", sans-serif', filter: X.DECO.emoji_shadow ? `drop-shadow(10px 12px 0 ${INK})` : 'none' }),
      X.esc(g.emoji || '')),
    motion: snap({ extra: 'rotate(-8deg)' }) }));
  reg('pointer', (g, X) => {
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, X.C.primary, 22));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: snap({ in: 'none' }) };
  });
})();
