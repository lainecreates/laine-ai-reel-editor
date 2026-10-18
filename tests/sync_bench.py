#!/usr/bin/env python3
"""Caption-sync benchmark with ground truth.

Builds continuous speech by synthesising each word separately with macOS
`say` and stitching them together, so the exact start of every word is
known. Runs the editor's real timing pipeline (whisper.cpp + DTW, silences,
alignment, onset refinement) and reports how far each word's start is from
the truth.

    python3 tests/sync_bench.py           # prints a report
    (tests/test_sync.py runs it as a test with pass/fail limits)
"""

import json
import shutil
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from laine_reel import align, config, media  # noqa: E402
from laine_reel.tools import find_whisper_model  # noqa: E402
from laine_reel.transcribe import transcribe  # noqa: E402

SENTENCES = [
    "Some of you are not waiting on a better camera",
    "you are waiting to finally know what you are doing when you hit record",
    "the real skill is knowing where to place your phone and what angle to get",
    "that is exactly why I made the morning light studio",
]
VOICES = ["Samantha", "Daniel"]   # one female, one male built-in voice
GAP = 0.02          # tiny gap between stitched words: continuous speech
PAUSE = 0.6         # between sentences


def sh(*cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True)


def voice_ok(v):
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return any(line.split()[0] == v for line in out.splitlines() if line.split())


def sound_span(wav):
    """Start/end of sound in a clip (trims the voice's own lead/tail silence)."""
    dur = media.duration(wav)
    sil = media.detect_silences(wav, -45, min_dur=0.02, duration=dur)
    start = next((s["end"] for s in sil if s["start"] <= 0.01), 0.0)
    end = next((s["start"] for s in reversed(sil) if s["end"] >= dur - 0.01), dur)
    return start, end


def build(tmp, voice):
    """Return (wav path, [{"text", "start"}] true onsets)."""
    parts, truth, t = [], [], 0.4
    silence = tmp / "gap.wav"
    for si, sentence in enumerate(SENTENCES):
        for wi, word in enumerate(sentence.split()):
            raw = tmp / f"w{si}_{wi}.aiff"
            sh("say", "-v", voice, "-o", raw, word)
            wav = tmp / f"w{si}_{wi}.wav"
            sh("ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-ac", "1", "-ar", "16000", wav)
            a, b = sound_span(wav)
            cut = tmp / f"c{si}_{wi}.wav"
            sh("ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af",
               f"atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS", cut)
            truth.append({"text": word, "start": round(t, 4)})
            parts.append(cut)
            t += b - a
            pause = PAUSE if wi == len(sentence.split()) - 1 else GAP
            gap = tmp / f"g{len(parts)}.wav"
            sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
               f"anullsrc=r=16000:cl=mono", "-t", f"{pause:.3f}", gap)
            parts.append(gap)
            t += pause
    lead = tmp / "lead.wav"
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
       "-t", "0.4", lead)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in [lead] + parts))
    out = tmp / f"speech_{voice}.wav"
    # faint room noise so it isn't digitally silent between words
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
       "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.001:sample_rate=16000",
       "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0",
       "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out)
    return out, truth


def timing(wav, refine=True):
    """The editor's own word timing for a 16 kHz wav."""
    model = find_whisper_model()
    words = transcribe(wav, model, wav.with_suffix(""))["words"]
    dur = media.duration(wav)
    mean = media.mean_volume(wav)
    thr = media.silence_threshold(mean)
    sil = media.detect_silences(wav, thr, duration=dur)
    gaps = media.detect_silences(wav, thr, min_dur=config.GAP_MIN_DETECT, duration=dur)
    words = align.align_words(words, sil, dur)
    if refine:
        align.snap_onsets(words, sil + gaps)
        align.refine_starts(words, wav)
        align.fill_ends(words, sil + gaps)
    return words


def score(words, truth):
    """Match recognised words to truth in order, return start errors (s)."""
    import difflib
    a = [w["text"].lower().strip(".,?!") for w in words]
    b = [w["text"].lower() for w in truth]
    errs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                errs.append(round(words[i1 + k]["start"] - truth[j1 + k]["start"], 3))
    return errs


def report(errs):
    late = [e for e in errs if e > 0]
    return {"words": len(errs), "median": round(st.median(errs), 3),
            "mean_abs": round(st.mean(abs(e) for e in errs), 3),
            "p90_abs": round(sorted(abs(e) for e in errs)[int(0.9 * (len(errs) - 1))], 3),
            "late_over_80ms": sum(e > 0.08 for e in errs),
            "early_over_80ms": sum(e < -0.08 for e in errs),
            "max_late": max(late) if late else 0.0}


def run(refine=True):
    tmp = Path(tempfile.mkdtemp(prefix="laine-sync-"))
    results = {}
    try:
        for v in VOICES:
            if not voice_ok(v):
                continue
            wav, truth = build(tmp, v)
            results[v] = report(score(timing(wav, refine), truth))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


if __name__ == "__main__":
    if "--raw" in sys.argv:
        print("whisper + lag correction only:", json.dumps(run(refine=False), indent=1))
    print("editor timing:", json.dumps(run(), indent=1))
