// Minimal: calm, clean, confident. Plain type in one family, generous space,
// no boxes or shapes (a single short accent bar at most), short crisp fades.
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['minimal.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  const splitNum = t => { const m = String(t || '').match(/^(.*?)(\d[\d.,]*\s?%?)(.*)$/);
                          return m ? [m[2].trim(), (m[1] + ' ' + m[3]).trim()] : [String(t || ''), '']; };
  // a thin line that draws itself across (underlines, progress lines)
  const draw = (e, g, delay, dur) => t => {
    const p = Math.max(0, Math.min(1, (t - g.start - delay) / dur));
    const k = Math.round((1 - Math.pow(1 - p, 3)) * 1000) / 1000;
    e.querySelectorAll('.line').forEach(r => { r.style.transform = `scaleX(${k})`; });
    return k;
  };
  const line = (X, w, extra) => `<div class="line" style="height:3px;width:${w};background:${X.C.accent};` +
    `transform-origin:left center;transform:scaleX(0);${extra || ''}"></div>`;
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  const text = (X, g, size, weight, extra) => Object.assign(X.box(g), {
    fontFamily: X.FONTVAR.body, fontSize: px(X, size), fontWeight: weight, lineHeight: 1.2,
    letterSpacing: '-.01em', color: '#FFFFFF', textAlign: 'left',
    textShadow: X.DECO.graphic_shadow ? '0 1px 3px rgba(0,0,0,.55), 0 3px 22px rgba(0,0,0,.5)' : 'none' }, extra || {});
  const bar = X => `<div style="width:${px(X, 44)};height:4px;background:${X.C.accent};margin-bottom:18px"></div>`;
  const crisp = extra => Object.assign({ in: 'fade', inDur: .28, out: 'fade', outDur: .22 }, extra || {});

  reg('hook', pick({
    bar: (g, X) => ({ e: X.mk('', text(X, g, 60, 600), bar(X) + X.esc(g.text || '')), motion: crisp() }),
    centred: (g, X) => ({ e: X.mk('', text(X, g, 58, 600, { textAlign: 'center' }), X.esc(g.text || '')),
                          motion: crisp({ in: 'rise', inDur: .35 }) }),
    underline: (g, X) => {
      const e = X.mk('', text(X, g, 60, 600), `<span style="display:inline-block">${X.esc(g.text || '')}` +
        line(X, '100%', 'margin-top:12px') + '</span>');
      return { e, motion: crisp({ tick: draw(e, g, .2, .5) }) };
    },
  }));
  reg('headline_bar', (g, X) => ({ e: X.mk('', text(X, g, 30, 600), X.esc(g.text || '')), motion: crisp() }));
  reg('key_phrase', (g, X) => ({ e: X.mk('', text(X, g, 50, 500), X.esc(g.text || '')), motion: crisp() }));
  reg('stat', pick({
    numeral: (g, X) => ({ e: X.mk('', text(X, g, 124, 300, { letterSpacing: '-.03em', lineHeight: 1 }), X.esc(g.text || '')),
                          motion: crisp({ inDur: .35 }) }),
    line: (g, X) => {
      // the number, its words, and a thin line drawn to that percentage
      const [n, rest] = splitNum(g.text);
      const pct = Math.max(0, Math.min(100, parseFloat(n.replace(',', '.')) || 0));
      const e = X.mk('', text(X, g, 110, 300, { letterSpacing: '-.03em', lineHeight: 1 }),
        `<div>${X.esc(n)}</div>` + (rest ? `<div style="font-size:${px(X, 34)};font-weight:500;letter-spacing:0;margin-top:10px">` +
        `${X.esc(rest)}</div>` : '') +
        `<div style="position:relative;height:3px;margin-top:22px;background:rgba(255,255,255,.28)">` +
        line(X, pct + '%', 'position:absolute;left:0;top:0') + '</div>');
      return { e, motion: crisp({ inDur: .35, tick: draw(e, g, .3, .9) }) };
    },
  }));
  const lines = (g, X) => {
    const e = X.mk('', text(X, g, 44, 500),
      (g.items || []).map(it => `<div class="part" style="opacity:0;margin:10px 0">— ${X.esc(it.text)}</div>`).join(''));
    return { e, parts: [...e.querySelectorAll('.part')], motion: crisp({ in: 'none', inDur: 0, partIn: 'fade', partDur: .25 }) };
  };
  const numbers = (g, X) => {
    const e = X.mk('', text(X, g, 44, 500),
      (g.items || []).map((it, i) => `<div class="part" style="opacity:0;margin:10px 0;display:flex;gap:22px;align-items:baseline">` +
        `<span style="font-size:${px(X, 28)};font-weight:600;color:${X.C.accent};min-width:1.4em">${i + 1}</span>` +
        `<span>${X.esc(it.text)}</span></div>`).join(''));
    return { e, parts: [...e.querySelectorAll('.part')], motion: crisp({ in: 'none', inDur: 0, partIn: 'fade', partDur: .25 }) };
  };
  reg('list', pick({ dashes: lines, numbers }));
  reg('question_list', lines);
  reg('cta', pick({
    arrow: (g, X) => ({ e: X.mk('', text(X, g, 40, 600), `${X.esc(g.text || '')} &nbsp;→`), motion: crisp() }),
    underline: (g, X) => {
      const e = X.mk('', text(X, g, 42, 600), `<span style="display:inline-block">${X.esc(g.text || '')}` +
        line(X, '100%', 'margin-top:10px') + '</span>');
      return { e, motion: crisp({ tick: draw(e, g, .15, .45) }) };
    },
  }));
  reg('quote', pick({
    bar: (g, X) => ({ e: X.mk('', text(X, g, 48, 400, { fontStyle: 'italic', borderLeft: `4px solid ${X.C.accent}`,
                                                       paddingLeft: px(X, 28) }), X.esc(g.text || '')),
                      motion: crisp({ inDur: .35 }) }),
  }));
  reg('contrast', pick({
    arrow: (g, X) => {
      // the old idea dimmed, the new one bright: two lines, nothing else
      const e = X.mk('', text(X, g, 50, 600),
        `<div class="part" style="opacity:0;font-weight:400;font-size:${px(X, 40)}"><span style="opacity:.5">${X.esc(g.before || '')}</span></div>` +
        `<div class="part" style="opacity:0;margin-top:12px"><span style="color:${X.C.accent}">→</span> ${X.esc(g.after || '')}</div>`);
      const d = Math.max(.5, (g.end - g.start) * .4);
      return { e, parts: [...e.querySelectorAll('.part')],
               motion: crisp({ in: 'none', inDur: 0, partIn: 'fade', partDur: .3, partAt: i => g.start + i * d }) };
    },
  }));
  reg('tip', pick({
    label: (g, X) => ({ e: X.mk('', text(X, g, 46, 500), `<span style="font-weight:700;color:${X.C.accent}">Tip —</span> ` +
                                   X.esc(g.text || '')), motion: crisp() }),
  }));
  reg('lower_third', (g, X) => ({ e: X.mk('', text(X, g, 30, 500, { opacity: .92 }), X.esc(g.text || '')), motion: crisp() }));
  reg('reaction', (g, X) => ({
    e: X.mk('', Object.assign(X.box(g), { fontSize: px(X, 88), lineHeight: 1, fontFamily: '"Apple Color Emoji", sans-serif',
      filter: X.DECO.emoji_shadow ? 'drop-shadow(0 4px 8px rgba(0,0,0,.25))' : 'none' }), X.esc(g.emoji || '')),
    motion: crisp() }));
  reg('pointer', (g, X) => {
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, '#FFFFFF', 3));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: crisp({ in: 'none', inDur: 0 }) };
  });
})();
