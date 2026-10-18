"""Unit tests for face-aware layout, overlay page, zoom expressions, sfx."""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import composite, faces, layout, overlay, planner, sfx  # noqa: E402

# Typical talking-head framing: face in the middle of the frame, low-ish.
FACE = [0.20, 0.46, 0.46, 0.26]


def track(box=FACE, dur=20.0):
    return {"source": "test", "fps": 2,
            "samples": [{"t": i / 2, "box": list(box)} for i in range(int(dur * 2) + 1)]}


def edit(captions=True, graphics=(), zooms=(), style="word_pop", position="lower_third"):
    items = [{"id": "cap1", "start": 0.5, "end": 1.0, "text": "hello",
              "words": [{"text": "hello", "start": 0.5, "end": 1.0, "emphasis": True}],
              "y": 1300}] if captions else []
    return {"duration": 20.0, "zooms": list(zooms), "graphics": list(graphics), "sfx": [],
            "music": None,
            "captions": {"enabled": captions, "items": items,
                         "style": {"style": style, "position": position, "size_px": 76,
                                   "animation": "none", "emphasis": "bigger", "case": "lower"}}}


def px(b):
    return (b[0] * 1080, b[1] * 1920, b[2] * 1080, b[3] * 1920)


class Layout(unittest.TestCase):
    def test_captions_never_cover_the_face(self):
        lay = layout.build(edit(), track())
        self.assertFalse(lay["captions"]["covers_face"])
        self.assertEqual(layout._overlap(tuple(lay["captions"]["rect"]), px(FACE)), 0)

    def test_lower_third_captions_go_just_under_the_chin(self):
        lay = layout.build(edit(), track())
        chin = (FACE[1] + FACE[3]) * 1920
        self.assertGreater(lay["captions"]["rect"][1], chin)
        self.assertIn("lowered", lay["captions"]["why"])

    def test_zoom_enlarges_the_face_and_captions_respect_it(self):
        z = {"id": "z1", "start": 0.0, "end": 5.0, "type": "punch", "scale": 1.2}
        plain = layout.build(edit(), track())["captions"]["rect"][1]
        zoomed = layout.build(edit(zooms=[z]), track())["captions"]["rect"][1]
        self.assertGreater(zoomed, plain)

    def test_zoom_focus_is_the_face_centre(self):
        z = {"id": "z1", "start": 0.0, "end": 5.0, "type": "punch", "scale": 1.2}
        f = layout.zoom_focus(track(), [z])["z1"]
        self.assertAlmostEqual(f["x"], FACE[0] + FACE[2] / 2, places=3)

    def test_graphics_never_cover_the_face(self):
        gs = [{"id": "g1", "type": "sticky_notes", "start": 1, "end": 6, "zone": "upper_third",
               "items": [{"text": "Where do I put it?", "at": 1},
                         {"text": "What angle do I get?", "at": 2},
                         {"text": "Why does my footage look so random?", "at": 3}]},
              {"id": "g2", "type": "emoji", "start": 2, "end": 3, "zone": "center", "emoji": "📸"},
              {"id": "g3", "type": "keyword_cards", "start": 7, "end": 9, "zone": "upper_third",
               "text": "Morning Light Studio"}]
        lay = layout.build(edit(graphics=gs), track())
        for gid, geo in lay["graphics"].items():
            self.assertFalse(geo["covers_face"], gid)

    def test_sticky_note_stays_readable(self):
        g = {"id": "g1", "type": "sticky_notes", "start": 1, "end": 6, "zone": "upper_third",
             "items": [{"text": "Where do I put it?", "at": 1}, {"text": "What angle?", "at": 2}]}
        self.assertEqual(layout.build(edit(graphics=[g]), track())["graphics"]["g1"]["scale"], 1.0)

    def test_overlapping_graphics_dont_collide(self):
        gs = [{"id": f"g{i}", "type": "keyword_cards", "start": 1, "end": 5, "zone": "upper_third",
               "text": "card"} for i in (1, 2)]
        lay = layout.build(edit(captions=False, graphics=gs), track())
        a, b = lay["graphics"]["g1"], lay["graphics"]["g2"]
        self.assertEqual(layout._overlap((a["x"], a["y"], a["w"], a["h"]),
                                         (b["x"], b["y"], b["w"], b["h"])), 0)


class AboveHead(unittest.TestCase):
    def test_requested_above_the_head(self):
        g = {"id": "g1", "type": "emoji", "start": 1, "end": 2, "zone": "center",
             "emoji": "📸", "place": "above_head"}
        geo = layout.build(edit(graphics=[g]), track())["graphics"]["g1"]
        face_top = FACE[1] * 1920
        self.assertLess(geo["y"] + geo["h"], face_top)
        face_cx = (FACE[0] + FACE[2] / 2) * 1080
        self.assertAlmostEqual(geo["x"] + geo["w"] / 2, face_cx, delta=2)
        self.assertFalse(geo["covers_face"])


class Faces(unittest.TestCase):
    def test_gaps_take_nearest_face(self):
        s = [{"t": 0, "box": [0.1, 0.1, 0.2, 0.2]}, {"t": 0.5, "box": None},
             {"t": 1.0, "box": [0.3, 0.3, 0.2, 0.2]}]
        out = faces.fill_gaps(s)
        self.assertEqual(out[1]["box"], [0.1, 0.1, 0.2, 0.2])
        self.assertTrue(out[1]["filled"])

    def test_union_over_time(self):
        tr = {"samples": [{"t": 0, "box": [0.1, 0.1, 0.2, 0.2]},
                          {"t": 1, "box": [0.2, 0.2, 0.2, 0.2]}]}
        self.assertEqual([round(v, 3) for v in faces.box_between(tr, 0, 1)], [0.1, 0.1, 0.3, 0.3])


class Zooms(unittest.TestCase):
    def test_expressions(self):
        zs = [{"id": "z1", "start": 1.0, "end": 3.0, "type": "punch", "scale": 1.18},
              {"id": "z2", "start": 5.0, "end": 8.0, "type": "push", "scale": 1.08}]
        z, x, y = composite.zoom_exprs(zs, {"z1": {"x": 0.45, "y": 0.6}, "z2": {"x": 0.5, "y": 0.5}})
        self.assertIn("between(it,1.000,2.999)", z)
        self.assertIn("1.1800", z)
        self.assertIn("(3-2*", z)               # smoothstep ease for the push
        self.assertIn("(iw-iw/zoom)*0.45", x)   # toward the face
        self.assertIsNone(composite.zoom_exprs([], {}))

    def test_no_text_filters_in_final_graph(self):
        g = composite.build_graph([[0, 2], [3, 5]], "24", "cover", 0.5,
                                  [{"id": "z1", "start": 0.5, "end": 2.0, "type": "punch",
                                    "scale": 1.2}], {"z1": {"x": .5, "y": .5}}, True, "0xFF3E8E",
                                  4.0, [{"index": 2, "at": 1.0, "gain_db": -15}], None)
        for bad in ("drawtext", "subtitles", "ass="):
            self.assertNotIn(bad, g)
        for good in ("zoompan", "overlay", "adelay=1000", "amix"):
            self.assertIn(good, g)


class Overlay(unittest.TestCase):
    def test_page_has_timeline_and_brand(self):
        brand = {"colors": {"primary": "#FF3E8E", "accent": "#A3B18A"},
                 "fonts": {"headline": "Playfair Display", "body": "Lato"},
                 "aesthetic": {"tokens": {"corner_radius": 12, "shadow": "glow"}}}
        e = edit()
        lay = layout.build(e, track())
        html = overlay.build_page(e, lay, brand, 24)
        self.assertIn("window.__seek", html)
        self.assertIn('"Lato", "Avenir Next"', html)       # brand font + installed fallback
        self.assertIn('"Playfair Display", "Didot"', html)
        data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
        self.assertEqual(data["colors"]["primary"], "#FF3E8E")
        self.assertEqual(data["captions"]["y"], lay["captions"]["y"])

    def test_sticky_font_and_keyword_colour_reach_the_page(self):
        brand = {"colors": {"primary": "#FF3E8E", "accent": "#A3B18A", "caption_keyword": "#FF3E8E"},
                 "fonts": {"headline": "Playfair Display", "body": "Lato"},
                 "graphics": {"sticky_font": "body"}, "aesthetic": {"tokens": {}}}
        e = edit()
        html = overlay.build_page(e, layout.build(e, track()), brand, 24)
        data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
        self.assertEqual(data["stickyFont"], "body")
        self.assertEqual(data["colors"]["captionKeyword"], "#FF3E8E")
        self.assertIn("if (C.captionKeyword) st = `color:${C.captionKeyword}`", html)

    def test_color_mix(self):
        self.assertEqual(overlay.mix("#000000", "#FFFFFF", 0.5), "#808080")


class Arrows(unittest.TestCase):
    def test_comment_arrow_lands_on_the_word(self):
        words = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3}
                 for i, t in enumerate('If you want it, comment"content".'.split())]
        brand = {"graphics": {"elements": ["arrows"], "min_gap_s": 5}, "captions": {}}
        gs = planner.plan_graphics(words, planner.split_sentences(words), set(), 10.0, brand)
        (arrow,) = [g for g in gs if g["type"] == "arrows"]
        self.assertEqual(arrow["start"], words[4]["start"])
        self.assertEqual(arrow["target"], "comment_button")


class SoundPack(unittest.TestCase):
    def test_generated_sounds_exist(self):
        pack = sfx.ensure_pack()
        self.assertEqual(set(pack), {"whoosh", "pop", "ding", "click"})
        for p in pack.values():
            self.assertTrue(Path(p).stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()


class NewGraphics(unittest.TestCase):
    def test_full_overlay_covers_frame_by_request_and_hides_captions(self):
        g = {"id": "rg1", "type": "full_overlay", "start": 0.4, "end": 0.9, "zone": "center",
             "text": "hello", "opacity": 0.5, "source": "review"}
        lay = layout.build(edit(graphics=[g]), track())
        self.assertEqual((lay["graphics"]["rg1"]["w"], lay["graphics"]["rg1"]["h"]), (1080, 1920))
        self.assertTrue(lay["graphics"]["rg1"]["allow_face"])
        e = edit()
        e["captions"]["items"][0]["start"] = 0.5
        planner.apply_overrides(e, {"add": {"graphics": [dict(g, start=0.4, end=0.9)]}})
        self.assertEqual(e["captions"]["items"], [])

    def test_top_placement_stays_off_the_face(self):
        g = {"id": "g3", "type": "profile_card", "start": 1, "end": 3, "zone": "upper_third",
             "place": "top"}
        geo = layout.build(edit(graphics=[g]), track())["graphics"]["g3"]
        self.assertEqual(geo["y"], layout.TOP)
        self.assertFalse(geo["covers_face"])

    def test_removed_graphic_takes_its_sound_and_swapped_sound_gets_a_file(self):
        e = edit()
        e["graphics"] = [{"id": "g2", "type": "emoji", "start": 1, "end": 2, "emoji": "📅",
                          "reason": "", "style": {}}]
        e["sfx"] = [{"id": "s1", "at": 0.0, "kind": "pop", "for": "g1", "file": "x"},
                    {"id": "s2", "at": 1.0, "kind": "pop", "for": "g2", "file": "x"}]
        planner.apply_overrides(e, {"remove_match": {"g2": {"type": "emoji", "start": 1}},
                                    "set": {"s1": {"kind": "whoosh"}}})
        self.assertEqual([s["id"] for s in e["sfx"]], ["s1"])
        self.assertTrue(e["sfx"][0]["file"].endswith("whoosh.wav"))

    def test_page_never_draws_bigger_than_the_approved_box(self):
        self.assertIn("e.style.zoom = String(k)", overlay.TEMPLATE)
        self.assertIn("window.__rects", overlay.TEMPLATE)


class FaceIsHardRule(unittest.TestCase):
    def test_big_image_shrinks_rather_than_touch_the_face(self):
        big_face = [0.25, 0.25, 0.5, 0.3]
        g = {"id": "i1", "type": "image", "start": 1, "end": 3, "zone": "upper_third",
             "asset": "none", "_size": (560, 700)}
        geo = layout.build(edit(captions=False, graphics=[g]), track(big_face))["graphics"]["i1"]
        self.assertFalse(geo["covers_face"])
