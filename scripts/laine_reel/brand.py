"""Brand onboarding: one question at a time, answers saved as you go.

Claude runs the conversation (see the laine-reel-editor skill); this module
owns the questions, checks each answer, remembers progress in
brand/onboarding.json (so onboarding can stop and resume), and compiles the
finished profile into brand/brand.json (+ a readable brand/brand.md).

    next_question()  -> the next unanswered question, or None when done
    answer(id, text) -> parse + validate + save; raises AnswerError with a
                        friendly message if the answer can't be used
    finish()         -> build brand.json / brand.md
"""

import datetime as _dt
import json
import re
from pathlib import Path

from . import config

PROFILE_VERSION = 2


class AnswerError(ValueError):
    pass


# -- colours ----------------------------------------------------------------

COLOR_NAMES = {
    "black": "#111111", "white": "#FFFFFF", "cream": "#F5EFE6", "ivory": "#FFFDF5",
    "beige": "#E8DCCB", "nude": "#E3C9B5", "sand": "#D8C3A5", "taupe": "#A39382",
    "rose gold": "#B76E79", "off white": "#F7F4EE", "nude pink": "#E8C1B5",
    "brown": "#6B4F3A", "chocolate": "#4A2F23", "gold": "#C9A227", "champagne": "#E9D8B4",
    "blush": "#F2C6C2", "blush pink": "#F2C6C2", "pink": "#F4A6C0", "hot pink": "#FF3E8E",
    "rose": "#D9798B", "dusty rose": "#C9878F", "mauve": "#B784A7", "red": "#E03131",
    "burgundy": "#7A1F2B", "coral": "#FF7F6B", "peach": "#FFC2A1", "orange": "#FF8A1F",
    "terracotta": "#C8654A", "rust": "#B4532A", "yellow": "#FFD43B", "butter yellow": "#FBE7A1",
    "mustard": "#D9A62E", "lime": "#B6E43F", "green": "#2F9E44", "sage": "#A3B18A",
    "sage green": "#A3B18A", "olive": "#6B7A3A", "mint": "#B8E6D0", "emerald": "#1F8A5B",
    "forest green": "#1F4D36", "teal": "#1A9C9C", "turquoise": "#2CC4C4", "sky blue": "#8CCBF0",
    "baby blue": "#BBDDF7", "blue": "#1C7ED6", "cobalt": "#1F4FD1", "navy": "#1B2A4A",
    "lavender": "#C9B8E8", "lilac": "#C8A2C8", "purple": "#7048E8", "plum": "#5E2750",
    "grey": "#8A8A8A", "gray": "#8A8A8A", "charcoal": "#333333", "silver": "#C0C0C0",
}
HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def parse_colors(text):
    """'#E8B4B8, cream and black' -> ['#E8B4B8', '#F5EFE6', '#111111']."""
    found = []
    rest = text
    for m in HEX.finditer(text):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        found.append((m.start(), "#" + h.upper()))
        rest = rest.replace(m.group(0), " ")
    low = rest.lower()
    for name in sorted(COLOR_NAMES, key=len, reverse=True):  # "blush pink" before "pink"
        for m in re.finditer(rf"\b{re.escape(name)}\b", low):
            found.append((m.start(), COLOR_NAMES[name]))
            low = low[:m.start()] + " " * len(name) + low[m.end():]
    leftovers = [w for w in re.split(r"[,/&+;]|\band\b", low) if w.strip(" .")]
    if leftovers:
        raise AnswerError(f"I didn't recognise: {', '.join(w.strip() for w in leftovers)}. "
                          "Use hex codes (like #E8B4B8) or common names (blush, sage, navy...).")
    colors = []
    for _, c in sorted(found):
        if c not in colors:
            colors.append(c)
    if not colors:
        raise AnswerError("Give at least one colour, as a hex code or a name.")
    return colors[:6]


def luminance(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(bg):
    """Black or white text, whichever reads better on bg."""
    return "#111111" if contrast(bg, "#111111") >= contrast(bg, "#FFFFFF") else "#FFFFFF"


# -- fonts ------------------------------------------------------------------

FONT_DIRS = [config.ASSETS_DIR / "fonts", Path("~/Library/Fonts").expanduser(),
             Path("/Library/Fonts"), Path("/System/Library/Fonts"),
             Path("/System/Library/Fonts/Supplemental")]


def find_font_file(name):
    """Look for a font file by name (read-only): the fonts included with the editor
    first, then the project's fonts folder and the Mac's installed fonts."""
    from . import fontlib
    included = fontlib.primary_file(name)
    if included:
        return included
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    for d in FONT_DIRS:   # an exact name first ("Avenir Next", not "Avenir Next Condensed")
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in (".ttf", ".otf", ".ttc") and \
                        re.sub(r"[^a-z0-9]", "", f.stem.lower()) == key:
                    return str(f)
    for d in FONT_DIRS:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in (".ttf", ".otf", ".ttc") and \
                        re.sub(r"[^a-z0-9]", "", f.stem.lower()).startswith(key):
                    return str(f)
    return None


def parse_fonts(text):
    parts = [p.strip() for p in re.split(r"/|\+|,|\bfor body\b|\band\b", text) if p.strip()]
    if not parts:
        raise AnswerError("Name a font (or two: headline / body).")
    head = parts[0]
    body = parts[1] if len(parts) > 1 else parts[0]
    return {"headline": head, "body": body}


# -- question bank ----------------------------------------------------------

def _q(id, section, prompt, kind, options=None, help=None, when=None, optional=False,
       default=None):
    return {"id": id, "section": section, "prompt": prompt, "kind": kind,
            "options": options or [], "help": help, "when": when, "optional": optional,
            "default": default}


def _has_captions(a):
    # Unanswered counts as "yes" so the question total doesn't jump around.
    return a.get("caption_style") != "none"


# New customers start with a style (a starting point, never a template) and end
# with their own words. Profiles made before styles existed answered "aesthetic"
# instead and are never asked these new questions (their reels stay Classic).

STYLE_CHOICES = [("luxe", "Luxe - quiet, elegant, refined"),
                 ("playful", "Playful - fun, colourful, hand-made"),
                 ("magazine", "Magazine - editorial, curated, smart"),
                 ("minimal", "Minimal - calm, clean, lots of space"),
                 ("bold", "Bold - big, heavy, confident"),
                 ("energetic", "Energetic - fast, kinetic, hype")]
PACK_TO_AESTHETIC = {"luxe": "soft_luxe", "playful": "playful", "magazine": "editorial",
                     "minimal": "clean_minimal", "bold": "bold_energetic", "energetic": "bold_energetic"}

QUESTIONS = [
    _q("style_pack", "1. Your style", "Which style is the best starting point for your reels?",
       "choice", options=STYLE_CHOICES, when=lambda a: "aesthetic" not in a,
       help="It's only a starting point: at the end you can describe your style in your own "
            "words, mix in parts of other styles, and change anything later. Not sure? Ask "
            "and I'll describe each one or suggest one from how you talk about your brand."),
    _q("colors", "2. Colours and fonts",
       "What are your exact brand colours? Paste your HEX codes, main colour first (2-4).",
       "colors",
       help="Exact HEX codes like #FF3E8E keep every reel precisely on-brand. Colour names work "
            "too (blush pink, cream). No brand colours yet? Say 'help me choose' and I'll "
            "suggest palettes that suit your style. The first is your main colour; the second "
            "highlights key words."),
    _q("fonts", "2. Colours and fonts", "Which fonts feel like you?", "fonts", options=[
        ("Montserrat / Inter", "Modern and clean (Montserrat headlines, Inter text)"),
        ("Playfair Display / Lato", "Elegant (serif headlines, simple text)"),
        ("Bebas Neue / Montserrat", "Bold and loud (tall caps headlines)"),
        ("Poppins / Poppins", "Friendly and rounded"),
    ], help="Have your own font files? Drag the TTF/OTF files into the chat and I'll add them to "
            "your library and use them. Or pick a pairing, or name your own as "
            "'Headline font / Text font'."),
    _q("brand_files", "2. Colours and fonts",
       "Do you have a logo, graphics, images or sound effects you'd like to use? (optional)",
       "text", optional=True, when=lambda a: "aesthetic" not in a,
       help="Drag them into the chat (PNG/JPG images, MP3/WAV sounds) and tell me what each is "
            "for - e.g. 'my logo, top right' or 'use this sound for headlines'. Nothing yet? "
            "Say 'skip'; you can add them any time in the Library tab."),
    _q("headline", "1. Colours and fonts",
       "Do you want a headline title on your reels (in your headline font)?", "choice", options=[
        ("opening_hook", "An opening hook title for the first ~3 seconds"),
        ("persistent", "A short title that stays at the top the whole reel"),
        ("both", "A big opening hook, then a small title that stays at the top"),
        ("none", "No headline")]),
    _q("caption_style", "2. Captions", "How should captions look?", "choice", options=[
        ("style", "Let my style decide (recommended)"),
        ("word_pop", "One word at a time, popping on"),
        ("karaoke", "A short line, with the word being said highlighted"),
        ("phrase_lines", "Clean subtitle lines (1-2 lines)"),
        ("keyword_boxes", "Short chunks with the key word in a colour box"),
        ("none", "No captions"),
    ]),
    _q("caption_position", "2. Captions", "Where on screen should captions sit?", "choice",
       options=[("lower_third", "Lower third (classic, below your face)"),
                ("center", "Centre of the screen"),
                ("upper_third", "Upper third")], when=_has_captions),
    _q("caption_size", "2. Captions", "How big should captions be?", "choice",
       options=[("small", "Small and subtle"), ("medium", "Medium"),
                ("large", "Large and bold")], when=_has_captions),
    _q("caption_animation", "2. Captions", "How should captions appear?", "choice", options=[
        ("style", "Let my style decide (recommended)"), ("pop", "Pop / bounce in"), ("fade", "Soft fade"), ("slide_up", "Slide up"),
        ("typewriter", "Typewriter, letter by letter"), ("none", "Just appear")],
       when=_has_captions),
    _q("caption_emphasis", "2. Captions", "How should key words stand out?", "choice", options=[
        ("style", "Let my style decide (recommended)"), ("accent_color", "In my highlight colour"), ("accent_box", "In a colour box"),
        ("bigger", "Bigger than the other words"), ("none", "They don't")],
       when=_has_captions),
    _q("caption_case", "2. Captions", "Caption lettering?", "choice", options=[
        ("as_spoken", "Normal Sentence case"), ("upper", "ALL CAPS"),
        ("lower", "all lowercase")], when=_has_captions),
    _q("caption_color", "2. Captions", "What colour should captions be?", "choice", options=[
        ("white_primary_keywords", "White, with key words in my main colour"),
        ("white_accent_keywords", "White, with key words in my highlight colour"),
        ("primary", "All words in my main colour"),
        ("white", "All white")], when=_has_captions),
    _q("pacing", "3. Pace and zooms", "How fast should your edits feel?", "choice", options=[
        ("natural", "Natural - keep my breathing room"), ("tight", "Tight - no dead air"),
        ("fast", "Fast - punchy, TikTok energy")]),
    _q("zoom_style", "3. Pace and zooms", "What kind of zooms do you like?", "choice", options=[
        ("style", "Let my style decide (recommended)"), ("subtle", "Subtle slow push-ins on key moments"),
        ("punchy", "Punchy snap zooms"),
        ("mixed", "A mix: snap zooms at cuts, slow pushes on key lines"),
        ("none", "No zooms")]),
    _q("zoom_frequency", "3. Pace and zooms", "How often should the frame zoom?", "choice",
       options=[("rare", "Rarely - only the biggest moments"),
                ("moderate", "Every few sentences"), ("frequent", "Often - keep it moving")],
       when=lambda a: a.get("zoom_style") not in ("none", "style")),
    _q("graphics_density", "4. Graphics", "How much on-screen graphics do you want?", "choice",
       options=[("minimal", "Minimal - only when it really helps"),
                ("balanced", "Balanced"), ("busy", "Busy - something every few seconds")]),
    _q("graphics_elements", "4. Graphics", "Which visual elements do you want? (pick any)",
       "multi", options=[
           ("sticky_notes", "Sticky notes"), ("text_callouts", "Text callouts (numbers, key points)"),
           ("keyword_cards", "Key-phrase cards"), ("lists", "Bullet / checklist cards"),
           ("emoji", "Emoji pops"), ("arrows", "Hand-drawn arrows"),
           ("lower_third", "Name / @handle lower third"),
           ("cta_card", "Call-to-action card at the end"), ("progress_bar", "Progress bar")],
       help="Comma-separated, e.g. 'sticky notes, emoji, cta card'."),
    _q("sticky_font", "4. Graphics", "Which font should sticky notes use?", "choice", options=[
        ("hand", "Handwritten, like a real sticky note"), ("body", "My text font"),
        ("headline", "My headline font")],
       when=lambda a: "sticky_notes" in a.get("graphics_elements", ["sticky_notes"])),
    _q("sfx", "5. Sound", "Sound effects?", "choice", options=[
        ("none", "None"), ("subtle", "Subtle - soft whooshes on zooms, light pops"),
        ("playful", "Playful - pops, dings and swooshes on graphics too")]),
    _q("music", "5. Sound", "Background music?", "choice", options=[
        ("none", "No music"), ("soft", "Soft, chill (lo-fi / acoustic)"),
        ("upbeat", "Upbeat and bright"), ("cinematic", "Cinematic / emotional"),
        ("own", "I'll provide my own track")]),
    _q("music_file", "5. Sound", "Path to your music track (mp3 / wav / m4a)?", "path",
       when=lambda a: a.get("music") == "own", optional=True),
    _q("aesthetic", "6. Aesthetic", "Which overall look fits your brand best?", "choice",
       options=[("clean_minimal", "Clean and minimal"), ("soft_luxe", "Soft and luxe"),
                ("bold_energetic", "Bold and energetic"), ("playful", "Playful and colourful"),
                ("editorial", "Editorial / magazine"), ("techy", "Sleek and techy")],
       when=lambda a: "aesthetic" in a),   # profiles made before styles existed only
    _q("personality", "6. Aesthetic", "Three words for how your videos should feel?", "text",
       help="For example: warm, confident, real."),
    _q("handle", "6. Aesthetic", "Your @handle or brand name for end cards? (optional)",
       "text", optional=True),
    _q("style_direction", "6. Aesthetic",
       "In your own words, how should your reels look and feel? Anything you always or never want? (optional)",
       "text", optional=True, when=lambda a: "aesthetic" not in a,
       help="Everyday language is perfect, e.g. 'hot pink headlines, clean captions, no outlines "
            "or glows' or 'calm and editorial, never emojis'. I'll turn it into exact settings and "
            "read it back to you. Say 'skip' if the style says it all."),
    _q("reference_reel", "7. Inspiration",
       "Is there a reel you love the editing of? Give a path to the video file (optional).",
       "path", optional=True,
       help="I'll measure its pace, cuts and loudness to tune your profile. Say 'skip' to skip."),
]
BY_ID = {q["id"]: q for q in QUESTIONS}
SKIP_WORDS = {"skip", "none", "no", "n/a", "na", "-", ""}


def parse_answer(qid, text, answers=None):
    q = BY_ID.get(qid)
    if not q:
        raise AnswerError(f"Unknown question '{qid}'.")
    raw = str(text).strip()
    if q["optional"] and raw.lower() in SKIP_WORDS:
        return None
    if q["kind"] == "colors":
        return parse_colors(raw)
    if q["kind"] == "fonts":
        picked = _match_option(q, raw)
        return parse_fonts(picked or raw)
    if q["kind"] == "choice":
        v = _match_option(q, raw)
        if v is None:
            raise AnswerError("Please pick one of: " + "; ".join(l for _, l in q["options"]))
        return v
    if q["kind"] == "multi":
        if raw.lower() in SKIP_WORDS:
            return []
        out = []
        for part in re.split(r",|\band\b|;", raw):
            if part.strip():
                v = _match_option(q, part.strip())
                if v is None:
                    raise AnswerError(f"'{part.strip()}' isn't one of the options.")
                if v not in out:
                    out.append(v)
        return out
    if q["kind"] == "path":
        try:
            p = config.check_not_protected(raw.strip("'\""))
        except ValueError as e:
            raise AnswerError(str(e))
        if not p.is_file():
            raise AnswerError(f"I can't find a file at {p}.")
        return str(p)
    if not raw:
        raise AnswerError("Please type an answer (or 'skip' if it's optional).")
    return raw


def _match_option(q, raw):
    low = raw.lower().strip(" .!")
    if low.isdigit() and 1 <= int(low) <= len(q["options"]):
        return q["options"][int(low) - 1][0]
    norm = re.sub(r"[^a-z0-9]", "", low)
    for value, label in q["options"]:
        if norm in (re.sub(r"[^a-z0-9]", "", value.lower()),
                    re.sub(r"[^a-z0-9]", "", label.lower())):
            return value
    # unique word overlap ("snap zooms" -> punchy)
    hits = [v for v, l in q["options"]
            if norm and (norm in re.sub(r"[^a-z0-9]", "", l.lower())
                         or re.sub(r"[^a-z0-9]", "", v.lower()) in norm)]
    return hits[0] if len(hits) == 1 else None


# -- progress ---------------------------------------------------------------

def _progress_path():
    return config.brand_dir() / "onboarding.json"


def load_progress():
    p = _progress_path()
    return json.loads(p.read_text()) if p.exists() else {"answers": {}, "started": None}


def _save_progress(prog):
    d = config.brand_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = _progress_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(prog, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(_progress_path())


def applicable(answers):
    return [q for q in QUESTIONS if q["when"] is None or q["when"](answers)]


def next_question(answers=None):
    answers = load_progress()["answers"] if answers is None else answers
    qs = applicable(answers)
    for i, q in enumerate(qs, 1):
        if q["id"] not in answers:
            return dict({k: v for k, v in q.items() if k != "when"}, number=i, total=len(qs))
    return None


def answer(qid, text):
    prog = load_progress()
    value = parse_answer(qid, text, prog["answers"])
    prog["answers"][qid] = value
    prog["started"] = prog["started"] or _now()
    prog["updated"] = _now()
    # Drop answers to questions that no longer apply (e.g. captions turned off);
    # settings that aren't onboarding questions (library fonts, sounds, logo) stay.
    live = {q["id"] for q in applicable(prog["answers"])}
    prog["answers"] = {k: v for k, v in prog["answers"].items() if k in live or k not in BY_ID}
    _save_progress(prog)
    return value


def is_onboarded():
    return (config.brand_dir() / "brand.json").exists()


NEUTRAL = config.PROJECT_ROOT / "brand" / "neutral.json"


def neutral_profile():
    """The clean look used until the customer finishes onboarding. Never saved
    as their brand and never pinned to a reel."""
    answers = json.loads(NEUTRAL.read_text())["answers"]
    prof = compile_profile(answers)
    prof.update(neutral=True, name=None)
    return prof


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


# -- compile ----------------------------------------------------------------

CAPTION_SIZE_PX = {"small": 58, "medium": 76, "large": 100}
# Caption outline (Brand settings). The default is the look every reel had before
# this was a setting, so existing reels render exactly as they did.
OUTLINE_WIDTHS = {"thin": 0.06, "medium": 0.10, "thick": 0.16}
DEFAULT_OUTLINE = {"enabled": True, "color": "#000000", "thickness": "thick", "opacity": 0.82}


def caption_outline(answers, pack_default=DEFAULT_OUTLINE):
    """The caption outline: the customer's own setting if they made one, else the
    style pack's default (Classic: the original look), else none (plain)."""
    if answers.get("caption_outline"):
        o, src = dict(DEFAULT_OUTLINE, **answers["caption_outline"]), "brand"
    elif pack_default:
        o, src = dict(pack_default), "pack"
    else:
        o, src = dict(DEFAULT_OUTLINE, enabled=False), "engine"
    o["width_em"] = OUTLINE_WIDTHS[o["thickness"]]
    o["source"] = src
    return o


# Settings a style pack recommends when the customer picks it. The customer can
# keep their own instead (answers["style"]["keep"]); colours, fonts, caption
# position, size, case and colour always stay theirs.
PACK_KEEPABLE = {"caption_style": ("captions", "style"), "caption_animation": ("captions", "animation"),
                 "caption_emphasis": ("captions", "emphasis"), "zooms": ("zooms", None)}


def _apply_pack(profile, answers):
    from . import styles
    st = profile.get("style") or {}
    if not st or st.get("pack") == "classic" and not st.get("mix"):
        return
    keep = set((answers.get("style") or {}).get("keep") or [])
    r = styles.resolve(profile)
    rec = r["aspects"]["captions"].get("recommended", {})
    caps = profile["captions"]
    for key, field in (("caption_style", "style"), ("caption_animation", "animation"),
                       ("caption_emphasis", "emphasis")):
        if key not in keep and rec.get(field) and caps.get("enabled"):
            caps[field] = rec[field]
            if field == "style":
                caps["max_lines"] = 1 if rec[field] in ("word_pop", "keyword_boxes") else 2
    zoom = r["aspects"].get("zoom") or {}
    if "zooms" not in keep and zoom and profile["zooms"].get("style") not in (None, "none"):
        profile["zooms"].update({k: zoom[k] for k in ("style", "frequency", "scale_min", "scale_max",
                                                      "min_gap_s") if k in zoom})
    snd = r["aspects"]["sound"]
    if snd.get("gain_offset_db") and profile.get("sfx", {}).get("gain_db") is not None:
        profile["sfx"]["gain_db"] = profile["sfx"]["gain_db"] + snd["gain_offset_db"]


def _style_and_outline(answers):
    from . import styles
    style = styles.compile_choice(answers)
    pack = styles.load_pack(style["pack"], style["version"])
    mixed = {a: m for m in style["mix"] for a in m["aspects"]}
    cap_pack = styles.load_pack(mixed["captions"]["pack"], mixed["captions"]["version"]) \
        if "captions" in mixed else pack
    default = cap_pack.get("aspects", {}).get("captions", {}).get("outline_default")
    return style, caption_outline(answers, default)
CAPTION_CHARS = {"small": 26, "medium": 20, "large": 15}  # per line at 1080 px wide
ZOOM_SCALES = {"subtle": (1.06, 1.10), "punchy": (1.15, 1.22), "mixed": (1.08, 1.18)}
ZOOM_GAP = {"rare": 9.0, "moderate": 5.0, "frequent": 2.8}
GRAPHICS_GAP = {"minimal": 10.0, "balanced": 5.0, "busy": 3.0}
AESTHETIC_TOKENS = {
    "clean_minimal": {"corner_radius": 18, "shadow": "soft", "stroke": 0, "card_opacity": 0.95},
    "soft_luxe": {"corner_radius": 28, "shadow": "soft", "stroke": 0, "card_opacity": 0.9},
    "bold_energetic": {"corner_radius": 8, "shadow": "hard", "stroke": 6, "card_opacity": 1.0},
    "playful": {"corner_radius": 32, "shadow": "hard", "stroke": 4, "card_opacity": 1.0},
    "editorial": {"corner_radius": 0, "shadow": "none", "stroke": 2, "card_opacity": 1.0},
    "techy": {"corner_radius": 12, "shadow": "glow", "stroke": 2, "card_opacity": 0.85},
}


def _with_style(answers):
    """New-flow answers (style_pack, style_direction) -> the style choice and the
    classic aesthetic tokens the renderer still uses as a base."""
    a = dict(answers)
    pack = a.get("style_pack")
    if pack:
        a.setdefault("aesthetic", PACK_TO_AESTHETIC.get(pack, "clean_minimal"))
        st = dict(a.get("style") or {})
        st.setdefault("pack", pack)
        if a.get("style_direction") and not st.get("direction"):
            st["direction"] = a["style_direction"]
        # what they chose themselves in onboarding stays theirs; "let my style decide"
        # takes the style's recommendation
        keep = set(st.get("keep") or [])
        for key in ("caption_style", "caption_animation", "caption_emphasis"):
            if key in a and a[key] != "style":
                keep.add(key)
        if "zoom_style" in a and a["zoom_style"] != "style":
            keep.add("zooms")
        st["keep"] = sorted(keep)
        a["style"] = st
    # placeholders for "let my style decide" (the style fills them in)
    for key, base in (("caption_style", "phrase_lines"), ("caption_animation", "fade"),
                      ("caption_emphasis", "accent_color"), ("zoom_style", "subtle")):
        if a.get(key) == "style":
            a[key] = base
    if a.get("zoom_style") == "subtle" and answers.get("zoom_style") == "style":
        a.setdefault("zoom_frequency", "moderate")
    return a


def compile_profile(answers, reference=None):
    """Answers -> the brand.json structure the planner and renderer read."""
    answers = _with_style(answers)
    missing = [q["id"] for q in applicable(answers)
               if q["id"] not in answers and not q["optional"]]
    if missing:
        raise AnswerError(f"Still need answers for: {', '.join(missing)}")
    palette = answers["colors"]
    primary = palette[0]
    accent = palette[1] if len(palette) > 1 else primary
    # Background for cards: lightest palette colour; text chosen for contrast.
    card_bg = max(palette, key=luminance)
    caps = _has_captions(answers)
    size = answers.get("caption_size", "medium")
    fonts = answers["fonts"]
    elements = answers.get("graphics_elements", [])
    zoom_style = answers["zoom_style"]
    zs = ZOOM_SCALES.get(zoom_style, (1.0, 1.0))
    caps = caps and "caption_style" in answers
    sfx = answers["sfx"]
    cap_color = answers.get("caption_color", "white")
    caption_text = primary if cap_color == "primary" else "#FFFFFF"
    keyword_color = {"white_primary_keywords": primary, "white_accent_keywords": accent}.get(
        cap_color)
    # exact colours for particular things ("hot pink headlines") beat the palette defaults
    roles = answers.get("color_roles") or {}
    caption_text = roles.get("captions") or caption_text
    keyword_color = roles.get("key_words") or keyword_color
    headline_color = roles.get("headline") or primary
    # Profiles from before the headline question: a hook title came with text_callouts.
    headline = answers.get("headline") or (
        "opening_hook" if "text_callouts" in elements else "none")
    from . import library
    font_files = answers.get("font_files") or {}

    def lib_font(role, fallback_name):
        a = library.get(font_files.get(role)) if font_files.get(role) else None
        if a and a["kind"] == "font" and Path(a["path"]).is_file():
            return a["family"], a["path"]
        return fallback_name, find_font_file(fallback_name)
    head_family, head_file = lib_font("headline", fonts["headline"])
    body_family, body_file = lib_font("body", fonts["body"])
    gfont = answers.get("graphics_font") or "headline"
    if str(gfont).startswith("font:"):            # any font by name (e.g. an included one)
        g_family = gfont.split(":", 1)[1]
        g_file = find_font_file(g_family)
    elif gfont in ("headline", "body"):
        g_family, g_file = (head_family, head_file) if gfont == "headline" else (body_family, body_file)
    else:
        g_family, g_file = lib_font("graphics", fonts["headline"]) if font_files.get("graphics") \
            else (head_family, head_file)
    sound_map = {k: v for k, v in (answers.get("sound_map") or {}).items() if v}
    logo = answers.get("logo") or None
    style, outline = _style_and_outline(answers)
    profile = {
        "version": PROFILE_VERSION,
        "updated": _now(),
        "name": answers.get("handle"),
        "colors": {
            "palette": palette, "primary": primary, "accent": accent,
            "card_background": card_bg, "card_text": readable_on(card_bg),
            "on_primary": readable_on(primary), "on_accent": readable_on(accent),
            "caption_text": caption_text, "caption_keyword": keyword_color,
            "headline": headline_color, "on_headline": readable_on(headline_color),
            "caption_outline": outline["color"],
        },
        "fonts": {
            "headline": head_family, "body": body_family, "graphics": g_family,
            "headline_file": head_file, "body_file": body_file, "graphics_file": g_file,
            "from_library": {k: v for k, v in font_files.items() if v},
        },
        "logo": logo,
        "captions": {
            "enabled": caps,
            "style": answers.get("caption_style"),
            "position": answers.get("caption_position", "lower_third"),
            "size": size, "size_px": CAPTION_SIZE_PX[size],
            "max_chars_per_line": CAPTION_CHARS[size],
            "max_lines": 1 if answers.get("caption_style") in ("word_pop", "keyword_boxes") else 2,
            "animation": answers.get("caption_animation", "none"),
            "emphasis": answers.get("caption_emphasis", "accent_color"),
            "case": answers.get("caption_case", "as_spoken"),
            "color": cap_color,
            "font": "body",
            "outline": {k: v for k, v in outline.items() if k != "source"},
            "outline_source": outline["source"],
        },
        "style": style,
        "headline": {"style": headline, "font": "headline"},
        "pacing": answers["pacing"],
        "framing": {"mode": "cover", "focus_x": 0.5},
        "zooms": {
            "style": zoom_style,
            "frequency": answers.get("zoom_frequency", "moderate") if zoom_style != "none" else None,
            "scale_min": zs[0], "scale_max": zs[1],
            "min_gap_s": ZOOM_GAP.get(answers.get("zoom_frequency", "moderate"), 5.0),
            "focus": {"x": 0.5, "y": 0.38},
        },
        "graphics": {
            "density": answers["graphics_density"], "elements": elements,
            "min_gap_s": GRAPHICS_GAP[answers["graphics_density"]],
            "sticky_font": answers.get("sticky_font", "hand"),
        },
        "sfx": {
            "style": sfx,
            "events": sorted(set({"none": [], "subtle": ["zoom_punch", "cta"],
                                  "playful": ["zoom_punch", "graphic_in", "emoji", "cta",
                                              "headline"]}[sfx]) | set(sound_map)),
            "gain_db": {"none": None, "subtle": -16, "playful": -10}[sfx] or -12,
            "min_gap_s": 1.2,
            # the customer's own sounds, by event; used exactly, never swapped for a default
            "sounds": sound_map,
        },
        "music": {
            "style": answers["music"], "file": answers.get("music_file"),
            "gain_db": -24, "duck_under_voice": True,
        },
        "aesthetic": {
            "preset": answers["aesthetic"],
            "personality": [w.strip() for w in re.split(r",|\band\b|/", answers["personality"])
                            if w.strip()],
            "tokens": AESTHETIC_TOKENS[answers["aesthetic"]],
        },
        "reference": reference,
        "answers": answers,
    }
    _apply_pack(profile, answers)
    return profile


def finish(reference=None, reason="onboarding"):
    prog = load_progress()
    profile = compile_profile(prog["answers"], reference=reference)
    d = config.brand_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = d / "brand.json"
    if out.exists():  # keep the previous profile, never silently lose it
        _to_history(json.loads(out.read_text()), reason)
        out.replace(d / f"brand.previous.json")
    out.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
    (d / "brand.md").write_text(summary_md(profile))
    return profile


def summary_md(p):
    c, cap, z, g = p["colors"], p["captions"], p["zooms"], p["graphics"]
    lines = [f"# Brand profile{(': ' + p['name']) if p.get('name') else ''}", "",
             f"Updated {p['updated']}. Edit by re-running onboarding, or change one answer "
             "with `reel.py brand answer <id> \"...\"` then `reel.py brand finish`.", "",
             "## Look", "",
             f"- Colours: {', '.join(c['palette'])} (main {c['primary']}, highlight {c['accent']})",
             f"- Fonts: {p['fonts']['headline']} (headlines), {p['fonts']['body']} (text)"
             + ("" if p["fonts"]["headline_file"] and p["fonts"]["body_file"]
                else " - not installed on this computer yet"),
             f"- Headline: {p.get('headline', {}).get('style', 'none').replace('_', ' ')}"
             f" ({p['fonts']['headline']})",
             f"- Aesthetic: {p['aesthetic']['preset'].replace('_', ' ')}; feels "
             f"{', '.join(p['aesthetic']['personality'])}", "",
             "## Captions", ""]
    if cap["enabled"]:
        lines.append(f"- {cap['style'].replace('_', ' ')}, {cap['size']} ({cap['size_px']} px), "
                     f"{cap['position'].replace('_', ' ')}, {cap['animation']} animation, "
                     f"key words: {cap['emphasis'].replace('_', ' ')}, case: {cap['case']}, "
                     f"colour: {cap.get('color', 'white').replace('_', ' ')}")
    else:
        lines.append("- No captions")
    lines += ["", "## Pace, zooms, graphics, sound", "",
              f"- Pacing: {p['pacing']}",
              f"- Zooms: {z['style']}" + (f", {z['frequency']} (scale {z['scale_min']}-"
                                          f"{z['scale_max']})" if z["style"] != "none" else ""),
              f"- Graphics: {g['density']}: {', '.join(e.replace('_', ' ') for e in g['elements']) or 'none'}"
              + (f" (sticky notes in {g.get('sticky_font', 'hand').replace('hand', 'handwriting')} font)"
                 if "sticky_notes" in g["elements"] else ""),
              f"- Sound effects: {p['sfx']['style']}",
              f"- Music: {p['music']['style']}" + (f" ({p['music']['file']})" if p['music']['file'] else "")]
    ref = p.get("reference")
    if ref:
        lines += ["", "## Reference reel", "",
                  f"- {Path(ref['file']).name}: {ref['duration']:.0f}s, {ref['cuts_per_minute']} cuts/min"
                  + (f", {ref['words_per_minute']} words/min" if ref.get("words_per_minute") else "")
                  + f", loudness {ref['loudness_lufs']} LUFS",
                  f"- Suggests: {ref['suggests']['pacing']} pacing, {ref['suggests']['zoom_frequency']} zooms"]
    return "\n".join(lines) + "\n"


# -- brand settings (after onboarding) ------------------------------------------

EXTRA_KEYS = ("font_files", "graphics_font", "sound_map", "logo", "caption_outline", "style",
              "creative_rules", "color_roles", "reference_prefs")
COLOR_ROLES = {"headline": "Headlines", "captions": "Captions", "key_words": "Key words in captions"}
SOUND_EVENTS = {"headline": "Headline appears", "graphic_in": "Graphics pop in",
                "emoji": "Emoji pops", "zoom_punch": "Snap zooms", "cta": "Call to action",
                "tick": "Checklist ticks"}
LOGO_POSITIONS = ["top_right", "top_left", "bottom_right", "bottom_left"]
# -- dated history of saved defaults -------------------------------------------
# brand/history/<YYYYmmdd-HHMMSS>.json holds the saved defaults exactly as they
# were before each change, so any earlier set can be restored. Never pruned.

def history_dir():
    return config.brand_dir() / "history"


def _to_history(profile, reason):
    d = history_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    p, n = d / f"{stamp}.json", 1
    while p.exists():
        n += 1
        p = d / f"{stamp}-{n}.json"
    p.write_text(json.dumps({"saved_at": _now(), "replaced_by": reason, "profile": profile},
                            indent=2, ensure_ascii=False) + "\n")
    return p.stem


def _short(v):
    if isinstance(v, dict):
        v = ", ".join(f"{k} {x}" for k, x in v.items() if x)
    elif isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    s = str(v if v not in (None, "") else "none").replace("_", " ")
    return s if len(s) <= 40 else s[:37] + "..."


def _diff_answers(old, new):
    labels = {q["id"]: q["prompt"] for q in QUESTIONS}
    out = []
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k) and k not in ("reference_reel",):
            out.append({"id": k, "label": labels.get(k, k.replace("_", " ")),
                        "before": _short(old.get(k)), "after": _short(new.get(k))})
    return out


def history():
    """Earlier saved defaults, newest first, each with what changed after it."""
    d = history_dir()
    entries = []
    order = lambda p: (p.stem[:15], int(p.stem[16:] or 1))   # 20261018-120000[-2]
    for p in sorted(d.glob("*.json"), key=order) if d.exists() else []:
        try:
            e = json.loads(p.read_text())
        except ValueError:
            continue
        entries.append({"id": p.stem, "saved_at": e.get("saved_at"),
                        "replaced_by": e.get("replaced_by"),
                        "answers": e.get("profile", {}).get("answers", {})})
    cur = config.load_brand().get("answers", {})
    for i, e in enumerate(entries):
        nxt = entries[i + 1]["answers"] if i + 1 < len(entries) else cur
        e["changed_after"] = _diff_answers(e["answers"], nxt)
        e["differs_from_now"] = _diff_answers(e["answers"], cur)
    return list(reversed(entries))


def restore_history(entry_id):
    """Make an earlier set of saved defaults current again. The set being
    replaced goes into the history too, so a restore can be undone."""
    if not re.fullmatch(r"\d{8}-\d{6}(-\d+)?", entry_id or ""):
        raise AnswerError("Unknown history entry")
    p = history_dir() / f"{entry_id}.json"
    if not p.exists():
        raise AnswerError("That earlier version isn't in your history")
    old = json.loads(p.read_text())["profile"]
    prog = load_progress()
    prog["answers"] = dict(old.get("answers", {}))
    prog["updated"] = _now()
    _save_progress(prog)
    return finish(reference=old.get("reference"), reason=f"restore {entry_id}")


# -- each reel keeps the brand it was made with ---------------------------------
# <reel>/brand.snapshot.json: the saved defaults when the reel was first planned.
# Later changes to saved defaults don't alter it, so older projects keep their look.

SNAPSHOT = "brand.snapshot.json"


def _may_pin(reel_root):
    """Never pin a test brand ($LAINE_BRAND_DIR) into a real reel."""
    import os
    if not os.environ.get("LAINE_BRAND_DIR"):
        return True
    root = Path(reel_root).resolve()
    real = (config.PROJECT_ROOT / "workspace").resolve()
    return real not in root.parents or "_tests" in root.parts or "selftest" in root.name


def _write_snapshot(reel_root, profile):
    p = Path(reel_root) / SNAPSHOT
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pinned_at": _now(), "profile": profile}, indent=2,
                              ensure_ascii=False) + "\n")
    tmp.replace(p)


def reel_base(reel_root, pin=True):
    """The saved defaults this reel uses: its snapshot, or (first time) today's
    saved defaults, which then get pinned to the reel."""
    p = Path(reel_root) / SNAPSHOT
    if p.exists():
        return json.loads(p.read_text())["profile"]
    base = config.load_brand()
    if pin and base and (Path(reel_root) / "reel.json").exists() and _may_pin(reel_root):
        _write_snapshot(reel_root, base)
    return base or neutral_profile()   # before onboarding: neutral, not pinned


def snapshot_info(reel_root):
    """When this reel's brand was pinned and how it differs from today's defaults."""
    p = Path(reel_root) / SNAPSHOT
    if not p.exists():
        return {"pinned_at": None, "differs": []}
    snap = json.loads(p.read_text())
    return {"pinned_at": snap.get("pinned_at"),
            "differs": _diff_answers(snap["profile"].get("answers", {}),
                                     config.load_brand().get("answers", {}))}


def use_current_defaults(reel_root):
    """Re-pin a reel to today's saved defaults. Returns the keys that change."""
    base = config.load_brand()
    if not base:
        raise AnswerError("No saved defaults yet")
    changed = [d["id"] for d in snapshot_info(reel_root)["differs"]]
    _write_snapshot(reel_root, base)
    return changed


EDITABLE = [q["id"] for q in QUESTIONS if q["id"] not in ("reference_reel", "music_file")]


def reel_answers_path(reel_root):
    return Path(reel_root) / "brand.answers.json"


def reel_answers(reel_root):
    p = reel_answers_path(reel_root)
    return json.loads(p.read_text()) if p.exists() else {}


def effective(reel_root=None):
    """The profile a reel renders with: the saved defaults pinned to the reel
    (brand.snapshot.json), plus any changes made for this reel only
    (reel/brand.answers.json)."""
    if not reel_root:
        return config.load_brand() or neutral_profile()
    base = reel_base(reel_root)
    extra = reel_answers(reel_root)
    if not extra or not base:
        return base
    answers = dict(base.get("answers", {}), **extra)
    prof = compile_profile(answers, reference=base.get("reference"))
    prof["scope"] = {"reel_only": sorted(extra)}
    return prof


def _validate_extra(key, value):
    from . import library
    if key == "font_files":
        out = {}
        for role, aid in (value or {}).items():
            if role not in ("headline", "body", "graphics"):
                raise AnswerError(f"Unknown font role {role}")
            if aid:
                a = library.get(aid)
                if not a or a["kind"] != "font":
                    raise AnswerError(f"No font {aid} in your library")
            out[role] = aid or None
        return out
    if key == "graphics_font":
        if value in ("headline", "body", "library"):
            return value
        if str(value).startswith("font:") and str(value)[5:].strip():
            return "font:" + str(value)[5:].strip()
        raise AnswerError("graphics_font must be headline, body, library or font:<name>")
    if key == "sound_map":
        out = {}
        for ev, aid in (value or {}).items():
            if ev not in SOUND_EVENTS:
                raise AnswerError(f"Unknown sound event {ev}")
            if aid:
                a = library.get(aid)
                if not a or a["kind"] != "sound":
                    raise AnswerError(f"No sound {aid} in your library")
            out[ev] = aid or None
        return out
    if key == "logo":
        if not value or not value.get("id"):
            return None
        a = library.get(value["id"])
        if not a or a["kind"] != "image":
            raise AnswerError("That logo isn't in your library")
        pos = value.get("position") or "top_right"
        if pos not in LOGO_POSITIONS:
            raise AnswerError("Logo position must be a corner")
        return {"id": value["id"], "position": pos,
                "opacity": max(0.2, min(1.0, float(value.get("opacity") or 0.9))),
                "size": max(80, min(400, int(value.get("size") or 180)))}
    if key == "reference_prefs":
        from . import reference_style
        try:
            return reference_style.validate_prefs(value)
        except ValueError as e:
            raise AnswerError(str(e))
    if key == "color_roles":
        out = {}
        for role, v in (value or {}).items():
            if role not in COLOR_ROLES:
                raise AnswerError(f"Unknown colour role {role}")
            if v in (None, ""):
                continue
            v = str(v).strip()
            if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", v):
                parsed = parse_colors(v)        # also accepts names like "hot pink"
                v = parsed[0] if parsed else None
            if not v:
                raise AnswerError(f"{COLOR_ROLES[role]}: use a HEX code like #FF3E8E")
            out[role] = ("#" + v.lstrip("#")).upper()
        return out
    if key in ("style", "creative_rules"):
        from . import styles
        try:
            return styles.validate_choice(value) if key == "style" else styles.validate_rules(value)
        except ValueError as e:
            raise AnswerError(str(e))
    if key == "caption_outline":
        v = dict(DEFAULT_OUTLINE, **(value or {}))
        if not isinstance(v["enabled"], bool):
            raise AnswerError("Caption outline must be on or off")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v["color"])):
            raise AnswerError("Caption outline colour must look like #000000")
        if v["thickness"] not in OUTLINE_WIDTHS:
            raise AnswerError("Caption outline thickness must be thin, medium or thick")
        try:
            op = float(v["opacity"])
        except (TypeError, ValueError):
            raise AnswerError("Caption outline opacity must be a number")
        return {"enabled": v["enabled"], "color": v["color"].upper(), "thickness": v["thickness"],
                "opacity": round(max(0.1, min(1.0, op)), 2)}
    raise AnswerError(f"Unknown setting {key}")


def save_settings(changes, scope, reel_root=None):
    """Save brand changes. scope "default": your saved defaults for future reels
    (and this reel); scope "reel": this reel only. Returns the parsed changes."""
    if scope not in ("default", "reel"):
        raise AnswerError("scope must be 'default' or 'reel'")
    parsed = {}
    # partial changes to these merge with what's already set (e.g. only new words)
    MERGE = ("style", "creative_rules", "color_roles", "reference_prefs")
    if any(k in MERGE for k in changes):
        current = dict(load_progress().get("answers", {}))
        if scope == "reel" and reel_root:
            current.update(reel_answers(reel_root))
        base_style = _with_style(current).get("style") or {}
    for k, v in changes.items():
        if k in MERGE and isinstance(v, dict):
            v = dict((base_style if k == "style" else current.get(k)) or {}, **v)
        if k in EXTRA_KEYS:
            parsed[k] = _validate_extra(k, v)
        elif k in EDITABLE:
            text = ", ".join(v) if isinstance(v, list) and k == "colors" else v
            if k == "graphics_elements" and isinstance(v, list):
                text = ", ".join(v) if v else "none"
            if k == "fonts" and isinstance(v, dict):
                text = f"{v.get('headline')} / {v.get('body')}"
            parsed[k] = parse_answer(k, text)
        else:
            raise AnswerError(f"{k} can't be changed here")
    # A caption setting the customer picks themselves stays theirs when a style is chosen
    # (otherwise the style's own caption look would quietly replace it).
    picked = [k for k in ("caption_style", "caption_animation", "caption_emphasis")
              if k in parsed and parsed[k] != "style"]
    if picked:
        cur = dict(load_progress().get("answers", {}))
        if scope == "reel" and reel_root:
            cur.update(reel_answers(reel_root))
        cur.update(parsed)
        st = dict(_with_style(cur).get("style") or {})
        if st.get("pack"):
            st["keep"] = sorted(set(st.get("keep") or []) | set(picked))
            parsed["style"] = st
    if scope == "default":
        if not is_onboarded():
            raise AnswerError("Finish your brand onboarding first. Until then, changes can "
                              "be saved for this reel only.")
        prog = load_progress()
        prog["answers"].update(parsed)
        prog["updated"] = _now()
        _save_progress(prog)
        finish(reference=config.load_brand().get("reference"),
               reason="settings: " + ", ".join(sorted(parsed)))
        if reel_root:   # the reel follows the new defaults for these settings only
            ra = {k: v for k, v in reel_answers(reel_root).items() if k not in parsed}
            _write_reel_answers(reel_root, ra)
            base = reel_base(reel_root, pin=False)
            if (Path(reel_root) / SNAPSHOT).exists() and base:
                answers = dict(base.get("answers", {}), **parsed)
                _write_snapshot(reel_root, compile_profile(answers, reference=base.get("reference")))
    else:
        if not reel_root:
            raise AnswerError("A reel is needed for reel-only changes")
        ra = dict(reel_answers(reel_root), **parsed)
        compile_profile(dict((reel_base(reel_root) or {}).get("answers", {}), **ra))  # must compile
        _write_reel_answers(reel_root, ra)
    return parsed


def _write_reel_answers(reel_root, ra):
    p = reel_answers_path(reel_root)
    if ra:
        p.write_text(json.dumps(ra, indent=2, ensure_ascii=False) + "\n")
    elif p.exists():
        p.unlink()


# -- reading settings back in plain language ------------------------------------

def explain(profile):
    """What a reel will follow, in plain words, with where each choice came from
    (Claude reads this back to the customer after saving their preferences)."""
    from . import styles
    r = styles.resolve(profile)
    c, f, cap = profile.get("colors", {}), profile.get("fonts", {}), profile.get("captions", {})
    src = {"engine": "plain default", "brand": "your setting", "profile": "your setting"}
    lines = [f"Style: {r['pack'].title()}" + (" (your original look)" if r["legacy"] else "")
             + ("".join(f"; {', '.join(m['aspects'])} borrowed from {m['pack'].title()}" for m in r["mix"]))]
    if r["direction"]:
        lines.append(f"In your words: \"{r['direction']}\"")
    lines.append(f"Colours: main {c.get('primary')}, highlight {c.get('accent')}; headlines {c.get('headline') or c.get('primary')}; "
                 f"captions {c.get('caption_text')}" + (f", key words {c.get('caption_keyword')}" if c.get("caption_keyword") else ""))
    fl = f.get("from_library") or {}
    lines.append(f"Fonts: headlines {f.get('headline')}{' (your uploaded file)' if fl.get('headline') else ''}, "
                 f"text {f.get('body')}{' (your uploaded file)' if fl.get('body') else ''}")
    lines.append(f"Captions: {cap.get('style', '').replace('_', ' ')}, {cap.get('animation', '').replace('_', ' ')}, "
                 f"key words {cap.get('emphasis', '').replace('_', ' ')}, {cap.get('position', '').replace('_', ' ')}")
    def why(s):
        if s.startswith("pack:"):
            return f"part of the {s[5:].title()} style"
        return src.get(s, s.replace("_", " "))
    on = [d.replace("_", " ") + f" ({why(v['source'])})" for d, v in r["decorations"].items() if v["on"]]
    off_by_rule = [d.replace("_", " ") for d, v in r["decorations"].items() if v["source"].startswith("rule:")]
    lines.append("Decorations on: " + (", ".join(on) if on else "none"))
    if off_by_rule:
        lines.append("Turned off by your rules: " + ", ".join(off_by_rule))
    if r["rules"].get("flags") or r["rules"].get("notes"):
        lines.append("Your rules: " + ", ".join(x.replace("_", " ") for x in r["rules"].get("flags", []))
                     + (f"; notes: {r['rules']['notes']}" if r["rules"].get("notes") else ""))
    if r["blocked_intents"]:
        lines.append("Never shown: " + ", ".join(r["blocked_intents"]))
    rp = (profile.get("answers") or {}).get("reference_prefs") or {}
    if rp.get("use") or rp.get("avoid"):
        lines.append("From your reference reel (inspiration only, never copied): "
                     + (f"like its {', '.join(rp['use'])}" if rp.get("use") else "")
                     + ("; " if rp.get("use") and rp.get("avoid") else "")
                     + (f"not its {', '.join(rp['avoid'])}" if rp.get("avoid") else ""))
    if r["sound_off"]:
        lines.append("Sound effects: none (your rule)")
    return lines


def suggestions(style_pack=None):
    """Starter palettes and font pairings for customers without branding yet."""
    from . import styles
    out = {}
    for p in styles.list_packs():
        if p["legacy"] or (style_pack and p["id"] != style_pack):
            continue
        out[p["id"]] = styles.load_pack(p["id"]).get("suggestions", {})
    return out
