// Motion primitives for style packs (Stage 1 of the creative redesign).
//
// Each primitive maps progress to CSS: pin = entrance progress 0..1, pout =
// remaining-exit progress 1..0 (1 = not exiting). They are pure and
// deterministic (no randomness), so the same reel always renders the same.
// At pin = 1 and pout = 1 every primitive returns the element's resting state.
// Classic doesn't use these; new packs name them in their "motion" aspect.

const MOTION = (() => {
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const easeOut = p => 1 - Math.pow(1 - p, 3);
  const easeInOut = p => (p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  const easeBack = p => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); };
  const r3 = v => Math.round(v * 1000) / 1000;
  const rest = () => ({ opacity: 1, x: 0, y: 0, sx: 1, sy: 1, rot: 0, blur: 0, clip: null });

  // entrance shapes: progress p (0..1) -> partial state
  const IN = {
    none:      p => ({}),
    fade:      p => ({ opacity: easeOut(p) }),
    rise:      p => ({ opacity: easeOut(p), y: 34 * (1 - easeOut(p)) }),
    drop:      p => ({ opacity: easeOut(p), y: -34 * (1 - easeOut(p)) }),
    scale_in:  p => ({ opacity: easeOut(p), sx: .86 + .14 * easeOut(p), sy: .86 + .14 * easeOut(p) }),
    pop:       p => ({ sx: .6 + .4 * easeBack(p), sy: .6 + .4 * easeBack(p) }),
    squash:    p => { const b = easeBack(p), w = Math.sin(Math.PI * clamp(p * 1.4, 0, 1)) * (1 - p);
                      return { sx: (.5 + .5 * b) * (1 + .18 * w), sy: (.5 + .5 * b) * (1 - .18 * w) }; },
    slam:      p => { const q = clamp(p * 1.6, 0, 1); return { opacity: q > 0 ? 1 : 0, sx: 1.45 - .45 * q, sy: 1.45 - .45 * q }; },
    blur_in:   p => ({ opacity: easeOut(p), blur: 14 * (1 - easeOut(p)) }),
    whip_left: p => ({ x: 420 * (1 - easeOut(p)), blur: 10 * (1 - p) }),
    whip_right:p => ({ x: -420 * (1 - easeOut(p)), blur: 10 * (1 - p) }),
    wipe_right:p => ({ clip: `inset(0 ${r3(100 * (1 - easeInOut(p)))}% 0 0)` }),
    wipe_left: p => ({ clip: `inset(0 0 0 ${r3(100 * (1 - easeInOut(p)))}%)` }),
    wipe_up:   p => ({ clip: `inset(${r3(100 * (1 - easeInOut(p)))}% 0 0 0)` }),
    wipe_down: p => ({ clip: `inset(0 0 ${r3(100 * (1 - easeInOut(p)))}% 0)` }),
    mask_open: p => { const h = r3(50 * (1 - easeInOut(p))); return { clip: `inset(${h}% 0 ${h}% 0)` }; },
    draw:      p => ({ sx: easeInOut(p), origin: 'left center' }),   // lines/rules drawing on
  };

  function combine(a, b) {
    const s = Object.assign(rest(), a);
    for (const [k, v] of Object.entries(b)) {
      if (k === 'opacity') s.opacity *= v;
      else if (k === 'sx' || k === 'sy') s[k] *= v;
      else if (k === 'x' || k === 'y' || k === 'rot' || k === 'blur') s[k] += v;
      else s[k] = v;
    }
    return s;
  }

  // Exits reuse entrance shapes, played backwards.
  function state(kindIn, pin, kindOut, pout, opts = {}) {
    let s = combine(rest(), (IN[kindIn] || IN.fade)(clamp(pin, 0, 1)));
    if (pout < 1) s = combine(s, (IN[kindOut] || IN.fade)(clamp(pout, 0, 1)));
    if (opts.shake && opts.t !== undefined && pin >= 1) {
      // a short deterministic shake right after landing (energetic impacts)
      const since = opts.t - (opts.landedAt || 0);
      if (since >= 0 && since < .25) s.x += Math.sin(since * 90) * 9 * (1 - since / .25);
    }
    return s;
  }

  function css(s) {
    const tf = `translate(${r3(s.x)}px, ${r3(s.y)}px) scale(${r3(s.sx)}, ${r3(s.sy)}) rotate(${r3(s.rot)}deg)`;
    return { opacity: String(r3(clamp(s.opacity, 0, 1))), transform: tf,
             filter: s.blur > 0.01 ? `blur(${r3(s.blur)}px)` : 'none',
             clipPath: s.clip || 'none', transformOrigin: s.origin || 'center center' };
  }

  // Children appear one after another: child i starts at i * gap seconds.
  function stagger(t, start, i, gap, dur) {
    return clamp((t - start - i * gap) / dur, 0, 1);
  }

  // Counting numbers up ("0" -> "37%") as the element enters.
  function counter(text, p) {
    const m = String(text).match(/^(\D*)(\d+(?:[.,]\d+)?)(.*)$/);
    if (!m) return text;
    const target = parseFloat(m[2].replace(',', '.'));
    const decimals = (m[2].split(/[.,]/)[1] || '').length;
    const v = target * easeOut(clamp(p, 0, 1));
    return m[1] + v.toFixed(decimals) + m[3];
  }

  return { IN, state, css, stagger, counter, kinds: Object.keys(IN) };
})();
if (typeof module !== 'undefined') module.exports = MOTION;
