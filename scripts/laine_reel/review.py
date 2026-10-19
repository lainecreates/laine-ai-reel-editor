"""Phase 4: the customer's review of a rendered reel.

    reel_data(reel)        -> everything the review page shows
    save_feedback(reel, f) -> review/feedback-<time>.json (never overwritten)
    apply_feedback(reel)   -> turns the latest saved feedback into per-reel edits:
        cuts      -> cleanup.review.json   (keep / remove phrases, cut pauses)
        captions  -> transcript.fixes.json (spelling, word timing)
        headline, graphic edits, new graphics / zooms / sound effects
                  -> edit.overrides.json
        notes     -> returned for Claude to interpret
    The brand profile (brand/) is never changed by a review. Before any file is
    rewritten, its previous version is copied to review/history/<time>/.
"""

import datetime as _dt
import json
import re
import shutil
from pathlib import Path

from . import config, timeline, versions
from .project import read_json, write_json

ANIMATIONS = ["pop", "fade", "fade_scale", "slide", "bounce", "none"]
ADDABLE = {"text_callouts": "Text callout", "sticky_notes": "Sticky note", "emoji": "Emoji",
           "arrows": "Arrow", "keyword_cards": "Key-phrase card", "lists": "Checklist",
           "full_overlay": "Full-screen overlay with text", "profile_card": "Profile page card",
           "image": "Image from my library"}


def _now():
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _opt(reel, name, default=None):
    p = reel.path(name)
    return read_json(p) if p.exists() else default


def output_to_source(t, keep):
    """Inverse of timeline.source_to_output (output time -> source time)."""
    offset = 0.0
    for a, b in keep:
        d = b - a
        if t <= offset + d + 1e-6:
            return round(a + (t - offset), 3)
        offset += d
    return round(keep[-1][1], 3) if keep else t


CAROUSEL_KEYS = ("place", "size", "speed", "direction", "motion")


def _added_item(ov, gid):
    """rg3 = the 3rd graphic requested in review (edit.overrides.json add.graphics)."""
    if not str(gid).startswith("rg") or not str(gid)[2:].isdigit():
        return None
    items = (ov.get("add") or {}).get("graphics") or []
    i = int(str(gid)[2:]) - 1
    return (i, items[i]) if 0 <= i < len(items) else None


# -- data for the page -------------------------------------------------------

def reel_data(reel):
    m = reel.manifest()
    edl = read_json(reel.path("edl.json"))
    edit = _opt(reel, "edit.json", {})
    from .brand import effective
    brand = effective(reel.root)
    words_src = _opt(reel, "transcript.json", {"words": []})["words"]
    words_out = _opt(reel, "transcript.cut.json", {"words": []})["words"]
    cl = _opt(reel, "cleanup.json", {"candidates": [], "removed_words": []})
    removed = set(cl.get("removed_words", []))
    keep = edl["keep"]

    def kept_at(t):
        return timeline.source_to_output(t, keep)

    # Source words with their fate, for the "Cuts" tab.
    src = []
    for i, w in enumerate(words_src):
        out = kept_at((w["start"] + w["end"]) / 2)
        src.append({"i": i, "text": w["text"], "start": w["start"], "end": w["end"],
                    "removed": i in removed or out is None, "out": out})
    # Pauses longer than the natural one (> 0.35 s), for "remove this pause".
    pauses = []
    for a, b in zip(words_out, words_out[1:]):
        gap = b["start"] - a["end"]
        if gap > 0.35:  # the natural pause the pacing keeps is ~0.3 s
            pauses.append({"after_word": a.get("i"), "at": round(a["end"], 3),
                           "length": round(gap, 2), "before": a["text"], "next": b["text"]})
    head = next((g for g in edit.get("graphics", []) if g.get("role") == "headline"), None)
    sugg = _opt(reel, "review/suggestions.json", {}).get("headlines", [])
    vs = versions.list_versions(reel)
    legacy = versions.legacy_renders(reel)
    finals = sorted(reel.output.glob("*-final.mp4"))
    cur = versions.current_number(reel)
    fb = sorted(reel.root.joinpath("review").glob("feedback-*.json")) if reel.root.joinpath("review").exists() else []
    colors = brand.get("colors", {})
    fonts = brand.get("fonts", {})
    return {
        "name": m["name"],
        "video": f"/media/{finals[0].relative_to(reel.root)}" if finals else
                 f"/media/{reel.video_out.relative_to(reel.root)}",
        "versions": [{"n": v["n"], "label": versions.label(v), "duration": v["duration"],
                      "url": f"/media/output/versions/v{v['n']:03d}/video.mp4",
                      "approved": v.get("approved", False), "current": v["n"] == cur,
                      "from_feedback": v.get("from_feedback"), "restorable": True}
                     for v in vs] +
                    [{"n": None, "label": version_label(p) + " (older, watch only)",
                      "url": f"/media/{p.relative_to(reel.root)}", "approved": False,
                      "current": False, "restorable": False}
                     for p in legacy if "-final-" in p.name],
        "current_version": cur,
        "approved": reel.manifest().get("approved_version"),
        "duration": edl["stats"]["output_duration"],
        "words_out": words_out, "words_src": src, "pauses": pauses,
        "candidates": cl.get("candidates", []),
        "cuts": [{"start": c["start"], "end": c["end"], "kind": c["kind"]} for c in edl["cuts"]],
        "captions": edit.get("captions", {}).get("items", []),
        "caption_style": edit.get("captions", {}).get("style", {}),
        "graphics": edit.get("graphics", []), "zooms": edit.get("zooms", []),
        "creative": edit.get("creative") or {"used": False},
        "sfx": edit.get("sfx", []),
        "headline": {"id": head["id"] if head else None, "text": head.get("text") if head else None,
                     "style": brand.get("headline", {}).get("style", "none"),
                     "suggestions": sugg},
        "brand": {"palette": colors.get("palette", []), "primary": colors.get("primary"),
                  "accent": colors.get("accent"),
                  "fonts": [{"key": "headline", "name": fonts.get("headline")},
                            {"key": "body", "name": fonts.get("body")},
                            {"key": "hand", "name": "Handwritten"}],
                  "name": brand.get("name")},
        "animations": ANIMATIONS, "addable": ADDABLE,
        "draft": _opt(reel, "review/draft.json"),
        "history": [{"file": f.name, "applied": bool(read_json(f).get("applied_at"))} for f in fb],
    }


def version_label(path):
    """review-test-copy-final-20261018-000023.mp4 -> 'Finished video · Oct 18, 12:00 AM'."""
    m = re.search(r"-(final|vertical)(?:-preview)?-(\d{8})-(\d{6})$", path.stem)
    if not m:
        return path.stem
    kind = "Finished video" if m.group(1) == "final" else "Clean cut (no graphics)"
    when = _dt.datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S")
    return f"{kind} · {when.strftime('%b %-d, %-I:%M %p')}"


# -- saving ---------------------------------------------------------------------

def save_draft(reel, data):
    d = reel.root / "review"
    d.mkdir(exist_ok=True)
    write_json(d / "draft.json", data)


def save_feedback(reel, data):
    d = reel.root / "review"
    d.mkdir(exist_ok=True)
    data = dict(data, saved_at=_dt.datetime.now().isoformat(timespec="seconds"))
    path = d / f"feedback-{_now()}.json"
    n = 2
    while path.exists():
        path = d / f"feedback-{_now()}-{n}.json"
        n += 1
    write_json(path, data)
    if (d / "draft.json").exists():
        (d / "draft.json").unlink()
    return path


def unapplied(reel):
    """Every saved-but-not-applied feedback file, oldest first."""
    d = reel.root / "review"
    files = sorted(d.glob("feedback-*.json")) if d.exists() else []
    return [f for f in files if not read_json(f).get("applied_at")]


def apply_all(reel):
    """Apply every unapplied feedback file in the order it was saved."""
    total = {"files": [], "applied": [], "skipped": [], "notes": [], "needs": None}
    rank = {None: 0, "final": 1, "recut": 2}
    for f in unapplied(reel):
        res = apply_feedback(reel, f)
        total["files"].append(Path(res["file"]).name)
        for k in ("applied", "skipped", "notes"):
            total[k] += res[k]
        if rank[res["needs"]] > rank[total["needs"]]:
            total["needs"] = res["needs"]
    total["file"] = ", ".join(total["files"]) or None
    return total


def latest_unapplied(reel):
    d = reel.root / "review"
    files = sorted(d.glob("feedback-*.json")) if d.exists() else []
    for f in reversed(files):
        if not read_json(f).get("applied_at"):
            return f
    return None


# -- applying -------------------------------------------------------------------

def _backup(reel, names, stamp):
    dest = reel.root / "review" / "history" / stamp
    for n in names:
        p = reel.path(n)
        if p.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / n)


def apply_feedback(reel, path=None):
    """Turn saved feedback into edits. Returns a summary dict:
    {"file", "applied": [...], "skipped": [...], "notes": [...], "needs": "recut"|"final"|None}"""
    path = path or latest_unapplied(reel)
    if not path:
        return {"file": None, "applied": [], "skipped": [], "notes": [], "needs": None}
    fb = read_json(path)
    stamp = _now()
    _backup(reel, ["cleanup.review.json", "transcript.fixes.json", "edit.overrides.json"], stamp)
    # Times on the page are on the timeline of the version the customer was
    # watching. Map them with THAT version's cut list, so requests land on the
    # right moment even if the reel was re-cut since.
    keep = read_json(reel.path("edl.json"))["keep"]
    watched = fb.get("version")
    if watched:
        snap = versions.vdir(reel) / f"v{int(watched):03d}" / "state" / "edl.json"
        if snap.exists():
            keep = read_json(snap)["keep"]
    words = read_json(reel.path("transcript.json"))["words"]
    cands = {c["id"]: c for c in _opt(reel, "cleanup.json", {"candidates": []})["candidates"]}
    applied, skipped = [], []
    needs_recut = False

    # cuts -----------------------------------------------------------------
    cuts = fb.get("cuts", {})
    rv = _opt(reel, "cleanup.review.json", {}) or {}
    rv.setdefault("remove", [])
    rv.setdefault("keep", [])
    rv.setdefault("pause_cuts", [])
    for cid in cuts.get("keep", []):
        c = cands.get(cid)
        if cid.startswith("r") and c:
            before = len(rv["remove"])
            rv["remove"] = [r for r in rv["remove"] if [r["from"], r["to"]] != c["words"]]
            if len(rv["remove"]) != before:
                applied.append(f"put back: \"{c['text']}\"")
                needs_recut = True
        elif cid not in rv["keep"]:
            rv["keep"].append(cid)
            applied.append(f"put back: \"{c['text'] if c else cid}\"")
            needs_recut = True
    for cid in cuts.get("remove", []):
        c = cands.get(cid)
        if c:
            rv["remove"].append({"from": c["words"][0], "to": c["words"][1], "type": "review",
                                 "reason": "removed in review"})
            rv["keep"] = [k for k in rv["keep"] if k != cid]
            applied.append(f"remove: \"{c['text']}\"")
            needs_recut = True
    for i, j in cuts.get("remove_words", []):
        i, j = int(i), int(j)
        if 0 <= i <= j < len(words):
            text = " ".join(w["text"] for w in words[i:j + 1])
            rv["remove"].append({"from": i, "to": j, "type": "review",
                                 "reason": "removed in review"})
            applied.append(f"remove words {i}-{j}: \"{text}\"")
            needs_recut = True
    for i in cuts.get("cut_pauses", []):
        if int(i) not in rv["pause_cuts"]:
            rv["pause_cuts"].append(int(i))
            applied.append(f"shorten the pause after \"{words[int(i)]['text']}\"")
            needs_recut = True
    if needs_recut:
        write_json(reel.path("cleanup.review.json"), rv)

    # captions -------------------------------------------------------------
    fixes = _opt(reel, "transcript.fixes.json", {"words": {}})
    for k, fix in (fb.get("captions") or {}).items():
        i = int(k)
        if not (0 <= i < len(words)):
            skipped.append(f"caption word {k}: not in the transcript")
            continue
        entry = fixes["words"].get(str(i), {})
        if fix.get("text") and fix["text"].strip() != words[i]["text"]:
            entry["text"] = fix["text"].strip()
            applied.append(f"caption spelling: \"{words[i]['text']}\" -> \"{entry['text']}\"")
        for key in ("start", "end"):
            if fix.get(f"{key}_out") is not None:
                entry[key] = output_to_source(float(fix[f"{key}_out"]), keep)
        if "start" in entry or "end" in entry:
            applied.append(f"caption timing for \"{entry.get('text', words[i]['text'])}\"")
        if entry:
            fixes["words"][str(i)] = entry
            needs_recut = True
    if fb.get("captions"):
        write_json(reel.path("transcript.fixes.json"), fixes)

    # headline, graphics, additions -----------------------------------------
    ov = _opt(reel, "edit.overrides.json", {}) or {}
    edit = _opt(reel, "edit.json", {"graphics": []})
    gfx = {g["id"]: g for g in edit.get("graphics", [])}
    changed = False
    if (fb.get("headline") or {}).get("choose_for_me"):
        pick = choose_headline(reel)
        if pick:
            fb["headline"] = {"text": pick, "chosen_for_me": True}
    if (fb.get("headline") or {}).get("text"):
        ov["headline"] = {"text": fb["headline"]["text"].strip()}
        from . import creative
        creative.set_headline(reel, ov["headline"]["text"])
        # a headline set by id earlier would win otherwise
        head = next((g for g in gfx.values() if g.get("role") == "headline"), None)
        if head and head["id"] in ov.get("set", {}):
            ov["set"][head["id"]].pop("text", None)
        applied.append(f"headline: \"{ov['headline']['text']}\""
                       + (" (chosen for you)" if fb["headline"].get("chosen_for_me") else ""))
        changed = True
    drop_added = set()
    for gid, change in (fb.get("graphics") or {}).items():
        g = gfx.get(gid)
        if not g:
            skipped.append(f"{gid}: graphic not found")
            continue
        added = _added_item(ov, gid)
        if added is not None:
            # something the customer asked for earlier (an image, a carousel, ...):
            # change or remove the request itself
            i, item = added
            label = g["type"].replace("_", " ")
            if change.get("remove"):
                drop_added.add(i)
                applied.append(f"remove {label} {gid}")
            elif change.get("reset_style"):
                item.pop("style", None)
                applied.append(f"{label} {gid}: back to your brand style")
            else:
                for key in ("text", "emoji") + CAROUSEL_KEYS:
                    if change.get(key) not in (None, ""):
                        item[key] = change[key]
                for key in ("start", "end"):
                    if change.get(key) not in (None, ""):
                        item[key] = round(float(change[key]), 3)
                if change.get("start") not in (None, ""):
                    item["src_start"] = output_to_source(item["start"], keep)
                for key, skey in (("background", "custom_background"), ("color", "custom_text"),
                                  ("font", "custom_font"), ("animation", "animation_in")):
                    if change.get(key):
                        item.setdefault("style", {})[skey] = change[key]
                applied.append(f"edit {label} {gid}: " + ", ".join(k for k in change if change[k] not in (None, "", False)))
            changed = True
            continue
        match = {"type": g["type"], "start": g["start"]}
        if change.get("reset_style"):
            # back to the brand's look: drop this graphic's own colours, font, animation
            spec = dict(ov.get("set", {}).get(gid, {}), _match=match)
            spec["style"] = {"custom_background": None, "custom_text": None, "custom_font": None,
                             "custom_paper": None, "animation_in": None}
            ov.setdefault("set", {})[gid] = spec
            applied.append(f"{g['type'].replace('_', ' ')} {gid}: back to your brand style")
            changed = True
            continue
        if change.get("design"):
            # "Try another design": only this graphic changes (pinned in designs.json)
            from . import designs
            from .brand import effective
            r = designs.another(reel, edit, gid, effective(reel.root) or {}, change["design"])
            if r:
                applied.append(f"{g['type'].replace('_', ' ')} {gid}: design \"{r[0]}\" -> \"{r[1]}\"")
                changed = True
            else:
                skipped.append(f"{gid}: no other design for this graphic in this style")
            change = {k: v for k, v in change.items() if k != "design"}
            if not change:
                continue
        if change.get("remove"):
            ov.setdefault("remove_match", {})[gid] = match
            applied.append(f"remove {g['type'].replace('_', ' ')} {gid}")
            changed = True
            continue
        spec = dict(ov.get("set", {}).get(gid, {}), _match=match)
        for key in ("text", "start", "end", "emoji"):
            if change.get(key) not in (None, ""):
                spec[key] = float(change[key]) if key in ("start", "end") else change[key]
        for key in ("start", "end"):
            if key in spec:   # remember where in the speech, for later re-cuts
                spec[f"src_{key}"] = output_to_source(spec[key], keep)
        if change.get("items") and g.get("items"):
            old_items = g["items"]
            spec["items"] = [{"text": t, "at": old_items[min(k, len(old_items) - 1)]["at"]}
                             for k, t in enumerate(change["items"])]
        style = dict(spec.get("style", {}))
        for key, skey in (("background", "custom_background"), ("color", "custom_text"),
                          ("font", "custom_font"), ("animation", "animation_in"),
                          ("paper", "custom_paper")):
            if change.get(key):
                style[skey] = change[key]
        if change.get("checks"):
            style["checks"] = True   # the planner adds a click as each box ticks
        if change.get("place"):
            spec["place"] = change["place"]
        if style:
            spec["style"] = style
        ov.setdefault("set", {})[gid] = spec
        applied.append(f"edit {g['type'].replace('_', ' ')} {gid}: "
                       + ", ".join(k for k in change if change[k] not in (None, "", False)))
        changed = True
    if drop_added:
        ov["add"]["graphics"] = [x for i, x in enumerate(ov["add"]["graphics"]) if i not in drop_added]
    add = fb.get("add") or {}
    if any(add.get(k) for k in ("graphics", "zooms", "sfx")):
        ovadd = ov.setdefault("add", {})
        for g in add.get("graphics", []):
            if g.get("type") not in ADDABLE:
                skipped.append(f"new graphic: unknown type {g.get('type')}")
                continue
            item = {"type": g["type"], "start": round(float(g["t"]), 3),
                    "end": round(float(g["t"]) + float(g.get("duration") or 2.5), 3),
                    "src_start": output_to_source(float(g["t"]), keep)}
            if g["type"] == "emoji":
                item["emoji"] = g.get("emoji") or g.get("text") or "✨"
            elif g["type"] in ("sticky_notes", "lists"):
                lines = [x.strip() for x in re.split(r"\n|;", g.get("text", "")) if x.strip()]
                item["items"] = [{"text": x, "at": item["start"]} for x in lines] or \
                                [{"text": "…", "at": item["start"]}]
            elif g["type"] == "arrows":
                item["direction"] = g.get("direction") or "down_right"
            elif g["type"] == "full_overlay":
                item["text"] = g.get("text", "")
                item["opacity"] = float(g.get("opacity") or 0.55)
            elif g["type"] == "profile_card":
                item["place"] = "top"
            elif g["type"] == "image":
                from . import library
                a = library.get(g.get("asset") or "")
                if not a or a["kind"] != "image":
                    skipped.append("new image: not in your library")
                    continue
                item.update(asset=a["id"], category=a.get("category"),
                            place=g.get("place") or ("top" if a.get("category") == "logo" else None))
                item["text"] = a["name"]
            else:
                item["text"] = g.get("text", "")
            ovadd.setdefault("graphics", []).append(item)
            applied.append(f"new {ADDABLE[g['type']].lower()} at {item['start']:.1f}s")
        for z in add.get("zooms", []):
            t = float(z["t"])
            item = {"type": z.get("type", "punch"), "start": round(t, 3),
                    "end": round(t + float(z.get("duration") or 2.0), 3),
                    "scale": float(z.get("scale") or 1.15),
                    "src_start": output_to_source(t, keep)}
            ovadd.setdefault("zooms", []).append(item)
            applied.append(f"new {item['type']} zoom at {t:.1f}s")
        for s in add.get("sfx", []):
            if str(s.get("kind", "")).startswith("library:"):
                from . import library
                if not library.path_of(s["kind"].split(":", 1)[1]):
                    skipped.append("new sound: not in your library")
                    continue
            t = float(s["t"])
            ovadd.setdefault("sfx", []).append({"at": round(t, 3), "kind": s.get("kind", "pop"),
                                                "src_at": output_to_source(t, keep)})
            label = s.get("kind", "pop")
            if label.startswith("library:"):
                from . import library
                label = f"“{(library.get(label.split(':', 1)[1]) or {}).get('name', 'library')}”"
            applied.append(f"new {label} sound at {t:.1f}s")
        changed = True
    if changed:
        write_json(reel.path("edit.overrides.json"), ov)

    notes = [dict(n, src_t=output_to_source(float(n["t"]), keep))
             for n in fb.get("notes", []) if n.get("text", "").strip()]
    fb["applied_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    fb["applied"] = {"applied": applied, "skipped": skipped, "backup": f"review/history/{stamp}"}
    write_json(path, fb)
    needs = "recut" if needs_recut else ("final" if changed else None)
    return {"file": str(path), "applied": applied, "skipped": skipped, "notes": notes,
            "needs": needs}


def retime_additions(ov, keep):
    """After a re-cut, requested items keep their place in the *speech*:
    convert their source time back to the new output timeline."""
    for spec in ov.get("set", {}).values():
        for key in ("start", "end"):
            src = spec.get(f"src_{key}")
            if src is not None:
                new = timeline.source_to_output(src, keep)
                if new is not None:
                    spec[key] = round(new, 3)
    add = ov.get("add", {})
    for layer, src_key, keys in (("graphics", "src_start", ("start", "end")),
                                 ("zooms", "src_start", ("start", "end")),
                                 ("sfx", "src_at", ("at",))):
        for it in add.get(layer, []):
            src = it.get(src_key)
            if src is None:
                continue
            new = timeline.source_to_output(src, keep)
            if new is None:
                continue
            shift = new - it[keys[0]]
            for k in keys:
                it[k] = round(it[k] + shift, 3)
    return ov


def choose_headline(reel):
    """'Choose for me': the strongest suggestion. Claude writes
    review/suggestions.json strongest first; without it, the first line."""
    sugg = _opt(reel, "review/suggestions.json", {}).get("headlines") or suggest_headlines(reel)
    return sugg[0] if sugg else None


def suggest_headlines(reel, count=3):
    """Fallback suggestions from the opening line, if Claude hasn't written
    review/suggestions.json. Claude's suggestions are better; this keeps the
    page useful without them."""
    from . import creative
    hook = creative.hook_text(reel)          # the plan's hook leads; no duplicates
    words = _opt(reel, "transcript.cut.json", {"words": []})["words"]
    first = []
    for w in words:
        first.append(w["text"].strip(",.?!\"“”"))
        if re.search(r"[.?!]$", w["text"]) or len(first) >= 8:
            break
    out = [hook] if hook else []
    for s in ([" ".join(first[:n]) for n in (4, 6, 8)] if first else []):
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out[:count]



def mark_settings_changed(reel, parsed, scope):
    """Remember that brand settings changed, so the next "apply my review"
    re-plans (and re-cuts if the pacing changed) and renders a new version."""
    d = reel.root / "review"
    d.mkdir(exist_ok=True)
    p = d / "settings-pending.json"
    cur = read_json(p) if p.exists() else {"keys": [], "scopes": []}
    cur["keys"] = sorted(set(cur["keys"]) | set(parsed))
    cur["scopes"] = sorted(set(cur["scopes"]) | {scope})
    cur["at"] = _dt.datetime.now().isoformat(timespec="seconds")
    write_json(p, cur)


def take_settings_changes(reel):
    p = reel.root / "review" / "settings-pending.json"
    if not p.exists():
        return None
    cur = read_json(p)
    p.unlink()
    return cur


def settings_supersede(reel, keys):
    """Newer brand settings beat older one-off choices for the same thing:
    a sound chosen for a moment in Brand settings replaces an earlier per-reel
    sound swap for that moment. Returns what was replaced."""
    replaced = []
    if "sound_map" not in keys:
        return replaced
    from .brand import effective
    smap = (effective(reel.root) or {}).get("sfx", {}).get("sounds", {})
    op, ep = reel.path("edit.overrides.json"), reel.path("edit.json")
    if not (op.exists() and ep.exists()):
        return replaced
    ov, edit = read_json(op), read_json(ep)
    events = {x["id"]: x.get("event") for x in edit.get("sfx", [])}
    for sid in list(ov.get("set", {})):
        if events.get(sid) in smap and "kind" in ov["set"][sid]:
            replaced.append(f"{events[sid]} sound '{ov['set'][sid]['kind']}' -> your chosen sound")
            del ov["set"][sid]
    if replaced:
        write_json(op, ov)
    return replaced
