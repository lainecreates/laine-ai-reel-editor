"""Spinning image carousel (version 1): a customer's own images orbiting on a
circular path with depth, added to ONE reel on request. Never a default.

A carousel is a requested graphic in edit.overrides.json (add.graphics):

  {"type": "carousel", "assets": ["photo-1", "photo-2", "shot-3"],
   "start": 12.4, "end": 17.4, "src_start": 31.2,
   "place": "auto | top | upper | middle | lower | left | right | top_left | top_right | near_subject",
   "size": "small | medium | large", "speed": "slow | normal | fast",
   "direction": "clockwise | counterclockwise", "motion": "subtle | noticeable"}

Images come from the asset library (photos, screenshots, product images, 2-8 of
them). The orbit is computed per frame from time alone, so every render of the
same reel is identical. Layout places it like any graphic (face rule, safe
zones, best spot for the footage unless a place was asked for); the review
page can retime, restyle or remove it.
"""

from . import library

PLACES = ["auto", "top", "upper", "middle", "lower", "left", "right", "top_left", "top_right",
          "near_subject"]
SIZES = {"small": 520, "medium": 720, "large": 940}            # orbit width on the 1080 canvas
SPEEDS = {"slow": 10.0, "normal": 7.0, "fast": 4.5}            # seconds per full turn (fast is capped:
                                                               # quicker would flicker at 30 fps)
DIRECTIONS = ["clockwise", "counterclockwise"]
MOTIONS = {
    # tilt: how far the far side of the ring rises (x orbit width); back: size of a card at the back;
    # turn: how much a card turns as it passes the sides (deg); dim: brightness at the back
    "subtle": {"tilt": 0.10, "back": 0.70, "turn": 16, "dim": 0.70},
    "noticeable": {"tilt": 0.17, "back": 0.52, "turn": 30, "dim": 0.50},
}
DEFAULTS = {"place": "auto", "size": "medium", "speed": "normal", "direction": "clockwise",
            "motion": "subtle"}
MIN_IMAGES, MAX_IMAGES = 2, 8
MIN_SECONDS, MAX_SECONDS = 2.0, 15.0


def options(g):
    return {k: g.get(k) or v for k, v in DEFAULTS.items()}


def problems(g):
    """Everything wrong with a carousel request, in plain words ([] = fine)."""
    p = []
    assets = g.get("assets") or []
    if not MIN_IMAGES <= len(assets) <= MAX_IMAGES:
        p.append(f"a carousel needs {MIN_IMAGES}-{MAX_IMAGES} images (got {len(assets)})")
    for a in assets:
        info = library.get(a)
        if not info:
            p.append(f"image '{a}' isn't in the asset library")
        elif info.get("kind") != "image":
            p.append(f"'{a}' is a {info.get('kind')}, not an image (version 1 carousels are images only)")
        elif not library.path_of(a):
            p.append(f"image '{a}' is missing from the asset library folder")
    o = options(g)
    for key, allowed in (("place", PLACES), ("size", SIZES), ("speed", SPEEDS),
                         ("direction", DIRECTIONS), ("motion", MOTIONS)):
        if o[key] not in allowed:
            p.append(f"{key} '{o[key]}' must be one of: {', '.join(allowed)}")
    d = float(g.get("end", 0)) - float(g.get("start", 0))
    if not MIN_SECONDS <= d <= MAX_SECONDS:
        p.append(f"a carousel shows for {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} s (asked for {d:.1f} s)")
    return p


def ratios(g):
    """Width / height of each image (cards keep their image's shape)."""
    out = []
    for a in g.get("assets") or []:
        w, h = library.display_size(library.get(a) or {})      # phone photos: upright size
        out.append(round(w / h, 4))
    return out


def geometry(g, width):
    """Orbit geometry for an orbit `width` px wide: card box, radius, ring tilt,
    and the overall height the layout reserves. Shared by layout and drawing."""
    o = options(g)
    m = MOTIONS[o["motion"]]
    n = max(MIN_IMAGES, len(g.get("assets") or []))
    card = width * (0.40 if n <= 3 else 0.34 if n <= 5 else 0.29)
    card_h = card * 1.25                        # tallest card (portrait screenshots fit inside)
    radius = (width - card) / 2
    tilt = width * m["tilt"]
    return {"card": round(card, 1), "card_h": round(card_h, 1), "radius": round(radius, 1),
            "tilt": round(tilt, 1), "height": round(card_h + 2 * tilt, 1),
            "back": m["back"], "turn": m["turn"], "dim": m["dim"],
            "period": SPEEDS[o["speed"]], "dir": 1 if o["direction"] == "clockwise" else -1}


def size_of(g):
    w = SIZES[options(g)["size"]]
    return w, geometry(g, w)["height"]


def layout_place(g):
    """The carousel's place in the words layout.py understands."""
    p = options(g)["place"]
    return {"auto": None, "top_left": "top left", "top_right": "top right"}.get(p, p)


def request(reel, images, at, duration=5.0, **opts):
    """Add a carousel to this reel (edit.overrides.json add.graphics). `at` is a
    time on the reel as it is now; it's stored against the speech too, so it
    stays put if the reel is re-cut. Returns (graphic, problems)."""
    from .project import read_json, write_json
    from .review import output_to_source
    keep = read_json(reel.path("edl.json"))["keep"]
    ids = []
    for x in images:
        if library.get(x):
            ids.append(x)
        else:      # a name, as the customer calls it
            hit = [a["id"] for a in library.items("image") if a.get("name", "").lower() == str(x).lower()]
            ids.append(hit[0] if hit else x)
    g = {"type": "carousel", "assets": ids, "start": round(float(at), 3),
         "end": round(float(at) + float(duration), 3), "src_start": output_to_source(float(at), keep),
         "reason": opts.pop("reason", "requested by the customer")}
    for k in DEFAULTS:
        if opts.get(k):
            g[k] = opts[k]
    p = problems(g)
    if p:
        return g, p
    opath = reel.path("edit.overrides.json")
    ov = read_json(opath) if opath.exists() else {}
    ov.setdefault("add", {}).setdefault("graphics", []).append(g)
    write_json(opath, ov)
    return g, []
