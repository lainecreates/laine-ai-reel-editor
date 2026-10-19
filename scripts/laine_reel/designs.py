"""Design variety across a customer's reels (Stage 6) - intentional, not random.

Each style pack lists several designs ("variants") per intent, e.g. Magazine's
stat: "numeral" (a big serif number) or "bar" (a bar chart, only for percentages).
For every graphic the editor picks, in this order:

  1. the customer's own choice in review ("Try another design")
  2. Claude's choice in the creative plan ("design": "bar")
  3. what this reel already uses for the same intent (one look per reel)
  4. the suitable design this customer's recent reels in this style used least
     (ties go to the style's own order, signature design first - never chance)

Choices are pinned in <reel>/designs.json, so re-planning or rendering other
reels later never changes a reel. brand/creative-history.json remembers what
each reel used. Classic (and anything without designs) is untouched.
"""

import json
from pathlib import Path

from . import config, styles
from .project import read_json, write_json

HISTORY_KEEP = 40
RECENT = 6


def variants_for(profile, intent):
    st = styles.resolve(profile)
    if st["legacy"]:
        return []
    return st["aspects"]["components"].get("variants", {}).get(intent, [])


def suits(v, g, deco=None):
    fits = v.get("fits") or {}
    if fits.get("needs_decoration") and deco is not None and not deco.get(fits["needs_decoration"]):
        return False          # a frame design with borders switched off would just look plain
    text = f"{g.get('text') or ''}"
    if fits.get("needs_percent") and not ("%" in text or "percent" in text.lower()):
        return False
    if fits.get("max_items") and len(g.get("items") or []) > fits["max_items"]:
        return False
    return True


def history_path():
    return config.brand_dir() / "creative-history.json"


def load_history():
    p = history_path()
    return read_json(p) if p.exists() else []


def record(reel, edit, profile):
    """After a render: remember which designs this reel used."""
    st = styles.resolve(profile)
    if st["legacy"]:
        return
    used = {}
    for g in edit.get("graphics", []):
        if g.get("variant"):
            used.setdefault(g["intent"], g["variant"])
    h = [x for x in load_history() if x.get("reel") != reel.root.name]
    h.append({"reel": reel.root.name, "pack": st["pack"], "designs": used})
    p = history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, h[-HISTORY_KEEP:])


def _pins_path(reel):
    return reel.path("designs.json")


def load_pins(reel):
    p = _pins_path(reel)
    return read_json(p) if p.exists() else {"intents": {}, "graphics": {}}


def _rank(vs, intent, pack, reel_name, history):
    recent = [x for x in history if x.get("reel") != reel_name and x.get("pack") == pack][-RECENT:]
    uses = {v["id"]: sum(1 for x in recent if x["designs"].get(intent) == v["id"]) for v in vs}
    last = {v["id"]: max([i for i, x in enumerate(recent) if x["designs"].get(intent) == v["id"]], default=-1)
            for v in vs}
    order = {v["id"]: i for i, v in enumerate(vs)}     # the style's signature design first
    return sorted(vs, key=lambda v: (uses[v["id"]], last[v["id"]], order[v["id"]]))


def assign(reel, edit, profile):
    """Give every style graphic its design; pin the choices. Returns {gid: variant}."""
    st = styles.resolve(profile)
    if st["legacy"]:
        return {}
    pins = load_pins(reel)
    per_intent, per_graphic = pins.setdefault("intents", {}), pins.setdefault("graphics", {})
    history = load_history()
    deco = styles.decorations_on(st)
    out = {}
    for g in edit.get("graphics", []):
        intent = g.get("intent")
        vs = variants_for(profile, intent)
        if not vs or not g.get("component"):
            continue
        ok = {v["id"] for v in vs if suits(v, g, deco)} or {vs[0]["id"]}
        pick = None
        own = per_graphic.get(g["id"]) or {}
        if own.get("intent") != intent or (own.get("text") and own["text"] != _key(g)):
            # ids can move after a re-plan: find the customer's pick by what the graphic says
            own = next((x for x in per_graphic.values() if isinstance(x, dict) and x.get("intent") == intent
                        and x.get("text") and x["text"] == _key(g)), {})
        own = own.get("design")
        for cand in (own, g.get("design"), per_intent.get(intent)):
            if cand in ok:
                pick = cand
                break
        if not pick:
            pick = next(v["id"] for v in _rank(vs, intent, st["pack"], reel.root.name, history) if v["id"] in ok)
            per_intent.setdefault(intent, pick)
        g["variant"] = pick
        g["variant_name"] = next(v["name"] for v in vs if v["id"] == pick)
        g["variants"] = [{"id": v["id"], "name": v["name"]} for v in vs if v["id"] in ok]
        out[g["id"]] = pick
    write_json(_pins_path(reel), pins)
    return out


def _key(g):
    """What a graphic says (text, or its list items): survives id changes."""
    return (g.get("text") or " / ".join(i.get("text", "") for i in g.get("items") or [])).strip().lower()


def another(reel, edit, gid, profile, design="next"):
    """'Try another design' for one graphic: the next suitable design (or the one
    named), pinned to that graphic only - the rest of the reel keeps its look.
    Returns (old, new) names, or None if there's no other design to try."""
    g = next((x for x in edit.get("graphics", []) if x["id"] == gid), None)
    if not g:
        return None
    deco = styles.decorations_on(styles.resolve(profile))
    vs = [v for v in variants_for(profile, g.get("intent")) if suits(v, g, deco)]
    if len(vs) < 2:
        return None
    ids = [v["id"] for v in vs]
    cur = g.get("variant") if g.get("variant") in ids else ids[0]
    if design in (None, "", "next"):
        nxt = ids[(ids.index(cur) + 1) % len(ids)]
    elif design in ids:
        nxt = design
    else:
        return None
    pins = load_pins(reel)
    pins.setdefault("graphics", {})[gid] = {"design": nxt, "intent": g.get("intent"), "text": _key(g)}
    write_json(_pins_path(reel), pins)
    name = {v["id"]: v["name"] for v in vs}
    return name[cur], name[nxt]


def catalog(profile):
    """Every design of the customer's style, by intent (for Claude's context)."""
    st = styles.resolve(profile)
    if st["legacy"]:
        return {}
    return {k: [{"id": v["id"], "name": v["name"], **({"only_when": v["fits"]} if v.get("fits") else {})}
                for v in vs]
            for k, vs in st["aspects"]["components"].get("variants", {}).items()}


def recent_for_context(profile, reel_name=None):
    st = styles.resolve(profile)
    recent = [x for x in load_history() if x.get("pack") == st["pack"] and x.get("reel") != reel_name][-RECENT:]
    return [x["designs"] for x in recent]
