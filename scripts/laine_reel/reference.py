"""Measure a reference reel the customer likes, to tune their profile.

Read-only: the reference file is never copied or changed. Measures, with
ffmpeg/ffprobe (scene scores, ebur128) and optionally whisper.cpp:

- cuts per minute                  -> how often the frame should change
  (per-frame scene scores; a cut is a score that stands out from the frames
  around it, which also catches jump cuts in a static talking-head shot)
- words per minute                 -> how tight the pacing is
- loudness                         -> how loud they master
and saves a small contact sheet of frames to brand/reference/ so Claude can
look at the visual style (caption placement, colours, graphics). The editing
style itself (captions, graphics, zooms, colour mood) is measured by
reference_style.py.
"""

import re

from . import config, media
from .tools import find_whisper_model, require, run


def analyse(path, transcribe_speech=True):
    path = config.check_not_protected(path)
    info = media.probe(path)
    duration = info["duration"] or 1.0

    cut_times = detect_cuts(path)
    cuts = len(cut_times)

    err = run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vn",
               "-af", "ebur128=framelog=quiet", "-f", "null", "-"], check=False).stderr
    m = re.search(r"I:\s*(-?[\d.]+) LUFS", err)
    loudness = float(m.group(1)) if m else None

    wpm = None
    if transcribe_speech and info["has_audio"] and find_whisper_model():
        from .transcribe import transcribe
        work = config.brand_dir() / "reference"
        work.mkdir(parents=True, exist_ok=True)
        wav = work / "reference16k.wav"
        media.extract_audio(path, wav)
        words = transcribe(wav, find_whisper_model(), work / "reference_whisper")["words"]
        wav.unlink()
        if words:
            speaking = max(1.0, words[-1]["end"] - words[0]["start"])
            wpm = round(len(words) / speaking * 60)

    sheet = _contact_sheet(path, duration)
    cpm = round(cuts / duration * 60, 1)
    from . import reference_style
    visual = reference_style.analyse_visual(path, duration, cut_times)
    reference_style.save(visual)
    return {
        "file": str(path),
        "duration": round(duration, 2),
        "size": f"{info['width']}x{info['height']}",
        "fps": info["fps"],
        "cuts": cuts,
        "cuts_per_minute": cpm,
        "words_per_minute": wpm,
        "loudness_lufs": loudness,
        "contact_sheet": sheet,
        "suggests": suggest(cpm, wpm),
        "visual": {k: v for k, v in visual.items() if k != "seen_text"},
    }


def scene_scores(path):
    """[(time, score)] for every frame (ffmpeg select's scene score)."""
    err = run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
               "scale=320:-2,select='gte(scene,0)',metadata=print:key=lavfi.scene_score",
               "-f", "null", "-"]).stderr
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", err)]
    scores = [float(s) for s in re.findall(r"lavfi\.scene_score=([\d.]+)", err)]
    return list(zip(times, scores))


def detect_cuts(path, floor=0.04, peak_ratio=3.0, window=5, min_gap=0.25):
    return find_cuts(scene_scores(path), floor, peak_ratio, window, min_gap)


def find_cuts(scores, floor=0.04, peak_ratio=3.0, window=5, min_gap=0.25):
    """Frames whose score clears `floor` and is `peak_ratio` x the average of
    the surrounding frames (so camera shake or gestures don't count)."""
    cuts = []
    for i, (t, s) in enumerate(scores):
        if s < floor or t < 0.1:
            continue
        around = [x for _, x in scores[max(0, i - window):i] + scores[i + 1:i + 1 + window]]
        base = sum(around) / len(around) if around else 0.0
        if s >= peak_ratio * max(base, 1e-4) and (not cuts or t - cuts[-1] >= min_gap):
            cuts.append(round(t, 3))
    return cuts


def suggest(cuts_per_minute, words_per_minute):
    """Map measurements to profile settings."""
    if (words_per_minute or 0) >= 175 or cuts_per_minute >= 20:
        pacing = "fast"
    elif (words_per_minute or 0) >= 150 or cuts_per_minute >= 10:
        pacing = "tight"
    else:
        pacing = "natural"
    if cuts_per_minute >= 20:
        zooms = "frequent"
    elif cuts_per_minute >= 8:
        zooms = "moderate"
    else:
        zooms = "rare"
    return {"pacing": pacing, "zoom_frequency": zooms}


def _contact_sheet(path, duration):
    """12 frames across the reel in one PNG (brand/reference/contact-sheet.png)."""
    out = config.brand_dir() / "reference" / "contact-sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    step = max(duration / 12, 0.1)
    run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", path,
         "-vf", f"fps=1/{step:.3f},scale=180:-2,tile=6x2", "-frames:v", "1", out])
    return str(out)
