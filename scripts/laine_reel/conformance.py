"""Does what we're about to render follow the customer's saved brand profile?

Checked right before compositing, against the exact data the overlay page
is drawn from. Any mismatch fails the render's `follows_brand_profile`
check, with a plain-language list of what's wrong.
"""

from . import config, overlay

HEADLINE_TYPES = {"opening_hook": {"text_callouts"}, "persistent": {"headline_bar"},
                  "both": {"text_callouts", "headline_bar"}, "none": set()}


def check(edit, page, brand):
    """Return a list of problems (empty = follows the profile)."""
    problems = []
    cap_b = brand.get("captions", {})
    cap_e = edit["captions"]
    if cap_b.get("enabled") != bool(cap_e["items"]):
        problems.append(f"captions {'missing' if cap_b.get('enabled') else 'present but turned off'}")
    if cap_e["items"]:
        for k in ("style", "position", "animation", "emphasis", "case", "size_px"):
            if cap_e["style"].get(k) != cap_b.get(k):
                problems.append(f"caption {k}: profile '{cap_b.get(k)}', plan '{cap_e['style'].get(k)}'")
    from . import overlay, styles
    st = styles.resolve(brand)
    want_o = overlay._outline(brand, st)
    got_o = page.get("captionOutline") or {}
    want_d = styles.decorations_on(st)
    if page.get("decorations") is not None and page["decorations"] != want_d:
        bad = [d for d in want_d if page["decorations"].get(d) != want_d[d]]
        problems.append("decorations differ from the style and rules: " + ", ".join(bad))
    for g in edit.get("graphics", []):
        if styles.intent_for(g["type"]) in st["blocked_intents"] and g.get("role") != "logo":
            problems.append(f"{g['id']} ({g['type']}) breaks a creative rule")
    if st["sound_off"] and edit.get("sfx"):
        problems.append("sound effects present but the creative rules say none")
    for k in ("enabled", "color", "width_em", "opacity"):
        if got_o.get(k) != want_o.get(k):
            problems.append(f"caption outline {k}: profile {want_o.get(k)}, render {got_o.get(k)}")
    colors = brand.get("colors", {})
    pc = page["colors"]
    for page_key, brand_key in (("primary", "primary"), ("accent", "accent"),
                                ("captionText", "caption_text"),
                                ("captionKeyword", "caption_keyword"), ("headline", "headline")):
        want = colors.get(brand_key) or (colors.get("primary") if brand_key == "headline" else None)
        if pc.get(page_key) != want:
            problems.append(f"colour {brand_key}: profile {want}, "
                            f"render {pc.get(page_key)}")

    hstyle = brand.get("headline", {}).get("style", "none")
    allowed = set(brand.get("graphics", {}).get("elements", [])) | HEADLINE_TYPES.get(hstyle, set())
    if brand.get("logo"):
        allowed.add("image")   # their logo watermark
    for s in edit.get("sfx", []):
        if s.get("missing_custom"):
            problems.append(f"your sound '{s['kind']}' ({s['event']}) is missing from the "
                            "library; no default sound was used in its place")
    for g in edit["graphics"]:
        if g.get("source") == "review":
            continue  # requested by the customer in review
        if g["type"] not in allowed:
            problems.append(f"{g['id']} is a {g['type'].replace('_', ' ')}, which isn't in the profile")
    has_headline = {g["type"] for g in edit["graphics"] if g.get("role") == "headline"}
    if cap_e["items"] and has_headline != HEADLINE_TYPES.get(hstyle, set()):
        problems.append(f"headline: profile '{hstyle}', plan has "
                        f"{sorted(has_headline) or 'none'}")
    if any(g.get("draft") for g in edit["graphics"] if g.get("role") == "headline"):
        problems.append("headline text is still the automatic draft (needs Claude's rewrite "
                        "in edit.overrides.json)")

    fonts = brand.get("fonts", {})
    if page.get("stickyFont") != brand.get("graphics", {}).get("sticky_font", "hand"):
        problems.append("sticky-note font differs from the profile")
    for role in ("headline", "body"):
        stack = overlay.font_stack(fonts.get(role))
        if not stack.startswith(f'"{fonts.get(role)}"'):
            problems.append(f"{role} font is not {fonts.get(role)}")
    return problems


def check_fonts(report, brand, edit=None):
    """report = fonts.json from render_overlay.mjs: the font stack Chrome
    computed for every caption / graphic element. Each must start with the
    brand font for its role (sticky notes: the profile's sticky font)."""
    fonts = brand.get("fonts", {})
    sticky = brand.get("graphics", {}).get("sticky_font", "hand")
    want = {"caption": fonts.get("body"), "headline": fonts.get("headline"),
            "body": fonts.get("body"), "graphics": fonts.get("graphics") or fonts.get("headline")}
    custom = {g["id"]: (g.get("style") or {}).get("custom_font")
              for g in (edit or {}).get("graphics", [])}
    names = {"headline": fonts.get("headline"), "body": fonts.get("body"),
             "hand": overlay.HAND.split(",")[0].strip('" '),
             "bulky": overlay.BULKY.split(",")[0].strip('" ')}
    problems = []
    from . import styles
    st = styles.resolve(brand)
    pack_fonts = None if st["legacy"] else (st["aspects"]["captions"].get("treatment") or {}).get("font", "body")
    own = {f for f in (fonts.get("headline"), fonts.get("body"), fonts.get("graphics")) if f}
    for el in report:
        role = el["role"]
        if role == "emoji":
            continue
        if custom.get(el["id"]):
            family = el["family"].split(",")[0].strip().strip('"\'')
            if family != names[custom[el["id"]]]:
                problems.append(f"{el['id']} should use the {custom[el['id']]} font chosen in review")
            continue
        family = el["family"].split(",")[0].strip().strip('"\'')
        if pack_fonts is not None:
            # new styles: every element in one of the customer's own fonts, and
            # captions in the font role the style declares
            if role == "caption":
                exp = fonts.get(pack_fonts) or fonts.get("body")
                if family != exp:
                    problems.append(f"{el['id']} (caption) is drawn in '{family}', expected '{exp}'")
            elif family not in own:
                problems.append(f"{el['id']} ({role}) is drawn in '{family}', not one of the brand's fonts "
                                f"({', '.join(sorted(own))})")
            continue
        if role == "sticky":
            expected = {"hand": overlay.HAND.split(",")[0].strip('" '),
                        "body": fonts.get("body"), "headline": fonts.get("headline")}[sticky]
        else:
            expected = want.get(role)
        if expected and family != expected:
            problems.append(f"{el['id']} ({role}) is drawn in '{family}', expected '{expected}'")
    return problems


def font_warnings(brand):
    """Brand fonts that aren't on this computer (a stand-in will be drawn)."""
    out = []
    fonts = brand.get("fonts", {})
    fonts_dir = config.ASSETS_DIR / "fonts"
    for role in ("headline", "body"):
        name = fonts.get(role)
        if not name or fonts.get(f"{role}_file"):
            continue
        key = name.lower().replace(" ", "")
        from . import fontlib
        in_assets = bool(fontlib.find(name)) or (fonts_dir.is_dir() and any(
            p.stem.lower().replace(" ", "").replace("-", "").startswith(key)
            for p in fonts_dir.iterdir()))
        if not in_assets:
            standin = overlay.FALLBACK.get(name.lower(), overlay.SANS).split(",")[0].strip('" ')
            out.append(f"{name} ({role}) isn't installed: drawn in {standin} instead. "
                       f"Add its .ttf to assets/fonts/ to use the real font.")
    return out
