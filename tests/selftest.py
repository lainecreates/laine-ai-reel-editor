#!/usr/bin/env python3
"""End-to-end self-test with synthetic clips (no real footage needed).

Builds test clips in tests/.fixtures/ with macOS `say` + ffmpeg test video,
runs the full pipeline into workspace/, and checks the results.

    python3 tests/selftest.py            # full test incl. speech re-check
    python3 tests/selftest.py --quick    # skip the speech re-check
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Test reels go to workspace/_tests/, never next to the customer's own reels.
os.environ["LAINE_REELS_WORKSPACE"] = str(ROOT / "workspace" / "_tests")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import config, media, pipeline  # noqa: E402
from laine_reel.project import read_json, sha256, write_json  # noqa: E402

FIX = ROOT / "tests" / ".fixtures"

# [[slnc N]] inserts N ms of silence in macOS `say`.
SCRIPT = ("Hi, this is a test of my new video editor. [[slnc 1600]] "
          "This sentence comes after a long pause. [[slnc 350]] "
          "And this one after a short, natural pause. [[slnc 2200]] "
          "Finally, we check that every word survives the edit.")
# Messy delivery for the cleanup test: a filler, a phrase restart, a
# two-word restart, and an intentional "very very" that must be kept.
MESSY = ("Um, [[slnc 300]] so, [[slnc 250]] today I want to, [[slnc 300]] today I want to show you my setup. "
         "[[slnc 600]] The real, [[slnc 300]] the real secret is light. [[slnc 400]] "
         "It is very very simple.")
EXPECT_WORDS = ["video", "editor", "long", "pause", "natural", "survives"]


def sh(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, capture_output=True)


def make_clip(script, name):
    """Synthetic talking clip: say + 1 s lead/tail silence + test video."""
    speech = FIX / f"{name}.aiff"
    sh("say", "-o", speech, script)
    clip = FIX / f"{name}.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
       "testsrc2=size=1080x1920:rate=30", "-i", speech, "-filter_complex",
       "[1:a]aresample=48000,adelay=1000|1000,apad=pad_dur=1.0[a]", "-map", "0:v",
       "-map", "[a]", "-shortest", "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", clip)
    return clip


def make_fixtures():
    FIX.mkdir(parents=True, exist_ok=True)
    speech = FIX / "speech.aiff"
    if not shutil.which("say"):
        raise SystemExit("`say` (macOS) is needed to synthesise test speech.")
    sh("say", "-o", speech, SCRIPT)
    # 1.2 s silence before, 1.8 s after, faint room noise underneath.
    audio = FIX / "speech.wav"
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", speech,
       "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.002:sample_rate=48000",
       "-filter_complex",
       "[0:a]aresample=48000,adelay=1200|1200,apad=pad_dur=1.8[s];"
       "[s][1:a]amix=inputs=2:duration=first:normalize=0",
       "-ac", "1", audio)
    land = FIX / "talking_landscape.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
       "testsrc2=size=1920x1080:rate=30", "-i", audio, "-shortest",
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", land)
    # Phone-style portrait: stored landscape + 90° rotation metadata.
    rot = FIX / "talking_portrait_rotated.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error", "-display_rotation", "90", "-i", land,
       "-c", "copy", rot)
    return land, rot


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    return cond


def main():
    quick = "--quick" in sys.argv
    # Replace earlier self-test reels (only folders this script creates).
    for old in config.WORKSPACE.glob("*-selftest-*"):
        if (old / "reel.json").exists():
            for f in old.rglob("*"):
                f.chmod(0o644) if f.is_file() else None
            shutil.rmtree(old)
    print("Building fixtures ...")
    land, rot = make_fixtures()
    fixture_hashes = {p: sha256(p) for p in (land, rot)}
    ok = True

    for clip, name, frame, speech in [(land, "selftest-landscape", "cover", not quick),
                                      (rot, "selftest-rotated", "blur", False)]:
        print()
        reel, result = pipeline.run_all(clip, name=name, frame=frame, check_speech=speech)
        src = media.probe(reel.original)
        out = media.probe(reel.video_out)
        edl = read_json(reel.path("edl.json"))
        words = read_json(reel.path("transcript.json"))["words"]
        text = " ".join(w["text"].lower() for w in words)
        print(f"\n  Results for {name}:")
        ok &= check("pipeline verify checks all passed", result["ok"])
        ok &= check(f"output is 1080x1920 (got {out['width']}x{out['height']})",
                    (out["width"], out["height"]) == (1080, 1920))
        ok &= check(f"pauses removed: {src['duration']:.2f}s -> {out['duration']:.2f}s",
                    out["duration"] < src["duration"] - 2.5)
        sil = read_json(reel.path("silences.json"))["silences"]
        short = [x for x in sil if 0.05 < x["start"] and x["end"] - x["start"] <= 0.45]
        big = [c for c in edl["cuts"] if c["kind"] == "pause" and c["end"] - c["start"] > 1.0]
        ok &= check(f"both long pauses cut hard ({len(big)})", len(big) == 2)
        ok &= check(f"short pauses untouched ({len(short)})", short and not any(
            c["start"] < x["end"] and c["end"] > x["start"] for c in edl["cuts"] for x in short))
        # "...a long pause, [pause] and this one": the word must land before
        # the silence that follows it, not after (whisper drift check).
        pw = next(w for w in words if w["text"].lower().startswith("pause,"))
        after = next(x for x in sil if x["end"] > pw["whisper_start"] + 0.2)
        ok &= check(f"word timing: 'pause,' at {pw['start']}s, before silence at {after['start']}s",
                    pw["start"] < after["start"])
        ok &= check("lead and tail silence trimmed",
                    {c["kind"] for c in edl["cuts"]} >= {"lead", "tail"})
        ok &= check("transcript has the expected words",
                    all(w in text for w in EXPECT_WORDS))
        ok &= check("output transcript exists on the cut timeline",
                    reel.path("transcript.cut.json").exists())
        if "speech_similarity" in result:
            ok &= check(f"no words lost (similarity {result['speech_similarity']})",
                        result["speech_similarity"] >= 0.9)
        ok &= check("raw input clip untouched", sha256(clip) == fixture_hashes[clip])
        ok &= check("original copy is read-only", not (reel.original.stat().st_mode & 0o222))
        if name == "selftest-rotated":
            ok &= check(f"rotation detected ({src['rotation']}°, shown {src['width']}x{src['height']})",
                        src["height"] > src["width"])

    # -- content cleanup ---------------------------------------------------
    print()
    messy = make_clip(MESSY, "messy")
    messy_hash = sha256(messy)
    reel, result = pipeline.run_all(messy, name="selftest-cleanup", check_speech=True)
    cl = read_json(reel.path("cleanup.json"))
    heard = " ".join(read_json(reel.path("transcript.json"))["words"][i]["text"]
                     for i in range(len(read_json(reel.path("transcript.json"))["words"])))
    out_words = [w["text"].lower().strip(",.") for w in read_json(reel.path("transcript.cut.json"))["words"]]
    out_text = " ".join(out_words)
    print(f"\n  Results for selftest-cleanup (whisper heard: {heard})")
    ok &= check("pipeline verify checks all passed (incl. clean joins)", result["ok"])
    ok &= check(f"'today I want to' kept exactly once ({out_text.count('today i want to')})",
                out_text.count("today i want to") == 1)
    ok &= check(f"'the real' kept exactly once ({out_text.count('the real')})",
                out_text.count("the real") == 1)
    ok &= check("intentional 'very very' kept", "very very" in out_text)
    ok &= check("sentences still complete", "show you my setup" in out_text
                and "secret is light" in out_text)
    if any(c["type"] == "filler" for c in cl["candidates"]):
        ok &= check("filler 'um' removed", "um" not in out_words)
    else:
        print("  [INFO] whisper did not transcribe the synthetic 'um'; filler check skipped")
    ok &= check("messy input clip untouched", sha256(messy) == messy_hash)

    # -- brand onboarding + edit plan (temporary brand folder) ---------------
    import os
    import tempfile
    from laine_reel import brand
    print()
    tmp_brand = tempfile.mkdtemp()
    old = os.environ.get("LAINE_BRAND_DIR")
    os.environ["LAINE_BRAND_DIR"] = tmp_brand
    try:
        script = {"colors": "navy, gold, cream", "fonts": "1", "headline": "opening hook",
                  "caption_color": "1", "sticky_font": "body", "caption_style": "phrase lines",
                  "caption_position": "lower third", "caption_size": "medium",
                  "caption_animation": "fade", "caption_emphasis": "1", "caption_case": "1",
                  "pacing": "natural", "zoom_style": "mixed", "zoom_frequency": "moderate",
                  "graphics_density": "balanced",
                  "graphics_elements": "text callouts, key-phrase cards, cta card",
                  "sfx": "subtle", "music": "none", "aesthetic": "clean minimal",
                  "personality": "clear, calm, kind", "handle": "skip", "reference_reel": "skip"}
        asked = 0
        while True:
            q = brand.next_question()
            if q is None:
                break
            brand.answer(q["id"], script[q["id"]])
            asked += 1
        profile = brand.finish()
        # the reel was cut before this brand existed: move it onto the new brand
        # (reels keep the brand they were made with until told otherwise)
        brand.use_current_defaults(reel.root)
        edit = pipeline.stage_design(reel, brand=profile)
        said = [w["text"] for c in edit["captions"]["items"] for w in c["words"]]
        kept = [w["text"] for w in read_json(reel.path("transcript.cut.json"))["words"]]
        print(f"\n  Results for onboarding + plan ({asked} questions answered)")
        ok &= check("profile saved (brand.json + brand.md)",
                    (Path(tmp_brand) / "brand.json").exists() and (Path(tmp_brand) / "brand.md").exists())
        ok &= check("captions cover every kept word, in order", len(said) == len(kept))
        ok &= check("zooms planned and never overlap", edit["zooms"] and all(
            a["end"] <= b["start"] for a, b in zip(edit["zooms"], edit["zooms"][1:])))
        ok &= check("plan renderable with this ffmpeg (overlay, no drawtext)",
                    all(r["ffmpeg_ok"] for r in edit["render_requirements"]))
        ok &= check("edit-plan.md written", reel.path("edit-plan.md").exists())

        # -- branded render (Chrome overlay + ffmpeg composite) -----------
        print()
        # Claude's review step: replace the draft hook with a real headline.
        hook = next(g for g in edit["graphics"] if g.get("role") == "headline")
        write_json(reel.path("edit.overrides.json"), {"set": {hook["id"]: {"text": "Light is the secret"}}})
        pipeline.stage_design(reel, brand=profile)
        out, fchecks = pipeline.stage_final(reel, preview=True)
        lay = read_json(reel.path("layout.json"))
        tr = read_json(reel.path("faces.json"))
        info = media.probe(out)
        frames = list((reel.work / "overlay" / "frames").glob("f_*.png"))
        print("\n  Results for branded render")
        ok &= check(f"final MP4 is {info['width']}x{info['height']} with audio",
                    (info["width"], info["height"]) == (1080, 1920) and info["has_audio"])
        ok &= check(f"final checks passed incl. follows_brand_profile ({fchecks})",
                    all(fchecks.values()))
        ok &= check(f"overlay frames drawn by Chrome ({len(frames)} unique)", len(frames) > 2)
        ok &= check(f"no face in test pattern -> estimated face used ({tr['source']})",
                    tr["source"] == "estimate")
        ok &= check("captions placed", bool(lay.get("captions")))
    finally:
        if old is None:
            os.environ.pop("LAINE_BRAND_DIR", None)
        else:
            os.environ["LAINE_BRAND_DIR"] = old
        shutil.rmtree(tmp_brand)

    # -- caption sync against ground truth ---------------------------------
    print("\n  Caption sync (speech with known word starts):")
    import sync_bench
    for voice, r in sync_bench.run().items():
        ok &= check(f"{voice}: median {r['median']:+.3f}s, mean error {r['mean_abs']:.3f}s, "
                    f"p90 {r['p90_abs']:.3f}s, {r['late_over_80ms']} late of {r['words']}",
                    abs(r["median"]) <= 0.04 and r["mean_abs"] <= 0.06
                    and r["late_over_80ms"] <= 0.15 * r["words"])

    print("\nSELF-TEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
