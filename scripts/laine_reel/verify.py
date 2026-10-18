"""Prove the customer's own assets are in the finished video.

Compares the final render with the clean cut (same cuts, no graphics or
effects), so whatever differs is what was added:

  sounds  - the customer's sound file is matched against the final audio at
            the moment it should play (normalised cross-correlation, a waveform
            fingerprint), and must match far better there than in the clean cut
  images  - the region where an image (or the logo) sits must differ from the
            clean cut while it's on screen, and not before it appears
  fonts   - Chrome must report the uploaded font as actually loaded, and the
            elements meant to use it must use it
"""

import array
import math
import subprocess
import wave
from pathlib import Path

from .project import read_json
from .tools import require

RATE = 8000


def _pcm(video, tmp):
    out = Path(tmp)
    subprocess.run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                    "-vn", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(out)], check=True)
    with wave.open(str(out), "rb") as w:
        data = array.array("h", w.readframes(w.getnframes()))
    out.unlink()
    return data


def _rms_db(x):
    if not x:
        return -120.0
    r = math.sqrt(sum(v * v for v in x) / len(x)) or 1.0
    return 20 * math.log10(r / 32768.0)


def _match(sig, tpl, at, search=0.08):
    """Best normalised cross-correlation of a sound template in `sig` near
    time `at` (+- search seconds). 1.0 = identical waveform."""
    if not tpl:
        return 0.0
    # skip silent lead-in of the template so its start lines up
    k = next((i for i, v in enumerate(tpl) if abs(v) > 300), 0)
    tpl = tpl[k:k + int(0.4 * RATE)]
    n = len(tpl)
    tnorm = math.sqrt(sum(v * v for v in tpl)) or 1.0
    best = 0.0
    start = int((at - search) * RATE) + k
    for off in range(max(0, start), max(0, start) + int(2 * search * RATE), 2):
        seg = sig[off:off + n]
        if len(seg) < n:
            break
        snorm = math.sqrt(sum(v * v for v in seg)) or 1.0
        c = sum(a * b for a, b in zip(seg, tpl)) / (snorm * tnorm)
        best = max(best, abs(c))
    return best


def _lag(fa, ca):
    """Samples by which the final's audio trails the clean cut (encoder delay)."""
    best, lag_best = -1.0, 0
    for at in (2.0, 6.0):
        a0, n = int(at * RATE), 4000
        a = fa[a0:a0 + n]
        an = math.sqrt(sum(x * x for x in a)) or 1.0
        for lag in range(-400, 401, 2):
            c = ca[a0 - lag:a0 - lag + n] if a0 - lag >= 0 else []
            if len(c) < n:
                continue
            cn = math.sqrt(sum(y * y for y in c)) or 1.0
            r = sum(x * y for x, y in zip(a, c)) / (an * cn)
            if r > best:
                best, lag_best = r, lag
    return lag_best


def _effects_only(fa, ca, lag):
    """Final audio minus the clean cut: what was added (sounds, music)."""
    out = array.array("h", [0]) * len(fa)
    for i in range(len(fa)):
        j = i - lag
        y = ca[j] if 0 <= j < len(ca) else 0
        out[i] = max(-32768, min(32767, fa[i] - y))
    return out


def _region(video, t, x, y, w, h):
    raw = subprocess.run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
                          "-i", str(video), "-frames:v", "1", "-vf",
                          f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)},scale=24:24:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return raw


def _overlaps(r, geo):
    x, y, w, h = r
    return min(x + w, geo["x"] + geo["w"]) > max(x, geo["x"]) and \
        min(y + h, geo["y"] + geo["h"]) > max(y, geo["y"])


def _diff(a, b):
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / max(n, 1)


def verify(reel, final=None):
    """Return {"ok": bool, "checks": [{"what", "ok", "detail"}]}."""
    edit = read_json(reel.path("edit.json"))
    lay = read_json(reel.path("layout.json"))
    final = Path(final or reel.output / f"{reel.slug}-final.mp4")
    clean = reel.video_out
    checks = []

    def add(what, ok, detail):
        checks.append({"what": what, "ok": bool(ok), "detail": detail})

    # sounds ---------------------------------------------------------------
    customs = [s for s in edit.get("sfx", []) if s.get("custom")]
    if customs:
        fa = _pcm(final, reel.work / "verify_final.wav")
        ca = _pcm(clean, reel.work / "verify_clean.wav")
        fx = _effects_only(fa, ca, _lag(fa, ca))   # her voice removed, effects left
        for s in customs:
            what = f"sound “{s['kind']}” at {s['at']:.1f}s"
            if s.get("missing_custom") or not s.get("file"):
                add(what, False, "missing from the library")
                continue
            tpl = _pcm(s["file"], reel.work / "verify_sound.wav")[: int(0.6 * RATE)]
            m_fx = _match(fx, tpl, s["at"])
            m_clean = _match(ca, tpl, s["at"])
            add(what, m_fx > 0.25 and m_fx > m_clean + 0.15,
                f"waveform match {m_fx:.2f} in the added audio vs {m_clean:.2f} in the clean cut")

    # images and logo ------------------------------------------------------------
    for g in edit.get("graphics", []):
        if g["type"] != "image":
            continue
        geo = lay["graphics"].get(g["id"])
        if not geo:
            add(f"image {g['id']}", False, "not placed")
            continue
        x, y, w, h = geo["x"] + 4, geo["y"] + 4, max(8, geo["w"] - 8), max(8, geo["h"] - 8)
        label = "your logo" if g.get("role") == "logo" else f"image “{g.get('text') or g['asset']}”"
        times = [g["start"] + 0.5, (g["start"] + g["end"]) / 2, g["end"] - 0.3]
        ok, worst = True, 999
        for t in times:
            d = _diff(_region(final, t, x, y, w, h), _region(clean, t, x, y, w, h))
            worst = min(worst, d)
            ok &= d > 12
        detail = f"differs from the clean cut by {worst:.0f}/255 while shown"
        tb = g["start"] - 0.4
        r0 = (x, y, w, h)
        busy = [o for o in edit.get("graphics", []) if o["id"] != g["id"] and o["start"] <= tb < o["end"]
                and lay["graphics"].get(o["id"]) and _overlaps(r0, lay["graphics"][o["id"]])]
        busy += [c for c in edit.get("captions", {}).get("items", []) if c["start"] <= tb < c["end"]
                 and lay.get("captions") and _overlaps(r0, dict(zip("xywh", lay["captions"]["rect"])))]
        # a zoom changes the whole frame, so "just before" can't be compared then
        zoomed = any(z["start"] - 0.1 <= tb <= z["end"] + 0.1 for z in edit.get("zooms", []))
        if g["start"] > 0.6 and not busy and not zoomed:
            before = _diff(_region(final, tb, x, y, w, h), _region(clean, tb, x, y, w, h))
            ok &= before < 12
            detail += f", {before:.0f}/255 just before"
        add(f"{label} ({g['start']:.1f}-{g['end']:.1f}s)", ok, detail)

    # fonts --------------------------------------------------------------------------
    frames = reel.work / "overlay" / "frames"
    loaded = read_json(frames / "fonts_loaded.json") if (frames / "fonts_loaded.json").exists() else {}
    report = read_json(frames / "fonts.json") if (frames / "fonts.json").exists() else []
    from .brand import effective
    fonts = (effective(reel.root) or {}).get("fonts", {})
    for role, key in (("headline", "headline"), ("caption", "body"), ("graphics", "graphics")):
        if not fonts.get("from_library", {}).get("body" if role == "caption" else role):
            continue
        fam = fonts.get(key)
        used = [e for e in report if e["role"] == role]
        uses = all(e["family"].split(",")[0].strip().strip('"\'') == fam for e in used) if used else None
        add(f"uploaded {role} font “{fam}”", loaded.get(fam) is True and uses is not False,
            ("loaded by the renderer" if loaded.get(fam) else "NOT loaded") +
            ("" if uses is None else (", used by every " + role if uses else ", not used")))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
