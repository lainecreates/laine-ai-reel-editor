// Energetic: fast, kinetic, hype. Heavy italic upper-case type, skewed tags,
// words punching in one by one, counters, whip moves, landing shakes, pulses.
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['energetic.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  const css = st => Object.entries(st).map(([k, v]) => `${k.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}:${v}`).join(';');
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  const r3 = v => Math.round(v * 1000) / 1000;
  const type = (X, g, size, extra) => Object.assign(X.box(g), {
    fontFamily: X.FONTVAR.headline, fontWeight: 900, fontStyle: 'italic', textTransform: 'uppercase',
    fontSize: px(X, size), lineHeight: .95, letterSpacing: '.01em', color: '#FFFFFF', textAlign: 'center',
    textShadow: '0 4px 16px rgba(0,0,0,.45)' }, extra || {});
  const tag = (X, bg, fg) => X.DECO.graphic_box
    ? { background: bg, color: fg, padding: '16px 72px 16px 34px', textShadow: 'none' } : {};   // room for the italic overhang
  // a short shake right after landing, deterministic
  const shake = (e, g, land) => t => {
    const s = t - g.start - land;
    if (s < 0 || s > .25) return 0;
    const x = r3(Math.sin(s * 90) * 10 * (1 - s / .25));
    e.style.transform += ` translateX(${x}px)`;
    return x;
  };
  const whip = (e, g, extra) => Object.assign({ in: 'whip_left', inDur: .22, out: 'whip_right', outDur: .14,
                                                extra: 'skewX(-10deg)', tick: shake(e, g, .22) }, extra || {});

  const punch = (g, X, size, quotes) => {
    const words = String(g.text || '').split(/\s+/).filter(Boolean);
    if (quotes && words.length) { words[0] = '“' + words[0]; words[words.length - 1] += '”'; }
    const tagCss = i => X.DECO.graphic_box
      ? `background:${i % 2 ? '#111111' : X.C.primary};color:${i % 2 ? '#FFFFFF' : X.C.onPrimary};padding:4px 18px;text-shadow:none`
      : `color:#FFFFFF`;
    const e = X.mk('', type(X, g, size), words.map((w, i) =>
      `<span class="part" data-tf=" skewX(-10deg)" style="display:inline-block;margin:6px .08em;opacity:0;${quotes ? 'color:#FFFFFF' : tagCss(i)}">` +
      `${X.esc(w)}</span>`).join(' '));
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: { in: 'none', inDur: 0, out: 'whip_right', outDur: .14, partIn: 'slam', partDur: .12,
                       partAt: i => g.start + i * (quotes ? .14 : .09),
                       tick: shake(e, g, words.length * (quotes ? .14 : .09) + .1) } };
  };
  // a bar that flashes on and off a few times, then stays
  const flash = (t, g, delay) => { const s = t - g.start - delay;
                                   return s < 0 ? 0 : s > .48 ? 1 : (Math.floor(s / .08) % 2 ? .25 : 1); };
  reg('hook', pick({
    tags: (g, X) => punch(g, X, 92, false),
    line: (g, X) => {
      const e = X.mk('', type(X, g, 84), `<span style="display:inline-block">${X.esc(g.text || '')}` +
        `<div class="bar" style="height:${px(X, 14)};margin-top:10px;background:${X.C.accent};opacity:0"></div></span>`);
      const bar = e.querySelector('.bar');
      return { e, motion: whip(e, g, { tick: t => { const o = flash(t, g, .22); bar.style.opacity = o;
                                                    return o + ':' + shake(e, g, .22)(t); } }) };
    },
  }));
  reg('quote', pick({ punch: (g, X) => punch(g, X, 76, true) }));
  reg('headline_bar', (g, X) => {
    const e = X.mk('', type(X, g, 40, tag(X, X.C.primary, X.C.onPrimary)), X.esc(g.text || ''));
    return { e, motion: whip(e, g) };
  });
  reg('key_phrase', (g, X) => {
    const e = X.mk('', type(X, g, 70, tag(X, X.C.primary, X.C.onPrimary)), X.esc(g.text || ''));
    return { e, motion: whip(e, g, { in: 'whip_right' }) };
  });
  const counter = burst => (g, X) => {
    // the number on a skewed tag (readable on any background); plain accent text if boxes are off
    const lines = burst ? [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map(a =>
      `<div class="ray" style="position:absolute;left:50%;top:50%;width:${px(X, 12)};height:${px(X, 70)};background:${X.C.accent};` +
      `transform:translate(-50%,-50%) rotate(${a}deg) translateY(-${Math.round(g.geo.h * .62 + 40)}px) scaleY(0)"></div>`).join('') : '';
    const e = X.mk('', type(X, g, 120, X.DECO.graphic_box ? tag(X, X.C.primary, X.C.onPrimary) : { color: X.C.accent }),
                   lines + '<span class="num" style="position:relative"></span>');
    const rays = [...e.querySelectorAll('.ray')];
    const num = e.querySelector('.num');
    const count = t => {
      const p = Math.max(0, Math.min(1, (t - g.start) / .8));
      num.textContent = X.MOTION.counter(g.text || '', p);
      // burst lines shoot out as the count lands
      const b = Math.max(0, Math.min(1, (t - g.start - .75) / .3));
      rays.forEach(r => { r.style.transform = r.style.transform.replace(/scaleY\([^)]*\)/, `scaleY(${r3(b < 1 ? b : 1)})`);
                          r.style.opacity = r3(1 - Math.max(0, (t - g.start - 1.2) / .4)); });
      return r3(p) + ':' + r3(b);
    };
    num.textContent = g.text || '';    // final size for layout and fit
    return { e, motion: { in: 'slam', inDur: .16, out: 'whip_right', outDur: .14, extra: 'skewX(-8deg)',
                          tick: t => count(t) + ':' + shake(e, g, .8)(t) } };
  };
  reg('stat', pick({ counter: counter(false), burst: counter(true) }));
  const tags = q => (g, X) => {
    const items = (g.items || []).map((it, i) => {
      const bg = i % 2 ? X.C.accent : X.C.primary, fg = i % 2 ? X.C.onAccent : X.C.onPrimary;
      const st = tag(X, bg, fg);
      const css = Object.entries(st).map(([k, v]) => `${k.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}:${v}`).join(';');
      return `<div class="part" data-tf=" skewX(-10deg)" style="display:inline-block;margin:8px 0;opacity:0;${css}">` +
             `${q ? '? ' : ''}${X.esc(it.text)}</div>`;
    }).join('<br>');
    const e = X.mk('', type(X, g, 50), items);
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: { in: 'none', inDur: 0, out: 'whip_right', outDur: .14, partIn: 'whip_left', partDur: .2 } };
  };
  const numbered = (g, X) => {
    // each item lands with a big accent number: #1, #2, #3
    const items = (g.items || []).map((it, i) =>
      `<div class="part" data-tf=" skewX(-10deg)" style="display:flex;align-items:center;gap:22px;justify-content:center;margin:8px 0;opacity:0">` +
      `<span style="font-size:${px(X, 96)};color:${X.C.accent};line-height:.9">#${i + 1}</span>` +
      `<span style="${css(tag(X, X.C.primary, X.C.onPrimary))}">${X.esc(it.text)}</span></div>`).join('');
    const e = X.mk('', type(X, g, 50), items);
    return { e, parts: [...e.querySelectorAll('.part')],
             motion: { in: 'none', inDur: 0, out: 'whip_right', outDur: .14, partIn: 'slam', partDur: .14 } };
  };
  reg('list', pick({ tags: tags(false), counter: numbered }));
  reg('question_list', tags(true));
  const pulseCta = (g, X) => {
    const e = X.mk('', type(X, g, 68, tag(X, X.C.accent, X.C.onAccent)), X.esc(g.text || ''));
    const pulse = t => {
      if (t - g.start < .3) return 0;
      const s = r3(1 + .035 * Math.sin((t - g.start) * 9));
      e.style.transform += ` scale(${s})`;
      return s;
    };
    return { e, motion: { in: 'slam', inDur: .16, out: 'whip_right', outDur: .14, extra: 'skewX(-10deg)', tick: pulse } };
  };
  reg('cta', pick({
    pulse: pulseCta,
    arrows: (g, X) => {
      // chevrons either side flash in sequence, pointing at the words
      const chev = side => `<span class="chev" style="display:inline-block;color:${X.C.accent};text-shadow:none;margin:0 .2em">` +
        `${side ? '‹‹‹' : '›››'}</span>`;
      const e = X.mk('', type(X, g, 64), chev(0) + `<span style="display:inline-block;${css(tag(X, X.C.primary, X.C.onPrimary))}">` +
        `${X.esc(g.text || '')}</span>` + chev(1));
      const ch = [...e.querySelectorAll('.chev')];
      return { e, motion: { in: 'slam', inDur: .16, out: 'whip_right', outDur: .14, extra: 'skewX(-10deg)',
        tick: t => { const on = Math.floor((t - g.start) / .18) % 2 ? .35 : 1;
                     ch.forEach(c => { c.style.opacity = on; }); return on; } } };
    },
  }));
  reg('contrast', pick({
    slash: (g, X) => {
      // the old idea gets slashed, then the answer slams in with a shake
      const e = X.mk('', type(X, g, 56),
        `<div class="part" style="opacity:0;position:relative;display:inline-block;font-size:${px(X, 50)};color:rgba(255,255,255,.7)">` +
        `${X.esc(g.before || '')}<div style="position:absolute;left:-12px;right:-12px;top:44%;height:${px(X, 12)};` +
        `background:${X.C.accent};transform:rotate(-6deg)"></div></div><br>` +
        `<div class="part" data-tf=" skewX(-10deg)" style="opacity:0;display:inline-block;margin-top:16px;font-size:${px(X, 76)};` +
        `${css(tag(X, X.C.primary, X.C.onPrimary))}">${X.esc(g.after || '')}</div>`);
      const d = Math.max(.45, (g.end - g.start) * .35);
      return { e, parts: [...e.querySelectorAll('.part')],
               motion: { in: 'none', inDur: 0, out: 'whip_right', outDur: .14, partIn: 'slam', partDur: .14,
                         partAt: i => g.start + i * d, tick: shake(e, g, d + .14) } };
    },
  }));
  reg('tip', pick({
    flash: (g, X) => {
      const e = X.mk('', type(X, g, 64),
        `<div class="lbl" style="display:inline-block;font-size:${px(X, 40)};${css(tag(X, X.C.accent, X.C.onAccent))};` +
        `${X.DECO.graphic_box ? '' : `color:${X.C.accent}`}">Tip</div><br>` +
        `<div style="display:inline-block;margin-top:12px;${css(tag(X, X.C.primary, X.C.onPrimary))}">${X.esc(g.text || '')}</div>`);
      const lbl = e.querySelector('.lbl');
      return { e, motion: whip(e, g, { tick: t => { const o = flash(t, g, .2); lbl.style.opacity = o;
                                                    return o + ':' + shake(e, g, .22)(t); } }) };
    },
  }));
  reg('lower_third', (g, X) => {
    const e = X.mk('', type(X, g, 36, Object.assign({ textAlign: 'left' }, tag(X, X.C.accent, X.C.onAccent))),
      X.esc(g.text || ''));
    return { e, motion: whip(e, g) };
  });
  reg('reaction', (g, X) => {
    const e = X.mk('', Object.assign(X.box(g), { height: g.geo.h + 'px', fontSize: px(X, 180), lineHeight: 1,
      textAlign: 'center', fontFamily: '"Apple Color Emoji", sans-serif',
      filter: X.DECO.emoji_shadow ? 'drop-shadow(0 10px 12px rgba(0,0,0,.35))' : 'none' }), X.esc(g.emoji || ''));
    return { e, motion: { in: 'slam', inDur: .14, out: 'whip_right', outDur: .14, tick: shake(e, g, .14) } };
  });
  reg('pointer', (g, X) => {
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, X.C.accent, 14));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: { in: 'whip_left', inDur: .2, out: 'whip_right', outDur: .14 } };
  });
})();
