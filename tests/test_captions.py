"""Caption outline setting and caption colours (Phase A)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from laine_reel import brand, conformance, overlay  # noqa: E402
from laine_reel.project import write_json  # noqa: E402
from test_library import Env  # noqa: E402


class Outline(Env):

    def test_default_is_the_old_look(self):
        o = brand.caption_outline({})
        self.assertEqual((o["enabled"], o["color"], o["width_em"], o["opacity"]), (True, "#000000", 0.16, 0.82))

    def test_profile_carries_outline(self):
        answers = dict(brand.load_progress()["answers"],
                       caption_outline={"enabled": True, "color": "#ffffff", "thickness": "thin", "opacity": 0.5})
        p = brand.compile_profile(answers)
        self.assertEqual(p["captions"]["outline"]["width_em"], 0.06)
        self.assertEqual(p["colors"]["caption_outline"], "#ffffff")

    def test_validation(self):
        v = brand._validate_extra("caption_outline", {"enabled": False})
        self.assertEqual(v["enabled"], False)
        self.assertEqual(brand._validate_extra("caption_outline", {"opacity": 7})["opacity"], 1.0)
        self.assertEqual(brand._validate_extra("caption_outline", {"color": "#00e5ff"})["color"], "#00E5FF")
        for bad in ({"color": "red"}, {"thickness": "huge"}, {"enabled": "yes"}, {"opacity": "lots"}):
            with self.assertRaises(brand.AnswerError):
                brand._validate_extra("caption_outline", bad)

    def test_reel_only_and_defaults(self):
        r = self.dir / "reel"
        r.mkdir()
        write_json(r / "reel.json", {"slug": "r"})
        brand.save_settings({"caption_outline": {"enabled": False}}, "reel", r)
        self.assertFalse(brand.effective(r)["captions"]["outline"]["enabled"])
        self.assertTrue(brand.effective()["captions"]["outline"]["enabled"])     # saved defaults untouched
        brand.save_settings({"caption_outline": {"thickness": "medium"}}, "default")
        self.assertEqual(brand.effective()["captions"]["outline"]["width_em"], 0.10)
        self.assertEqual([d["id"] for d in brand.history()[0]["differs_from_now"]], ["caption_outline"])

    def test_render_page_follows_outline_and_check_catches_mismatch(self):
        prof = brand.compile_profile(dict(brand.load_progress()["answers"],
                                          caption_outline={"enabled": False}))
        page = {"colors": {"primary": prof["colors"]["primary"], "accent": prof["colors"]["accent"],
                           "captionText": prof["colors"]["caption_text"],
                           "captionKeyword": prof["colors"]["caption_keyword"],
                           "headline": prof["colors"]["headline"]},
                "captionOutline": overlay._outline(prof),
                "stickyFont": prof.get("graphics", {}).get("sticky_font", "hand")}
        edit = {"captions": {"items": [], "style": {}}, "graphics": [], "sfx": []}
        prof["captions"]["enabled"] = False
        self.assertEqual(conformance.check(edit, page, prof), [])
        page["captionOutline"] = dict(page["captionOutline"], enabled=True)
        self.assertTrue(any("outline" in p for p in conformance.check(edit, page, prof)))

    def test_old_profiles_without_outline_render_as_before(self):
        old = brand.compile_profile(brand.load_progress()["answers"])
        old["captions"].pop("outline")
        self.assertEqual(overlay._outline(old), {"enabled": True, "color": "#000000",
                                                 "width_em": 0.16, "opacity": 0.82})

    def test_page_has_no_hardcoded_outline(self):
        self.assertNotIn("text-stroke: 0.16em", overlay.TEMPLATE)
        self.assertIn("capTiming", overlay.TEMPLATE)


if __name__ == "__main__":
    unittest.main()
