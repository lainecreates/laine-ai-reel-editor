"""What a reference reel's EDITING looks like, measured (Stage 5).

Extends reference.py (pacing, loudness, contact sheet) with visual traits:

  captions    where they sit, words at a time, letter case, size, colour,
              how often they change (word-by-word vs lines), on boxes or not
  graphics    other on-screen text: how often, where, upper case, on boxes
  zooms       from the speaker's face size over time: punch-ins vs slow pushes
  colour      overall mood (bright/dark, saturated/muted, warm/cool)

Measured with Apple Vision (tools/text.js, tools/faces.js) on frames sampled
a few times per second, plus plain pixel statistics. Nothing is copied: the
reference's own words are kept only in `seen_text`, so a plan can be checked
never to reuse them; no image from it is ever drawn into a customer's reel.
"""

import json
import platform
import re
import shutil
import statistics as st
import subprocess
import tempfile
from pathlib import Path

from . import config
from .tools import require, run

FPS = 3
CATEGORIES = ["captions", "typography", "animation", "graphics", "zooms", "pacing", "colour"]


def _frames(path, tmp, fps=FPS):
    run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
         "-vf", f"fps={fps},scale=540:-2", "-q:v", "3", str(tmp / "frame_%05d.jpg")])
    return sorted(tmp.glob("frame_*.jpg"))


def _vision(script, folder):
    if platform.system() != "Darwin" or not shutil.which("osascript"):
        return None
    out = run(["osascript", "-l", "JavaScript", config.PROJECT_ROOT / "tools" / script, folder], check=False)
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", "", str(t).lower()).strip()


def _pixels(img, box, size=(540, 960)):
    """RGB pixels inside a normalised box of a frame (small sample)."""
    W, H = size
    x, y, w, h = box
    cx, cy, cw, ch = int(x * W), int(y * H), max(2, int(w * W)), max(2, int(h * H))
    raw = subprocess.run([require("ffmpeg"), "-loglevel", "error", "-i", str(img), "-vf",
                          f"scale={W}:{H},crop={cw}:{ch}:{cx}:{cy},scale=24:8:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]


def _hsv(p):
    r, g, b = (v / 255 for v in p)
    mx, mn = max(r, g, b), min(r, g, b)
    s = 0 if mx == 0 else (mx - mn) / mx
    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        h = 60 * ((b - r) / (mx - mn)) + 120
    else:
        h = 60 * ((r - g) / (mx - mn)) + 240
    return h, s, mx


def _text_look(img, box):
    """Is the text white or coloured, and is it sitting on a solid box?"""
    x, y, w, h = box          # a little wider than the letters, to see any box around them
    px = _pixels(img, (max(0, x - w * .08), max(0, y - h * .25), min(1 - max(0, x - w * .08), w * 1.16),
                       min(1 - max(0, y - h * .25), h * 1.5)))
    if not px:
        return None
    hsv = [_hsv(p) for p in px]
    bright_col = [h for h, s, v in hsv if s > .45 and v > .45]
    white = sum(1 for h, s, v in hsv if s < .18 and v > .82)
    # a solid box: one colour fills most of the text's rectangle
    buckets = {}
    for p in px:                       # coarse colour buckets: video compression adds noise
        k = tuple(v // 64 for v in p)
        buckets[k] = buckets.get(k, 0) + 1
    solid = max(buckets.values()) / len(px)
    sat_fill = sum(1 for h, s, v in hsv if s > .5 and v > .35) / len(px)
    solid = max(solid, sat_fill)       # a strong colour behind the letters is a box too
    return {"coloured": len(bright_col) > .12 * len(px) and len(bright_col) > white * .5,
            "white": white > .12 * len(px), "boxed": solid > .5}


def _band(y):
    return "upper_third" if y < .4 else "center" if y < .56 else "lower_third"


def analyse_visual(path, duration, cut_times=()):
    """Visual editing traits of a reference reel, or {"available": False}."""
    tmp = Path(tempfile.mkdtemp(prefix="laine-ref-"))
    try:
        frames = _frames(path, tmp)
        texts = _vision("text.js", tmp)
        faces = _vision("faces.js", tmp) or {}
        if texts is None or not frames:
            return {"available": False, "why": "needs macOS (Apple Vision)"}
        names = [f.name for f in frames]
        n = len(names)
        # 1. background text (printed on clothes, signs): same place, most of the reel
        seen = {}
        for nm in names:
            for it in texts.get(nm, []):
                key = (_norm(it["text"]), round(it["box"][0], 1), round(it["box"][1], 1))
                seen[key] = seen.get(key, 0) + 1
        static = {k for k, c in seen.items() if c >= .5 * n}
        # low-confidence reads are background print (clothes, signs), not editing
        items = {nm: [it for it in texts.get(nm, []) if it["conf"] >= .5 and _norm(it["text"]) and
                      (_norm(it["text"]), round(it["box"][0], 1), round(it["box"][1], 1)) not in static]
                 for nm in names}
        # 2. the caption band: where text appears in the most frames
        hist = {}
        for nm in names:
            for b in {round((it["box"][1] + it["box"][3] / 2) / .05) for it in items[nm]}:
                hist[b] = hist.get(b, 0) + 1
        band = max(hist, key=hist.get) * .05 if hist else None
        # captions can run to two lines: the band spans about 2.6 line heights
        near = [it["box"][3] for nm in names for it in items[nm]
                if band is not None and abs(it["box"][1] + it["box"][3] / 2 - band) <= .05]
        reach = max(.06, 2.6 * st.median(near)) if near else .06
        caps, gfx = {}, {}
        for nm in names:
            for it in items[nm]:
                cy = it["box"][1] + it["box"][3] / 2
                (caps if band is not None and -reach * .5 <= cy - band <= reach else gfx).setdefault(nm, []).append(it)
        cap_frames = [nm for nm in names if caps.get(nm)]
        out = {"available": True, "frames": n, "fps": FPS}
        if cap_frames:
            words = [sum(len(it["text"].split()) for it in caps[nm]) for nm in cap_frames]
            texts_seq = [" ".join(_norm(it["text"]) for it in sorted(caps.get(nm, []), key=lambda i: i["box"][0])) for nm in names]
            changes = sum(1 for a, b in zip(texts_seq, texts_seq[1:]) if b and a != b)
            letters = "".join(it["text"] for nm in cap_frames for it in caps[nm])
            up = sum(c.isupper() for c in letters) / max(1, sum(c.isalpha() for c in letters))
            heights = [it["box"][3] for nm in cap_frames for it in caps[nm]]
            looks = [lk for nm in cap_frames[:: max(1, len(cap_frames) // 20)] for it in caps[nm][:2]
                     for lk in [_text_look(tmp / nm, it["box"])] if lk]
            per_change = changes / max(.1, duration)
            wpc = st.median(words)
            out["captions"] = {
                "present": len(cap_frames) / n > .25,
                "position": _band(band), "y": round(band, 2),
                "words_at_a_time": wpc,
                "changes_per_second": round(per_change, 2),
                "style_guess": "word_pop" if wpc <= 2 and per_change >= .9 else "phrase_lines",
                "case": "upper" if up > .8 else "lower" if up < .05 else "as_spoken",
                "size": ("small" if st.median(heights) < .032 else "large" if st.median(heights) > .05 else "medium"),
                "line_height": round(st.median(heights), 3),
                "coloured_words": round(sum(1 for l in looks if l["coloured"]) / max(1, len(looks)), 2),
                "on_boxes": round(sum(1 for l in looks if l["boxed"]) / max(1, len(looks)), 2),
            }
        # 3. graphics: other text, grouped into appearances
        gframes = [i for i, nm in enumerate(names) if gfx.get(nm)]
        runs, last = [], -9
        for i in gframes:
            if i - last > 2:
                runs.append([i])
            else:
                runs[-1].append(i)
            last = i
        gy = [it["box"][1] + it["box"][3] / 2 for nm in names for it in gfx.get(nm, [])]
        gl = "".join(it["text"] for nm in names for it in gfx.get(nm, []))
        glooks = [lk for r in runs for nm in [names[r[len(r) // 2]]] for it in gfx[nm][:1]
                  for lk in [_text_look(tmp / nm, it["box"])] if lk]
        out["graphics"] = {
            "appearances": len(runs),
            "per_minute": round(len(runs) / max(.1, duration) * 60, 1),
            "typical_position": _band(st.median(gy)) if gy else None,
            "upper_case": round(sum(c.isupper() for c in gl) / max(1, sum(c.isalpha() for c in gl)), 2) if gl else None,
            "on_boxes": round(sum(1 for l in glooks if l["boxed"]) / max(1, len(glooks)), 2) if glooks else None,
            "average_seconds_on_screen": round(st.mean(len(r) for r in runs) / FPS, 1) if runs else 0,
        }
        # 4. zooms from the face size over time: a lasting jump in face size is a
        #    punch-in (often right on a jump cut); a steady rise is a slow push
        raw = [max((b[3] for b in faces.get(nm) or []), default=None) for nm in names]
        fh = []
        for i in range(n):                       # median of 3 removes detector jitter
            win = [h for h in raw[max(0, i - 1):i + 2] if h]
            fh.append(st.median(win) if win else None)
        punches = pushes = 0
        i = 1
        while i < n:
            a, b = fh[i - 1], fh[i]
            ra, rb = raw[i - 1], raw[i]
            held = i + 2 < n and rb and all(raw[k] and raw[k] >= rb * .95 for k in (i + 1, i + 2))
            if ra and rb and rb / ra >= 1.08 and held:            # instant jump that holds
                punches += 1
                while i + 1 < n and raw[i + 1] and raw[i + 1] >= rb * .93:
                    i += 1
                i += 1
                continue
            if a and b and b > a:
                k = i
                while k + 1 < n and fh[k + 1] and fh[k + 1] > fh[k]:
                    k += 1
                if (k - i + 1) / FPS >= 1.0 and fh[k] / a >= 1.06:
                    pushes += 1
                    i = k + 1
                    continue
            i += 1
        out["zooms"] = {"face_tracked": sum(1 for h in raw if h) / n > .5,
                        "punch_ins": punches, "slow_pushes": pushes,
                        "per_minute": round((punches + pushes) / max(.1, duration) * 60, 1),
                        "kind": ("none" if punches + pushes == 0 else "punchy" if punches > pushes * 2 else
                                 "subtle" if pushes > punches * 2 else "mixed")}
        # 5. colour mood
        px = []
        for f in frames[:: max(1, n // 12)]:
            px += _pixels(f, (0, 0, 1, 1))
        hsv = [_hsv(p) for p in px] or [(0, 0, 0)]
        sat, val = st.mean(s for h, s, v in hsv), st.mean(v for h, s, v in hsv)
        warm = sum(1 for h, s, v in hsv if s > .15 and (h < 70 or h > 300)) / max(1, sum(1 for h, s, v in hsv if s > .15))
        out["colour"] = {"brightness": round(val, 2), "saturation": round(sat, 2), "warmth": round(warm, 2),
                         "mood": f"{'bright' if val > .6 else 'dark' if val < .35 else 'mid-tone'}, "
                                 f"{'saturated' if sat > .45 else 'muted' if sat < .22 else 'natural'}, "
                                 f"{'warm' if warm > .6 else 'cool' if warm < .35 else 'neutral'}"}
        # 6. their words, kept only to make sure they are never reused
        # text split across stacked boxes ("THREE TIPS / FOR BETTER / VIDEOS") counts as one
        # phrase: everything on screen at a moment, top to bottom, left to right
        seen = {_norm(it["text"]) for nm in names for it in items[nm] if len(_norm(it["text"])) > 2}
        for nm in names:
            for group in (gfx.get(nm, []), caps.get(nm, [])):
                if group:
                    seen.add(" ".join(_norm(it["text"]) for it in sorted(group, key=lambda i: (round(i["box"][1], 2), i["box"][0]))))
        out["seen_text"] = sorted(s for s in seen if s)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# -- what the customer likes about it ---------------------------------------------

def validate_prefs(value):
    v = dict(value or {})
    use = [c for c in v.get("use") or [] if c in CATEGORIES]
    avoid = [c for c in v.get("avoid") or [] if c in CATEGORIES and c not in use]
    bad = [c for c in (v.get("use") or []) + (v.get("avoid") or []) if c not in CATEGORIES]
    if bad:
        raise ValueError(f"Unknown part of a reel: {bad[0]} (use: {', '.join(CATEGORIES)})")
    return {"use": use, "avoid": avoid, "notes": str(v.get("notes") or "").strip()[:2000]}


def inspired_settings(visual, reference, prefs):
    """Brand settings that would bring the parts they LIKE closer to the reference.
    Only proposals: Claude reads them to the customer, who decides (their own
    settings always win). Nothing for parts they don't like or didn't mention."""
    use = set((prefs or {}).get("use") or [])
    out, why = {}, {}
    cap = (visual or {}).get("captions") or {}
    if "captions" in use and cap.get("present"):
        out["caption_position"] = cap["position"]; why["caption_position"] = f"their captions sit in the {cap['position'].replace('_', ' ')}"
        out["caption_style"] = cap["style_guess"]; why["caption_style"] = f"{cap['words_at_a_time']} word(s) at a time"
        out["caption_size"] = cap["size"]; why["caption_size"] = f"{cap['size']} lettering"
    if ("captions" in use or "typography" in use) and cap.get("present"):
        out["caption_case"] = cap["case"]; why["caption_case"] = {"upper": "ALL CAPS", "lower": "all lowercase",
                                                                  "as_spoken": "normal case"}[cap["case"]]
    z = (visual or {}).get("zooms") or {}
    if ("zooms" in use or "animation" in use) and z.get("face_tracked"):
        if z["kind"] == "none":
            out["zoom_style"] = "none"; why["zoom_style"] = "no zooms"
        else:
            out["zoom_style"] = z["kind"]
            out["zoom_frequency"] = "frequent" if z["per_minute"] >= 10 else "moderate" if z["per_minute"] >= 4 else "rare"
            why["zoom_style"] = f"{z['punch_ins']} punch-ins and {z['slow_pushes']} slow pushes ({z['per_minute']}/min)"
    if "pacing" in use and (reference or {}).get("suggests"):
        out["pacing"] = reference["suggests"]["pacing"]
        why["pacing"] = f"{reference.get('cuts_per_minute')} cuts/min, {reference.get('words_per_minute')} words/min"
    g = (visual or {}).get("graphics") or {}
    if "graphics" in use and g:
        out["graphics_density"] = "busy" if g["per_minute"] >= 10 else "balanced" if g["per_minute"] >= 4 else "minimal"
        why["graphics_density"] = f"{g['per_minute']} text graphics a minute"
    return {"settings": out, "why": why}


def save(visual, folder=None):
    d = Path(folder) if folder else config.brand_dir() / "reference"
    d.mkdir(parents=True, exist_ok=True)
    (d / "visual.json").write_text(json.dumps(visual, indent=1, ensure_ascii=False))
    return d / "visual.json"


def load(folder=None):
    p = (Path(folder) if folder else config.brand_dir() / "reference") / "visual.json"
    return json.loads(p.read_text()) if p.exists() else None
