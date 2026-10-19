"""Pre-release fixes: HEIC uploads, the "Edit my reel" workflow gaps, and design
revisions that must survive re-plans and the customer's rules."""

import copy
import io
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, creative, designs, library, planner, review  # noqa: E402
from laine_reel.project import read_json, write_json  # noqa: E402
from test_creative import DUR, W, good  # noqa: E402
from test_designs import FakeReel  # noqa: E402
from test_library import Env  # noqa: E402
from test_review import make_reel  # noqa: E402

MAC = bool(shutil.which("osascript")) and sys.platform == "darwin"


@unittest.skipUnless(MAC, "HEIC conversion uses macOS ImageIO")
class Heic(Env):

    def heic(self, w, h, orientation):
        """A HEIC like an iPhone's: stored w x h, with a rotation tag."""
        src, out = self.dir / "src.png", self.dir / f"photo-{orientation}.heic"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=blue:s={w}x{h}",
                        "-frames:v", "1", src], check=True)
        js = self.dir / "mk.js"
        js.write_text("""ObjC.import('Foundation'); ObjC.import('ImageIO'); ObjC.import('CoreGraphics');
function run(a) { const s = $.CGImageSourceCreateWithURL($.NSURL.fileURLWithPath(a[0]), null);
  const i = $.CGImageSourceCreateImageAtIndex(s, 0, null);
  const d = $.CGImageDestinationCreateWithURL($.NSURL.fileURLWithPath(a[1]), $('public.heic'), 1, null);
  $.CGImageDestinationAddImage(d, i, $.NSDictionary.dictionaryWithObjectForKey(
    $.NSNumber.numberWithInt(parseInt(a[2])), $('Orientation')));
  return $.CGImageDestinationFinalize(d) ? 'ok' : 'fail'; }""")
        subprocess.run(["osascript", "-l", "JavaScript", js, src, out, str(orientation)], check=True,
                       capture_output=True)
        return out

    def test_iphone_portrait_heic_becomes_an_upright_jpeg(self):
        a = library.add_file(self.heic(400, 300, 6), name="Phone photo")     # stored sideways
        self.assertTrue(a["file"].endswith(".jpg"))
        self.assertEqual(a["converted_from"], "HEIC")
        self.assertEqual((a["width"], a["height"]), (300, 400))                # upright, full size
        self.assertEqual(library.display_size(library.get(a["id"])), (300, 400))
        self.assertTrue(a["original_name"].endswith(".heic"))

    def test_upright_heic_keeps_its_shape(self):
        a = library.add_file(self.heic(320, 200, 1), name="Wide photo")
        self.assertEqual((a["width"], a["height"]), (320, 200))

    def test_damaged_heic_is_refused_kindly(self):
        bad = self.dir / "broken.heic"
        bad.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64)
        with self.assertRaises(library.LibraryError) as cm:
            library.add_file(bad)
        self.assertIn("JPG", str(cm.exception))


class Workflow(Env):

    def setUp(self):
        super().setUp()
        self.reel = make_reel(self.dir / "tiny")

    def plan(self, hook="Hello there"):
        words = read_json(self.reel.path("transcript.cut.json"))["words"]
        b = {"version": 1, "summary": "a tiny test", "moments": [
            {"intent": "hook", "from": 0, "to": 1, "text": hook, "why": "the opening"}]}
        creative.save(self.reel, b, words)

    def test_suggestions_start_with_the_plans_hook_without_duplicates(self):
        self.plan("Hello there")
        s = review.suggest_headlines(self.reel)
        self.assertEqual(s[0], "Hello there")
        self.assertEqual(len({x.lower() for x in s}), len(s))

    def test_chosen_headline_is_written_back_to_the_plan(self):
        self.plan()
        self.assertTrue(creative.set_headline(self.reel, "Hi friends, listen up today"))
        hook = creative.load(self.reel)["moments"][0]
        self.assertEqual((hook["text"], hook["source"]), ("Hi friends, listen up today", "customer"))
        # also through the review page's headline choice
        review.save_feedback(self.reel, {"headline": {"text": "Hello friends"}})
        review.apply_feedback(self.reel)
        self.assertEqual(creative.load(self.reel)["moments"][0]["text"], "Hello friends")

    def test_no_plan_no_writeback(self):
        self.assertFalse(creative.set_headline(self.reel, "Anything"))

    def test_customer_headline_may_be_longer_than_plan_limits(self):
        p = brand.compile_profile(dict(brand.load_progress()["answers"], headline="opening_hook",
                                       graphics_elements=["text_callouts", "keyword_cards", "lists", "cta_card"]))
        b = good()
        b["moments"][0].update(text="Three simple tips that changed every video I make", source="customer")
        creative.validate(creative.complete(copy.deepcopy(b), W)[0], W, p, DUR)   # no error

    def test_words_shows_times_on_the_reel(self):
        sys.argv = ["reel.py"]
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib
        reel_cli = importlib.import_module("reel")
        buf = io.StringIO()
        with redirect_stdout(buf):
            reel_cli.main(["words", str(self.reel.root)])
        out = buf.getvalue()
        self.assertIn("[on the reel]", out)
        self.assertIn("   4.00s [  3.00s]  [4]Comment", out)   # said at 4.0 s in the clip, 3.0 s on the reel


class DesignRevisions(Env):

    def prof(self, pack="luxe", **a):
        base = dict(graphics_elements=["text_callouts", "keyword_cards", "lists", "cta_card"],
                    headline="opening_hook", style={"pack": pack})
        base.update(a)
        return brand.compile_profile(dict(brand.load_progress()["answers"], **base))

    def edit(self, p, b=None):
        b = creative.complete(copy.deepcopy(b or good()), W)[0]
        return planner.plan(W, DUR, [], p, {}, brief=b)

    def test_pick_survives_a_replan_that_renumbers_graphics(self):
        p = self.prof("magazine")
        r = FakeReel(self.dir / "reels", "renumber")
        e = self.edit(p)
        designs.assign(r, e, p)
        stat = next(g for g in e["graphics"] if g.get("intent") == "stat")
        _, new = designs.another(r, e, stat["id"], p)
        # a new moment at the start shifts every id by one
        b = good()
        b["moments"].insert(1, {"intent": "key_phrase", "from": 7, "to": 11, "text": "Film near a window",
                                "why": "added", "source": "customer"})
        b["moments"][2]["items"] = b["moments"][2]["items"][1:]
        b["moments"][2]["from"] = 12
        e2 = self.edit(p, b)
        designs.assign(r, e2, p)
        stat2 = next(g for g in e2["graphics"] if g.get("intent") == "stat")
        self.assertNotEqual(stat2["id"], stat["id"])
        self.assertEqual(stat2["variant_name"], new)

    def test_frame_designs_not_offered_when_borders_are_off(self):
        on = self.prof()
        off = self.prof(creative_rules={"flags": ["no_boxes"], "notes": ""})
        for p, expect in ((on, True), (off, False)):
            r = FakeReel(self.dir / "reels", f"frame-{expect}")
            e = self.edit(p)
            designs.assign(r, e, p)
            hook = next(g for g in e["graphics"] if g.get("intent") == "hook")
            ids = [v["id"] for v in hook["variants"]]
            if not designs.styles.decorations_on(designs.styles.resolve(on)).get("graphic_border"):
                expect = False
            self.assertEqual("frame" in ids, expect, ids)


if __name__ == "__main__":
    unittest.main()


class CustomGraphics(unittest.TestCase):
    """A per-reel custom graphic keeps its own component and size."""

    def test_component_size_and_page(self):
        from laine_reel import layout, overlay, styles
        from test_render import edit, track
        g = {"id": "rg1", "type": "custom", "custom_component": "custom.spin-badge", "size": [300, 300],
             "start": 0.2, "end": 3.0, "params": {"text": "SALE"}}
        e = edit(captions=False, graphics=[g])
        planner.style_graphics(e["graphics"], styles.resolve({"style": {"pack": "bold"}}))
        self.assertEqual(e["graphics"][0]["component"], "custom.spin-badge")
        geo = layout.build(e, track())["graphics"]["rg1"]
        self.assertEqual((geo["w"], geo["h"]), (300, 300))
        self.assertFalse(geo["covers_face"])
        js = overlay.custom_js({"_custom_js": {"badge.js": "window.COMPONENTS['custom.x'] = 1;"}})
        self.assertIn("custom/badge.js", js)
        self.assertIn("try {", js)


class AutomaticHeadline(Env):

    def test_finish_picks_the_plans_hook_without_asking(self):
        reel = make_reel(self.dir / "tiny")
        words = read_json(reel.path("transcript.cut.json"))["words"]
        creative.save(reel, {"version": 1, "summary": "s", "moments": [
            {"intent": "hook", "from": 0, "to": 1, "text": "Hello there", "why": "opening"}]}, words)
        self.assertEqual(creative.hook_text(reel), "Hello there")


class FontLibrary(Env):
    """24 included fonts, 6 per category, licensed, findable by name and usable per role."""

    def test_catalog(self):
        from laine_reel import fontlib
        fams = fontlib.families()
        self.assertEqual(len(fams), 24)
        for cat in fontlib.CATEGORIES:
            self.assertEqual(sum(1 for f in fams if f["category"] == cat), 6, cat)
        for f in fams:
            self.assertTrue(f["files"], f["family"])
            self.assertIn(f["license"], ("SIL Open Font License 1.1", "Apache License 2.0"))
            d = f["files"][0].parent
            self.assertTrue((d / "OFL.txt").exists() or (d / "LICENSE.txt").exists(), f["family"])

    def test_roles_resolve_to_included_files(self):
        from laine_reel import conformance, fontlib
        p = brand.compile_profile(dict(brand.load_progress()["answers"], fonts={"headline": "Bebas Neue", "body": "Inter"},
                                       graphics_font="font:Caveat"))
        f = p["fonts"]
        self.assertEqual((f["headline"], f["body"], f["graphics"]), ("Bebas Neue", "Inter", "Caveat"))
        for role in ("headline_file", "body_file", "graphics_file"):
            self.assertTrue(f[role].startswith(str(fontlib.INCLUDED_DIR)), role)
        self.assertEqual(conformance.font_warnings(p), [])          # nothing to download or warn about

    def test_page_declares_every_weight(self):
        from laine_reel import overlay
        p = brand.compile_profile(dict(brand.load_progress()["answers"], fonts={"headline": "Lato", "body": "Poppins"}))
        css = overlay.font_faces(p)
        self.assertIn('font-family: "Lato"', css)
        self.assertIn("Lato-Bold.ttf", css)
        self.assertIn("font-weight: 700", css)

    def test_bad_graphics_font_refused(self):
        with self.assertRaises(brand.AnswerError):
            brand.save_settings({"graphics_font": "comic"}, "reel", self.dir)
