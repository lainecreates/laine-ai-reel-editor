"""Stage 2: the six style packs."""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, overlay, planner, styles  # noqa: E402
from test_library import Env  # noqa: E402

SIX = ["luxe", "playful", "magazine", "minimal", "bold", "energetic"]
CAPTION_ANIMS = {"none", "pop", "fade", "slide_up", "typewriter"}
EMPHASIS = {"bigger", "accent_color", "accent_box", "none", "italic", "underline", "highlight_block",
            "color_fill", "bolder", "color_tilt"}


def motion_kinds():
    return set(re.findall(r"^\s{4}(\w+):\s*p\b", (ROOT / "tools" / "motion.js").read_text(), re.M))


class PackFiles(unittest.TestCase):

    def test_all_six_exist_with_every_aspect(self):
        ids = {p["id"] for p in styles.list_packs()}
        self.assertTrue(set(SIX) <= ids and "classic" in ids)
        for pid in SIX:
            a = styles.load_pack(pid)["aspects"]
            for k in ("captions", "components", "decorations", "composition", "zoom", "sound"):
                self.assertTrue(a.get(k), f"{pid} missing {k}")

    def test_every_promised_component_is_drawn(self):
        for pid in SIX:
            js = (ROOT / "styles" / pid / "1.0.0" / "components.js").read_text()
            drawn = set(re.findall(r"reg\('(\w+)'", js))
            promised = {c.split(".", 1)[1] for c in styles.load_pack(pid)["aspects"]["components"]["by_intent"].values()}
            self.assertEqual(promised - drawn, set(), pid)

    def test_no_hardcoded_brand_colours_in_components(self):
        # neutrals (white/ink) are allowed; customer colours must come from X.C
        for pid in SIX:
            js = (ROOT / "styles" / pid / "1.0.0" / "components.js").read_text()
            hexes = set(h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", js))
            self.assertLessEqual(hexes, {"#FFFFFF", "#111111", "#1D1D1F", "#FFD400"}, pid)

    def test_caption_choices_and_motion_exist(self):
        kinds = motion_kinds() | CAPTION_ANIMS
        for pid in SIX:
            rec = styles.load_pack(pid)["aspects"]["captions"]["recommended"]
            self.assertIn(rec["animation"], kinds, pid)
            self.assertIn(rec["emphasis"], EMPHASIS, pid)
            self.assertIn(rec["style"], ("word_pop", "phrase_lines", "karaoke", "keyword_boxes"), pid)

    def test_outlines_and_glow_never_forced(self):
        for pid in SIX:
            d = styles.load_pack(pid)["aspects"]["decorations"]
            self.assertFalse(d["caption_outline"], pid)
            self.assertFalse(d["caption_glow"], pid)

    def test_styles_really_differ_in_their_definitions(self):
        sig = {}
        for pid in SIX:
            a = styles.load_pack(pid)["aspects"]
            sig[pid] = (json.dumps(a["captions"]["recommended"], sort_keys=True), json.dumps(a["zoom"], sort_keys=True),
                        json.dumps(sorted(a["sound"]["recipes"])), json.dumps(a["composition"]["default"], sort_keys=True))
        for i, a in enumerate(SIX):
            for b in SIX[i + 1:]:
                same = sum(1 for x, y in zip(sig[a], sig[b]) if x == y)
                self.assertLessEqual(same, 1, f"{a} and {b} share too much")


class ChoosingAStyle(Env):

    def prof(self, **a):
        return brand.compile_profile(dict(brand.load_progress()["answers"], **a))

    def test_style_applies_its_captions_and_zooms(self):
        p = self.prof(style={"pack": "bold"})
        self.assertEqual((p["captions"]["style"], p["captions"]["emphasis"]), ("word_pop", "highlight_block"))
        self.assertEqual(p["zooms"]["scale_max"], 1.2)

    def test_customer_can_keep_their_own(self):
        base = self.prof()
        p = self.prof(style={"pack": "bold", "keep": ["caption_style", "zooms"]})
        self.assertEqual(p["captions"]["style"], base["captions"]["style"])
        self.assertEqual(p["zooms"], base["zooms"])
        self.assertEqual(p["captions"]["emphasis"], "highlight_block")   # not kept: the style's

    def test_colours_fonts_and_personal_caption_settings_stay(self):
        base = self.prof()
        for pid in SIX:
            p = self.prof(style={"pack": pid})
            self.assertEqual(p["colors"], base["colors"], pid)
            self.assertEqual(p["fonts"], base["fonts"], pid)
            for k in ("position", "size", "case", "color"):
                self.assertEqual(p["captions"][k], base["captions"][k], f"{pid} {k}")

    def test_classic_profile_unchanged_by_stage_2(self):
        a, b = self.prof(), self.prof(style={"pack": "classic"})
        for k in ("captions", "zooms", "sfx", "colors"):
            self.assertEqual(a[k], b[k])

    def test_customer_rules_still_win(self):
        p = self.prof(style={"pack": "playful"}, creative_rules={"flags": ["no_boxes", "no_shadows"]})
        d = styles.decorations_on(styles.resolve(p))
        self.assertFalse(d["graphic_box"] or d["graphic_shadow"] or d["emoji_shadow"])
        self.assertFalse(d["graphic_border"])       # "no boxes" covers sticker borders too
        self.assertTrue(d["caption_shadow"] is False)  # "no shadows" covers captions

    def test_plan_uses_components_layout_and_sounds(self):
        p = self.prof(style={"pack": "magazine"}, graphics_elements=["text_callouts", "emoji", "lists"],
                      sfx="playful", headline="opening_hook")
        words = [{"text": t, "start": i * .4, "end": i * .4 + .3} for i, t in enumerate(
            "This is my secret. It costs 500 dollars and my camera matters. Comment GUIDE below.".split())]
        plan = planner.plan(words, 9.0, [], p, overrides={"add": {"graphics": [
            {"type": "keyword_cards", "start": 2.0, "end": 4.0, "text": "Added in review"}]}})
        comps = {g["component"] for g in plan["graphics"]}
        self.assertIn("magazine.hook", comps)
        self.assertTrue(all(c.startswith("magazine.") for c in comps if c))
        self.assertTrue(all(g.get("comp", {}).get("align") == "left" for g in plan["graphics"]
                            if g.get("component") and g["intent"] not in ("pointer",)))
        files = [Path(s["file"]).name for s in plan["sfx"] if s.get("file")]
        self.assertTrue(files and all(re.match(r"(page|pen|tick)-\d\.wav", f) for f in files), files)

    def test_page_loads_the_style_components(self):
        p = self.prof(style={"pack": "luxe", "mix": [{"pack": "energetic", "aspects": ["captions"]}]})
        js = overlay._component_js(p)
        self.assertIn("COMPONENTS['luxe.'", js)
        self.assertIn("COMPONENTS['energetic.'", js)
        self.assertNotIn("COMPONENTS['bold.'", js)


if __name__ == "__main__":
    unittest.main()
