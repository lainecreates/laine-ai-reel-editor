"""Edit plan: brand profile + cut transcript -> timed captions, zooms,
graphics, sound effects and music, written to edit.json (+ edit-plan.md).

Everything is timed on the OUTPUT timeline (transcript.cut.json), so the plan
lines up with the clean MP4. This module only plans; the renderer (next
phase) draws captions/graphics as transparent frames and composites them with
ffmpeg `overlay`, because this ffmpeg has no drawtext/subtitles.

Claude reviews the plan (hook wording, which moments get graphics) and can
adjust it through edit.overrides.json, which survives re-planning.
"""

import datetime as _dt
import re

from . import config
from .cleanup import norm
from .tools import ffmpeg_filters

W, H = config.OUTPUT["width"], config.OUTPUT["height"]
# Keep text out of the areas Instagram / TikTok / Shorts cover with their UI.
SAFE = {"top": 250, "bottom": H - 420, "left": 60, "right": W - 60}
ZONE_Y = {"upper_third": 560, "center": 960, "lower_third": 1300, "top_edge": 120}

STOP = set("""a an the and or but so to of in on at for with from by as is are was were be been
being am i you he she it we they me him her us them my your his its our their this that these
those there here what which who whom when where why how do does did doing have has had having
not no yes just like um uh okay ok oh if then than too very can could would should will shall
may might must also into out up down over about all any some more most other such only own same
again once now know get got go going really y'all you're i'm it's that's don't can't""".split())
POWER = {"secret", "real", "skill", "mistake", "never", "always", "free", "best", "worst",
         "easy", "hack", "money", "exactly", "everyday", "random", "intentional", "angle",
         "camera", "edit", "film", "post", "posting", "phone", "content", "lab", "stop",
         "nothing", "everything", "finally", "newest", "better"}
EMOJI = {"camera": "📷", "phone": "📱", "iphone": "📱", "film": "🎬", "edit": "✂️",
         "money": "💰", "love": "❤️", "idea": "💡", "secret": "🤫", "random": "🎲",
         "fire": "🔥", "time": "⏰", "light": "💡", "record": "🔴", "posting": "📲",
         "intentional": "🎯", "angle": "📸", "heck": "😅", "skill": "🧠",
         "dime": "💸", "paid": "💸", "buy": "🛒", "sell": "🛍️", "trust": "🤝",
         "trusted": "🤝", "purpose": "🎯", "remembered": "🧠", "consistent": "📅",
         "post": "📲", "content": "📲", "audience": "👥", "problem": "🧩", "goal": "🎯",
         "seen": "👀", "cute": "😌", "listen": "👂"}
# Never end a caption line on these; they belong with the next word.
DANGLE = {"a", "an", "the", "to", "of", "my", "your", "our", "their", "his", "her", "its",
          "and", "or", "but", "in", "on", "at", "for", "with", "from", "by", "as", "if",
          "so", "that", "what", "how", "when", "where", "i", "you", "we", "is", "are"}
MIN_ZOOM_S = 1.5
CAPTION_LEAD = 0.08  # captions appear this much before the word is heard
TICK_DELAY = 0.12    # a checklist box ticks this long after its line appears (overlay.py too)
# Phrases that point at something -> arrow direction.
POINTING = [(re.compile(r"\b(down below|link in (my )?bio|below)\b", re.I), "down"),
            (re.compile(r"\b(up here|above)\b", re.I), "up"),
            (re.compile(r"\b(right here|look at this|this one|over here)\b", re.I), "down_right")]
CTA = re.compile(r"\b(comment|dm me|link in (my )?bio|follow( me)?|save this|share this|"
                 r"subscribe|sign up|join)\b", re.I)


def plan(words, duration, joins, brand, overrides=None):
    """Return the edit plan dict."""
    sentences = split_sentences(words)
    emphasis = {s[0]: pick_emphasis(words, s) for s in sentences if s}
    emph_idx = {i for i in emphasis.values() if i is not None}

    cap = brand.get("captions", {})
    captions = caption_items(words, sentences, emph_idx, cap) if cap.get("enabled") else []
    zooms = plan_zooms(words, sentences, joins, duration, brand.get("zooms", {}))
    graphics = plan_graphics(words, sentences, emph_idx, duration, brand)
    sfx = plan_sfx(zooms, graphics, duration, brand.get("sfx", {}))
    sfx_brand = brand.get("sfx", {})
    music = plan_music(brand.get("music", {}))

    edit = {
        "version": 2,
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "brand_updated": brand.get("updated"),
        "canvas": {"width": W, "height": H, "safe_zone": SAFE},
        "duration": round(duration, 3),
        "captions": {"enabled": bool(cap.get("enabled")),
                     "style": {k: cap.get(k) for k in ("style", "position", "size_px",
                                                        "animation", "emphasis", "case")},
                     "font": brand.get("fonts", {}).get("body"),
                     "colors": {"text": brand.get("colors", {}).get("caption_text"),
                                "outline": brand.get("colors", {}).get("caption_outline"),
                                "emphasis": brand.get("colors", {}).get("accent")},
                     "items": captions},
        "zooms": zooms,
        "graphics": graphics,
        "sfx": sfx,
        "music": music,
        "_sfx_brand": {"sounds": sfx_brand.get("sounds", {})},
    }
    apply_overrides(edit, overrides or {})
    edit["render_requirements"] = render_requirements(edit)
    return edit


# -- text helpers -------------------------------------------------------------

def split_sentences(words):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if re.search(r"[.?!]\W*$", w["text"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def pick_emphasis(words, sentence):
    """The one word per sentence that carries it."""
    best, best_score = None, 0.0
    for pos, i in enumerate(sentence):
        t = norm(words[i]["text"])
        if not t or t in STOP or len(t) < 3:
            continue
        score = len(t) / 4
        if any(c.isdigit() for c in t):
            score += 2
        if pos > 0 and words[i]["text"][:1].isupper():
            score += 1.5
        if t in POWER:
            score += 1
        if score > best_score:
            best, best_score = i, score
    return best if best_score >= 1.0 else None


def display(text, case):
    t = re.sub(r"(\w)([\"“])(?=\w)", r"\1 \2", text.strip())  # comment"x" -> comment "x"
    return t.upper() if case == "upper" else t.lower() if case == "lower" else t


def spoken_list(words, s):
    """'how to film, edit, and turn your everyday content into ...' ->
    [film, edit, turn your everyday content]: 3+ short items separated by
    commas, the last one after 'and' / 'or'. Each item is timed to when it's said."""
    commas = [k for k, i in enumerate(s) if words[i]["text"].endswith(",")]
    for a, b in zip(commas, commas[1:]):
        gap = b - a
        if gap > 3:
            continue
        nxt = b + 1
        if nxt >= len(s) or norm(words[s[nxt]]["text"]) not in ("and", "or"):
            continue
        first = s[max(0, a - gap + 1):a + 1]
        second = s[a + 1:b + 1]
        last = []
        for i in s[nxt + 1:nxt + 5]:
            if norm(words[i]["text"]) in ("into", "so", "because", "to", "with", "for") and last:
                break
            last.append(i)
            if re.search(r"[,.?!]$", words[i]["text"]):
                break
        if not last:
            continue
        out = []
        for part in (first, second, last):
            text = " ".join(words[i]["text"] for i in part).strip(" ,.?!")
            out.append({"text": _cap_first(text), "at": words[part[0]]["start"]})
        return out
    return []


def _cap_first(t):
    """Sentence starts get a capital (a cleanup cut may have removed the
    original first word, leaving 'some of y'all...')."""
    return t[:1].upper() + t[1:]


def is_question(words, s):
    return words[s[-1]]["text"].rstrip().endswith("?")


def sentence_text(words, s):
    return " ".join(words[i]["text"] for i in s)


# -- captions -----------------------------------------------------------------

def caption_items(words, sentences, emph_idx, cap):
    style = cap.get("style", "phrase_lines")
    per_line = cap.get("max_chars_per_line", 20)
    if style == "word_pop":
        chunks = _word_pop_chunks(words, sentences)
    else:
        max_chars = per_line * cap.get("max_lines", 2)
        max_words = 3 if style == "keyword_boxes" else 99
        chunks = []
        for s in sentences:
            chunks.extend(break_lines(words, s, max_chars, max_words))

    items = []
    case = cap.get("case", "as_spoken")
    starts = {s[0] for s in sentences}
    for n, c in enumerate(chunks):
        # Captions appear ~2 frames before the sound: reads as "in sync".
        start = max(0.0, words[c[0]]["start"] - CAPTION_LEAD)
        if items:
            start = max(start, items[-1]["start"] + 0.05)
        end = words[c[-1]]["end"]
        nxt = (words[chunks[n + 1][0]]["start"] - CAPTION_LEAD) if n + 1 < len(chunks) else None
        if nxt is not None:
            end = nxt if nxt - end < 0.25 else min(end + 0.4, nxt)
        else:
            end += 0.6
        shown = [_cap_first(words[i]["text"]) if i in starts and case == "as_spoken"
                 else words[i]["text"] for i in c]
        items.append({
            "id": f"cap{n + 1}", "start": round(start, 3), "end": round(end, 3),
            "text": display(" ".join(shown), case),
            "words": [{"text": display(t, case), "start": words[i]["start"],
                       "end": words[i]["end"], "emphasis": i in emph_idx,
                       "i": words[i].get("i")}
                      for t, i in zip(shown, c)],
            "y": ZONE_Y.get(cap.get("position", "lower_third"), ZONE_Y["lower_third"]),
        })
    return items


def _word_pop_chunks(words, sentences):
    """One word at a time; a short word (a, to, I) rides with the next one,
    unless there's a pause between them (then it would show too early)."""
    chunks = []
    for s in sentences:
        cur = []
        for k, i in enumerate(s):
            cur.append(i)
            nxt = s[k + 1] if k + 1 < len(s) else None
            paused = nxt is not None and words[nxt]["start"] - words[i]["end"] > 0.2
            if len(norm(words[i]["text"])) > 2 or nxt is None or paused:
                chunks.append(cur)
                cur = []
    return chunks


def break_lines(words, sentence, max_chars, max_words=99):
    """Best split of one sentence into caption chunks (dynamic programming).

    Hard: a chunk fits max_chars / max_words and never spans a pause > 0.45 s.
    Cost: unused space (ragged lines), ending on a dangling word ('the', 'to'),
    one-word chunks, splitting a name. Bonus: breaking after a comma or at a short pause.
    """
    n = len(sentence)
    texts = [words[i]["text"] for i in sentence]
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for end in range(1, n + 1):
        for start in range(end - 1, -1, -1):
            length = len(" ".join(texts[start:end]))
            count = end - start
            if count > 1 and (length > max_chars or count > max_words):
                break
            inner = [words[sentence[k + 1]]["start"] - words[sentence[k]]["end"]
                     for k in range(start, end - 1)]
            if any(g > 0.45 for g in inner):
                break
            cost = ((max_chars - min(length, max_chars)) / max_chars) ** 2
            last = texts[end - 1]
            if end < n:
                if norm(last) in DANGLE:
                    cost += 5
                if last.endswith((",", ";", ":")):
                    cost -= 1
                gap = words[sentence[end]]["start"] - words[sentence[end - 1]]["end"]
                if gap > 0.25:
                    cost -= 1
                nxt = texts[end]
                if last[:1].isupper() and nxt[:1].isupper() and end - 1 > 0:
                    cost += 6  # don't split a name ("Everyday / Content Lab")
            if count == 1 and n > 1:
                cost += 4
            if best[start] + cost < best[end]:
                best[end], back[end] = best[start] + cost, start
    chunks, end = [], n
    while end > 0:
        chunks.append(sentence[back[end]:end])
        end = back[end]
    return chunks[::-1]


# -- zooms --------------------------------------------------------------------

def plan_zooms(words, sentences, joins, duration, z):
    style = z.get("style", "none")
    if style in (None, "none"):
        return []
    lo, hi = z.get("scale_min", 1.08), z.get("scale_max", 1.15)
    gap = z.get("min_gap_s", 5.0)
    focus = z.get("focus", {"x": 0.5, "y": 0.38})
    cands = []
    # Snap zooms at jump cuts hide the cut (punchy / mixed).
    sent_ends = sorted(words[s[-1]]["end"] for s in sentences)
    if style in ("punchy", "mixed"):
        for t in joins:
            # Release at the next cut, or at the first sentence end >= 2 s in -
            # never snapping back in the middle of a line.
            nxt = min([j for j in joins if j > t + 0.1] + [duration])
            ends = [e for e in sent_ends if e >= t + 2.0]
            release = min(nxt, ends[0] if ends else duration)
            cands.append((2, t, release, "punch", hi, "hides the jump cut"))
    # Slow pushes on the lines that matter (subtle / mixed).
    if style in ("subtle", "mixed"):
        for k, s in enumerate(sentences):
            text = sentence_text(words, s)
            st, en = words[s[0]]["start"], words[s[-1]]["end"]
            if en - st < 1.0:
                continue
            why = ("hook" if k == 0 else "call to action" if CTA.search(text)
                   else "question" if is_question(words, s) else None)
            if why:
                cands.append((1 if why != "question" else 3, st, en, "push",
                              hi if style == "subtle" else lo, why))
    # Frequent / moderate punchy styles also punch in on new sentences that
    # carry a key word, so long uncut stretches still move.
    if style in ("punchy", "mixed") and z.get("frequency") in ("moderate", "frequent"):
        for s in sentences:
            st, en = words[s[0]]["start"], words[s[-1]]["end"]
            if en - st >= 2.0 and pick_emphasis(words, s) is not None:
                cands.append((4, st, en, "punch", lo if style == "mixed" else hi,
                              "new key line"))
    # Highest priority first, then in time order; keep them apart.
    picked = []
    for pri, st, en, kind, scale, why in sorted(cands, key=lambda c: (c[0], c[1])):
        if en - st < MIN_ZOOM_S:
            continue  # a zoom that short just flickers
        if any(st < p["end"] and en > p["start"] for p in picked):
            continue
        if any(abs(st - p["start"]) < gap for p in picked):
            continue
        picked.append({"start": round(st, 3), "end": round(en, 3), "type": kind,
                       "scale": scale, "ease_s": 0.0 if kind == "punch" else round(en - st, 2),
                       "focus": focus, "reason": why})
    picked.sort(key=lambda p: p["start"])
    for n, p in enumerate(picked, 1):
        p["id"] = f"z{n}"
    return picked


# -- graphics -----------------------------------------------------------------

def _style(brand, kind):
    c, f = brand.get("colors", {}), brand.get("fonts", {})
    tokens = brand.get("aesthetic", {}).get("tokens", {})
    anim = {"soft_luxe": "fade_scale", "clean_minimal": "fade", "bold_energetic": "pop",
            "playful": "bounce", "editorial": "slide", "techy": "slide"}.get(
        brand.get("aesthetic", {}).get("preset"), "fade")
    bg = c.get("accent") if kind == "cta_card" else (
        "#FFF4A3" if kind == "sticky_notes" else c.get("card_background"))
    text = c.get("on_accent") if kind == "cta_card" else (
        "#111111" if kind == "sticky_notes" else c.get("card_text"))
    return {"background": bg, "text": text, "accent": c.get("accent"),
            "font": f.get("headline"), "animation_in": anim, "animation_out": "fade",
            **tokens}


def plan_graphics(words, sentences, emph_idx, duration, brand):
    g = brand.get("graphics", {})
    elements = set(g.get("elements", []))
    if not words:
        return []
    # (the logo is added after placement; it doesn't compete with other graphics)
    cap_pos = brand.get("captions", {}).get("position", "lower_third")
    zone = "lower_third" if cap_pos == "upper_third" else "upper_third"
    gap = g.get("min_gap_s", 5.0)
    cands = []  # (priority, item)

    def item(kind, start, end, reason, draft=False, z=zone, **content):
        return {"type": kind, "start": round(max(0.0, start), 3),
                "end": round(min(duration, end), 3), "zone": z, "y": ZONE_Y[z],
                "reason": reason, "draft": draft, **content}

    # Call to action -> end card.
    if "cta_card" in elements:
        for s in sentences:
            text = sentence_text(words, s)
            m = CTA.search(text)
            if m:
                quoted = re.search(r"[\"“]([^\"”]+)[\"”]", text)
                after = text[m.end():].strip(" ,.:\"“”").split()
                kw = quoted.group(1) if quoted else (after[0] if after else "")
                label = f"{m.group(1).capitalize()} \"{kw.upper()}\"" if kw else text
                cands.append((0, item("cta_card", words[s[0]]["start"], duration,
                                      "call to action", text=label, z="center")))
    # Runs of 2+ questions -> sticky note / checklist that fills in as she asks.
    kind = "sticky_notes" if "sticky_notes" in elements else (
        "lists" if "lists" in elements else None)
    if kind:
        run_ = []
        for s in sentences + [None]:
            if s is not None and is_question(words, s):
                run_.append(s)
                continue
            if len(run_) >= 2:
                cands.append((1, item(kind, words[run_[0][0]]["start"],
                                      words[run_[-1][-1]]["end"] + 1.2, "list of questions",
                                      items=[{"text": sentence_text(words, q),
                                              "at": words[q[0]]["start"]} for q in run_])))
            run_ = []
    # Headline (its own brand setting, in the headline font): an opening hook
    # title, a small title that stays at the top, or both.
    hstyle = brand.get("headline", {}).get("style") or (
        "opening_hook" if "text_callouts" in elements else "none")
    if hstyle != "none" and sentences:
        s = sentences[0]
        draft = [words[i]["text"].strip(",.") for i in s][:6]
        draft[0] = _cap_first(draft[0])
        hook_end = round(min(max(words[s[-1]]["end"], 2.5), 3.5), 3)
        if hstyle in ("opening_hook", "both"):
            cands.append((0, item("text_callouts", 0.0, hook_end,
                                  "headline: opening hook (draft - Claude rewrites it short)",
                                  draft=True, text=" ".join(draft), role="headline")))
        if hstyle in ("persistent", "both"):
            cands.append((0, item("headline_bar", hook_end if hstyle == "both" else 0.0,
                                  duration, "headline: title for the whole reel (draft)",
                                  draft=True, z="top_edge", text=" ".join(draft),
                                  role="headline")))
    # Spoken lists ("how to film, edit, and turn ...") -> checklist that fills
    # in as each item is said.
    if "lists" in elements:
        for s in sentences:
            items = spoken_list(words, s)
            if items:
                cands.append((1, item("lists", items[0]["at"], words[s[-1]]["end"] + 1.2,
                                      "spoken list", items=items)))
    # Named things ("Morning Light Studio") -> key-phrase card.
    if "keyword_cards" in elements:
        for s in sentences:
            names, cur = [], []
            for pos, i in enumerate(s):
                t = words[i]["text"].strip(",.?!\"")
                if pos > 0 and t[:1].isupper() and t.lower() not in ("i", "i'm", "okay"):
                    cur.append(i)
                else:
                    if len(cur) >= 2:
                        names.append(cur)
                    cur = []
            if len(cur) >= 2:
                names.append(cur)
            for n in names:
                cands.append((2, item("keyword_cards", words[n[0]]["start"],
                                      words[n[-1]]["end"] + 2.0, "named thing",
                                      text=" ".join(words[i]["text"].strip(",.?!") for i in n))))
    # Numbers -> callout.
    if "text_callouts" in elements:
        for i, w in enumerate(words):
            if re.search(r"\d", w["text"]):
                cands.append((3, item("text_callouts", w["start"], w["end"] + 2.0, "number",
                                      text=w["text"].strip(",."))))
    if "arrows" in elements:
        for s in sentences:
            text = sentence_text(words, s)
            m = CTA.search(text)
            if m and m.group(1).lower() == "comment":
                # point at the comment button on the right-hand rail
                at = next((words[i]["start"] for i in s
                           if norm(words[i]["text"]).startswith("comment")), words[s[0]]["start"])
                cands.append((1, item("arrows", at, at + 2.6, "points to the comment button",
                                      z="center", direction="down_right",
                                      target="comment_button")))
                continue
            for rx, direction in POINTING:
                hit = rx.search(text)
                if hit:
                    first = hit.group(0).split()[0].lower()
                    at = next((words[i]["start"] for i in s
                               if norm(words[i]["text"]) == norm(first)), words[s[0]]["start"])
                    cands.append((3, item("arrows", at, at + 2.2, f"says '{hit.group(0)}'",
                                          z="center", direction=direction)))
                    break
    if "lower_third" in elements and brand.get("name"):
        cands.append((4, item("lower_third", 0.8, 3.8, "who's talking", z="lower_third",
                              text=brand["name"])))
    if "emoji" in elements:
        for i in sorted(emph_idx):
            e = EMOJI.get(norm(words[i]["text"]))
            if e:
                cands.append((5, item("emoji", words[i]["start"], words[i]["start"] + 1.2,
                                      f"emphasis on '{words[i]['text']}'", z="center",
                                      emoji=e)))

    picked = []
    for pri, it in sorted(cands, key=lambda c: (c[0], c[1]["start"])):
        def clashes():
            if it["type"] == "arrows":
                return []  # arrows accompany other graphics; layout keeps them apart
            return [p for p in picked if it["start"] < p["end"] and it["end"] > p["start"]
                    and p["type"] != "arrows"
                    and (p["zone"] == it["zone"] or "center" in (p["zone"], it["zone"]))]
        # Only the tail overlaps something already placed: end it just before.
        for p in clashes():
            if p["start"] > it["start"] + 1.5:
                it["end"] = round(p["start"] - 0.1, 3)
        clash = bool(clashes())
        # Density: at most one graphic per `gap` seconds overall, and a beat
        # of breathing room between one ending and the next starting.
        others = [p for p in picked if p["type"] not in ("progress_bar", "cta_card", "arrows",
                                                          "headline_bar")]
        room = min(1.0, 0.2 * gap)
        too_close = it["type"] not in ("cta_card", "arrows", "headline_bar") and any(
            it["start"] < p["end"] + room and it["end"] > p["start"] - room for p in others)
        full = it["type"] not in ("cta_card", "arrows", "headline_bar") and \
            it.get("role") != "headline" and len(others) >= max(1, int(duration // gap))
        repeat = it["type"] == "emoji" and any(
            p.get("emoji") == it.get("emoji") for p in picked)   # each emoji once per reel
        if not clash and not too_close and not full and not repeat:
            picked.append(it)
    logo = brand.get("logo")
    if logo and logo.get("id"):
        picked.append({"type": "image", "role": "logo", "asset": logo["id"], "start": 0.0,
                       "end": round(duration, 3), "zone": "top_edge", "y": ZONE_Y["top_edge"],
                       "place": logo.get("position", "top_right"), "opacity": logo.get("opacity", 0.9),
                       "size": logo.get("size", 180), "reason": "your logo", "draft": False})
    if "progress_bar" in elements:
        picked.append({"type": "progress_bar", "start": 0.0, "end": round(duration, 3),
                       "zone": "top_edge", "y": ZONE_Y["top_edge"], "reason": "watch-time cue",
                       "draft": False})
    picked.sort(key=lambda p: p["start"])
    for n, p in enumerate(picked, 1):
        p["id"] = f"g{n}"
        p["style"] = _style(brand, p["type"])
    return picked


# -- sound ----------------------------------------------------------------------

SFX_KIND = {"zoom_punch": "whoosh", "graphic_in": "pop", "emoji": "pop", "cta": "ding",
            "headline": "pop", "tick": "click"}


def find_sfx_file(kind):
    """Customer's own sound (assets/sfx/<kind>*) or the generated pack."""
    from .sfx import resolve
    return resolve(kind)


def custom_sound(s, event):
    """(path, name) of the customer's sound for an event, or None if not set.
    A set-but-missing sound returns ("", name) so the render check catches it."""
    from . import library
    aid = (s.get("sounds") or {}).get(event)
    if not aid:
        return None
    a = library.get(aid)
    p = library.path_of(aid)
    return (str(p) if p else "", a["name"] if a else aid,
            library.level_match_db(a) if (a and p) else 0.0)


def plan_sfx(zooms, graphics, duration, s):
    allowed = set(s.get("events", []))
    if not allowed:
        return []
    events = []
    for z in zooms:
        if z["type"] == "punch":
            events.append(("zoom_punch", max(0.0, z["start"] - 0.08), z["id"]))
    for g in graphics:
        if g["type"] == "cta_card":
            events.append(("cta", g["start"], g["id"]))
        elif g["type"] == "emoji":
            events.append(("emoji", g["start"], g["id"]))
        elif g.get("role") == "headline":
            events.append(("headline", g["start"], g["id"]))
        elif g.get("role") == "logo":
            continue   # a watermark is silent
        elif g["type"] != "progress_bar":
            events.append(("graphic_in", g["start"], g["id"]))
    out, last = [], -99.0
    for ev, t, ref in sorted(events, key=lambda e: e[1]):
        if ev == "headline" and ev not in allowed and "graphic_in" in allowed:
            ev_ok = True       # older profiles: the headline pops like other graphics
        else:
            ev_ok = ev in allowed
        if not ev_ok or t - last < s.get("min_gap_s", 1.2) or t >= duration:
            continue
        custom = custom_sound(s, ev)
        if custom is not None:
            f, kind = custom[0] or None, custom[1]
            item = {"custom": True, "missing_custom": not custom[0], "level_db": custom[2]}
        else:
            kind = SFX_KIND[ev]
            f = find_sfx_file(kind)
            item = {}
        out.append({"id": f"s{len(out) + 1}", "at": round(t, 3), "kind": kind, "event": ev,
                    "for": ref, "gain_db": s.get("gain_db", -18), "file": f,
                    "needs_asset": f is None, **item})
        last = t
    return out


def plan_music(m):
    if m.get("style") in (None, "none"):
        return None
    return {"style": m["style"], "file": m.get("file"), "gain_db": m.get("gain_db", -24),
            "duck_under_voice": m.get("duck_under_voice", True),
            "needs_asset": not m.get("file")}


# -- overrides + feasibility ----------------------------------------------------

def apply_overrides(edit, ov):
    """edit.overrides.json (Claude's review + the customer's review page):

    {"remove": ["g2", "z3"],
     "set": {"g1": {"text": "...", "style": {"custom_background": "#..."},
                    "_match": {"type": "emoji", "start": 30.6}}},
     "headline": {"text": "..."},
     "add": {"graphics": [...], "zooms": [...], "sfx": [...]}}

    `_match` finds the same graphic again after a re-plan shifted ids
    (same type, start within 2 s). Styles are merged, not replaced.
    """
    sets = ov.get("set", {})
    remove = set(ov.get("remove", []))

    def target(layer, key, spec):
        m = spec.get("_match") if isinstance(spec, dict) else None
        if m:
            near = [x for x in edit[layer] if x.get("type") == m.get("type")
                    and abs(x["start"] - m.get("start", 0)) <= 2.0]
            if near:
                return min(near, key=lambda x: abs(x["start"] - m["start"]))["id"]
        return key

    resolved, gone = {}, set()
    for layer in ("zooms", "graphics", "sfx"):
        ids = {x["id"] for x in edit[layer]}
        for key, spec in sets.items():
            tid = target(layer, key, spec) if layer == "graphics" else key
            if tid in ids:
                resolved[tid] = {k: v for k, v in spec.items() if k != "_match"}
        for key in remove:
            gone.add(key)
        for key, spec in ov.get("remove_match", {}).items():
            tid = target(layer, key, {"_match": spec}) if layer == "graphics" else key
            if tid in ids:
                gone.add(tid)

    def merged(x):
        spec = resolved.get(x["id"])
        if not spec:
            return x
        out = dict(x, **{k: v for k, v in spec.items() if k != "style"})
        if "style" in spec:
            # None = "back to the brand": drop the customer's own choice and keep
            # what the plan had (e.g. its planned animation).
            planned = x.get("style", {})
            out["style"] = dict(planned)
            for k, v in spec["style"].items():
                if v is not None:
                    out["style"][k] = v
                elif k in planned and not k.startswith("custom_"):
                    out["style"][k] = planned[k]
                else:
                    out["style"].pop(k, None)
        out["draft"] = False
        out["reason"] = re.sub(r"\s*\(draft[^)]*\)", " (reviewed)", x.get("reason", ""))
        return out

    for layer in ("zooms", "graphics", "sfx"):
        edit[layer] = [merged(x) for x in edit[layer] if x["id"] not in gone]
    # A removed graphic takes its sound with it; a swapped sound gets its file.
    edit["sfx"] = [x for x in edit["sfx"] if x.get("for") not in gone]
    for x in edit["sfx"]:
        if x["id"] in resolved and "kind" in resolved[x["id"]]:
            f = find_sfx_file(x["kind"])
            # a built-in sound now: never labelled as the customer's own
            x.update(file=f, needs_asset=f is None, custom=False, missing_custom=False)
            x.pop("level_db", None)
    items = edit["captions"]["items"]
    edit["captions"]["items"] = [dict(x, **sets.get(x["id"], {})) for x in items
                                 if x["id"] not in gone]
    if ov.get("headline", {}).get("text"):
        for x in edit["graphics"]:
            if x.get("role") == "headline":
                x["text"] = ov["headline"]["text"]
                x["draft"] = False
                x["reason"] = re.sub(r"\s*\(draft[^)]*\)", " (reviewed)", x["reason"])

    # Customer requests: new graphics, zooms, sound effects.
    add = ov.get("add", {})
    for n, g in enumerate(add.get("graphics", []), 1):
        g = dict(g)
        g.setdefault("zone", "upper_third" if g.get("type") != "emoji" else "center")
        g.setdefault("y", ZONE_Y.get(g["zone"], 560))
        g.update(id=f"rg{n}", source="review", draft=False,
                 reason=g.get("reason", "requested in review"))
        g.setdefault("style", {})
        edit["graphics"].append(g)
    for n, z in enumerate(add.get("zooms", []), 1):
        z = dict(z)
        z.update(id=f"rz{n}", source="review", reason=z.get("reason", "requested in review"))
        z.setdefault("ease_s", 0.0 if z.get("type") == "punch" else round(z["end"] - z["start"], 2))
        z.setdefault("focus", {"x": 0.5, "y": 0.4})
        # a requested zoom replaces any planned zoom it overlaps
        edit["zooms"] = [x for x in edit["zooms"]
                         if not (x["start"] < z["end"] and x["end"] > z["start"])] + [z]
    edit["zooms"].sort(key=lambda x: x["start"])
    for n, sfx_ in enumerate(add.get("sfx", []), 1):
        sfx_ = dict(sfx_)
        if str(sfx_.get("kind", "")).startswith("library:"):
            from . import library
            aid = sfx_["kind"].split(":", 1)[1]
            p = library.path_of(aid)
            a = library.get(aid) or {}
            sfx_.update(id=f"rs{n}", source="review", event="requested", custom=True,
                        file=str(p) if p else None, needs_asset=p is None,
                        missing_custom=p is None, kind=a.get("name", aid),
                        level_db=library.level_match_db(a) if p else 0.0)
            sfx_.setdefault("gain_db", -10)
            edit["sfx"].append(sfx_)
            continue
        f = find_sfx_file(sfx_.get("kind", "pop"))
        sfx_.update(id=f"rs{n}", source="review", event="requested", file=f,
                    needs_asset=f is None)
        sfx_.setdefault("gain_db", -12)
        edit["sfx"].append(sfx_)
    # Tick boxes click as each one ticks (timed from the items themselves, so
    # the sound can't drift from the tick after a re-cut).
    n = 0
    for g in edit["graphics"]:
        if (g.get("style") or {}).get("checks"):
            for it in g.get("items", []):
                n += 1
                mine = custom_sound(edit.get("_sfx_brand", {}), "tick")
                f = (mine[0] or None) if mine else find_sfx_file("click")
                lvl = mine[2] if mine else 0.0
                edit["sfx"].append({"id": f"ck{n}", "at": round(it["at"] + TICK_DELAY, 3),
                                    "kind": "click", "event": "tick", "for": g["id"],
                                    "gain_db": -8, "file": f, "needs_asset": f is None,
                                    "source": "review", "level_db": lvl})
    # Words shown big on a full-screen overlay aren't captioned twice.
    for g in edit["graphics"]:
        if g["type"] == "full_overlay" and g.get("hide_captions", True):
            edit["captions"]["items"] = [c for c in edit["captions"]["items"]
                                         if not (c["start"] >= g["start"] - 0.05 and
                                                 c["start"] < g["end"])]
    edit["sfx"].sort(key=lambda x: x["at"])
    edit["graphics"].sort(key=lambda x: x["start"])


def render_requirements(edit):
    """How each layer will be rendered, and whether this ffmpeg can do it."""
    have = ffmpeg_filters()
    rows = []

    def need(layer, method, filters, external=None):
        missing = [f for f in filters if f not in have]
        rows.append({"layer": layer, "method": method, "ffmpeg_filters": filters,
                     "ffmpeg_ok": not missing, "missing": missing,
                     "external": external})

    if edit["captions"]["items"] or edit["graphics"]:
        need("captions + graphics", "draw transparent frames outside ffmpeg, composite with overlay",
             ["overlay"], external="frame renderer (next phase; not built yet)")
    if edit["zooms"]:
        need("zooms", "zoompan on a 2x frame, centred on the face", ["zoompan", "scale", "crop"])
    if edit["sfx"]:
        need("sound effects", "delay each effect to its time, mix under the voice",
             ["adelay", "amix", "volume"], external="sound files in assets/sfx/"
             if any(s["needs_asset"] for s in edit["sfx"]) else None)
    if edit["music"]:
        need("music", "music bed ducked under the voice", ["amix", "sidechaincompress", "volume"],
             external="a music file" if edit["music"]["needs_asset"] else None)
    rows.append({"layer": "text", "method": "never drawtext/subtitles",
                 "ffmpeg_filters": [], "ffmpeg_ok": True, "missing": [],
                 "external": None,
                 "note": f"drawtext available: {'drawtext' in have}, subtitles: {'subtitles' in have}"})
    return rows


# -- readable summary -----------------------------------------------------------

def plan_markdown(edit, reel_name):
    def ts(t):
        return f"{int(t // 60)}:{t % 60:04.1f}"
    cap = edit["captions"]
    lines = [f"# Edit plan: {reel_name}", "",
             f"{edit['duration']:.1f}s · {len(cap['items'])} captions · {len(edit['zooms'])} zooms · "
             f"{len(edit['graphics'])} graphics · {len(edit['sfx'])} sound effects · "
             f"music: {edit['music']['style'] if edit['music'] else 'none'}", ""]
    drafts = [g for g in edit["graphics"] if g.get("draft")]
    if drafts:
        lines += ["**Needs Claude's review:** " + ", ".join(
            f"{g['id']} ({g['type']}: \"{g.get('text', '')}\")" for g in drafts), ""]
    lines += ["## Timeline", "", "| Time | Layer | What | Why |", "|---|---|---|---|"]
    rows = []
    for z in edit["zooms"]:
        rows.append((z["start"], f"{ts(z['start'])}–{ts(z['end'])}", f"zoom {z['id']}",
                     f"{z['type']} to {z['scale']}x", z["reason"]))
    for g in edit["graphics"]:
        what = g.get("text") or g.get("emoji") or ", ".join(i["text"] for i in g.get("items", [])) \
            or g["type"]
        rows.append((g["start"], f"{ts(g['start'])}–{ts(g['end'])}", f"{g['type']} {g['id']}",
                     what, g["reason"]))
    for s in edit["sfx"]:
        rows.append((s["at"], ts(s["at"]), f"sfx {s['id']}",
                     s["kind"] + (" (needs file)" if s["needs_asset"] else ""), s["event"]))
    for _, t, layer, what, why in sorted(rows):
        lines.append(f"| {t} | {layer} | {what} | {why} |")
    if cap["items"]:
        lines += ["", f"## Captions ({cap['style']['style']}, first 8)", ""]
        for c in cap["items"][:8]:
            text = " ".join(f"**{w['text']}**" if w["emphasis"] else w["text"] for w in c["words"])
            lines.append(f"- {ts(c['start'])} {text}")
    lines += ["", "## Can this machine render it?", ""]
    for r in edit["render_requirements"]:
        state = "ready" if r["ffmpeg_ok"] else f"missing {', '.join(r['missing'])}"
        extra = f"; needs {r['external']}" if r.get("external") else ""
        lines.append(f"- **{r['layer']}**: {r['method']} — ffmpeg {state}{extra}"
                     + (f" ({r['note']})" if r.get("note") else ""))
    return "\n".join(lines) + "\n"
