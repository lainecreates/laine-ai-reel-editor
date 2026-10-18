#!/usr/bin/env python3
"""Do uploaded assets really end up in the rendered video?

Uses a temporary library and a temporary copy of the brand (never the
customer's own), a synthetic test reel in workspace/_tests/, and checks the
finished MP4 itself:
  - font:   the headline is drawn in the uploaded font (Chrome's report)
  - sound:  a 1200 Hz tone uploaded as the headline sound is in the audio,
            and a 600 Hz tone requested at 3.0 s is there too
  - logo:   magenta pixels where the logo sits, on every frame checked
  - image:  the screenshot requested at 3.0 s is drawn where layout put it
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="laine-assets-"))
os.environ["LAINE_LIBRARY_DIR"] = str(TMP / "lib")
os.environ["LAINE_BRAND_DIR"] = str(TMP / "brand")
os.environ["LAINE_REELS_WORKSPACE"] = str(ROOT / "workspace" / "_tests")
sys.path.insert(0, str(ROOT / "scripts"))

from laine_reel import brand, library, pipeline, review  # noqa: E402
from laine_reel.project import Reel, read_json  # noqa: E402

FONT = "/System/Library/Fonts/Supplemental/Impact.ttf"


def sh(*cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True)


def tone_level(video, start, dur, freq):
    """Peak level (dB) of a narrow band around `freq` in a stretch of audio."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start}", "-t", f"{dur}",
                          "-i", str(video), "-vn", "-af",
                          f"bandpass=f={freq}:width_type=h:w=60,bandpass=f={freq}:width_type=h:w=60,"
                          "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    import re
    m = re.search(r"max_volume: (-?[\d.]+) dB", err)
    return float(m.group(1)) if m else -99.0


def pixel(video, t, x, y, w, h):
    """Average RGB of a region of one frame."""
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t}", "-i",
                          str(video), "-frames:v", "1", "-vf",
                          f"crop={w}:{h}:{x}:{y},scale=1:1:flags=area", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return tuple(raw[:3])


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


def main():
    ok = True
    try:
        sys.path.insert(0, str(ROOT / "tests"))
        from fixture_brand import write_test_brand
        write_test_brand(TMP / "brand", sfx="playful")   # clearly audible effects
        # assets
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=1200:d=0.5",
           TMP / "headline-tone.wav")
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=600:d=0.5",
           "-c:a", "libmp3lame", TMP / "requested-tone.mp3")
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
           "color=c=0xFF00FF:s=300x120,format=rgba", "-frames:v", "1", TMP / "logo.png")
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
           "color=c=0x00C000:s=1080x1350", "-frames:v", "1", TMP / "screenshot.jpg")
        font = library.add_file(FONT, name="My Bold")
        hsound = library.add_file(TMP / "headline-tone.wav", name="Headline tone", category="pop")
        rsound = library.add_file(TMP / "requested-tone.mp3", name="Requested tone")
        logo = library.add_file(TMP / "logo.png", name="Logo")
        shot = library.add_file(TMP / "screenshot.jpg", name="Screenshot", category="screenshot")

        for old in (ROOT / "workspace" / "_tests").glob("*-assets-check*"):
            shutil.rmtree(old, ignore_errors=True)   # earlier runs of this check only
        fixture = ROOT / "tests" / ".fixtures" / "messy.mp4"
        if not fixture.exists():
            raise SystemExit("Run tests/selftest.py once first (it builds the test clips).")
        reel, _ = pipeline.run_all(fixture, name="assets-check")
        brand.save_settings({"font_files": {"headline": font["id"]},
                             "sound_map": {"headline": hsound["id"]},
                             "logo": {"id": logo["id"], "position": "top_left", "size": 200,
                                      "opacity": 1.0}}, "reel", reel.root)
        review.save_feedback(reel, {"version": None, "headline": {"choose_for_me": True},
                                    "add": {"graphics": [{"type": "image", "asset": shot["id"],
                                                          "t": 3.0, "duration": 2.0}],
                                            "zooms": [],
                                            "sfx": [{"kind": "library:" + rsound["id"], "t": 3.0}]}})
        (reel.root / "review").mkdir(exist_ok=True)
        (reel.root / "review" / "suggestions.json").write_text(
            json.dumps({"headlines": ["light is the secret", "my setup"]}))
        res = review.apply_feedback(reel)
        pipeline.stage_design(reel)
        out, checks = pipeline.stage_final(reel, preview=True)
        print("\n  Results for uploaded assets in the rendered video")
        ok &= check("render checks all passed", all(checks.values()), str(checks))
        ok &= check("Choose for me picked the strongest headline",
                    any("light is the secret" in a and "chosen for you" in a for a in res["applied"]))
        fonts = read_json(reel.work / "overlay" / "frames" / "fonts.json")
        head = next(x for x in fonts if x["role"] == "headline")
        ok &= check("headline drawn in the uploaded font", head["family"].startswith('"Impact"')
                    or head["family"].startswith("Impact"), head["family"].split(",")[0])
        edit = read_json(reel.path("edit.json"))
        hs = next(s for s in edit["sfx"] if s["event"] == "headline")
        ok &= check("headline sound is the uploaded file", hs["file"] == hsound["path"])
        # same moment, clean cut (no effects) vs final: the difference is the sound
        clean = reel.video_out
        lvl_on = tone_level(out, max(0, hs["at"]), 0.5, 1200)
        lvl_base = tone_level(clean, max(0, hs["at"]), 0.5, 1200)
        ok &= check("uploaded headline sound is heard in the final audio", lvl_on > lvl_base + 8,
                    f"1200 Hz {lvl_on:.1f} dB in the final vs {lvl_base:.1f} dB without effects")
        rq = next(s for s in edit["sfx"] if s.get("event") == "requested")
        lvl_r = tone_level(out, rq["at"], 0.5, 600)
        lvl_r_base = tone_level(clean, rq["at"], 0.5, 600)
        ok &= check("sound requested at 3.0 s is heard there", lvl_r > lvl_r_base + 8,
                    f"600 Hz {lvl_r:.1f} dB vs {lvl_r_base:.1f} dB without effects")
        lay = read_json(reel.path("layout.json"))
        g1 = lay["graphics"]
        logo_id = next(g["id"] for g in edit["graphics"] if g.get("role") == "logo")
        others = [v for k, v in g1.items() if k != logo_id and not v.get("allow_face")]
        from laine_reel import layout as _L
        lr = (g1[logo_id]["x"], g1[logo_id]["y"], g1[logo_id]["w"], g1[logo_id]["h"])
        ok &= check("nothing drawn on top of the logo",
                    all(_L._overlap(lr, (v["x"], v["y"], v["w"], v["h"])) == 0 for v in others))
        lay = read_json(reel.path("layout.json"))
        lg = next(v for k, v in lay["graphics"].items()
                  if any(g["id"] == k and g.get("role") == "logo" for g in edit["graphics"]))
        for t in (0.5, 2.5, edit["duration"] - 0.3):
            r, g_, b = pixel(out, t, lg["x"] + 20, lg["y"] + 20, 40, 30)
            ok &= check(f"logo visible at {t:.1f}s", r > 200 and b > 200 and g_ < 80, f"rgb {r},{g_},{b}")
        sg = next(g for g in edit["graphics"] if g["type"] == "image" and g.get("role") != "logo")
        sgeo = lay["graphics"][sg["id"]]
        mid = (sg["start"] + sg["end"]) / 2
        r, g_, b = pixel(out, mid, sgeo["x"] + 40, sgeo["y"] + 40, 60, 60)
        ok &= check(f"screenshot drawn at {mid:.1f}s where layout placed it", g_ > 150 and r < 90,
                    f"rgb {r},{g_},{b}")
        r2, g2, b2 = pixel(out, sg["start"] - 0.4, sgeo["x"] + 40, sgeo["y"] + 40, 60, 60)
        ok &= check("screenshot not there before its time", not (g2 > 150 and r2 < 90),
                    f"rgb {r2},{g2},{b2}")
        from laine_reel.verify import verify as _verify
        res_v = _verify(reel, out)
        for c in res_v["checks"]:
            ok &= check("verify-assets: " + c["what"], c["ok"], c["detail"])
        ok &= check("your real brand and library untouched",
                    not (ROOT / "assets" / "library" / "library.json").exists() or
                    all(a["id"] not in (font["id"], logo["id"]) for a in
                        json.loads((ROOT / "assets" / "library" / "library.json").read_text())["assets"]))
    finally:
        if not os.environ.get("KEEP_ASSET_TMP"):
            shutil.rmtree(TMP, ignore_errors=True)
        else:
            print("kept", TMP)
    print("\nASSETS CHECK " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
