"""The creative plan: Claude's content-aware decisions for one reel.

    <reel>/creative.json   written by Claude after the cut (see the skill)

Claude reads what is said (reel.py creative-context), works out the message
and its beats, and decides which moments deserve something on screen, which
intent each one is, short on-screen wording, which words carry the meaning,
and where a zoom helps - and, just as important, where nothing is needed.

The engine never trusts the plan blindly. validate() rejects anything that
would invent words or numbers, is too long to read, breaks the customer's
rules or brand choices, crowds the screen, or has no reason. Spoken captions
are never changed: on-screen graphic text is separate and may be shortened.

Format (version 1):
{
  "version": 1,
  "summary": "one line: what the reel says",
  "tone": "calm and practical",
  "beats": [{"type": "hook|setup|point|step|proof|contrast|question|payoff|cta|aside",
             "from": 0, "to": 7}],
  "key_words": [3, 18, 40],               # word numbers that carry the meaning
  "moments": [{
      "intent": "hook|headline_bar|key_phrase|stat|list|question_list|cta|reaction|pointer|lower_third|quote|contrast|tip",
      "from": 0, "to": 7,                  # spoken words it belongs to
      "quote": "here are three tips for better videos",   # those words, as said
      "text": "3 tips for better videos",   # on-screen wording (short)
      "items": [{"text": "Film near a window", "at_word": 12}],   # list intents
      "emoji": "📷", "direction": "down_right", "until": "end",   # where relevant
      "before": "posting every day", "after": "posting with purpose",   # contrast only
      "design": "bar",                     # optional: one of the style's designs (creative-context lists them)
      "place": "lower left",               # optional: top | upper | middle | lower | above_head,
                                           #   with left | right | centre; default: best spot for the footage
      "backing": "none",                   # optional: none (clean text on the footage) | box; default: the style's
      "why": "the promise of the reel: viewers decide to stay here",
      "source": "plan" | "customer"        # customer = their exact wording/request
  }],
  "zooms": [{"from": 30, "to": 36, "kind": "push|punch", "why": "..."}],   # optional
  "no_graphics": [{"from": 40, "to": 55, "why": "personal story: keep it about her face"}]
}
"""

import hashlib
import json
import re

PLACES = ["top", "upper", "middle", "lower", "above_head", "left", "right", "centre"]

from .project import read_json, write_json

INTENTS = ["hook", "headline_bar", "key_phrase", "stat", "list", "question_list", "cta",
           "reaction", "pointer", "lower_third", "quote", "contrast", "tip"]
BEATS = ["hook", "setup", "point", "step", "proof", "contrast", "question", "payoff", "cta", "aside"]
# intent -> the graphic type the layout engine, review page and Classic understand
TYPE = {"hook": "text_callouts", "headline_bar": "headline_bar", "key_phrase": "keyword_cards",
        "stat": "text_callouts", "list": "lists", "question_list": "sticky_notes", "cta": "cta_card",
        "reaction": "emoji", "pointer": "arrows", "lower_third": "lower_third",
        "quote": "keyword_cards", "contrast": "keyword_cards", "tip": "keyword_cards"}
# intent -> brand graphics elements that allow it (brand choice; a customer request overrides)
ELEMENTS = {"key_phrase": {"keyword_cards", "text_callouts"}, "stat": {"text_callouts", "keyword_cards"},
            "list": {"lists"}, "question_list": {"sticky_notes", "lists"}, "cta": {"cta_card"},
            "reaction": {"emoji"}, "pointer": {"arrows"}, "lower_third": {"lower_third"},
            "quote": {"keyword_cards", "text_callouts"}, "contrast": {"keyword_cards", "text_callouts"},
            "tip": {"keyword_cards", "text_callouts"}}
# readability limits for on-screen wording
LIMITS = {"hook": (7, 42), "headline_bar": (6, 36), "key_phrase": (8, 48), "stat": (5, 28),
          "cta": (6, 34), "lower_third": (4, 30), "item": (7, 40), "quote": (12, 70), "tip": (9, 52),
          "side": (5, 30)}
# how long a graphic stays after its words (seconds)
HOLD = {"hook": 0.6, "headline_bar": 0.0, "key_phrase": 1.0, "stat": 1.4, "list": 1.2,
        "question_list": 1.2, "cta": 0.0, "reaction": 0.6, "pointer": 1.2, "lower_third": 2.5,
        "quote": 1.4, "contrast": 1.6, "tip": 1.2}
DIRECTIONS = {"down_right", "up_left", "down", "right", "left", "up"}
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
                "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000,
                "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "half": 50}
# words that may appear on screen without being said (labels, glue, symbols)
FREE = set("""a an the and or but so to of in on at for with from by as is are be your you my our
this that these those it its how why what when who not no yes vs & + - — : % # @ x step tip tips
next new one two three four five six seven eight nine ten first second third percent""".split())


class BriefError(ValueError):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def norm(t):
    return re.sub(r"[^a-z0-9%']", "", str(t).lower().replace("’", "'"))


def stem(t):
    t = norm(t).replace("'", "")
    for suf in ("ing", "ers", "er", "ed", "es", "s", "ly"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def cut_signature(words):
    return hashlib.sha256(" ".join(norm(w["text"]) for w in words).encode()).hexdigest()[:16]


def spoken_numbers(words):
    """Every number said, as digits (words like 'eighty percent' included)."""
    nums = set()
    for w in words:
        t = norm(w["text"]).replace("%", "")
        if re.fullmatch(r"\d+(\.\d+)?", t):
            nums.add(t.rstrip("0").rstrip(".") if "." in t else t)
        elif t in NUMBER_WORDS:
            nums.add(str(NUMBER_WORDS[t]))
    tens = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}
    for i, w in enumerate(words):
        t = norm(w["text"])
        if t in tens:
            nums.add(str(tens[t]))
            if i + 1 < len(words) and norm(words[i + 1]["text"]) in NUMBER_WORDS:
                nums.add(str(tens[t] + NUMBER_WORDS[norm(words[i + 1]["text"])]))
    return nums


# -- context for Claude --------------------------------------------------------

def context(words, duration, profile, reel_answers=None, reel_name=None):
    """Everything Claude needs to write the plan, in one compact structure."""
    from . import styles
    st = styles.resolve(profile)
    allowed = allowed_intents(profile)
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append(f"[{i}]{w['text']}")
        if w["text"].rstrip().endswith((".", "?", "!")) or len(cur) >= 16:
            lines.append(f"{words[int(cur[0][1:cur[0].index(']')])]['start']:6.2f}s " + " ".join(cur))
            cur = []
    if cur:
        lines.append(f"{words[int(cur[0][1:cur[0].index(']')])]['start']:6.2f}s " + " ".join(cur))
    g = profile.get("graphics", {})
    return {
        "duration": round(duration, 2),
        "cut_signature": cut_signature(words),
        "transcript": lines,
        "word_count": len(words),
        "style": {"pack": st["pack"], "mix": st["mix"], "direction": st["direction"],
                  "decorations_on": [d for d, v in st["decorations"].items() if v["on"]]},
        "customer_rules": st["rules"],
        "brand": {"personality": profile.get("aesthetic", {}).get("personality"),
                  "headline": profile.get("headline", {}).get("style"),
                  "graphics_elements": g.get("elements", []), "density": g.get("density"),
                  "max_graphics": max_graphics(profile, duration), "sound": profile.get("sfx", {}).get("style"),
                  "handle": profile.get("name")},
        "allowed_intents": sorted(allowed),
        "designs": _designs_context(profile, reel_name),
        "composition": {
            "place": PLACES,
            "backing": ["none", "box"],
            "how": ("Composition is your call per moment, for this footage; nothing has a fixed slot. "
                    "Leave \"place\" out and the editor finds the best clear spot (moving rather than "
                    "shrinking, lower when the person sits high in the frame). Set it when another spot "
                    "composes better or the customer asked. Text may tuck over hair or the top of the head "
                    "when it stays readable; never over the face. \"backing\": \"none\" for clean text "
                    "straight on the footage when that looks best (common for bold headlines), \"box\" "
                    "only when it truly helps legibility or matches their taste; their rules always win. "
                    "Keep text in the platform safe zones without making it small."),
        },
        "settings_readback": __import__("laine_reel.brand", fromlist=["explain"]).explain(profile),
        "reference": reference_context(profile),
        "limits_words_chars": LIMITS,
        "reel_instructions": (reel_answers or {}).get("instructions", ""),
        "how": ("Write creative.json in the reel folder. Choose few, purposeful moments; leave stretches "
                "with nothing when the face and words carry it. On-screen text must come from what is "
                "said (shorten, never invent facts or numbers). Every moment needs a why. "
                "Then run: python3 scripts/reel.py plan <reel>"),
    }


def _designs_context(profile, reel_name=None):
    """The style's designs per intent and what this customer's recent reels used,
    so Claude can vary the look on purpose. Without a "design", the editor picks
    the one their recent reels used least."""
    from . import designs
    cat = designs.catalog(profile)
    if not cat:
        return {"available": False}
    return {"available": True, "by_intent": cat, "recent_reels": designs.recent_for_context(profile, reel_name),
            "how": ("Optional per moment: \"design\": \"<id>\". Choose one that suits the content "
                    "(a percentage suits a bar; a contrast needs before/after) and differs from the "
                    "recent reels where it fits. Keep one design per intent within a reel unless "
                    "there's a reason. Leave it out to let the editor vary it automatically.")}


def set_headline(reel, text):
    """The customer's chosen headline becomes the plan's hook (their wording), so the
    plan, the suggestions and the video agree. No-op without a plan or a hook."""
    brief = load(reel)
    if not brief:
        return False
    hook = next((m for m in brief.get("moments", []) if m.get("intent") in ("hook", "headline_bar")), None)
    if not hook or not str(text).strip():
        return False
    hook["text"], hook["source"] = str(text).strip(), "customer"
    words = read_json(reel.path("transcript.cut.json"))["words"]
    save(reel, brief, words)
    return True


def hook_text(reel):
    brief = load(reel) or {}
    return next((m.get("text") for m in brief.get("moments", []) if m.get("intent") in ("hook", "headline_bar")),
                None)


def reference_context(profile):
    """What the customer likes about their reference reel, as measured traits -
    only the parts they like, and explicitly what to stay away from. Inspiration:
    their own settings and rules come first; nothing is copied."""
    from . import config, reference_style
    vis = reference_style.load()
    prefs = (profile.get("answers") or {}).get("reference_prefs") or {}
    if not vis or not vis.get("available"):
        return {"available": False}
    use, avoid = set(prefs.get("use") or []), set(prefs.get("avoid") or [])
    cat_map = {"captions": "captions", "typography": "captions", "animation": "zooms", "zooms": "zooms",
               "graphics": "graphics", "colour": "colour"}
    traits = {}
    for cat in (use or set(reference_style.CATEGORIES)) - avoid:
        key = cat_map.get(cat)
        if key and vis.get(key):
            traits[cat] = vis[key]
    interp = config.brand_dir() / "reference" / "traits.json"
    return {"available": True, "likes": sorted(use), "avoid": sorted(avoid), "their_words": prefs.get("notes", ""),
            "traits": traits,
            "interpretation": json.loads(interp.read_text()) if interp.exists() else None,
            "rule": "Inspiration only, below the customer's own settings, words and rules. Never reuse the "
                    "reference's text, logos or artwork; never copy its layout exactly."}


def _reference_words():
    from . import reference_style
    vis = reference_style.load() or {}
    return [p for p in vis.get("seen_text", []) if len(p.split()) >= 3]


def _copies_reference(text, phrases):
    t = " " + " ".join(norm(w) for w in str(text).split()) + " "
    tw = t.split()
    for ph in phrases:
        if f" {ph} " in t:
            return ph
        pw = ph.split()
        for i in range(len(pw) - 3):
            if " " + " ".join(pw[i:i + 4]) + " " in t:
                return " ".join(pw[i:i + 4])
    return None


def max_graphics(profile, duration):
    gap = profile.get("graphics", {}).get("min_gap_s", 5.0)
    return max(1, int(duration // gap))


def allowed_intents(profile):
    from . import styles
    st = styles.resolve(profile)
    elements = set(profile.get("graphics", {}).get("elements", []))
    hstyle = profile.get("headline", {}).get("style", "none")
    comps = st["aspects"]["components"].get("by_intent", {})
    out = set()
    for intent in INTENTS:
        if intent == "hook" and hstyle not in ("opening_hook", "both"):
            continue
        if intent == "headline_bar" and hstyle not in ("persistent", "both"):
            continue
        if intent in ELEMENTS and not (ELEMENTS[intent] & elements):
            continue
        if styles.intent_for(TYPE[intent]) in st["blocked_intents"] or intent in st["blocked_intents"]:
            continue
        if comps and intent not in comps and not st["legacy"]:
            continue
        out.add(intent)
    return out


# -- loading and re-anchoring --------------------------------------------------------

def load(reel):
    p = reel.path("creative.json")
    return read_json(p) if p.exists() else None


def _find(words, quote, near):
    q = [norm(x) for x in str(quote).split() if norm(x)]
    if not q:
        return None
    hits = [i for i in range(len(words) - len(q) + 1)
            if [norm(words[i + k]["text"]) for k in range(len(q))] == q]
    return min(hits, key=lambda i: abs(i - near)) if hits else None


def complete(brief, words):
    """A plan Claude just wrote is for the current cut: stamp it, and record each
    moment's spoken words (its quote) so a later re-cut can find it again."""
    if not brief or brief.get("cut_signature"):
        return brief, False
    n = len(words)
    for m in brief.get("moments", []):
        lo, hi = m.get("from"), m.get("to")
        if not m.get("quote") and isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi < n:
            m["quote"] = " ".join(w["text"] for w in words[lo:hi + 1])
    brief["cut_signature"] = cut_signature(words)
    return brief, True


def reanchor(brief, words):
    """After a re-cut the word numbers shift: find each moment's quote again.
    Returns (brief, notes). Moments whose words were cut are dropped, with a note."""
    if not brief or brief.get("cut_signature") == cut_signature(words):
        return brief, []
    notes, out = [], []
    for m in brief.get("moments", []):
        q = m.get("quote")
        i = _find(words, q, m.get("from", 0)) if q else None
        if i is None:
            notes.append(f"dropped {m.get('intent')} '{m.get('text') or q}': its words were cut")
            continue
        shift = i - m["from"]
        m = dict(m, **{"from": i, "to": m["to"] + shift})
        if m.get("items"):
            m["items"] = [dict(it, at_word=it["at_word"] + shift) for it in m["items"]]
        out.append(m)
    b = dict(brief, moments=out, cut_signature=cut_signature(words))
    # key words and zoom moments are plain word numbers: after a re-cut they're
    # reset (automatic emphasis and the style's zooms) until Claude updates the plan
    if b.pop("key_words", None):
        notes.append("key words reset after the re-cut (update creative.json to choose them again)")
    if b.pop("zooms", None):
        notes.append("zoom moments reset after the re-cut (the style's zooms are used)")
    return b, notes


# -- validation -----------------------------------------------------------------------

def _words_ok(text, words, lo, hi, window=40):
    """Content words of on-screen text must have been said near the moment
    (or anywhere in the reel for the hook). Returns the unsaid words."""
    said = {stem(w["text"]) for w in words[max(0, lo - window): hi + window + 1]}
    missing = []
    for tok in re.findall(r"[A-Za-z0-9%'’]+", text):
        n = norm(tok)
        if not n or n in FREE or re.fullmatch(r"\d+%?", n):
            continue
        if stem(tok) not in said:
            missing.append(tok)
    return missing


def _numbers_ok(text, said_numbers):
    bad = []
    for n in re.findall(r"\d+(?:\.\d+)?", text):
        if n not in said_numbers:
            bad.append(n)
    return bad


def validate(brief, words, profile, duration):
    """Raise BriefError with every problem found, or return the brief."""
    p = []
    if not isinstance(brief, dict) or brief.get("version") != 1:
        raise BriefError(["creative.json must be an object with \"version\": 1"])
    n = len(words)
    nums = spoken_numbers(words)
    allowed = allowed_intents(profile)
    from . import styles as _st
    rule_flags = set((_st.resolve(profile).get("rules") or {}).get("flags", []))
    for k in ("summary",):
        if not str(brief.get(k) or "").strip():
            p.append(f"missing \"{k}\"")
    for b in brief.get("beats", []):
        if b.get("type") not in BEATS:
            p.append(f"unknown beat type {b.get('type')!r}")
        if not (0 <= b.get("from", -1) <= b.get("to", -1) < n):
            p.append(f"beat {b.get('type')} has word numbers outside 0..{n - 1}")
    kws = brief.get("key_words", [])
    if any(not isinstance(k, int) or not 0 <= k < n for k in kws):
        p.append(f"key_words must be word numbers 0..{n - 1}")
    from .planner import STOP, split_sentences
    for k in kws:
        if isinstance(k, int) and 0 <= k < n and norm(words[k]["text"]) in STOP:
            p.append(f"key word [{k}] '{words[k]['text']}' is a filler word; pick words that carry the meaning")
    sentences = split_sentences(words)
    if len(kws) > max(1, int(len(sentences) * 1.5)):
        p.append(f"too many key words ({len(kws)}); at most {max(1, int(len(sentences) * 1.5))} so they stand out")
    moments = brief.get("moments", [])
    chosen = [m for m in moments if m.get("source") != "customer"]   # their requests don't count
    if len(chosen) > max_graphics(profile, duration) + 2:
        p.append(f"{len(chosen)} moments is more than this brand's density allows "
                 f"(about {max_graphics(profile, duration)}); keep only the ones that matter")
    spans = []
    for j, m in enumerate(moments, 1):
        tag = f"moment {j} ({m.get('intent')})"
        it = m.get("intent")
        if it not in INTENTS:
            p.append(f"{tag}: unknown intent; use one of {', '.join(INTENTS)}")
            continue
        customer = m.get("source") == "customer"
        if it not in allowed and not customer:
            p.append(f"{tag}: not available for this brand/style/rules (allowed: {', '.join(sorted(allowed))})")
        lo, hi = m.get("from", -1), m.get("to", -1)
        if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi < n):
            p.append(f"{tag}: from/to must be word numbers 0..{n - 1}")
            continue
        if not str(m.get("why") or "").strip():
            p.append(f"{tag}: needs a \"why\" (every choice has a purpose)")
        quote = " ".join(norm(w["text"]) for w in words[lo:hi + 1])
        if m.get("quote") and [norm(x) for x in m["quote"].split() if norm(x)] != quote.split():
            p.append(f"{tag}: quote doesn't match words {lo}-{hi} (they say: \"{quote}\")")
        texts = []
        if it in ("list", "question_list"):
            items = m.get("items") or []
            if not 2 <= len(items) <= 5:
                p.append(f"{tag}: lists need 2-5 items")
            for i2, x in enumerate(items):
                texts.append(("item", x.get("text", "")))
                if not (isinstance(x.get("at_word"), int) and lo <= x["at_word"] <= hi):
                    p.append(f"{tag}: item {i2 + 1} needs at_word inside {lo}-{hi}")
            ats = [x.get("at_word", 0) for x in items]
            if ats != sorted(ats):
                p.append(f"{tag}: items must be in the order they're said")
        elif it == "reaction":
            if not m.get("emoji"):
                p.append(f"{tag}: needs an emoji")
        elif it == "pointer":
            if m.get("direction") not in DIRECTIONS:
                p.append(f"{tag}: direction must be one of {', '.join(sorted(DIRECTIONS))}")
        elif it == "contrast":
            if not (m.get("before") and m.get("after")):
                p.append(f"{tag}: a comparison needs \"before\" (what's wrong / the old way) and \"after\" "
                         "(what's right / the new way)")
            texts += [("side", m.get("before", "")), ("side", m.get("after", ""))]
        else:
            texts.append((it, m.get("text", "")))
        for w in str(m.get("place") or "").split():
            if w not in PLACES:
                p.append(f"{tag}: place \"{w}\" isn't one of {', '.join(PLACES)}")
        if m.get("backing") not in (None, "none", "box", "auto"):
            p.append(f"{tag}: backing must be \"none\" or \"box\"")
        if m.get("backing") == "box" and "no_boxes" in rule_flags:
            p.append(f"{tag}: the customer's rules say no boxes; leave backing out or use \"none\"")
        if m.get("design"):
            from . import designs as _d
            names = [v["id"] for v in _d.variants_for(profile, it)]
            if names and m["design"] not in names:
                p.append(f"{tag}: design \"{m['design']}\" isn't one of this style's designs for {it} "
                         f"({', '.join(names)})")
        ref_words = _reference_words()
        for kind, t in texts:
            hit = _copies_reference(t, ref_words) if ref_words else None
            if hit:
                p.append(f"{tag}: \"{t}\" repeats text from the reference reel (\"{hit}\") - another creator's "
                         "words are never reused; say it in the customer's own words")
            if not str(t).strip():
                p.append(f"{tag}: empty on-screen text")
                continue
            mw, mc = LIMITS[kind]
            if (len(t.split()) > mw or len(t) > mc) and not customer:
                p.append(f"{tag}: \"{t}\" is too long to read ({len(t.split())} words, {len(t)} chars; "
                         f"max {mw} words / {mc} chars) - shorten it")
            if not customer:
                bad_n = _numbers_ok(t, nums)
                if bad_n:
                    p.append(f"{tag}: number(s) {', '.join(bad_n)} weren't said - never invent numbers")
                miss = _words_ok(t, words, 0 if it == "hook" else lo, n - 1 if it == "hook" else hi)
                if miss:
                    p.append(f"{tag}: \"{t}\" uses words not said ({', '.join(miss)}) - use their words")
        if it == "stat" and not re.search(r"\d", m.get("text", "")):
            p.append(f"{tag}: a stat needs the number that was said")
        if it not in ("pointer",):
            spans.append((words[lo]["start"], words[hi]["end"], tag, it))
    # the brand's headline setting is an explicit choice
    hstyle = profile.get("headline", {}).get("style", "none")
    have = {m.get("intent") for m in moments}
    if hstyle in ("opening_hook", "both") and "hook" not in have:
        p.append("this brand shows an opening headline: add a \"hook\" moment at the start")
    if hstyle in ("persistent", "both") and "headline_bar" not in have:
        p.append("this brand shows a headline bar: add a \"headline_bar\" moment")
    # no clutter: one primary graphic at a time (a pointer may accompany one)
    spans.sort()
    for (a0, a1, at, ai), (b0, b1, bt, bi) in zip(spans, spans[1:]):
        if b0 < a1 - 0.05 and "headline_bar" not in (ai, bi):
            p.append(f"{at} and {bt} overlap in time; one at a time keeps it readable")
    for q in brief.get("no_graphics", []) or []:
        if not (0 <= q.get("from", -1) <= q.get("to", -1) < n) or not str(q.get("why") or "").strip():
            p.append("each no_graphics stretch needs word numbers from/to and a why")
            continue
        for m in moments:
            if isinstance(m.get("from"), int) and m.get("from", 0) <= q["to"] and m.get("to", -1) >= q["from"] \
                    and m.get("intent") != "headline_bar" and m.get("source") != "customer":
                p.append(f"{m.get('intent')} at words {m.get('from')}-{m.get('to')} is inside a stretch you "
                         f"marked for no graphic ({q['from']}-{q['to']})")
    for z in brief.get("zooms", []) or []:
        if z.get("kind") not in ("push", "punch") or not (0 <= z.get("from", -1) <= z.get("to", -1) < n):
            p.append("zooms need kind push/punch and word numbers from/to")
        elif not str(z.get("why") or "").strip():
            p.append("each zoom needs a why")
    if p:
        raise BriefError(p)
    return brief


# -- turning the plan into graphics --------------------------------------------------

def graphics(brief, words, duration, profile, zone_for):
    """Graphics in the format the layout, renderer and review page use."""
    out = []
    for m in brief.get("moments", []):
        it, lo, hi = m["intent"], m["from"], m["to"]
        start = words[lo]["start"]
        end = duration if m.get("until") == "end" or it == "cta" else words[hi]["end"] + HOLD[it]
        if it == "headline_bar":
            end = duration if m.get("until") == "end" else max(end, words[hi]["end"] + 2.0)
        g = {"type": TYPE[it], "start": round(max(0.0, start), 3), "end": round(min(duration, end), 3),
             "reason": m.get("why", ""), "why": m.get("why", ""), "draft": False, "source": "brief",
             "brief_intent": it}
        zone = "center" if it in ("cta", "pointer") else "lower_third" if it == "lower_third" else zone_for
        if it == "headline_bar":
            zone = "top_edge"
        g.update(zone=zone)
        if it in ("hook", "headline_bar"):
            g["role"] = "headline"
        if it in ("list", "question_list"):
            g["items"] = [{"text": x["text"], "at": round(words[x["at_word"]]["start"], 3)} for x in m["items"]]
        elif it == "reaction":
            g["emoji"] = m["emoji"]
            g["end"] = round(min(duration, start + max(1.2, words[hi]["end"] - start + HOLD[it])), 3)
        elif it == "pointer":
            g["direction"] = m["direction"]
            if m.get("target"):
                g["target"] = m["target"]
        else:
            g["text"] = m.get("text") or (profile.get("name") if it == "lower_third" else "")
        if m.get("kicker"):
            g["kicker"] = m["kicker"]
        if it == "contrast":
            g["before"], g["after"] = m["before"], m["after"]
            g["text"] = f"{m['before']} → {m['after']}"      # how a style without a comparison design shows it
        if m.get("design"):
            g["design"] = m["design"]
        if m.get("place"):
            g["place"] = m["place"]
        if m.get("backing") in ("none", "box"):
            g["backing"] = m["backing"]
        # the linger after the words never runs into a stretch the plan keeps
        # quiet, or into the next moment
        stops = [words[q["from"]]["start"] for q in brief.get("no_graphics", [])] + \
                [words[o["from"]]["start"] for o in brief.get("moments", [])
                 if o is not m and o.get("intent") not in ("pointer", "headline_bar")]
        nxt = [t - 0.08 for t in stops if t > g["start"] + 0.05]
        if nxt and it not in ("headline_bar",):
            g["end"] = round(max(min(g["end"], min(nxt)), min(g["end"], words[hi]["end"])), 3)
        out.append(g)
    out.sort(key=lambda g: g["start"])
    return out


def zooms(brief, words, z):
    """Zoom moments chosen by meaning, with the brand/style's zoom strength."""
    if z.get("style") in (None, "none") or not brief.get("zooms"):
        return None
    lo, hi = z.get("scale_min", 1.06), z.get("scale_max", 1.12)
    out = []
    for k, m in enumerate(sorted(brief["zooms"], key=lambda m: m["from"]), 1):
        st, en = words[m["from"]]["start"], words[m["to"]]["end"]
        punch = m["kind"] == "punch"
        out.append({"id": f"z{k}", "start": round(st, 3), "end": round(en, 3), "type": m["kind"],
                    "scale": hi if punch else lo, "ease_s": 0.0 if punch else round(en - st, 2),
                    "focus": z.get("focus", {"x": 0.5, "y": 0.38}), "reason": m.get("why", "")})
    return out


def save(reel, brief, words):
    brief = dict(brief, cut_signature=cut_signature(words))
    write_json(reel.path("creative.json"), brief)
    return brief
