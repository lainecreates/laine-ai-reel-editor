"""Map source times onto the cut timeline.

Every later layer (captions, zooms, graphics, sound effects) is timed against
the *output* video, so the transcript is remapped once here.
"""


def source_to_output(t, keep):
    """Output time for source time t, or None if t falls inside a cut."""
    offset = 0.0
    for a, b in keep:
        if a <= t <= b:
            return round(offset + (t - a), 3)
        offset += b - a
    return None


def remap_words(words, keep):
    """Words on the output timeline. Words fully inside a cut are dropped;
    words straddling a join are clamped to the kept part."""
    out, offset = [], 0.0
    bounds = []
    for a, b in keep:
        bounds.append((a, b, offset))
        offset += b - a
    for w in words:
        for a, b, off in bounds:
            s, e = max(w["start"], a), min(w["end"], b)
            if e > s:
                out.append(dict(w, start=round(off + s - a, 3), end=round(off + e - a, 3),
                                source_start=w["start"], source_end=w["end"]))
                break
    return out
