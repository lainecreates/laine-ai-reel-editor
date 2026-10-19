"""Stage 5: reference reels - likes/dislikes, inspiration only, never copied."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, config, creative, library, reference_style  # noqa: E402
from test_library import Env  # noqa: E402
from test_creative import W, DUR, good  # noqa: E402

VISUAL = {"available": True,
          "captions": {"present": True, "position": "upper_third", "words_at_a_time": 1, "changes_per_second": 1.9,
                       "style_guess": "word_pop", "case": "upper", "size": "large"},
          "graphics": {"appearances": 9, "per_minute": 12.0, "typical_position": "center", "upper_case": 1.0, "on_boxes": 1.0},
          "zooms": {"face_tracked": True, "punch_ins": 8, "slow_pushes": 1, "per_minute": 15.0, "kind": "punchy"},
          "colour": {"mood": "bright, saturated, warm"},
          "seen_text": ["stop posting without a plan", "link in bio", "my morning routine for creators"]}
LIKES = {"use": ["captions", "animation"], "avoid": ["graphics"],
         "notes": "I love the captions and transitions, but not the graphics"}


class Prefs(unittest.TestCase):

    def test_parts_and_validation(self):
        v = reference_style.validate_prefs(LIKES)
        self.assertEqual(v["use"], ["captions", "animation"])
        with self.assertRaises(ValueError):
            reference_style.validate_prefs({"use": ["vibes"]})
        self.assertEqual(reference_style.validate_prefs({"use": ["zooms"], "avoid": ["zooms"]})["avoid"], [])

    def test_proposals_only_for_liked_parts(self):
        s = reference_style.inspired_settings(VISUAL, {"suggests": {"pacing": "fast"}}, LIKES)["settings"]
        self.assertEqual((s["caption_style"], s["caption_position"], s["caption_case"]), ("word_pop", "upper_third", "upper"))
        self.assertEqual((s["zoom_style"], s["zoom_frequency"]), ("punchy", "frequent"))   # "transitions"
        self.assertNotIn("graphics_density", s)     # they don't like the graphics
        self.assertNotIn("pacing", s)               # they didn't mention pacing
        self.assertEqual(reference_style.inspired_settings(VISUAL, {}, {})["settings"], {})


class Inspiration(Env):

    def setUp(self):
        super().setUp()
        reference_style.save(VISUAL)

    def test_planner_sees_only_liked_parts_and_the_rule(self):
        brand.save_settings({"reference_prefs": LIKES}, "default")
        ref = creative.context(W, DUR, brand.effective())["reference"]
        self.assertEqual(sorted(ref["traits"]), ["animation", "captions"])
        self.assertEqual(ref["avoid"], ["graphics"])
        self.assertIn("Never reuse", ref["rule"])
        self.assertIn("not the graphics", ref["their_words"])

    def test_reference_never_changes_their_settings_by_itself(self):
        before = json.dumps(brand.effective()["captions"], sort_keys=True)
        brand.save_settings({"reference_prefs": LIKES}, "default")
        self.assertEqual(json.dumps(brand.effective()["captions"], sort_keys=True), before)
        self.assertTrue(any("inspiration only" in l for l in brand.explain(brand.effective())))

    def test_plan_reusing_reference_words_is_rejected(self):
        p = brand.compile_profile(dict(brand.load_progress()["answers"], graphics_elements=["text_callouts", "lists", "cta_card"],
                                       headline="opening_hook"))
        words = [{"text": t, "start": i * .4, "end": i * .4 + .3} for i, t in
                 enumerate("Here are three tips. Stop posting without a plan. Thanks.".split())]
        b = {"version": 1, "summary": "tips", "key_words": [], "moments": [
            {"intent": "hook", "from": 0, "to": 3, "text": "Three tips", "why": "promise"},
            {"intent": "key_phrase" if False else "stat", "from": 4, "to": 8,
             "text": "Stop posting without a plan", "why": "the point"}]}
        try:
            creative.validate(b, words, p, 5.0)
            self.fail("should be rejected")
        except creative.BriefError as e:
            self.assertTrue(any("reference reel" in x for x in e.problems), e.problems)

    def test_library_refuses_reference_files(self):
        ref_dir = config.brand_dir() / "reference"
        (ref_dir / "frame.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
        with self.assertRaises(library.LibraryError) as e:
            library.add_file(ref_dir / "frame.png")
        self.assertIn("never reused", str(e.exception))


if __name__ == "__main__":
    unittest.main()
