// Magazine: editorial and curated. Letter-spaced kicker labels, serif
// headlines, pull quotes, numbered columns and hairline rules on paper cards
// (the brand's lightest colour), left-aligned grid, mask wipes.
// Several designs per intent (g.variant, chosen by designs.py); the first is
// the original design and the default.
(() => {
  const reg = (k, f) => { window.COMPONENTS['magazine.' + k] = f; };
  const pick = designs => (g, X) => (designs[g.variant] || designs[Object.keys(designs)[0]])(g, X);
  // "80% of creators quit" -> ["80%", "of creators quit"]
  const splitNum = t => { const m = String(t || '').match(/^(.*?)(\d[\d.,]*\s?%?)(.*)$/);
                          return m ? [m[2].trim(), (m[1] + ' ' + m[3]).trim()] : null; };
  const px = (X, n) => Math.round(n * X.sc) + 'px';
  // A kicker can be written per graphic later (creative brief); until then, by intent.
  const KICKER = { hook: 'The story', key_phrase: 'Key point', stat: 'By the numbers', list: 'The list',
                   question_list: 'The questions', cta: 'Next', lower_third: 'By', headline_bar: '',
                   quote: 'In her words', contrast: 'Rethink', tip: 'Tip', contents: 'Contents' };
  // The highlight colour on the paper card must be readable: when the card is tinted from
  // the highlight itself (e.g. sage on sage), use whichever brand colour reads best.
  const lum = hex => { const c = [1, 3, 5].map(i => parseInt(String(hex).slice(i, i + 2), 16) / 255)
    .map(v => (v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4)));
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const ink = X => {
    if (!X.DECO.graphic_box || !/^#[0-9a-f]{6}$/i.test(String(X.C.card))) return X.C.accent;
    if (contrast(X.C.accent, X.C.card) >= 3) return X.C.accent;
    return [X.C.primary, X.C.cardText].filter(c => /^#[0-9a-f]{6}$/i.test(String(c)))
      .sort((a, b) => contrast(b, X.C.card) - contrast(a, X.C.card))[0] || X.C.accent;
  };
  const paper = (X, g, extra) => {
    const on = X.DECO.graphic_box;
    return Object.assign(X.box(g), { background: on ? X.C.card : 'transparent', color: on ? X.C.cardText : '#FFFFFF',
      padding: on ? '30px 38px 32px' : '0', textAlign: 'left', fontFamily: X.FONTVAR.body,
      textShadow: on ? 'none' : '0 3px 16px rgba(0,0,0,.45)',
      boxShadow: X.DECO.graphic_shadow ? '0 18px 40px rgba(0,0,0,.25)' : 'none' }, extra || {});
  };
  const kicker = (X, text) => text ? `<div style="font-family:${X.FONTVAR.body};font-size:${px(X, 21)};` +
    `letter-spacing:.3em;text-transform:uppercase;color:${ink(X)};font-weight:700;margin-bottom:12px">` +
    `${X.esc(text)}</div><div class="rule" style="height:2px;background:currentColor;opacity:.8;` +
    `transform-origin:left center;transform:scaleX(0);margin-bottom:18px"></div>` : '';
  const serif = (X, size, extra) => `font-family:${X.FONTVAR.headline};font-size:${px(X, size)};font-weight:700;` +
    `line-height:1.04;letter-spacing:-.01em;${extra || ''}`;
  const rules = (e, g, delay) => t => {
    const p = Math.max(0, Math.min(1, (t - g.start - delay) / .6));
    const k = Math.round((p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2) * 1000) / 1000;
    e.querySelectorAll('.rule').forEach(r => { r.style.transform = `scaleX(${k})`; });
    return k;
  };
  const wipe = (e, g, extra) => Object.assign({ in: 'wipe_right', inDur: .6, out: 'wipe_left', outDur: .3,
                                                tick: rules(e, g, .3) }, extra || {});
  // a box line is a border: it follows the "no outlines / no boxes" rules
  const keyline = X => X.DECO.graphic_border ? `2px solid ${ink(X)}` : 'none';

  reg('hook', pick({
    kicker: (g, X) => {
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.hook) +
        `<div style="${serif(X, 74)}">${X.esc(g.text || '')}</div>`);
      return { e, motion: wipe(e, g) };
    },
    masthead: (g, X) => {
      // a magazine's title block: double rule, big caps, issue line
      const dbl = `<div class="rule" style="height:6px;border-top:2px solid currentColor;border-bottom:1px solid currentColor;` +
        `transform:scaleX(0)"></div>`;
      const e = X.mk('', paper(X, g, { textAlign: 'center' }), dbl +
        `<div style="${serif(X, 80, 'text-transform:uppercase;letter-spacing:.02em;margin:18px 0 14px')}">${X.esc(g.text || '')}</div>` +
        dbl + (X.handle ? `<div style="font-size:${px(X, 20)};letter-spacing:.32em;text-transform:uppercase;margin-top:12px">` +
                          `${X.esc(X.handle)}</div>` : ''));
      return { e, motion: wipe(e, g, { in: 'mask_open' }) };
    },
    cover: (g, X) => {
      // a cover line: a huge number beside the words when the hook has one
      const sp = splitNum(g.text);
      const body = sp ? `<div style="display:flex;gap:24px;align-items:center">` +
          `<span style="${serif(X, 190, `color:${X.C.primary};line-height:.8`)}">${X.esc(sp[0])}</span>` +
          `<span style="${serif(X, 56, 'text-transform:uppercase')}">${X.esc(sp[1])}</span></div>`
        : `<div style="${serif(X, 78, 'text-transform:uppercase')}">${X.esc(g.text || '')}</div>`;
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || 'Cover story') + body);
      return { e, motion: wipe(e, g, { in: 'wipe_up' }) };
    },
  }));
  reg('headline_bar', (g, X) => {
    const e = X.mk('', paper(X, g, { textAlign: 'center', padding: X.DECO.graphic_box ? '16px 28px' : '0' }),
      `<div class="rule" style="height:1px;background:currentColor;transform:scaleX(0)"></div>` +
      `<div style="${serif(X, 34, 'letter-spacing:.24em;text-transform:uppercase;font-weight:400;margin:10px 0')}">` +
      `${X.esc(g.text || '')}</div><div class="rule" style="height:1px;background:currentColor;transform:scaleX(0)"></div>`);
    return { e, motion: wipe(e, g, { in: 'mask_open' }) };
  });
  reg('key_phrase', (g, X) => {
    const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.key_phrase) +
      `<div style="display:flex;gap:16px;align-items:flex-start">` +
      `<span style="${serif(X, 120, `color:${ink(X)};line-height:.8`)}">“</span>` +
      `<span style="${serif(X, 50, 'font-style:italic;font-weight:400;line-height:1.15')}">${X.esc(g.text || '')}</span></div>`);
    return { e, motion: wipe(e, g) };
  });
  reg('stat', pick({
    numeral: (g, X) => {
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.stat) +
        `<div style="${serif(X, 150, 'line-height:.95')}">${X.esc(g.text || '')}</div>`);
      return { e, motion: wipe(e, g, { in: 'wipe_up' }) };
    },
    bar: (g, X) => {
      // a bar chart that fills to the percentage that was said
      const sp = splitNum(g.text) || [g.text || '', ''];
      const pct = Math.max(0, Math.min(100, parseFloat(String(sp[0]).replace(',', '.')) || 0));
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.stat) +
        `<div style="display:flex;align-items:baseline;gap:20px"><span style="${serif(X, 120, 'line-height:.95')}">` +
        `${X.esc(sp[0])}</span><span style="font-size:${px(X, 34)};line-height:1.2">${X.esc(sp[1])}</span></div>` +
        `<div style="position:relative;height:${px(X, 26)};margin-top:18px;background:${X.rgba(X.C.primary, .22)}">` +
        `<div class="fill" style="position:absolute;left:0;top:0;bottom:0;width:${pct}%;background:${X.C.primary};` +
        `transform-origin:left center;transform:scaleX(0)"></div></div>`);
      const base = rules(e, g, .3);
      return { e, motion: wipe(e, g, { in: 'wipe_up', tick: t => {
        const p = Math.max(0, Math.min(1, (t - g.start - .5) / .9));
        const k = Math.round((1 - Math.pow(1 - p, 3)) * 1000) / 1000;
        e.querySelector('.fill').style.transform = `scaleX(${k})`;
        return base(t) + ':' + k; } }) };
    },
  }));
  const column = q => (g, X) => {
    const items = (g.items || []).map((it, i) =>
      `<div class="part" style="display:flex;gap:22px;align-items:baseline;padding:12px 0;opacity:0;` +
      `border-top:${i ? '1px solid currentColor' : 'none'}">` +
      `<span style="${serif(X, 38, `color:${ink(X)}`)}">${q ? 'Q.' : String(i + 1).padStart(2, '0')}</span>` +
      `<span style="font-size:${px(X, 40)};line-height:1.2">${X.esc(it.text)}</span></div>`).join('');
    const e = X.mk('', paper(X, g), kicker(X, g.kicker || (q ? KICKER.question_list : KICKER.list)) + items);
    return { e, parts: [...e.querySelectorAll('.part')], motion: wipe(e, g, { in: 'mask_open', inDur: .45,
             partIn: 'wipe_right', partDur: .45 }) };
  };
  const contents = (g, X) => {
    // a contents page: words, dotted leader, page-style number
    const items = (g.items || []).map((it, i) =>
      `<div class="part" style="display:flex;gap:14px;align-items:baseline;padding:10px 0;opacity:0">` +
      `<span style="font-size:${px(X, 40)};line-height:1.2">${X.esc(it.text)}</span>` +
      `<span style="flex:1;border-bottom:3px dotted currentColor;opacity:.55;transform:translateY(-6px)"></span>` +
      `<span style="${serif(X, 38, `color:${ink(X)}`)}">${String(i + 1).padStart(2, '0')}</span></div>`).join('');
    const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.contents) + items);
    return { e, parts: [...e.querySelectorAll('.part')], motion: wipe(e, g, { in: 'mask_open', inDur: .45,
             partIn: 'fade', partDur: .4 }) };
  };
  reg('list', pick({ column: column(false), contents }));
  reg('question_list', column(true));
  reg('cta', pick({
    footer: (g, X) => {
      const e = X.mk('', paper(X, g, { padding: X.DECO.graphic_box ? '20px 34px' : '0' }),
        `<div class="rule" style="height:3px;background:${ink(X)};transform-origin:left center;transform:scaleX(0);margin-bottom:14px"></div>` +
        `<div style="font-size:${px(X, 34)};letter-spacing:.2em;text-transform:uppercase;font-weight:700">` +
        `${X.esc(g.kicker || KICKER.cta)} &nbsp;→&nbsp; <span style="${serif(X, 50, 'letter-spacing:0;text-transform:none')}">` +
        `${X.esc(g.text || '')}</span></div>`);
      return { e, motion: wipe(e, g, { tick: rules(e, g, 0) }) };
    },
    boxed: (g, X) => {
      // an editor's note in a keyline box
      const e = X.mk('', paper(X, g, { border: keyline(X), textAlign: 'center',
                                       padding: X.DECO.graphic_box || X.DECO.graphic_border ? '26px 34px' : '0' }),
        `<div style="font-size:${px(X, 22)};letter-spacing:.32em;text-transform:uppercase;font-weight:700;color:${ink(X)}">` +
        `${X.esc(g.kicker || "Editor's note")}</div>` +
        `<div style="${serif(X, 54, 'margin-top:12px')}">${X.esc(g.text || '')}</div>`);
      return { e, motion: wipe(e, g, { in: 'mask_open' }) };
    },
  }));
  reg('quote', pick({
    pull: (g, X) => {
      // a centred pull quote between rules, accent quotation marks
      const e = X.mk('', paper(X, g, { textAlign: 'center' }),
        `<div class="rule" style="height:2px;background:currentColor;transform:scaleX(0)"></div>` +
        `<div style="${serif(X, 52, 'font-style:italic;font-weight:400;line-height:1.18;margin:22px 0')}">` +
        `<span style="color:${ink(X)}">“</span>${X.esc(g.text || '')}<span style="color:${ink(X)}">”</span></div>` +
        `<div class="rule" style="height:2px;background:currentColor;transform:scaleX(0)"></div>`);
      return { e, motion: wipe(e, g, { in: 'mask_open' }) };
    },
    siderule: (g, X) => {
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.quote) +
        `<div style="border-left:6px solid ${ink(X)};padding-left:26px">` +
        `<span style="${serif(X, 50, 'font-style:italic;font-weight:400;line-height:1.18')}">${X.esc(g.text || '')}</span></div>`);
      return { e, motion: wipe(e, g) };
    },
  }));
  reg('contrast', pick({
    strike: (g, X) => {
      // "Not this — this": the old idea crossed out, the new one in the headline serif
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.contrast) +
        `<div style="position:relative;display:inline-block;font-size:${px(X, 40)};opacity:.7">${X.esc(g.before || '')}` +
        `<div class="rule" style="position:absolute;left:0;right:0;top:52%;height:4px;background:${ink(X)};` +
        `transform-origin:left center;transform:scaleX(0)"></div></div>` +
        `<div style="${serif(X, 64, 'margin-top:14px')}">${X.esc(g.after || '')}</div>`);
      return { e, motion: wipe(e, g, { tick: rules(e, g, .5) }) };
    },
  }));
  reg('tip', pick({
    tip_card: (g, X) => {
      const e = X.mk('', paper(X, g), kicker(X, g.kicker || KICKER.tip) +
        `<div style="display:flex;gap:20px;align-items:flex-start"><span style="${serif(X, 64, `color:${ink(X)};line-height:.9`)}">→</span>` +
        `<span style="${serif(X, 50, 'font-weight:400;line-height:1.15')}">${X.esc(g.text || '')}</span></div>`);
      return { e, motion: wipe(e, g) };
    },
  }));
  reg('lower_third', (g, X) => {
    const e = X.mk('', paper(X, g, { padding: X.DECO.graphic_box ? '14px 24px' : '0' }),
      `<div style="font-size:${px(X, 24)};letter-spacing:.3em;text-transform:uppercase">` +
      `${KICKER.lower_third} <b>${X.esc(g.text || '')}</b></div>` +
      `<div class="rule" style="height:1px;margin-top:10px;background:currentColor;transform-origin:left center;transform:scaleX(0)"></div>`);
    return { e, motion: wipe(e, g) };
  });
  reg('reaction', (g, X) => {
    const e = X.mk('', Object.assign(X.box(g), { fontSize: px(X, 100), lineHeight: 1, textAlign: 'center',
      fontFamily: '"Apple Color Emoji", sans-serif', filter: X.DECO.emoji_shadow ? 'drop-shadow(0 6px 10px rgba(0,0,0,.3))' : 'none' }),
      X.esc(g.emoji || ''));
    return { e, motion: { in: 'wipe_up', inDur: .4, out: 'fade', outDur: .3 } };
  });
  reg('pointer', (g, X) => {
    const e = X.mk('', { left: g.geo.x + 'px', top: g.geo.y + 'px', width: g.geo.w + 'px', height: g.geo.h + 'px' },
      X.arrow(g.direction, ink(X), 4));
    const svg = e.querySelector('svg'); svg.setAttribute('width', g.geo.w); svg.setAttribute('height', g.geo.h);
    return { e, motion: { in: 'none', inDur: 0, out: 'wipe_left', outDur: .3 } };
  });
})();
