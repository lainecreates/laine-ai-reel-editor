"""Content cleanup: repeated words, restarts, fillers, abandoned sentences.

Two halves:

1. detect()  - find candidate removals in the transcript (word index ranges).
   Automatic, conservative rules:
     repeat       "some of y'all, some of y'all, some of y'all are..." -> keep
                  the last, complete delivery, remove the earlier copies
     filler       standalone um / uh / erm / hmm
     false_start  a cut-off word ("real-") followed by a restart of the same
                  phrase
   Meaning-level judgements (abandoned sentences, "Tuesday, I mean Wednesday")
   come from a review file written by Claude: cleanup.review.json.

2. place()   - turn each candidate into a cut ONLY if the audio allows a clean
   edit: both ends must land in a silent gap measured by ffmpeg, and the
   speech between the gaps must match the words being removed. Anything
   uncertain is left in, with the reason recorded.
"""

import re

from . import config

# Single words people double on purpose ("very very", "no no no").
EMPHATIC = {"very", "really", "so", "no", "yes", "yeah", "bye", "ha", "haha", "that",
            "had", "is", "go", "ok", "okay", "please", "more", "far", "long", "again",
            "over", "round", "on", "out", "now", "wait", "stop", "come", "hey", "oh"}
# Style words: flagged for review, never removed automatically.
SOFT_FILLERS = {"like", "basically", "literally", "actually", "honestly", "just"}
MAX_NGRAM = 6
SENTENCE_END = re.compile(r"[.?!]\W*$")
CUT_OFF = re.compile(r"(-|—|–|\.\.\.|…)$")


def norm(text):
    """Comparable form of a word: lowercase letters/digits/apostrophes
    (curly apostrophes count as straight ones)."""
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    return "".join(re.findall(r"[a-z0-9']+", text))


def heard(w):
    """What was actually said. Caption spelling fixes change how a word is
    shown, never what the cut detector compares."""
    return w.get("heard", w["text"])


def tokens(words):
    """Word list -> comparable tokens (comment"content" -> comment, content)."""
    out = []
    for w in words:
        t = heard(w).lower().replace("\u2019", "'").replace("\u2018", "'")
        out.extend(re.findall(r"[a-z0-9']+", t))
    return out


# -- 1. detection -----------------------------------------------------------

def detect(words):
    n = len(words)
    keys = [norm(heard(w)) for w in words]
    cands, taken = [], set()

    def add(kind, i, j, reason, auto=True):
        if any(k in taken for k in range(i, j + 1)) and auto:
            return
        cands.append({"id": f"c{len(cands) + 1}", "type": kind, "words": [i, j],
                      "text": " ".join(w["text"] for w in words[i:j + 1]),
                      "reason": reason, "auto": auto, "source": "engine"})
        if auto:
            taken.update(range(i, j + 1))

    i = 0
    while i < n:
        found = False
        for k in range(MAX_NGRAM, 0, -1):
            if i + 2 * k > n:
                continue
            gram = keys[i:i + k]
            if not all(gram) or keys[i + k:i + 2 * k] != gram:
                continue
            if k == 1 and gram[0] in EMPHATIC:
                continue
            reps = 2
            while keys[i + reps * k:i + (reps + 1) * k] == gram:
                reps += 1
            last_of_first = words[i + k - 1]["text"]
            if SENTENCE_END.search(last_of_first) and not CUT_OFF.search(last_of_first):
                # "Camera. Camera." - a complete sentence repeated on purpose.
                continue
            end = i + (reps - 1) * k - 1
            add("repeat", i, end, f"said {reps}x; keeping the last, complete delivery")
            i, found = end + 1, True
            break
        if found:
            continue
        if keys[i] in config.FILLER_WORDS:
            add("filler", i, i, "filler sound")
        elif keys[i] in SOFT_FILLERS:
            add("soft_filler", i, i, "style word - flagged, not removed", auto=False)
        elif CUT_OFF.search(words[i]["text"]) and i + 1 < n:
            # Cut-off word: if the speaker restarts the same phrase, the
            # fragment from its start to the cut-off is abandoned.
            start = i
            # The fragment starts after the last sentence end, cut-off or comma
            # ("...your audience has, | building trust or giving a people-").
            while start > 0 and i - start < 6 and not SENTENCE_END.search(
                    words[start - 1]["text"]) and not CUT_OFF.search(words[start - 1]["text"]) \
                    and not words[start - 1]["text"].rstrip().endswith((",", ";", ":")):
                start -= 1
            if keys[i + 1] == keys[start]:
                add("false_start", start, i, "cut-off phrase, then restarted")
            else:
                add("false_start", start, i, "cut-off phrase - flagged for review", auto=False)
        i += 1
    return cands


def merge_review(cands, review, words):
    """Apply Claude's review: veto engine candidates, add meaning-level ones."""
    if not review:
        return cands
    vetoed = set(review.get("keep", []))
    for c in cands:
        if c["id"] in vetoed:
            c["auto"] = False
            c["reason"] += " (kept after review)"
    for r in review.get("remove", []):
        i, j = int(r["from"]), int(r["to"])
        if not (0 <= i <= j < len(words)):
            continue
        cands.append({"id": f"r{len(cands) + 1}", "type": r.get("type", "review"),
                      "words": [i, j], "text": " ".join(w["text"] for w in words[i:j + 1]),
                      "reason": r.get("reason", "review"), "auto": True, "source": "review"})
    return cands


# -- 2. placing cuts on the audio ------------------------------------------

def _mid(w):
    return (w["start"] + w["end"]) / 2


def place(cands, words, gaps, pacing, fps=None):
    """Return (cuts, decisions). gaps = fine silences [{"start","end"}]."""
    spans = _spans([c for c in cands if c["auto"]])
    gaps = sorted((g["start"], g["end"]) for g in gaps)
    cuts, decisions = [], {}
    before = pacing.keep_pause * 0.55
    after = pacing.keep_pause - before

    for i, j, ids in spans:
        prev = words[i - 1] if i > 0 else None
        nxt = words[j + 1] if j + 1 < len(words) else None
        first, last = words[i], words[j]

        # Gap A: the last silence before the first removed word.
        if prev is None:
            a_opts = [g for g in gaps if g[0] <= 0.05 and g[1] < _mid(first)] or [(0.0, 0.0)]
        else:
            a_opts = [g for g in gaps if g[0] >= prev["end"] - 0.1 and g[0] < _mid(first)]
        # Gap B: the first silence after the last removed word.
        if nxt is None:
            b_opts = [g for g in gaps if g[1] > _mid(last)]
        else:
            b_opts = [g for g in gaps if g[1] > _mid(last) and g[1] <= nxt["start"] + 0.15]

        reason = None
        if not a_opts:
            reason = "no silent gap before it - would clip a word"
        elif not b_opts:
            reason = "no silent gap after it - would clip a word"
        else:
            A, B = a_opts[-1], b_opts[0]
            speech = B[0] - A[1]
            spoken = last["end"] - first["start"]
            if speech < 0.08:
                reason = "gaps too close together"
            elif speech > max(spoken * 2.0, spoken + 0.6):
                reason = "more speech between the gaps than the words being removed"
            elif prev is not None and _mid(prev) > A[0]:
                reason = "previous word overlaps the cut"
            elif nxt is not None and _mid(nxt) < B[1]:
                reason = "next word overlaps the cut"
        if reason:
            for cid in ids:
                decisions[cid] = {"applied": False, "why": reason}
            continue

        if prev is None:
            start = 0.0
            end = B[1] - min(pacing.lead_in, (B[1] - B[0]))
        else:
            start = A[0] + min(before, (A[1] - A[0]) / 2)
            end = B[1] - min(after, (B[1] - B[0]) / 2) if nxt else B[1]
        cuts.append({"start": start, "end": end, "kind": "content", "candidates": ids,
                     "silence": [round(A[0], 3), round(B[1], 3)]})
        for cid in ids:
            decisions[cid] = {"applied": True, "cut": [round(start, 3), round(end, 3)]}
    return cuts, decisions


def _spans(cands):
    """Merge touching/overlapping candidate ranges into single cuts."""
    out = []
    for c in sorted(cands, key=lambda c: c["words"][0]):
        i, j = c["words"]
        if out and i <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], j), out[-1][2] + [c["id"]])
        else:
            out.append((i, j, [c["id"]]))
    return out


def removed_indices(cands, decisions):
    out = set()
    for c in cands:
        if decisions.get(c["id"], {}).get("applied"):
            out.update(range(c["words"][0], c["words"][1] + 1))
    return out


BREATH = 0.15  # longest non-speech sound a requested pause cut may remove
REQUESTED_KEEP = 0.12  # a pause the customer asked to remove keeps only this


def pause_cut(words, i, quiet, pacing):
    """Shorten the pause after word i (a "missed pause" from review). Only
    inside measured silence between word i and word i+1; keeps the pacing's
    natural gap. Returns (cut or None, reason)."""
    if not (0 <= i < len(words) - 1):
        return None, "no word after it"
    a, b = words[i]["end"], words[i + 1]["start"]
    spans = sorted((q["start"], q["end"]) for q in quiet
                   if q["end"] > a - 0.15 and q["start"] < b + 0.15)
    if not spans:
        return None, "no measured silence there"
    s0, s1 = spans[0][0], spans[0][1]
    # The customer asked for this pause to go, so short non-speech sounds
    # inside it (a breath, a lip click: < 0.15 s, and there's no transcribed
    # word between the two words) go too. Longer sound stops the cut.
    for x0, x1 in spans[1:]:
        if x0 - s1 > BREATH:
            break
        s1 = max(s1, x1)
    # "Remove this pause" means remove it: keep just a breath so no word is
    # clipped, not the pacing's natural pause.
    keep = min(pacing.keep_pause, REQUESTED_KEEP)
    start, end = s0 + keep * 0.55, s1 - keep * 0.45
    if end - start < 0.06:
        return None, "the pause is already short"
    return {"start": start, "end": end, "kind": "content", "candidates": [f"pause_after_{i}"],
            "silence": [round(s0, 3), round(s1, 3)],
            "pause_before": round(b - a, 3)}, "ok"
