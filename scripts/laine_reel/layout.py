"""Face-aware placement for captions and graphics: composition, not fixed slots.

Each graphic goes where it reads best in THIS footage. Where it was asked to go
(the customer's review, their instructions, or Claude's plan: "place") comes first;
otherwise the style's preferred zone is only a gentle pull, so a person framed
high gets the headline lower, and so on. Every candidate position is scored;
the cheapest wins:
  covering the face (eyes to chin)   x1000   never, unless there is no room at all
  covering hair / head               x30 (captions), x3 (graphics): tucking text over
                                     the hairline is fine when it stays readable
  shrinking                          moving beats shrinking; below 72 % only to keep
                                     off the face (text must stay readable on a phone)
  colliding with captions            x300
  colliding with another graphic     x1000 (never on top of each other)
  sitting in the platforms' UI strips (bottom caption area, right-hand buttons)
  distance from the preferred spot   small tie-breaker
Zooms enlarge the face on screen, so the face box is transformed by any zoom
active while the element is visible.

layout.json is the resolved geometry; edit.json stays the intent.
"""

from . import faces as facemod

W, H = 1080, 1920
SIDE = 60
TOP = 250                 # platform header / status bar
GRAPHIC_BOTTOM = 1500     # graphics stay above the bottom UI strip
CAPTION_BOTTOM = 1650     # captions may sit lower: the centre of the bottom strip stays visible
RIGHT_RAIL = (960, 1000, 1080, 1800)  # like / comment / share buttons
PREF_Y = {"upper_third": 560, "center": 960, "lower_third": 1300, "top_edge": 120}
# Positions a plan or the customer can ask for ("place"); "top" and "above_head"
# are handled separately below.
PLACE_Y = {"top": 380, "upper": 560, "middle": 960, "lower": 1300}
PLACE_X = {"left": "left", "right": "right", "centre": "center", "center": "center"}
LUMA_GRID = (27, 48)      # brightness map of the frame behind unboxed text (1 cell = 40 px)


def _brightness(luma, r):
    """Mean brightness 0..1 of the footage under rect r (from a LUMA_GRID map)."""
    gw, gh = LUMA_GRID
    cw, ch = W / gw, H / gh
    x0, x1 = max(0, int(r[0] // cw)), min(gw, int((r[0] + r[2]) // cw) + 1)
    y0, y1 = max(0, int(r[1] // ch)), min(gh, int((r[1] + r[3]) // ch) + 1)
    vals = [luma[y * gw + x] for y in range(y0, y1) for x in range(x0, x1)]
    return sum(vals) / len(vals) / 255 if vals else 0.0

# Base sizes (px) per graphic type; the renderer scales content to fit.
SIZES = {
    "sticky_notes": (600, 0), "lists": (640, 0), "emoji": (170, 170),
    "text_callouts": (900, 230), "keyword_cards": (760, 190), "cta_card": (860, 240),
    "lower_third": (700, 150), "arrows": (200, 200), "headline_bar": (860, 110),
    "profile_card": (700, 520), "calendar": (400, 450),
}


def _face_at(box, zoom):
    """Face box as it appears on screen under a zoom (scale z about focus)."""
    if not zoom:
        return box
    z, fx, fy = zoom["scale"], zoom["focus"]["x"], zoom["focus"]["y"]
    x0, y0 = (1 - 1 / z) * fx, (1 - 1 / z) * fy
    return [(box[0] - x0) * z, (box[1] - y0) * z, box[2] * z, box[3] * z]


def _px(b):
    return (b[0] * W, b[1] * H, b[2] * W, b[3] * H)


def _head(face):
    """Face box -> head incl. hair: up 55 % and sides 18 % of the face, plus
    a small chin margin. Not the neck / chest: covering those is normal."""
    x, y, w, h = face
    return (x - 0.18 * w, y - 0.55 * h, w * 1.36, h * 1.59)


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return w * h if w > 0 and h > 0 else 0.0


def screen_face(track, zooms, start, end):
    """Union of face boxes (px) between start and end, including any zoom."""
    base = facemod.box_between(track, start, end)
    rects = [_px(base)]
    for z in zooms:
        if z["start"] < end and z["end"] > start:
            rects.append(_px(_face_at(base, z)))
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def zoom_focus(track, zooms):
    """Zoom toward the face: the face centre stays put and grows."""
    out = {}
    for z in zooms:
        b = facemod.box_between(track, z["start"], z["end"])
        out[z["id"]] = {"x": round(min(0.85, max(0.15, b[0] + b[2] / 2)), 4),
                        "y": round(min(0.85, max(0.15, b[1] + b[3] / 2)), 4)}
    return out


def caption_block(cap_style):
    """Caption box: one line for word-pop / keyword styles, two otherwise;
    the line grows when emphasised words are drawn bigger."""
    size = cap_style.get("size_px") or 76
    lines = 1 if cap_style.get("style") in ("word_pop", "keyword_boxes") else 2
    grow = 1.38 if cap_style.get("emphasis") == "bigger" else 1.0
    width = 620 if cap_style.get("style") == "word_pop" else 940
    return width, int(size * 1.15 * grow + size * 1.15 * (lines - 1) + 16)


def place_captions(edit, track, zooms):
    cap = edit["captions"]
    if not cap["items"]:
        return None
    bw, bh = caption_block(cap["style"])
    face = screen_face(track, zooms, 0, edit["duration"])
    pref = PREF_Y.get(cap["style"].get("position") or "lower_third", 1300)
    best = None
    for yc in range(TOP + bh // 2, CAPTION_BOTTOM - bh // 2 + 1, 10):
        rect = ((W - bw) / 2, yc - bh / 2, bw, bh)
        cost = (_overlap(rect, face) * 1000 + _overlap(rect, _head(face)) * 30) / 1000
        cost += abs(yc - pref) * 0.05
        if best is None or cost < best[0]:
            best = (cost, yc, rect)
    cost, yc, rect = best
    moved = abs(yc - pref) > 40
    where = (cap['style'].get('position') or 'lower_third').replace('_', ' ')
    if not moved:
        why = f"{where}, clear of the face"
    elif yc > pref:
        why = f"{where}, lowered to clear the chin"
    else:
        why = f"moved up from the {where} to stay off the face"
    return {"y": yc, "rect": [round(v) for v in rect],
            "covers_face": _overlap(rect, face) > 0, "why": why}


def place_graphics(edit, track, zooms, cap_layout):
    placed, out = [], {}
    cap_rect = tuple(cap_layout["rect"]) if cap_layout else None
    # The logo is there the whole time: place it first so everything else avoids it.
    ordered = sorted(edit["graphics"], key=lambda g: 0 if g.get("role") == "logo" else 1)
    for g in ordered:
        if g["type"] == "progress_bar":
            out[g["id"]] = {"x": 0, "y": 0, "w": W, "h": 14, "scale": 1.0, "why": "top edge"}
            continue
        face = screen_face(track, zooms, g["start"], g["end"])
        head = _head(face)
        bw, bh = g.get("_size") or SIZES.get(g["type"], (600, 200))
        if g["type"] == "custom" and g.get("size"):          # a custom graphic says how big it is
            bw, bh = g["size"]
            g = dict(g, _size=(bw, bh))
        if g["type"] == "image":
            from . import library
            a = library.get(g.get("asset") or "") or {}
            iw, ih = a.get("width") or 4, a.get("height") or 3
            if g.get("role") == "logo":
                bw = g.get("size", 180)
            elif (g.get("category") or a.get("category")) in ("screenshot", "photo"):
                bw = 560
            else:
                bw = 420
            bh = bw * ih / iw
            if bh > 900:                     # very tall: limit the height
                bw, bh = bw * 900 / bh, 900
            g = dict(g, _size=(round(bw), round(bh)))
            if g.get("role") == "logo" or str(g.get("place", "")).startswith(("top_", "bottom_")):
                # a corner: the chosen one if it's clear of the face, else the nearest clear one
                corners = {"top_right": (W - SIDE - bw, TOP), "top_left": (SIDE, TOP),
                           "bottom_right": (W - SIDE - bw, GRAPHIC_BOTTOM - bh),
                           "bottom_left": (SIDE, GRAPHIC_BOTTOM - bh)}
                want = g.get("place") if g.get("place") in corners else "top_right"
                for c in [want] + [k for k in corners if k != want]:
                    r = (corners[c][0], corners[c][1], bw, bh)
                    if not _overlap(r, face):
                        break
                placed.append({"start": g["start"], "end": g["end"], "rect": r})
                out[g["id"]] = {"x": round(r[0]), "y": round(r[1]), "w": round(bw), "h": round(bh),
                                "scale": 1.0, "covers_face": _overlap(r, face) > 0,
                                "corner": c, "why": f"{c.replace('_', ' ')} corner"}
                continue
        if g["type"] == "carousel":
            # the customer's images on an orbit: sized by its options, placed like any
            # graphic (their place if they gave one, else the best spot for the footage)
            from . import carousel
            g = dict(g, _size=carousel.size_of(g), place=carousel.layout_place(g))
            bw, bh = g["_size"]
        if g["type"] == "full_overlay":
            # the customer asked for a full-screen overlay: it covers everything
            out[g["id"]] = {"x": 0, "y": 0, "w": W, "h": H, "scale": 1.0, "covers_face": True,
                            "allow_face": True, "why": "full-screen overlay (requested)"}
            continue
        if g.get("place") == "top":
            # top of the frame, centred; shrink if needed to stay off the face
            bw, bh = g.get("_size") or SIZES.get(g["type"], (600, 200))
            for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
                w, h = bw * scale, bh * scale
                r = ((W - w) / 2, TOP, w, h)
                if not _overlap(r, face):
                    break
            placed.append({"start": g["start"], "end": g["end"], "rect": r})
            out[g["id"]] = {"x": round(r[0]), "y": round(r[1]), "w": round(r[2]), "h": round(r[3]),
                            "scale": scale, "covers_face": _overlap(r, face) > 0,
                            "covers_head": _overlap(r, head) > 0, "why": "top of the frame (requested)"}
            continue
        if g.get("place") == "above_head":
            # centred over the face, just above the hairline (as close as fits)
            bw, bh = g.get("_size") or SIZES.get(g["type"], (600, 200))
            cx = face[0] + face[2] / 2
            x = min(max(SIDE, cx - bw / 2), W - SIDE - bw)
            y = max(TOP, head[1] - bh - 10)
            r = (x, y, bw, bh)
            if not _overlap(r, face):
                placed.append({"start": g["start"], "end": g["end"], "rect": r})
                out[g["id"]] = {"x": round(x), "y": round(y), "w": bw, "h": bh, "scale": 1.0,
                                "covers_face": False, "covers_head": _overlap(r, head) > 0,
                                "why": "above the head (requested)"}
                continue
        target = None
        if g.get("target") == "comment_button":
            # The comment icon sits on the right-hand rail, ~2/3 down the
            # screen: the arrow goes as close to it as the face allows.
            target = (RIGHT_RAIL[0], 1300)
        comp = g.get("comp") or {}            # the style pack's layout preference
        if comp.get("w"):
            bw = comp["w"]
        if comp.get("h"):
            bh = comp["h"]
        if g["type"] in ("sticky_notes", "lists") and comp.get("row_h"):
            # the style's own list geometry: a header, then rows that wrap
            cpr = comp.get("chars_per_row", 24)
            bh = comp.get("list_head", 40) + sum(comp["row_h"] * (1 + len(i["text"]) // cpr) * 0.82
                                                 for i in g.get("items", []))
        elif g["type"] in ("sticky_notes", "lists") and not comp.get("h"):
            # ~2 lines per item at 46 px in a 600 px note
            bh = 90 + sum(60 + 56 * (len(i["text"]) // 24) for i in g.get("items", []))
        pref_y = PREF_Y.get(comp.get("zone") or g.get("zone"), 560)
        pull = 0.01                     # the style's zone: a gentle preference
        align = comp.get("align")
        for want in str(g.get("place") or "").split():   # e.g. "lower left"
            if want in PLACE_Y:
                pref_y, pull = PLACE_Y[want], 0.08         # asked for: a firm preference
            if want in PLACE_X:
                align = PLACE_X[want]
        if align == "scatter":   # alternate sides, graphic by graphic
            align = "left" if int("".join(c for c in g["id"] if c.isdigit()) or 0) % 2 else "right"
        luma = g.get("_luma")
        def search(bw, bh):
            best = None
            scales = (1.0, 0.85, 0.72, 0.6, 0.5, 0.4) if g["type"] == "image" else (1.0, 0.85, 0.72, 0.6)
            if g["type"] == "carousel":
                # fine steps: the largest orbit that fits, so "large" never ends up smaller than "medium"
                scales = tuple(round(1 - 0.01 * i, 2) for i in range(61))
            for scale in scales:
                w, h = bw * scale, bh * scale
                xs = sorted({SIDE, (W - w) / 2, W - SIDE - w,
                             head[0] - w - 10, head[0] + head[2] + 10})
                if align == "full" and scale == 1.0:
                    xs = [0]                       # edge to edge (bold bands)
                for x in xs:
                    if (x < SIDE - 1 or x + w > W - SIDE + 1) and not (align == "full" and x == 0):
                        continue
                    for y in range(TOP, int(GRAPHIC_BOTTOM - h) + 1, 20):
                        r = (x, y, w, h)
                        # Face: never. Hair / top of head: a light preference only, so
                        # a note can tuck over the hairline instead of shrinking.
                        # (carousel cards are opaque pictures: hair behind them costs less)
                        cost = _overlap(r, face) * 1000 + _overlap(r, head) * (1 if g["type"] == "carousel" else 3)
                        if cap_rect and _overlaps_time(g, edit):
                            cost += _overlap(r, cap_rect) * 300
                        for p in placed:
                            if p["start"] < g["end"] and p["end"] > g["start"]:
                                cost += _overlap(r, p["rect"]) * 1000
                        rx, ry, rx1, ry1 = RIGHT_RAIL
                        cost += _overlap(r, (rx, ry, rx1 - rx, ry1 - ry)) * 5
                        if luma:
                            # light text with no box: a pale wall behind it is hard to
                            # read; prefer a darker, calmer part of this frame
                            cost += max(0.0, _brightness(luma, r) - 0.45) * 1500 * 1000
                        # Shrinking hurts readability on a phone: it costs about as
                        # much as covering a palm-sized patch of hair.
                        cost = cost / 1000 + (1 - scale) * 900
                        if scale < 0.72 and (g["type"] != "image"):
                            cost += 5000        # tiny text: only if every bigger spot is on the face
                        if target:
                            cost += (abs(x + w - target[0]) + abs(y + h - target[1])) * 0.03
                        elif g["type"] == "emoji" or g.get("place") == "near_subject":
                            # beside the head at eye level reads best
                            cost += abs(y + h / 2 - (face[1] + face[3] * 0.35)) * 0.02
                        else:
                            cost += abs(y + h / 2 - pref_y) * pull
                        if align in ("left", "right", "center"):
                            want_x = {"left": SIDE, "right": W - SIDE - w, "center": (W - w) / 2}[align]
                            # asked for: holds unless the face is in the way (hair is not a reason)
                            cost += abs(x - want_x) * (0.3 if g.get("place") else 0.004)
                        # The face is a hard rule: any clear position beats any
                        # position on the face, whatever else it costs.
                        key = (_overlap(r, face) > 0, cost)
                        if best is None or key < best[0]:
                            best = (key, r, scale)
            return best

        best = search(bw, bh)
        list_mode = None
        if comp.get("row_h") and g["type"] in ("sticky_notes", "lists") and best[2] < 0.85:
            # Readability rule: a list that would have to shrink shows one item
            # at a time, full size, each as it's said.
            cpr = comp.get("chars_per_row", 24)
            one = comp.get("list_head", 40) + max(comp["row_h"] * (1 + len(i["text"]) // cpr) * 0.82
                                                  for i in g.get("items", [{"text": ""}]))
            seq = search(bw, one)
            if seq[2] > best[2]:
                best, list_mode = seq, "sequence"
        cost, r, scale = best
        placed.append({"start": g["start"], "end": g["end"], "rect": r})
        out[g["id"]] = {"x": round(r[0]), "y": round(r[1]), "w": round(r[2]), "h": round(r[3]),
                        "scale": scale, "covers_face": _overlap(r, face) > 0,
                        "covers_head": _overlap(r, head) > 0}
        if luma:
            out[g["id"]]["backdrop"] = round(_brightness(luma, r), 2)   # 0 dark .. 1 bright
        if list_mode:
            out[g["id"]]["list_mode"] = list_mode
    for g in edit["graphics"]:
        if g["type"] == "carousel" and g["id"] in out:
            # the orbit for the size it was given (shared with the drawing code)
            from . import carousel
            out[g["id"]]["orbit"] = carousel.geometry(g, out[g["id"]]["w"])
    return out


def _overlaps_time(g, edit):
    return any(c["start"] < g["end"] and c["end"] > g["start"] for c in edit["captions"]["items"])


def build(edit, track):
    focus = zoom_focus(track, edit["zooms"])
    zooms = [dict(z, focus=focus[z["id"]]) for z in edit["zooms"]]
    cap = place_captions(edit, track, zooms)
    return {"face_source": track["source"], "zoom_focus": focus, "captions": cap,
            "graphics": place_graphics(edit, track, zooms, cap)}
