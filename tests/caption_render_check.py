#!/usr/bin/env python3
"""Do captions really look the way the brand settings say? (Phase A)

Renders one synthetic talking clip on a dark navy background (where a
half-transparent pink keyword used to look violet) in several caption setups,
then measures the finished MP4 frame by frame:

  - keyword colour: keyword pixels match the brand colour exactly (not a blend)
  - solid: the keyword is at full colour for (nearly) all of its time on screen
  - no fade with animation "none": every frame is all-or-nothing
  - outline: present in the chosen colour when on, absent when off
  - karaoke: a keyword keeps its colour after the highlight moves past it
  - sync: the keyword appears on the frame its caption starts

Uses a temporary brand and library (never yours) and workspace/_tests/.
"""

import colorsys
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="laine-captions-"))
os.environ["LAINE_LIBRARY_DIR"] = str(TMP / "lib")
os.environ["LAINE_BRAND_DIR"] = str(TMP / "brand")
os.environ["LAINE_REELS_WORKSPACE"] = str(ROOT / "workspace" / "_tests")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from fixture_brand import write_test_brand  # noqa: E402
from laine_reel import brand, pipeline  # noqa: E402
from laine_reel.project import read_json  # noqa: E402

FPS = 30
NAVY = "0x1F2A44"
SPEECH = ("Content matters. Lighting changes everything. Post consistently. "
          "Save this video. Comment guide below.")

SETUPS = [
    ("word pop, no animation, pink keywords, black outline (your current look)",
     dict(caption_style="word_pop", caption_animation="none", caption_color="white_primary_keywords",
          caption_emphasis="bigger", colors=["#FF3E8E", "#A3B18A"]), "primary"),
    ("word pop, fade, blue keywords, outline OFF",
     dict(caption_style="word_pop", caption_animation="fade", caption_color="white_primary_keywords",
          caption_emphasis="bigger", colors=["#2F80ED", "#F2C94C"],
          caption_outline={"enabled": False}), "primary"),
    ("phrase lines, pop, orange accent keywords, thin cyan outline",
     dict(caption_style="phrase_lines", caption_animation="pop", caption_color="white_accent_keywords",
          caption_emphasis="accent_color", colors=["#27AE60", "#F2994A"],
          caption_outline={"enabled": True, "color": "#00E5FF", "thickness": "thin", "opacity": 1.0}),
     "accent"),
    ("karaoke, slide up, pink keywords, medium white outline",
     dict(caption_style="karaoke", caption_animation="slide_up", caption_color="white_primary_keywords",
          caption_emphasis="bigger", colors=["#FF3E8E", "#F2C94C"],
          caption_outline={"enabled": True, "color": "#FFFFFF", "thickness": "medium", "opacity": 0.9}),
     "primary"),
]


def sh(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, capture_output=True)


def frames(video, start, dur, rect):
    x, y, w, h = [int(v) for v in rect]
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                          "-i", str(video), "-vf", f"crop={w}:{h}:{x}:{y},fps={FPS}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = w * h * 3
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]


def count(frame, hex_color, tol=70):
    R, G, B = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    c = 0
    for i in range(0, len(frame), 6):         # every other pixel is plenty
        if abs(frame[i] - R) + abs(frame[i + 1] - G) + abs(frame[i + 2] - B) < tol:
            c += 1
    return c


def hue(hex_color):
    return colorsys.rgb_to_hsv(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360


def check(label, ok, detail=""):
    print(f"    [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


def main():
    ok = True
    try:
        for old in (ROOT / "workspace" / "_tests").glob("*-caption-check*"):
            shutil.rmtree(old, ignore_errors=True)
        write_test_brand(TMP / "brand", headline="none", sfx="none", graphics_elements=[])
        sh("say", "-r", "165", "-o", TMP / "voice.aiff", SPEECH)
        clip = TMP / "navy.mp4"
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={NAVY}:s=1080x1920:r=30",
           "-i", TMP / "voice.aiff", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", clip)
        reel, _ = pipeline.run_all(clip, name="caption-check")

        heavy = None   # black-outline pixels with the default heavy outline (setup 1)
        for label, answers, key in SETUPS:
            print(f"\n  {label}")
            write_test_brand(TMP / "brand", headline="none", sfx="none", graphics_elements=[], **answers)
            brand.use_current_defaults(reel.root)
            pipeline.stage_design(reel)
            out, fchecks = pipeline.stage_final(reel, preview=True)
            ok &= check("render checks incl. follows_brand_profile", all(fchecks.values()),
                        "" if all(fchecks.values()) else str(fchecks))
            prof = brand.effective(reel.root)
            kw = prof["colors"]["accent"] if key == "accent" else prof["colors"]["caption_keyword"]
            outline = prof["captions"]["outline"]
            edit = read_json(reel.path("edit.json"))
            lay = read_json(reel.path("layout.json"))
            x, y, w, h = lay["captions"]["rect"]
            rect = (max(0, x - 40), max(0, y - 60), min(1080, w + 80), min(1920 - y + 60, h + 120))
            anim = edit["captions"]["style"]["animation"]
            karaoke = edit["captions"]["style"]["style"] == "karaoke"
            solid_fracs, delays, outline_px, partial = [], [], 0, 0
            kept_colour = []
            for c in edit["captions"]["items"]:
                ems = [k for k, wd in enumerate(c["words"]) if wd.get("emphasis")]
                if not ems:
                    continue
                fr = frames(out, c["start"], c["end"] - c["start"], rect)[1:-1]   # 1-frame edge margin
                if len(fr) < 3:
                    continue
                times = [c["start"] + (k + 1) / FPS for k in range(len(fr))]
                if karaoke:
                    # the keyword shows the highlight colour while it's being spoken:
                    # measure it only before and after that
                    wd = c["words"][ems[0]]
                    idx = [k for k, tt in enumerate(times) if tt < wd["start"] - 0.05 or tt > wd["end"] + 0.1]
                    if ems[0] + 1 < len(c["words"]):
                        after = [k for k, tt in enumerate(times) if tt > wd["end"] + 0.1]
                        if after:
                            # most frames after the highlight (the very end may fade out normally)
                            kept = [count(fr[k], kw) >= 30 for k in after]
                            kept_colour.append(sum(kept) >= 0.6 * len(kept))
                    fr = [fr[k] for k in idx]
                    if not fr:
                        continue
                counts = [count(f, kw) for f in fr]
                ref = sorted(counts)[len(counts) // 2]          # typical (median) keyword size
                if ref < 30:
                    continue
                solid = [n >= 0.5 * ref for n in counts]
                solid_fracs.append(sum(solid) / len(solid))
                if not karaoke:
                    delays.append(solid.index(True) / FPS if True in solid else 9)
                partial += sum(1 for n in counts if 0 < n < 0.5 * ref)
                col = outline["color"] if outline["enabled"] else "#000000"
                outline_px += sum(count(f, col, 110) for f in fr) // len(fr)
            ok &= check(f"keywords drawn in the brand colour {kw} (hue {hue(kw):.0f}°)", bool(solid_fracs),
                        f"{len(solid_fracs)} keyword captions measured")
            if solid_fracs:
                avg = sum(solid_fracs) / len(solid_fracs)
                need = 0.97 if anim == "none" else 0.85
                ok &= check(f"keywords at full colour for {avg:.0%} of their screen time (need {need:.0%})",
                            avg >= need, f"worst caption {min(solid_fracs):.0%}")
                if anim == "none":
                    ok &= check("animation 'none': no faded frames at all", partial == 0,
                                f"{partial} part-faded frames")
                if delays:
                    lim = 1.5 / FPS if anim == "none" else 0.15   # entrances are capped at 0.14 s
                    ok &= check(f"keyword at full colour when its caption starts (within {lim * 1000:.0f} ms)",
                                max(delays) <= lim, f"latest {max(delays) * 1000:.0f} ms")
            if outline["enabled"]:
                ok &= check(f"outline drawn in {outline['color']}", outline_px > 30, f"{outline_px} px per frame")
                if outline["color"] == "#000000" and heavy is None:
                    heavy = outline_px
            else:
                # the soft drop shadow stays (it isn't the outline): far fewer dark pixels
                ok &= check("outline off: black outline gone", heavy and outline_px < 0.02 * heavy,
                            f"{outline_px} dark px per frame (shadow only) vs {heavy} with the outline")
            if karaoke:
                ok &= check("karaoke: keyword keeps its colour after the highlight passes",
                            bool(kept_colour) and all(kept_colour), f"{sum(kept_colour)}/{len(kept_colour)}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nCAPTION CHECK " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
