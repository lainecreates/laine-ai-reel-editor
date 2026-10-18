"""Snap whisper word times onto real speech.

Order in the pipeline: whisper (DTW, lag-corrected in transcribe.py) ->
align_words (into speech regions) -> snap_onsets (words after a pause start
when the sound starts) -> refine_starts (words mid-phrase start at the small
loudness dip between words).

whisper.cpp recognises words well, but its timestamps drift: the first word
is often placed at 0.0 s even after a long silent lead-in, and words get
stretched over the pause that follows them. Audio energy (silencedetect) is
accurate, so speech regions = everything that is not silence, and each word
is moved into the speech region it belongs to.

These aligned times drive the cut timeline, captions and every later layer.
"""


def speech_regions(silences, duration):
    regions, cursor = [], 0.0
    for s in sorted(silences, key=lambda s: s["start"]):
        if s["start"] > cursor:
            regions.append((cursor, s["start"]))
        cursor = max(cursor, s["end"])
    if cursor < duration:
        regions.append((cursor, duration))
    return regions


def align_words(words, silences, duration):
    """Return words with start/end inside speech regions, order preserved.
    Original whisper times are kept as whisper_start / whisper_end."""
    regions = speech_regions(silences, duration)
    if not regions:
        return [dict(w) for w in words]
    out, prev_end = [], 0.0
    for w in words:
        s, e = w["start"], w["end"]
        length = max(0.04, e - s)
        best = max(regions, key=lambda r: min(r[1], e) - max(r[0], s))
        overlap = min(best[1], e) - max(best[0], s)
        starts_in_speech = best[0] <= s < best[1]
        if overlap >= 0.5 * length or (overlap > 0 and starts_in_speech):
            # Mostly speech, or a word stretched over the pause after it.
            ns, ne = max(best[0], s), min(best[1], e)
        elif overlap > 0:
            # Mostly in "silence" but touching sound: likely a soft word
            # below the threshold. Trust whisper rather than squeeze it.
            ns, ne = s, e
        else:
            # Entirely inside a silence: move to the nearest speech region
            # (ties go to the later one - whisper usually runs early).
            def gap(r):
                return r[0] - e if r[0] >= e else s - r[1]
            r = min(regions, key=lambda r: (gap(r), -r[0]))
            if r[0] >= e:
                ns, ne = r[0], min(r[1], r[0] + length)
            else:
                ns, ne = max(r[0], r[1] - length), r[1]
        # Never let a word start before the previous one ended.
        ns = max(ns, prev_end)
        ne = max(ne, ns + 0.02)
        out.append(dict(w, start=round(ns, 3), end=round(ne, 3),
                        whisper_start=w["start"], whisper_end=w["end"]))
        prev_end = ne
    return out



def snap_onsets(words, quiet, look_back=0.5, inside=0.25):
    """Start each word when the voice actually starts.

    After the DTW lag correction a word is within ~0.1 s of its real start.
    Where a measured silence or gap ends just before a
    word (within `look_back`), or the word's start sits inside a silence that
    ends shortly after it (within `inside`), the word starts at that silence's
    end: the moment sound begins. Never earlier than the previous word's end.
    """
    ends = sorted(q["end"] for q in quiet)
    spans = sorted((q["start"], q["end"]) for q in quiet)
    # A word can't run on past a real pause that follows it (whisper often
    # stretches the last word before a pause, which would block the next
    # word's onset). Only pauses >= 0.12 s: short gaps also occur inside words.
    pauses = [(a, b) for a, b in spans if b - a >= 0.12]
    for k, w in enumerate(words):
        nxt = words[k + 1]["start"] if k + 1 < len(words) else float("inf")
        for a, b in pauses:
            if w["start"] + 0.05 < a < w["end"] and a < nxt + 0.3:
                w["end"] = round(max(w["start"] + 0.04, a), 3)
                break
    prev_end = 0.0
    moved = 0
    for w in words:
        s = w["start"]
        target = None
        for a, b in spans:
            if a <= s < b and b - s <= inside:      # starts inside silence: too early
                target = b
                break
        if target is None:
            before = [e for e in ends if s - look_back <= e <= s + 0.02]
            if before:
                target = before[-1]                   # nearest onset before it: too late
        if target is not None and target >= prev_end - 0.005 and abs(target - s) > 0.03 \
                and target < w["end"] - 0.02:
            w["start"] = round(target, 3)
            w["onset_snapped"] = True
            moved += 1
        prev_end = max(prev_end, w["end"])
    return moved


HOP = 0.01  # 10 ms envelope


def envelope(wav_path):
    """Loudness (dB) every 10 ms of a 16-bit mono WAV (standard library only)."""
    import array
    import math
    import wave
    with wave.open(str(wav_path), "rb") as w:
        rate, width, chans = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("expected 16-bit audio")
    data = array.array("h", raw)
    if chans > 1:
        data = data[::chans]
    n = int(rate * HOP)
    env = []
    for i in range(0, len(data) - n + 1, n):
        chunk = data[i:i + n]
        rms = math.sqrt(sum(x * x for x in chunk) / n) or 1.0
        env.append(20 * math.log10(rms / 32768.0))
    return env


def refine_starts(words, wav_path, window=0.14, min_depth=6.0):
    """Move each word's start to the real onset: the end of the loudness dip
    between it and the previous word, if there is a clear dip (>= min_depth
    dB below the speech around it) within `window` of the estimate.
    Words whose start was already snapped to a pause onset are left alone."""
    env = envelope(wav_path)
    if not env:
        return 0

    def at(t):
        return env[min(len(env) - 1, max(0, int(round(t / HOP))))]

    moved = 0
    prev_start = -1.0
    for k, w in enumerate(words):
        est = w["start"]
        if w.get("onset_snapped") or k == 0:
            prev_start = est
            continue
        lo = max(prev_start + 0.06, est - window)
        hi = est + window
        if hi - lo < 0.04:
            prev_start = est
            continue
        frames = range(int(lo / HOP), min(len(env) - 1, int(hi / HOP)) + 1)
        if not frames:
            prev_start = est
            continue
        # the deepest dip in the window, preferring ones near the estimate
        best = min(frames, key=lambda f: env[f] + 0.08 * abs(f * HOP - est) / HOP)
        dip = env[best]
        around = max(env[max(0, best - 15):best + 16])
        if around - dip < min_depth:
            prev_start = est
            continue
        # onset = first frame after the dip that climbs a third of the way back
        rise = dip + (around - dip) / 3
        f = best
        while f < len(env) - 1 and env[f] < rise and f * HOP < est + window:
            f += 1
        new = round(f * HOP, 3)
        if new < w["end"] - 0.02 and abs(new - est) > 0.015:
            w["start"] = new
            w["onset_refined"] = True
            moved += 1
            if k > 0 and words[k - 1]["end"] > new:
                words[k - 1]["end"] = new
        prev_start = w["start"]
    return moved


def fill_ends(words, quiet, min_pause=0.12):
    """Each word lasts until the next word starts or a real pause begins,
    whichever comes first. whisper's end times are unreliable (and the DTW
    lag correction moves them earlier too); cut decisions need real ends."""
    pauses = sorted((q["start"], q["end"]) for q in quiet if q["end"] - q["start"] >= min_pause)
    for k, w in enumerate(words):
        nxt = words[k + 1]["start"] if k + 1 < len(words) else None
        pause = next((a for a, b in pauses if a > w["start"] + 0.04), None)
        cands = [x for x in (nxt, pause) if x is not None]
        if cands:
            w["end"] = round(max(w["start"] + 0.04, min(cands)), 3)
