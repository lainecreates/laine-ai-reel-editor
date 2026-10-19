"""Spinning image carousel (v1): request checks, placement, orbit geometry, the
review round trip (change / remove), and that it never appears by default."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import carousel, layout, library, planner, review, styles  # noqa: E402
from laine_reel.project import read_json, write_json  # noqa: E402
from test_library import Env  # noqa: E402
from test_render import edit, track  # noqa: E402
from test_review import make_reel  # noqa: E402

HIGH_FACE = [0.30, 0.16, 0.40, 0.20]


class Carousel(Env):

    def setUp(self):
        super().setUp()
        self.ids = []
        for i, name in enumerate(["Product one", "Product two", "Product three"]):
            a = library.add_file(self.png(f"p{i}.png"), name=name, category="photo")
            self.ids.append(a["id"])
        self.reel = make_reel(self.dir / "tiny")

    def car(self, **kw):
        g = {"id": "rg1", "type": "carousel", "assets": self.ids, "start": 0.5, "end": 4.5,
             "source": "review"}
        g.update(kw)
        return g

    def place(self, g, box=None):
        return layout.build(edit(captions=False, graphics=[g]), track(box) if box else track())["graphics"][g["id"]]

    # -- request ---------------------------------------------------------------
    def test_good_request_has_no_problems(self):
        self.assertEqual(carousel.problems(self.car()), [])

    def test_bad_requests_are_explained(self):
        self.assertTrue(carousel.problems(self.car(assets=self.ids[:1])))          # one image
        self.assertTrue(carousel.problems(self.car(assets=self.ids + ["nope"])))   # unknown image
        snd = library.add_file(self.wav(), name="Click")["id"]
        self.assertTrue(any("not an image" in p for p in carousel.problems(self.car(assets=[snd] + self.ids))))
        self.assertTrue(carousel.problems(self.car(speed="warp")))
        self.assertTrue(carousel.problems(self.car(end=30)))                     # too long

    def test_request_by_name_writes_a_per_reel_override(self):
        g, p = carousel.request(self.reel, ["product one", "Product two"], 3.2, 1.5, place="top_right",
                                speed="slow")
        self.assertTrue(p)                                                       # 1.5 s is too short
        g, p = carousel.request(self.reel, ["product one", "Product two"], 1.0, 3.0, place="top_right",
                                speed="slow")
        self.assertEqual(p, [])
        ov = read_json(self.reel.path("edit.overrides.json"))
        item = ov["add"]["graphics"][0]
        self.assertEqual((item["assets"], item["place"], item["speed"]), (self.ids[:2], "top_right", "slow"))
        self.assertEqual(item["src_start"], review.output_to_source(1.0, [[0.0, 2.0], [3.0, 6.0]]))

    # -- placement & geometry ---------------------------------------------------
    def test_auto_place_is_clear_of_the_face_and_inside_safe_zones(self):
        for box in (None, HIGH_FACE):
            geo = self.place(self.car(), box)
            self.assertFalse(geo["covers_face"])
            self.assertGreaterEqual(geo["y"], layout.TOP)
            self.assertLessEqual(geo["y"] + geo["h"], layout.GRAPHIC_BOTTOM + 1)
            self.assertGreaterEqual(geo["x"], layout.SIDE - 1)
            self.assertLessEqual(geo["x"] + geo["w"], layout.W - layout.SIDE + 1)

    def test_asked_corner_and_size(self):
        geo = self.place(self.car(place="top_right", size="small"))        # face low: the corner is free
        self.assertAlmostEqual(geo["x"] + geo["w"], layout.W - layout.SIDE, delta=2)
        self.assertLess(geo["y"], 700)
        self.assertLessEqual(geo["w"], carousel.SIZES["small"])

    def test_face_beats_an_asked_corner(self):
        # framed high, the top-right corner would cover the face: it goes elsewhere
        self.assertFalse(self.place(self.car(place="top_right", size="small"), HIGH_FACE)["covers_face"])

    def test_requested_corner_holds_against_hair(self):
        # framed so the corner is clear of the face but over hair: the request still holds
        geo = self.place(self.car(place="top_right", size="medium"), [0.36, 0.40, 0.38, 0.22])
        self.assertFalse(geo["covers_face"])
        self.assertAlmostEqual(geo["x"] + geo["w"], layout.W - layout.SIDE, delta=2)

    def test_sizes_grow(self):
        ws = [self.place(self.car(size=s), HIGH_FACE)["w"] for s in ("small", "medium", "large")]
        self.assertEqual(ws, sorted(ws))
        self.assertLess(ws[0], ws[2])

    def test_orbit_geometry_matches_its_box(self):
        geo = self.place(self.car(motion="noticeable"), HIGH_FACE)
        o = geo["orbit"]
        self.assertAlmostEqual(o["radius"] * 2 + o["card"], geo["w"], delta=1)
        self.assertLessEqual(o["height"], geo["h"] + 1)
        subtle = carousel.geometry(self.car(), geo["w"])
        self.assertGreater(o["tilt"], subtle["tilt"])          # more depth when "noticeable"
        self.assertLess(o["back"], subtle["back"])
        self.assertEqual(carousel.geometry(self.car(direction="counterclockwise"), 600)["dir"], -1)
        self.assertGreater(carousel.geometry(self.car(speed="slow"), 600)["period"],
                           carousel.geometry(self.car(speed="fast"), 600)["period"])

    # -- planning & review -------------------------------------------------------
    def test_never_planned_by_default_and_drawn_by_the_engine(self):
        from laine_reel import brand
        prof = brand.compile_profile(dict(brand.load_progress()["answers"], style={"pack": "luxe"}))
        e = {"graphics": [], "captions": {"items": []}, "zooms": [], "sfx": []}
        planner.apply_overrides(e, {"add": {"graphics": [self.car(id=None)]}})
        planner.style_graphics(e["graphics"], styles.resolve(prof))
        g = e["graphics"][0]
        self.assertEqual((g["id"], g["intent"], g["component"]), ("rg1", "carousel", None))
        self.assertNotIn("carousel", json.dumps(styles.load_pack("luxe")["aspects"]["components"]["by_intent"]))

    def test_carousel_takes_the_stage(self):
        # the plan's own zoom and a still-showing graphic step aside; the headline and a
        # zoom the customer asked for stay
        e = {"captions": {"items": []}, "sfx": [],
             "zooms": [{"id": "z1", "start": 1.0, "end": 2.0}, {"id": "z2", "start": 6.0, "end": 7.0}],
             "graphics": [{"id": "g1", "type": "lists", "start": 0.0, "end": 1.2},
                          {"id": "g2", "type": "text_callouts", "role": "headline", "start": 0.0, "end": 9.0}]}
        planner.apply_overrides(e, {"add": {"graphics": [self.car(id=None)],
                                            "zooms": [{"type": "punch", "start": 1.5, "end": 2.5}]}})
        self.assertEqual([z["start"] for z in e["zooms"]], [1.5, 6.0])
        g = {x["id"]: x for x in e["graphics"]}
        self.assertEqual(g["g1"]["end"], 0.5)
        self.assertEqual(g["g2"]["end"], 9.0)

    def test_phone_photo_rotation_is_respected(self):
        # phones save portrait photos sideways + EXIF orientation 6; cards must be portrait
        import struct, subprocess
        jpg = self.dir / "side.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=400x300",
                        "-frames:v", "1", jpg], check=True)
        data = jpg.read_bytes()
        tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + struct.pack(">HHIHH", 0x0112, 3, 1, 6, 0) + b"\x00" * 4
        app1 = b"Exif\x00\x00" + tiff
        jpg.write_bytes(data[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + data[2:])
        a = library.add_file(jpg, name="Phone photo", category="photo")
        self.assertEqual(library.exif_orientation(library.get(a["id"])["path"]), 6)
        self.assertEqual(library.display_size(library.get(a["id"])), (300, 400))
        self.assertLess(carousel.ratios(self.car(assets=[a["id"], self.ids[0]]))[0], 1)
        self.assertEqual(library.exif_orientation(library.get(self.ids[0])["path"]), 1)   # PNG: upright

    def test_review_changes_and_removes_it(self):
        carousel.request(self.reel, self.ids, 1.0, 3.0)
        e = read_json(self.reel.path("edit.json"))
        e["graphics"].append(dict(read_json(self.reel.path("edit.overrides.json"))["add"]["graphics"][0], id="rg1"))
        write_json(self.reel.path("edit.json"), e)
        review.save_feedback(self.reel, {"graphics": {"rg1": {"speed": "fast", "direction": "counterclockwise",
                                                              "place": "left", "start": 1.5}}})
        res = review.apply_feedback(self.reel)
        item = read_json(self.reel.path("edit.overrides.json"))["add"]["graphics"][0]
        self.assertEqual((item["speed"], item["direction"], item["place"], item["start"]),
                         ("fast", "counterclockwise", "left", 1.5))
        self.assertEqual(item["src_start"], review.output_to_source(1.5, [[0.0, 2.0], [3.0, 6.0]]))
        self.assertTrue(res["needs"])
        item_style = dict(item, style={"animation_in": "bounce"})
        ov = read_json(self.reel.path("edit.overrides.json")); ov["add"]["graphics"][0] = item_style
        write_json(self.reel.path("edit.overrides.json"), ov)
        review.save_feedback(self.reel, {"graphics": {"rg1": {"reset_style": True}}})
        review.apply_feedback(self.reel)
        self.assertNotIn("style", read_json(self.reel.path("edit.overrides.json"))["add"]["graphics"][0])
        review.save_feedback(self.reel, {"graphics": {"rg1": {"remove": True}}})
        review.apply_feedback(self.reel)
        self.assertEqual(read_json(self.reel.path("edit.overrides.json"))["add"]["graphics"], [])


if __name__ == "__main__":
    unittest.main()


class Calendar(unittest.TestCase):
    """Page-flip calendar (a requested graphic): placed like any graphic, flips move with it."""

    def test_placed_clear_of_the_face(self):
        g = {"id": "rg1", "type": "calendar", "start": 1.0, "end": 4.0, "flips": [0.4, 1.8, 2.8]}
        geo = layout.build(edit(captions=False, graphics=[g]), track())["graphics"]["rg1"]
        self.assertFalse(geo["covers_face"])
        self.assertEqual((geo["w"], geo["h"]), layout.SIZES["calendar"])

    def test_flips_are_relative_so_a_recut_keeps_them_on_the_words(self):
        ov = {"add": {"graphics": [{"type": "calendar", "start": 1.0, "end": 4.0, "src_start": 1.0,
                                    "flips": [0.4, 1.8]}]}}
        out = review.retime_additions(ov, [[0.0, 0.5], [1.0, 6.0]])     # 0.5 s cut before it
        g = out["add"]["graphics"][0]
        self.assertEqual((g["start"], g["end"], g["flips"]), (0.5, 3.5, [0.4, 1.8]))

    def test_drawn_by_the_engine_not_a_style(self):
        e = {"graphics": [], "captions": {"items": []}, "zooms": [], "sfx": []}
        planner.apply_overrides(e, {"add": {"graphics": [{"type": "calendar", "start": 1, "end": 4, "flips": [1]}]}})
        planner.style_graphics(e["graphics"], styles.resolve({"style": {"pack": "bold"}}))
        self.assertEqual((e["graphics"][0]["intent"], e["graphics"][0]["component"]), ("calendar", None))
