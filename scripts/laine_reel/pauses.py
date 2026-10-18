"""Decide which pauses to shorten, keeping natural speech rhythm.

Audio energy (ffmpeg silencedetect) alone decides where it is silent: it is
accurate to a few ms, while whisper's word times drift by up to ~1 s. Cuts
only ever happen inside measured silence, and only remove the part of a
pause beyond the pacing's keep_pause, so speech is never touched. The
pipeline's --check-speech re-transcription is the safety net.
"""

import math

from . import config

MIN_CUT = 0.06    # don't bother with cuts shorter than this (s)
MIN_KEEP = 0.05   # keep-segments shorter than this are absorbed into a cut
# Two silences separated by any measurable sound are NOT merged: that "blip"
# is often the soft end of a word ("goo-d"). Only touching spans merge.
MERGE_GAP = 0.005


def plan_cuts(duration, silences, pacing, audio_end=None, fps=config.OUTPUT["fps"],
              extra_cuts=None, quiet=None):
    """Return {"cuts": [...], "keep": [[start, end], ...], "stats": {...}}.

    extra_cuts: content cuts from cleanup.place() (already audio-checked).
    quiet: all measured silence incl. short gaps; kept slivers between two
    cuts that hold no sound at all are dropped so pauses don't stack up.

    audio_end: where the audio track stops. Phone clips often have video
    running on after the audio; that stretch is treated as tail silence.

    Each cut: {"start", "end", "kind": lead|pause|tail, "silence": [s, e]}.
    Keep boundaries are snapped to the output frame grid so audio and video
    segments have identical lengths (no A/V drift across many joins).
    """
    silences = _merge(silences, duration, audio_end)
    cuts = []
    for s in silences:
        start, end = float(s["start"]), float(s["end"])
        length = end - start
        if start <= 0.05:
            c = (0.0, end - pacing.lead_in, "lead")
        elif end >= duration - 0.05:
            c = (start + pacing.tail, duration, "tail")
        elif length > pacing.min_pause:
            # Keep slightly more after the last word (natural decay) than
            # before the next one.
            before = pacing.keep_pause * 0.55
            after = pacing.keep_pause - before
            c = (start + before, end - after, "pause")
        else:
            continue
        if c[1] - c[0] >= MIN_CUT:
            cuts.append({"start": c[0], "end": c[1], "kind": c[2],
                         "silence": [round(start, 3), round(end, 3)]})

    cuts += [dict(c) for c in (extra_cuts or [])]
    cuts = [_snap(c, fps) for c in cuts]
    cuts = sorted((c for c in cuts if c["end"] - c["start"] >= MIN_CUT), key=lambda c: c["start"])
    keep = _complement(cuts, duration, fps)
    if quiet:
        keep = [k for k in keep if _sound_in(k[0], k[1], quiet) >= 0.03]

    kept = sum(b - a for a, b in keep)
    return {
        "pacing": pacing.to_dict(),
        "cuts": cuts,
        "keep": keep,
        "stats": {
            "source_duration": round(duration, 3),
            "output_duration": round(kept, 3),
            "removed": round(duration - kept, 3),
            "removed_pct": round(100 * (duration - kept) / duration, 1) if duration else 0,
            "cuts": len(cuts),
            "pauses_shortened": sum(1 for c in cuts if c["kind"] == "pause"),
            "content_cuts": sum(1 for c in cuts if c["kind"] == "content"),
        },
    }


def _merge(silences, duration, audio_end):
    spans = sorted((float(s["start"]), float(s["end"])) for s in silences)
    if audio_end is not None and audio_end < duration - MERGE_GAP:
        spans.append((audio_end, duration))
        spans.sort()
    merged = []
    for a, b in spans:
        if merged and a - merged[-1][1] <= MERGE_GAP:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [{"start": a, "end": b} for a, b in merged]


def _sound_in(a, b, quiet):
    """Seconds of non-silence inside [a, b]."""
    covered, cursor = 0.0, a
    for q in sorted(quiet, key=lambda q: q["start"]):
        s, e = max(q["start"], cursor), min(q["end"], b)
        if e > s:
            covered += e - s
            cursor = e
    return (b - a) - covered


def _snap(cut, fps):
    """Shrink a cut inward to whole frames (never cut more than planned)."""
    start = math.ceil(cut["start"] * fps - 1e-6) / fps
    end = math.floor(cut["end"] * fps + 1e-6) / fps
    return dict(cut, start=round(start, 6), end=round(end, 6))


def _complement(cuts, duration, fps):
    end_frame = math.floor(duration * fps + 1e-6) / fps
    keep, cursor = [], 0.0
    for c in sorted(cuts, key=lambda c: c["start"]):
        if c["start"] > cursor:
            keep.append([round(cursor, 6), round(min(c["start"], end_frame), 6)])
        cursor = max(cursor, c["end"])
    if cursor < end_frame:
        keep.append([round(cursor, 6), round(end_frame, 6)])
    return [k for k in keep if k[1] - k[0] >= MIN_KEEP]


def find_fillers(words):
    """Filler words, flagged for review (Phase 1 never cuts them)."""
    out = []
    for i, w in enumerate(words):
        token = w["text"].lower().strip(".,!?;:\"'")
        if token in config.FILLER_WORDS:
            out.append({"index": i, "text": w["text"], "start": w["start"], "end": w["end"]})
    return out
