"""Composition: placement adapts to the footage, the plan / customer can choose a
spot and a backing, the face itself is protected, hair is not off-limits, and
text moves before it shrinks."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, creative, layout, planner  # noqa: E402
from test_creative import DUR, W, good  # noqa: E402
from test_library import Env  # noqa: E402
from test_render import edit, track  # noqa: E402

HIGH_FACE = [0.30, 0.16, 0.40, 0.20]     # person framed high: face top at ~300 px


def card(**kw):
    g = {"id": "g1", "type": "keyword_cards", "text": "3 tips for better videos", "start": 0.5, "end": 3.0,
         "zone": "upper_third", "role": "headline"}
    g.update(kw)
    return g


def face_px(box):
    return layout._px(box)


class Placement(unittest.TestCase):

    def place(self, g, box=None):
        return layout.build(edit(captions=False, graphics=[g]), track(box) if box else track())["graphics"][g["id"]]

    def test_person_high_in_frame_gets_headline_lower(self):
        geo = self.place(card(), HIGH_FACE)
        fx, fy, fw, fh = face_px(HIGH_FACE)
        self.assertFalse(geo["covers_face"])
        self.assertGreater(geo["y"], fy + fh - 1)          # below the face, not squeezed above it
        self.assertEqual(geo["scale"], 1.0)                # moved, not shrunk

    def test_normal_framing_keeps_the_upper_third(self):
        geo = self.place(card())
        fx, fy, fw, fh = face_px([0.20, 0.46, 0.46, 0.26])
        self.assertLess(geo["y"] + geo["h"], fy)
        self.assertEqual(geo["scale"], 1.0)

    def test_asked_position_wins(self):
        geo = self.place(card(place="lower left"), HIGH_FACE)
        self.assertAlmostEqual(geo["x"], layout.SIDE, delta=2)
        self.assertGreater(geo["y"] + geo["h"] / 2, 1100)

    def test_face_still_beats_an_asked_position(self):
        # face low in the frame: "lower" would cover it, so the card goes elsewhere
        geo = self.place(card(place="lower"))
        self.assertFalse(geo["covers_face"])

    def test_hair_may_be_overlapped_rather_than_shrinking(self):
        # a big card that only fits at full size by tucking over the top of the head
        g = card(_size=(980, 330))
        geo = self.place(g, [0.30, 0.22, 0.40, 0.20])
        self.assertFalse(geo["covers_face"])
        self.assertGreaterEqual(geo["scale"], 0.85)

    def test_unboxed_text_avoids_a_bright_wall(self):
        gw, gh = layout.LUMA_GRID
        # bright wall in the top half, dark clothing below
        luma = [235 if y < gh // 2 else 40 for y in range(gh) for _ in range(gw)]
        plain = self.place(card(_size=(900, 200)), HIGH_FACE)
        unboxed = self.place(card(_size=(900, 200), _luma=luma), HIGH_FACE)
        self.assertLess(unboxed["backdrop"], 0.45)
        self.assertGreater(unboxed["y"] + unboxed["h"] / 2, gh // 2 * 40)   # centred in the dark half
        self.assertNotIn("backdrop", plain)

    def test_never_tiny_when_a_readable_spot_exists(self):
        for box in (HIGH_FACE, [0.20, 0.46, 0.46, 0.26], [0.25, 0.30, 0.5, 0.3]):
            geo = self.place(card(_size=(900, 300)), box)
            self.assertGreaterEqual(geo["scale"], 0.72, box)
            self.assertFalse(geo["covers_face"], box)


class PlanChoices(Env):

    def prof(self, **a):
        base = dict(graphics_elements=["text_callouts", "keyword_cards", "lists", "cta_card"],
                    headline="opening_hook", style={"pack": "bold"})
        base.update(a)
        return brand.compile_profile(dict(brand.load_progress()["answers"], **base))

    def check(self, b, p):
        try:
            creative.validate(creative.complete(copy.deepcopy(b), W)[0], W, p, DUR)
            return []
        except creative.BriefError as e:
            return e.problems

    def test_place_and_backing_reach_the_graphic(self):
        p = self.prof()
        b = good()
        b["moments"][0].update(place="lower", backing="none")
        self.assertEqual(self.check(b, p), [])
        e = planner.plan(W, DUR, [], p, {}, brief=creative.complete(b, W)[0])
        hook = next(g for g in e["graphics"] if g.get("role") == "headline")
        self.assertEqual((hook["place"], hook["backing"]), ("lower", "none"))

    def test_bad_place_refused(self):
        b = good()
        b["moments"][0]["place"] = "bottom_corner"
        self.assertTrue(any("place" in x for x in self.check(b, self.prof())))

    def test_box_refused_when_customer_said_no_boxes(self):
        b = good()
        b["moments"][0]["backing"] = "box"
        self.assertEqual(self.check(b, self.prof()), [])
        p = self.prof(creative_rules={"flags": ["no_boxes"], "notes": ""})
        self.assertTrue(any("no boxes" in x for x in self.check(b, p)))

    def test_context_explains_composition(self):
        ctx = creative.context(W, DUR, self.prof())
        self.assertIn("lower", ctx["composition"]["place"])
        self.assertIn("never over the face", ctx["composition"]["how"])


if __name__ == "__main__":
    unittest.main()
