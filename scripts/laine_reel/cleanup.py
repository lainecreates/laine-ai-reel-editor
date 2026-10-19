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

   Customers (via Claude) can also name a phrase and which time it was said:
   {"phrase": "they started", "occurrence": "first"} in cleanup.review.json.

2. place()   - turn each candidate into a cut ONLY if the audio allows a clean
   edit. Each end lands in a silent gap measured by ffmpeg; where the speaker
   runs straight on (no silence), it may land on a measured quiet point between
   the two words instead - at least DIP_DB quieter than the speech around it.
   The speech check re-transcribes every join afterwards; a quiet-point join
   that doesn't pass is put back automatically. Anything else is left in, with
   the reason recorded in plain words.
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
DIP_DB = 12.0          # a quiet point between words must be this much quieter than the speech
DIP_DB_AUTO = 15.0     # ... and more so for removals nobody asked for
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
    _sentence_restarts(words, keys, add)
    return cands


def _sentence_restarts(words, keys, add):
    """'The women creating freedom online. The women creating freedom online didn't
    start...' - a short sentence that the next sentence starts with again and then
    finishes: the first one was a false start."""
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if SENTENCE_END.search(w["text"]):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    for a, b in zip(sents, sents[1:]):
        k = len(a)
        if 3 <= k <= 10 and len(b) > k and all(keys[x] for x in a) \
                and [keys[x] for x in a] == [keys[x] for x in b[:k]]:
            add("restart", a[0], a[-1], "sentence started, then restarted and finished")


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
        if r.get("phrase") and r.get("from") is None:
            found = find_phrase(words, r["phrase"], r.get("occurrence", "first"))
            if isinstance(found, str):          # not found: say so, never ignore it silently
                cands.append({"id": f"r{len(cands) + 1}", "type": r.get("type", "review"), "words": None,
                              "text": r["phrase"], "reason": found, "auto": False, "source": "review",
                              "unresolved": True})
                continue
            r = dict(r, **{"from": found[0], "to": found[1]})
        i, j = int(r["from"]), int(r["to"])
        if not (0 <= i <= j < len(words)):
            continue
        c = {"id": f"r{len(cands) + 1}", "type": r.get("type", "review"),
             "words": [i, j], "text": " ".join(w["text"] for w in words[i:j + 1]),
             "reason": r.get("reason", "review"), "auto": True, "source": "review"}
        if r.get("approved_end") is not None and r.get("approved_by"):
            # a one-off the customer approved: this cut may END at a measured quiet point
            # (not a full silence) - the start still has to be in real silence
            c["approved_end"] = float(r["approved_end"])
            c["approved_by"] = str(r["approved_by"])
        cands.append(c)
    return cands


def find_phrase(words, phrase, occurrence="first"):
    """(from, to) word numbers of the Nth time `phrase` was said ("first", "second",
    "last", or 1, 2, ...), or a plain-words reason it can't be found."""
    want = [t for t in re.findall(r"[a-z0-9']+", str(phrase).lower().replace("\u2019", "'"))]
    if not want:
        return "no words to look for"
    keys = [norm(heard(w)) for w in words]
    hits = [i for i in range(len(words) - len(want) + 1) if keys[i:i + len(want)] == want]
    if not hits:
        return f"\"{phrase}\" isn't in the transcript (check the wording against `reel.py words`)"
    names = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": len(hits)}
    n = names.get(str(occurrence).lower(), None) if not str(occurrence).isdigit() else int(occurrence)
    if not n or not 1 <= n <= len(hits):
        return f"\"{phrase}\" is said {len(hits)} time(s); occurrence \"{occurrence}\" doesn't exist"
    i = hits[n - 1]
    return i, i + len(want) - 1


# -- 2. placing cuts on the audio ------------------------------------------

def _mid(w):
    return (w["start"] + w["end"]) / 2


def place(cands, words, gaps, pacing, fps=None, dip=None, no_dip=()):
    """Return (cuts, decisions). gaps = fine silences [{"start","end"}].
    dip(t0, t1) -> (t, level_db, speech_db) measures the quietest point between two
    words (pipeline: from the clip's audio); None = silence-only (the old rule)."""
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
        approved = next((c for c in cands if c["id"] in ids and c.get("approved_end") is not None), None)
        if approved:
            t = approved["approved_end"]
            gaps_b = sorted(gaps + [(t - 0.02, t + 0.02)])
        else:
            gaps_b = gaps
        # Gap B: the first silence after the last removed word.
        if nxt is None:
            b_opts = [g for g in gaps_b if g[1] > _mid(last)]
        else:
            b_opts = [g for g in gaps_b if g[1] > _mid(last) and g[1] <= nxt["start"] + 0.15]

        # No silence where the speaker runs straight on: a measured quiet point between
        # the two words can carry the join instead.
        asked = any(c.get("source") == "review" for c in cands if c["id"] in ids)
        dip_here = dip if i not in no_dip else None    # a quiet join here failed the speech check before
        need = DIP_DB if asked else DIP_DB_AUTO
        joins = {}
        if not a_opts and prev is not None and dip_here:
            # word times from the transcriber drift: look from the middle of the word before
            # into the first part of the removed word for the real boundary
            q = dip_here(_mid(prev), min(first["end"] - 0.03, first["start"] + 0.2))
            if q and q[2] - q[1] >= need:
                a_opts = [(q[0] - 0.01, q[0] + 0.01)]
                joins["start"] = q
        if not b_opts and nxt is not None and dip_here:
            q = dip_here(_mid(last), _mid(nxt))
            if q and q[2] - q[1] >= need:
                b_opts = [(q[0] - 0.01, q[0] + 0.01)]
                joins["end"] = q
        reason = None
        if not a_opts:
            reason = ("no pause or quiet point before it - a cut there would clip "
                      f"\"{prev['text'] if prev else ''}\"" if dip_here else "no silent gap before it - would clip a word")
        elif not b_opts:
            reason = ("no pause or quiet point after it - a cut there would clip "
                      f"\"{nxt['text'] if nxt else ''}\"" if dip_here else "no silent gap after it - would clip a word")
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
        cut = {"start": start, "end": end, "kind": "content", "candidates": ids,
               "silence": [round(A[0], 3), round(B[1], 3)]}
        if approved:
            cut["approved_join"] = approved["approved_by"]
        if joins:
            cut["quiet_joins"] = {k: {"at": round(v[0], 3), "level_db": round(v[1], 1),
                                      "below_speech_db": round(v[2] - v[1], 1)} for k, v in joins.items()}
        cuts.append(cut)
        for cid in ids:
            decisions[cid] = {"applied": True, "cut": [round(start, 3), round(end, 3)],
                              **({"approved_join": approved["approved_by"]} if approved else {}),
                              **({"quiet_join": True} if joins else {})}
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
