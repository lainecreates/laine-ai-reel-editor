"""Style packs: complete design languages, and how one is chosen for a reel.

    styles/<pack>/<version>/pack.json

A pack defines *aspects* of a look: typography, captions, components (one per
intent), motion, shape, sound, decorations. Packs never contain customer colours
or fonts: those come from the brand and plug into every pack by role.

A customer's style is a starting pack, optionally mixed with other packs per
aspect ("Magazine layouts with Luxe motion"), plus their own creative direction
in their own words. Every resolved value records where it came from, in this
priority order (highest first):

    review     notes and per-graphic edits on this reel     (applied at render)
    reel       instructions for this reel only              (reel brand.answers.json)
    rules      the customer's standing creative rules       (brand creative_rules)
    brand      explicit brand choices (e.g. caption outline)
    pack       the chosen style pack(s)
    reference  traits learned from a reference reel         (Stage 5)
    engine     plain: no outlines, glows, boxes or shadows

Reels pin pack id + version in their brand snapshot, so a later pack version
never changes an older reel.
"""

import json
import os
import re
from pathlib import Path

from . import config

ASPECTS = ["typography", "captions", "components", "motion", "shape", "sound", "decorations",
           "composition", "zoom"]

# What a moment needs (Claude chooses intents; the pack chooses how they look).
INTENTS = ["hook", "headline_bar", "key_phrase", "stat", "list", "question_list", "steps",
           "contrast", "question", "quote", "definition", "tip", "reaction", "cta",
           "social_proof", "chapter", "lower_third", "pointer", "image", "logo", "progress",
           "full_overlay", "carousel", "calendar", "custom"]

# Graphic types the planner, layout and review page already use -> intents.
TYPE_TO_INTENT = {
    "text_callouts": "key_phrase", "headline_bar": "headline_bar", "keyword_cards": "key_phrase",
    "lists": "list", "sticky_notes": "question_list", "cta_card": "cta", "lower_third": "lower_third",
    "emoji": "reaction", "arrows": "pointer", "image": "image", "progress_bar": "progress",
    "full_overlay": "full_overlay", "profile_card": "social_proof", "carousel": "carousel", "calendar": "calendar", "custom": "custom",
}

# Decorations are OFF unless a pack, the brand or the customer turns them on.
DECORATIONS = ["caption_outline", "caption_glow", "caption_shadow", "graphic_box",
               "graphic_shadow", "graphic_border", "emoji_shadow"]
ENGINE_DEFAULT = {d: False for d in DECORATIONS}

# Standing creative rules (Brand settings, Stage 4 UI). Each switches things OFF.
RULES = {
    "no_outlines": {"decorations": ["caption_outline"]},
    "no_glow": {"decorations": ["caption_glow"]},
    "no_shadows": {"decorations": ["caption_shadow", "graphic_shadow", "emoji_shadow"]},
    "no_boxes": {"decorations": ["graphic_box", "graphic_border"]},
    "no_emojis": {"intents": ["reaction"]},
    "no_sound_effects": {"sound": True},
}

DEFAULT_PACK = "classic"
LEGACY_VERSION = "1.0.0"        # profiles from before packs existed render as Classic 1.0.0


def styles_dir():
    return Path(os.environ.get("LAINE_STYLES_DIR", config.PROJECT_ROOT / "styles"))


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def versions(pack_id):
    d = styles_dir() / pack_id
    return sorted((p.name for p in d.iterdir() if (p / "pack.json").exists()), key=_vkey) \
        if d.is_dir() else []


def list_packs():
    out = []
    if styles_dir().is_dir():
        for d in sorted(styles_dir().iterdir()):
            vs = versions(d.name) if d.is_dir() else []
            if vs:
                p = load_pack(d.name, vs[-1])
                out.append({"id": p["id"], "version": p["version"], "name": p["name"],
                            "description": p.get("description", ""), "legacy": p.get("legacy", False)})
    return out


_cache = {}


def load_pack(pack_id, version=None):
    """A pack at a pinned version (or its latest). Raises ValueError if unknown."""
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", pack_id or ""):
        raise ValueError(f"Unknown style pack {pack_id!r}")
    vs = versions(pack_id)
    if not vs:
        raise ValueError(f"Unknown style pack {pack_id!r}")
    v = version or vs[-1]
    if v not in vs:
        raise ValueError(f"Style pack {pack_id} has no version {v}")
    key = (str(styles_dir()), pack_id, v)
    if key not in _cache:
        _cache[key] = json.loads((styles_dir() / pack_id / v / "pack.json").read_text())
    return _cache[key]


def latest_version(pack_id):
    vs = versions(pack_id)
    return vs[-1] if vs else None


# -- the customer's style choice (stored in brand answers as "style") ------------

def validate_choice(value):
    """{"pack", "mix": [{"pack", "aspects": [...]}], "direction": str,
        "decorations": {name: bool}} -> cleaned, or ValueError."""
    v = dict(value or {})
    pack = v.get("pack") or DEFAULT_PACK
    load_pack(pack)
    mix = []
    for m in v.get("mix") or []:
        load_pack(m.get("pack"))
        aspects = [a for a in (m.get("aspects") or []) if a in ASPECTS]
        if not aspects:
            raise ValueError(f"Say which aspects to take from {m.get('pack')}: {', '.join(ASPECTS)}")
        mix.append({"pack": m["pack"], "aspects": aspects})
    direction = str(v.get("direction") or "").strip()[:2000]
    keep = [k for k in (v.get("keep") or []) if k in ("caption_style", "caption_animation",
                                                       "caption_emphasis", "zooms")]
    decorations = {}
    for k, on in (v.get("decorations") or {}).items():
        if k not in DECORATIONS or not isinstance(on, bool):
            raise ValueError(f"Unknown decoration setting {k}")
        decorations[k] = on
    return {"pack": pack, "mix": mix, "direction": direction, "decorations": decorations, "keep": keep}


def validate_rules(value):
    """Standing creative rules: {"flags": [...], "notes": "free text"}."""
    v = dict(value or {})
    flags = [f for f in (v.get("flags") or [])]
    bad = [f for f in flags if f not in RULES]
    if bad:
        raise ValueError(f"Unknown creative rule {bad[0]}")
    return {"flags": sorted(set(flags)), "notes": str(v.get("notes") or "").strip()[:4000]}


def compile_choice(answers):
    """The profile's "style" block: the choice with every pack version pinned."""
    choice = validate_choice(answers.get("style"))
    pinned = {"pack": choice["pack"], "version": latest_version(choice["pack"]),
              "mix": [dict(m, version=latest_version(m["pack"])) for m in choice["mix"]],
              "direction": choice["direction"], "decorations": choice["decorations"],
              "rules": validate_rules(answers.get("creative_rules"))}
    return pinned


# -- resolving a reel's style ---------------------------------------------------------

def resolve(profile):
    """Everything the planner and renderer need from the style, with sources.

    profile: the brand profile a reel renders with (already merged with any
    reel-only changes). Old profiles without a "style" block are Classic 1.0.0.
    """
    choice = profile.get("style") or {"pack": DEFAULT_PACK, "version": LEGACY_VERSION,
                                      "mix": [], "direction": "", "decorations": {},
                                      "rules": {"flags": [], "notes": ""}}
    base = load_pack(choice["pack"], choice.get("version"))
    aspect_pack = {a: base for a in ASPECTS}
    aspect_src = {a: f"pack:{base['id']}" for a in ASPECTS}
    for m in choice.get("mix") or []:
        p = load_pack(m["pack"], m.get("version"))
        for a in m["aspects"]:
            aspect_pack[a], aspect_src[a] = p, f"pack:{p['id']}"
    aspects = {a: aspect_pack[a].get("aspects", {}).get(a, {}) for a in ASPECTS}
    aspect_packs = {a: (aspect_pack[a]["id"], aspect_pack[a]["version"]) for a in ASPECTS}

    # decorations, lowest priority first
    deco = {d: {"on": ENGINE_DEFAULT[d], "source": "engine"} for d in DECORATIONS}
    for d, on in aspects["decorations"].items():
        if d in deco:
            deco[d] = {"on": bool(on), "source": aspect_src["decorations"]}
    caps = profile.get("captions", {})
    # An outline the customer set wins over the pack. Profiles saved before
    # outlines had a source (Phase A) keep exactly the outline they had.
    if caps.get("outline") and caps.get("outline_source") in (None, "brand"):
        deco["caption_outline"] = {"on": bool(caps["outline"].get("enabled")),
                                   "source": "brand" if caps.get("outline_source") else "profile"}
    for d, on in (choice.get("decorations") or {}).items():
        deco[d] = {"on": on, "source": "brand"}
    rules = (choice.get("rules") or {}).get("flags", [])
    blocked_intents, sound_off = set(), False
    for r in rules:
        for d in RULES[r].get("decorations", []):
            deco[d] = {"on": False, "source": f"rule:{r}"}
        blocked_intents |= set(RULES[r].get("intents", []))
        sound_off |= bool(RULES[r].get("sound"))

    return {
        "pack": base["id"], "version": base["version"], "legacy": base.get("legacy", False),
        "mix": [{"pack": m["pack"], "aspects": m["aspects"]} for m in choice.get("mix") or []],
        "direction": choice.get("direction", ""),
        "rules": choice.get("rules") or {"flags": [], "notes": ""},
        "aspects": aspects, "aspect_sources": aspect_src, "aspect_packs": aspect_packs,
        "decorations": deco, "blocked_intents": sorted(blocked_intents), "sound_off": sound_off,
    }


def decorations_on(resolved):
    return {d: v["on"] for d, v in resolved["decorations"].items()}


def intent_for(graphic_type):
    return TYPE_TO_INTENT.get(graphic_type, "key_phrase")


def intent_of(g):
    """A planned graphic's intent, more precisely than its type."""
    if g.get("role") == "logo":
        return "logo"
    if g.get("brief_intent") in ("quote", "contrast", "tip"):   # chosen by Claude's creative plan
        return g["brief_intent"]
    if g["type"] == "text_callouts":
        if g.get("role") == "headline":
            return "hook"
        if re.search(r"\d", g.get("text") or ""):
            return "stat"
    return intent_for(g["type"])


NO_COMPOSITION = {"logo", "image", "progress", "full_overlay", "carousel", "calendar", "custom"}


def composition_for(resolved, intent):
    """Where/how big a pack wants this intent: {"align", "w", "h", "zone"}."""
    comp = resolved["aspects"].get("composition") or {}
    if not comp or intent in NO_COMPOSITION:
        return None
    c = dict(comp.get("default") or {}, **(comp.get("by_intent", {}).get(intent) or {}))
    return c or None


def component_for(resolved, intent):
    return resolved["aspects"]["components"].get("by_intent", {}).get(intent)
