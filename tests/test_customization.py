"""Stage 4: onboarding invitations, everyday-language preferences, colour roles."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, conformance, creative, overlay, styles  # noqa: E402
from laine_reel.project import write_json  # noqa: E402
from test_library import Env  # noqa: E402

WORDS = "hot pink headlines, clean captions, no outlines or glows"
PREFS = {"color_roles": {"headline": "#FF1493"},
         "creative_rules": {"flags": ["no_outlines", "no_glow"]},
         "style": {"direction": WORDS}}


class Onboarding(unittest.TestCase):

    def test_new_customers_are_invited_to_give_exact_brand_assets(self):
        q = brand.BY_ID
        self.assertIn("HEX", q["colors"]["prompt"])
        self.assertIn("help me choose", q["colors"]["help"])
        self.assertIn("TTF/OTF", q["fonts"]["help"])
        self.assertIn("logo", q["brand_files"]["prompt"])
        self.assertIn("own words", q["style_direction"]["prompt"])
        self.assertEqual(brand.applicable({})[0]["id"], "style_pack")

    def test_starter_palettes_for_every_style(self):
        s = brand.suggestions()
        self.assertEqual(set(s), {"luxe", "playful", "magazine", "minimal", "bold", "energetic"})
        for pid, v in s.items():
            self.assertEqual(len(v["palettes"]), 3, pid)
            self.assertTrue(all(c.startswith("#") and len(c) == 7 for p in v["palettes"] for c in p), pid)


class Preferences(Env):

    def reel(self, name="r"):
        r = self.dir / name
        r.mkdir()
        write_json(r / "reel.json", {"slug": name})
        return r

    def test_everyday_words_become_exact_settings_for_future_reels(self):
        brand.save_settings(PREFS, "default")
        p = brand.effective()
        self.assertEqual(p["colors"]["headline"], "#FF1493")
        d = styles.decorations_on(styles.resolve(p))
        self.assertFalse(d["caption_outline"] or d["caption_glow"])
        self.assertEqual(p["style"]["direction"], WORDS)
        self.assertEqual(p["style"]["pack"], "classic")          # the rest of the style kept
        text = "\n".join(brand.explain(p))
        self.assertIn("#FF1493", text)
        self.assertIn("no outlines", text)
        self.assertIn(WORDS, text)

    def test_one_reel_only_leaves_defaults_alone(self):
        r = self.reel()
        before = json.dumps(brand.effective()["colors"], sort_keys=True)
        brand.save_settings(PREFS, "reel", r)
        self.assertEqual(brand.effective(r)["colors"]["headline"], "#FF1493")
        self.assertEqual(json.dumps(brand.effective()["colors"], sort_keys=True), before)

    def test_partial_changes_merge(self):
        brand.save_settings({"style": {"pack": "magazine"}}, "default")
        brand.save_settings({"style": {"direction": "calm and editorial"}}, "default")
        st = brand.effective()["style"]
        self.assertEqual((st["pack"], st["direction"]), ("magazine", "calm and editorial"))
        brand.save_settings({"color_roles": {"headline": "#FF1493"}}, "default")
        brand.save_settings({"color_roles": {"key_words": "#C9A227"}}, "default")
        c = brand.effective()["colors"]
        self.assertEqual((c["headline"], c["caption_keyword"]), ("#FF1493", "#C9A227"))

    def test_colour_names_and_bad_codes(self):
        v = brand._validate_extra("color_roles", {"headline": "ff1493", "captions": "white"})
        self.assertEqual(v["headline"], "#FF1493")
        self.assertTrue(v["captions"].startswith("#"))
        with self.assertRaises(brand.AnswerError):
            brand._validate_extra("color_roles", {"sparkles": "#FFFFFF"})

    def test_headline_colour_reaches_every_style_and_is_checked(self):
        for pack in ("classic", "bold", "playful"):
            p = brand.compile_profile(dict(brand.load_progress()["answers"], style={"pack": pack},
                                           color_roles={"headline": "#FF1493"}))
            page = overlay.page_data({"graphics": [], "captions": {"style": {}, "items": []}},
                                     {"graphics": {}, "captions": {"y": 1300}}, p, 30)
            self.assertEqual(page["colors"]["headline"], "#FF1493", pack)
            self.assertNotEqual(page["colors"]["primary"], "#FF1493", pack)   # other things keep the palette
            page["colors"]["headline"] = page["colors"]["primary"]
            probs = conformance.check({"captions": {"items": [], "style": {}}, "graphics": [], "sfx": []}, page,
                                      dict(p, captions=dict(p["captions"], enabled=False)))
            self.assertTrue(any("headline" in x for x in probs), pack)

    def test_classic_headline_unchanged_without_a_role(self):
        p = brand.compile_profile(brand.load_progress()["answers"])
        self.assertEqual(p["colors"]["headline"], p["colors"]["primary"])
        p.pop("style"); p["colors"].pop("headline")                      # a profile from before roles
        page = overlay.page_data({"graphics": [], "captions": {"style": {}, "items": []}},
                                 {"graphics": {}, "captions": {"y": 1300}}, p, 30)
        self.assertEqual(page["colors"]["headline"], p["colors"]["primary"])

    def test_planner_context_carries_their_words_and_rules(self):
        brand.save_settings(PREFS, "default")
        ctx = creative.context([{"text": "Hello.", "start": 0, "end": .4}], 1.0, brand.effective())
        self.assertEqual(ctx["style"]["direction"], WORDS)
        self.assertIn("no_outlines", ctx["customer_rules"]["flags"])
        self.assertTrue(any("#FF1493" in l for l in ctx["settings_readback"]))


if __name__ == "__main__":
    unittest.main()


class ExplicitCaptionChoicesStay(unittest.TestCase):
    """Picking a caption style in Brand settings keeps it, even with a style chosen."""

    def test_reel_caption_style_is_kept(self):
        import tempfile, os, shutil
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        old = {k: os.environ.get(k) for k in ("LAINE_BRAND_DIR", "LAINE_LIBRARY_DIR")}
        os.environ["LAINE_BRAND_DIR"], os.environ["LAINE_LIBRARY_DIR"] = str(d / "brand"), str(d / "lib")
        try:
            from fixture_brand import write_test_brand
            write_test_brand(d / "brand")
            reel = d / "reel"; reel.mkdir()
            brand.save_settings({"style": {"pack": "playful"}}, "reel", reel)
            brand.save_settings({"caption_style": "phrase_lines"}, "reel", reel)
            p = brand.effective(reel)
            self.assertEqual(p["captions"]["style"], "phrase_lines")
            self.assertIn("caption_style", brand.reel_answers(reel)["style"]["keep"])
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            shutil.rmtree(d)
