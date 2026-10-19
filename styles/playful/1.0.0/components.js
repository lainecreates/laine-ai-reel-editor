// Playful: fun, friendly, hand-made. Chunky rounded type on tilted stickers,
// speech bubbles, starbursts, name tags; scattered angles; squash-and-stretch.
// Boxes, sticker borders and hard shadows are this style's declared
// decorations: each one disappears when the customer switches it off.
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['playful.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  const css = st => Object.entries(st).map(([k, v]) => `${k.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}:${v}`).join(';');
  // a scribbled tick, drawn in the brand's main colour
  const tick = (X, size) => `<svg width="${size}" height="${size}" viewBox="0 0 40 40" style="flex:none">` +
    `<path d="M6 22 C 11 25, 14 30, 16 33 C 21 22, 28 12, 36 6" fill="none" stroke="${X.C.primary}" ` +
    `stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  const tilt = g => ((parseInt(String(g.id).replace(/\D/g, ''), 10) || 0) % 2 ? 4 : -6);   // deterministic
  const sticker = (X, g, bg, fg, extra) => Object.assign(X.box(g), {
    background: X.DECO.graphic_box ? bg : 'transparent', color: X.DECO.graphic_box ? fg : '#FFFFFF',
    borderRadius: '36px', padding: '22px 34px', textAlign: 'center',
    border: X.DECO.graphic_border && X.DECO.graphic_box ? '7px solid #FFFFFF' : 'none',
    // layered sticker: a second sticker in the brand's highlight colour peeks out behind
    boxShadow: X.DECO.graphic_shadow && X.DECO.graphic_box ? `14px 14px 0 ${bg === X.C.accent ? X.C.primary : X.C.accent}` : 'none',
    textShadow: X.DECO.graphic_box ? 'none' : '0 4px 14px rgba(0,0,0,.45)',
    fontFamily: X.FONTVAR.headline, fontWeight: 900, lineHeight: 1.05 }, extra || {});
  const bounce = (g, extra) => Object.assign({ in: 'squash', inDur: .5, out: 'pop', outDur: .22,
                                               extra: `rotate(${tilt(g)}deg)` }, extra || {});
  const wobble = (e, g, amp) => t => {
    const w = Math.sin((t - g.start) * 5.5) * amp;
    e.style.transform += ` rotate(${X_q(w)}deg)`;
    return X_q(w);
  };
  const X_q = v => Math.round(v * 100) / 100;

  const bubbleTail = (X, color, left) => X.DECO.graphic_box ? `<div style="position:absolute;left:${left}px;bottom:-34px;` +
    `width:0;height:0;border-left:22px solid transparent;border-right:22px solid transparent;` +
    `border-top:36px solid ${color}"></div>` : '';
  reg('hook', pick({
    sticker: (g, X) => {
      const e = X.mk('', sticker(X, g, X.C.primary, X.C.onPrimary, { fontSize: px(X, 70) }), X.esc(g.text || ''));
      return { e, motion: bounce(g) };
    },
    bubble: (g, X) => {
      const e = X.mk('', sticker(X, g, X.C.primary, X.C.onPrimary, { fontSize: px(X, 64), borderRadius: '54px',
        border: 'none', position: 'absolute' }), X.esc(g.text || '') + bubbleTail(X, X.C.primary, 90));
      return { e, motion: bounce(g, { extra: 'rotate(-3deg)' }) };
    },
    badge: (g, X) => {
      // a round badge with a dashed inner ring, like a pin on a jacket
      const ring = X.DECO.graphic_box ? `<div style="position:absolute;inset:14px;border-radius:50%;` +
        `border:4px dashed ${X.rgba(X.C.onAccent.length === 7 ? X.C.onAccent : '#FFFFFF', .55)}"></div>` : '';
      const e = X.mk('', sticker(X, g, X.C.accent, X.C.onAccent, { fontSize: px(X, 58), borderRadius: '50%',
        padding: '70px 64px', position: 'absolute' }), ring + `<span style="position:relative">${X.esc(g.text || '')}</span>`);
      return { e, motion: bounce(g, { in: 'pop', inDur: .45, extra: 'rotate(7deg)' }) };
    },
  }));
  reg('headline_bar', (g, X) => {
    const e = X.mk('', sticker(X, g, X.rgba(X.C.accent.length === 7 ? X.C.accent : '#FFD400', .92), X.C.onAccent,
      { fontSize: px(X, 40), borderRadius: '6px', padding: '14px 28px', border: 'none' }), X.esc(g.text || ''));
    return { e, motion: bounce(g, { extra: 'rotate(-2deg)' }) };
  });
  reg('key_phrase', (g, X) => {
    // a speech bubble with a little tail
    const tail = X.DECO.graphic_box ? `<div style="position:absolute;left:70px;bottom:-34px;width:0;height:0;` +
      `border-left:22px solid transparent;border-right:22px solid transparent;border-top:36px solid #FFFFFF"></div>` : '';
    const e = X.mk('', sticker(X, g, '#FFFFFF', '#1D1D1F', { fontSize: px(X, 56), borderRadius: '48px',
      border: 'none', position: 'absolute' }), X.esc(g.text || '') + tail);
    return { e, motion: bounce(g) };
  });
  reg('quote', pick({
    bubble: (g, X) => {
      const e = X.mk('', sticker(X, g, '#FFFFFF', '#1D1D1F', { fontSize: px(X, 52), borderRadius: '48px',
        border: 'none', position: 'absolute' }), `“${X.esc(g.text || '')}”` + bubbleTail(X, '#FFFFFF', 70));
      return { e, motion: bounce(g) };
    },
    thought: (g, X) => {
      // a cloud-ish bubble with two little circles trailing off
      const dots = X.DECO.graphic_box ? [[60, -40, 34], [26, -78, 20]].map(([l, b, d]) =>
        `<div style="position:absolute;left:${l}px;bottom:${b}px;width:${d}px;height:${d}px;border-radius:50%;` +
        `background:#FFFFFF"></div>`).join('') : '';
      const e = X.mk('', sticker(X, g, '#FFFFFF', '#1D1D1F', { fontSize: px(X, 50), borderRadius: '80px',
        border: 'none', position: 'absolute', fontStyle: 'italic' }), X.esc(g.text || '') + dots);
      return { e, motion: bounce(g, { in: 'pop', inDur: .45, extra: 'rotate(2deg)' }) };
    },
  }));
  const starburst = (g, X) => {
    const n = 12, pts = [];
    for (let i = 0; i < n * 2; i++) {
      const r = i % 2 ? 0.72 : 1, a = Math.PI * i / n;
      pts.push(`${50 + 50 * r * Math.cos(a)},${50 + 50 * r * Math.sin(a)}`);
    }
    const burst = X.DECO.graphic_box ? `<svg viewBox="0 0 100 100" style="position:absolute;inset:0;width:100%;height:100%">` +
      `<polygon points="${pts.join(' ')}" fill="${X.C.accent}" stroke="#FFFFFF" stroke-width="${X.DECO.graphic_border ? 2.5 : 0}"/></svg>` : '';
    const e = X.mk('', Object.assign(X.box(g), { height: g.geo.h + 'px', display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontFamily: X.FONTVAR.headline, fontWeight: 900, fontSize: px(X, 110),
      color: X.DECO.graphic_box ? X.C.onAccent : '#FFFFFF',
      filter: X.DECO.graphic_shadow ? 'drop-shadow(8px 10px 0 rgba(0,0,0,.25))' : 'none' }),
      burst + starText(X, g.text));
    return { e, motion: bounce(g, { in: 'pop', inDur: .45, extra: 'rotate(-8deg)' }) };
  };
  // the number big, any other words small underneath, so it all stays inside the shape
  const starText = (X, t) => {
    const m = String(t || '').match(/^(.*?)(\d[\d.,]*\s?%?)(.*)$/);
    const rest = m ? (m[1] + ' ' + m[3]).trim() : '';
    if (!m || !rest) return `<span style="position:relative">${X.esc(t || '')}</span>`;
    return `<span style="position:relative;display:flex;flex-direction:column;align-items:center;max-width:62%;` +
      `text-align:center"><span>${X.esc(m[2].trim())}</span><span style="font-size:${px(X, 34)};line-height:1.05;` +
      `margin-top:6px">${X.esc(rest)}</span></span>`;
  };
  reg('stat', pick({
    starburst,
    blob: (g, X) => {
      const blob = X.DECO.graphic_box ? `<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">` +
        `<path d="M50 4 C 74 2, 97 20, 95 48 C 93 76, 76 97, 48 95 C 20 93, 3 74, 5 47 C 7 22, 27 6, 50 4 Z" ` +
        `fill="${X.C.primary}" stroke="#FFFFFF" stroke-width="${X.DECO.graphic_border ? 2.5 : 0}"/></svg>` : '';
      const e = X.mk('', Object.assign(X.box(g), { height: g.geo.h + 'px', display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontFamily: X.FONTVAR.headline, fontWeight: 900, fontSize: px(X, 104),
        color: X.DECO.graphic_box ? X.C.onPrimary : '#FFFFFF', textAlign: 'center', padding: '0 40px',
        filter: X.DECO.graphic_shadow ? `drop-shadow(10px 10px 0 ${X.C.accent})` : 'none' }),
        blob + starText(X, g.text));
      return { e, motion: bounce(g, { extra: 'rotate(5deg)' }) };
    },
  }));
  const stack = q => (g, X) => {
    const items = (g.items || []).map((it, i) => {
      const bg = i % 2 ? X.C.accent : X.C.primary, fg = i % 2 ? X.C.onAccent : X.C.onPrimary;
      const st = sticker(X, g, bg, fg, { fontSize: px(X, 46), padding: '14px 28px', borderRadius: '28px',
                                          display: 'inline-block', margin: '8px 0', position: 'relative' });
      delete st.left; delete st.top; delete st.width;
      const css = Object.entries(st).map(([k, v]) => `${k.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}:${v}`).join(';');
      return `<div class="part" data-tf=" rotate(${i % 2 ? 2.5 : -2.5}deg)" style="${css};opacity:0">` +
             `${q ? '❓ ' : ''}${X.esc(it.text)}</div>`;
    }).join('<br>');
    const e = X.mk('', Object.assign(X.box(g), { textAlign: 'center' }), items);
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: { in: 'none', inDur: 0, out: 'pop', outDur: .2, partIn: 'squash', partDur: .42 } };
  };
  const notebook = (g, X) => {
    // a lined notebook page; each item gets a scribbled tick as it's said
    const lined = X.DECO.graphic_box ? `background:#FFFFFF repeating-linear-gradient(transparent 0 ${Math.round(70 * X.sc) - 3}px,` +
      `${X.rgba(X.C.primary, .3)} ${Math.round(70 * X.sc) - 3}px ${Math.round(70 * X.sc)}px);color:#1D1D1F;` : 'color:#FFFFFF;';
    const items = (g.items || []).map(it =>
      `<div class="part" style="display:flex;gap:18px;align-items:center;min-height:${px(X, 70)};opacity:0">` +
      `${tick(X, Math.round(46 * X.sc))}<span>${X.esc(it.text)}</span></div>`).join('');
    const e = X.mk('', Object.assign(X.box(g), {
      fontFamily: X.FONTVAR.hand, fontSize: px(X, 46), lineHeight: 1.1, padding: '26px 34px 26px 40px',
      borderRadius: '10px', textAlign: 'left',
      borderLeft: X.DECO.graphic_box && X.DECO.graphic_border ? `6px solid ${X.C.accent}` : 'none',
      boxShadow: X.DECO.graphic_shadow && X.DECO.graphic_box ? `12px 12px 0 ${X.C.accent}` : 'none',
      textShadow: X.DECO.graphic_box ? 'none' : '0 4px 14px rgba(0,0,0,.45)' }), '');
    e.setAttribute('style', e.getAttribute('style') + ';' + lined);
    e.innerHTML = items;
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: bounce(g, { extra: 'rotate(-2deg)', partIn: 'pop', partDur: .35 }) };
  };
  reg('list', pick({ stickers: stack(false), notebook }));
  reg('question_list', stack(true));
  reg('cta', pick({
    pill: (g, X) => {
      const e = X.mk('', sticker(X, g, X.C.accent, X.C.onAccent, { fontSize: px(X, 58), borderRadius: '999px' }),
        `👉 ${X.esc(g.text || '')}`);
      return { e, motion: bounce(g, { extra: '', tick: wobble(e, g, 2.5) }) };
    },
    arrow_sticker: (g, X) => {
      // a sticker with a hand-drawn arrow curling down towards the caption / comments
      const arrow = `<svg width="${Math.round(120 * X.sc)}" height="${Math.round(110 * X.sc)}" viewBox="0 0 120 110" ` +
        `style="position:absolute;right:-${Math.round(40 * X.sc)}px;bottom:-${Math.round(96 * X.sc)}px">` +
        `<path d="M20 8 C 70 6, 100 40, 84 92" fill="none" stroke="${X.DECO.graphic_box ? X.C.primary : '#FFFFFF'}" stroke-width="8" stroke-linecap="round"/>` +
        `<path d="M64 76 L 84 96 L 102 72" fill="none" stroke="${X.DECO.graphic_box ? X.C.primary : '#FFFFFF'}" stroke-width="8" ` +
        `stroke-linecap="round" stroke-linejoin="round"/></svg>`;
      const e = X.mk('', sticker(X, g, X.C.primary, X.C.onPrimary, { fontSize: px(X, 56), position: 'absolute' }),
        X.esc(g.text || '') + arrow);
      return { e, motion: bounce(g, { extra: 'rotate(-4deg)' }) };
    },
  }));
  reg('contrast', pick({
    xcheck: (g, X) => {
      // two stickers: the old way crossed, then the new way ticked
      const mark = (ok, color) => `<span style="display:inline-flex;align-items:center;justify-content:center;` +
        `width:1.1em;height:1.1em;border-radius:50%;background:${color};color:#FFFFFF;font-size:.8em;margin-right:14px">` +
        `${ok ? '✓' : '✕'}</span>`;
      const one = (txt, ok, i) => {
        const st = sticker(X, g, ok ? X.C.accent : '#FFFFFF', ok ? X.C.onAccent : '#1D1D1F', {
          fontSize: px(X, ok ? 54 : 44), padding: '14px 28px', borderRadius: '28px', display: 'inline-flex',
          alignItems: 'center', margin: '10px 0', position: 'relative' });
        delete st.left; delete st.top; delete st.width;
        return `<div class="part" data-tf=" rotate(${i ? 2.5 : -3}deg)" style="${css(st)};opacity:0">` +
          `${X.DECO.graphic_box ? mark(ok, ok ? X.C.primary : '#1D1D1F') : ''}` +
          `<span style="${ok ? '' : 'text-decoration:line-through;text-decoration-thickness:4px;opacity:.8'}">${X.esc(txt)}</span></div>`;
      };
      const e = X.mk('', Object.assign(X.box(g), { textAlign: 'center' }),
        one(g.before || '', false, 0) + '<br>' + one(g.after || '', true, 1));
      const d = Math.max(.6, (g.end - g.start) * .4);
      return { e, parts: [...e.querySelectorAll('.part')],
               motion: { in: 'none', inDur: 0, out: 'pop', outDur: .2, partIn: 'squash', partDur: .42,
                         partAt: i => g.start + i * d } };
    },
  }));
  reg('tip', pick({
    postit: (g, X) => {
      // a sticky note with a strip of tape
      const tape = X.DECO.graphic_box ? `<div style="position:absolute;left:50%;top:-18px;width:120px;height:36px;` +
        `transform:translateX(-50%) rotate(-3deg);background:rgba(255,255,255,.6)"></div>` : '';
      const e = X.mk('', Object.assign(X.box(g), {
        background: X.DECO.graphic_box ? (X.C.sticky || X.C.accent) : 'transparent',
        color: X.DECO.graphic_box ? '#1D1D1F' : '#FFFFFF', padding: '34px 38px 30px', borderRadius: '6px',
        fontFamily: X.FONTVAR.hand, fontSize: px(X, 50), lineHeight: 1.15, textAlign: 'left', position: 'absolute',
        boxShadow: X.DECO.graphic_shadow && X.DECO.graphic_box ? '8px 10px 0 rgba(0,0,0,.18)' : 'none',
        textShadow: X.DECO.graphic_box ? 'none' : '0 4px 14px rgba(0,0,0,.45)' }),
        tape + `<div style="font-family:${X.FONTVAR.headline};font-weight:900;font-size:${px(X, 28)};letter-spacing:.14em;` +
        `color:${X.DECO.graphic_box ? X.C.primary : X.C.accent};margin-bottom:10px">TIP</div>${X.esc(g.text || '')}`);
      return { e, motion: bounce(g, { extra: 'rotate(-3deg)' }) };
    },
  }));
  reg('lower_third', (g, X) => {
    const e = X.mk('', sticker(X, g, '#FFFFFF', '#1D1D1F', { padding: 0, overflow: 'hidden', fontSize: px(X, 40) }),
      (X.DECO.graphic_box ? `<div style="background:${X.C.primary};color:${X.C.onPrimary};font-size:${px(X, 22)};` +
       `letter-spacing:.2em;padding:8px 0">HELLO, I'M</div>` : '') +
      `<div style="padding:12px 20px">${X.esc(g.text || '')}</div>`);
    return { e, motion: bounce(g) };
  });
  reg('reaction', (g, X) => {
    const lines = [0, 60, 120, 180, 240, 300].map(a =>
      `<div style="position:absolute;left:50%;top:50%;width:10px;height:34px;border-radius:5px;background:${X.C.accent};` +
      `transform:translate(-50%,-50%) rotate(${a}deg) translateY(-${Math.round(g.geo.h * .55)}px)"></div>`).join('');
    const e = X.mk('', Object.assign(X.box(g), { height: g.geo.h + 'px', display: 'flex', alignItems: 'center',
      justifyContent: 'center', fontSize: px(X, 160), lineHeight: 1, fontFamily: '"Apple Color Emoji", sans-serif',
      filter: X.DECO.emoji_shadow ? 'drop-shadow(0 10px 12px rgba(0,0,0,.3))' : 'none' }),
      (X.DECO.graphic_box ? lines : '') + `<span style="position:relative">${X.esc(g.emoji || '')}</span>`);
    return { e, motion: bounce(g, { inDur: .45 }) };
  });
  reg('pointer', (g, X) => {
    // a hand-drawn doodle arrow: same draw-on as the original, wobbly line
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, X.C.primary, 9).replace(/C (\d+) (\d+)/, (m, a, b) => `C ${+a + 18} ${+b - 14}`));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: { in: 'none', inDur: 0, out: 'pop', outDur: .2 } };
  });
})();
