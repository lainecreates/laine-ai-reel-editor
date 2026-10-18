"""Phase 5: asset library, brand settings, custom sounds, logo, Choose for me."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import brand, library, planner  # noqa: E402

FONT = "/System/Library/Fonts/Supplemental/Impact.ttf"


def sh(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, capture_output=True)


class Env(unittest.TestCase):
    """A temporary library and a temporary copy of the brand (never the real ones)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.old = {k: os.environ.get(k) for k in ("LAINE_LIBRARY_DIR", "LAINE_BRAND_DIR")}
        os.environ["LAINE_LIBRARY_DIR"] = str(self.dir / "lib")
        os.environ["LAINE_BRAND_DIR"] = str(self.dir / "brand")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fixture_brand import write_test_brand
        write_test_brand(self.dir / "brand")

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir)

    def wav(self, freq=1200, name="beep.wav"):
        p = self.dir / name
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f={freq}:d=0.3", p)
        return p

    def png(self, name="logo.png"):
        p = self.dir / name
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
           "color=c=0xFF00FF:s=300x120,format=rgba", "-frames:v", "1", p)
        return p


class Library(Env):
    def test_add_and_read_details(self):
        f = library.add_file(FONT, name="My Bold")
        self.assertEqual((f["kind"], f["family"]), ("font", "Impact"))
        s = library.add_file(self.wav(), name="My pop", category="pop")
        self.assertAlmostEqual(s["duration"], 0.3, delta=0.02)
        i = library.add_file(self.png(), name="Logo")
        self.assertEqual((i["width"], i["height"], i["transparent"], i["category"]),
                         (300, 120, True, "logo"))
        self.assertEqual(len(library.items()), 3)

    def test_refuses_fakes_and_wrong_types(self):
        fake = self.dir / "fake.ttf"
        fake.write_bytes(b"hello")
        renamed = self.dir / "sound.png"
        shutil.copy2(self.wav(), renamed)
        doc = self.dir / "notes.pdf"
        doc.write_bytes(b"%PDF-1.4")
        for p in (fake, renamed, doc):
            with self.assertRaises(library.LibraryError):
                library.add_file(p)
        self.assertEqual(library.items(), [])

    def test_organise_and_archive(self):
        s = library.add_file(self.wav(), name="tmp")
        library.update(s["id"], name="Swish", category="whoosh")
        library.update(s["id"], archived=True)
        self.assertEqual(library.items(), [])
        a = library.items(include_archived=True)[0]
        self.assertEqual((a["name"], a["category"], a["archived"]), ("Swish", "whoosh", True))
        self.assertTrue(Path(a["path"]).exists())   # archived, never deleted


class Settings(Env):
    def test_reel_only_vs_defaults(self):
        reel = self.dir / "reel"
        reel.mkdir()
        before = json.loads((self.dir / "brand" / "brand.json").read_text())
        brand.save_settings({"caption_size": "large", "colors": ["#112233", "#445566"]},
                            "reel", reel)
        eff = brand.effective(reel)
        self.assertEqual(eff["captions"]["size"], "large")
        self.assertEqual(eff["colors"]["primary"], "#112233")
        # defaults untouched
        self.assertEqual(json.loads((self.dir / "brand" / "brand.json").read_text())["captions"],
                         before["captions"])
        brand.save_settings({"caption_size": "small"}, "default", reel)
        self.assertEqual(json.loads((self.dir / "brand" / "brand.json").read_text())
                         ["captions"]["size"], "small")
        self.assertTrue((self.dir / "brand" / "brand.previous.json").exists())
        # the reel follows the new default for that setting, keeps its own colours
        eff = brand.effective(reel)
        self.assertEqual(eff["captions"]["size"], "small")
        self.assertEqual(eff["colors"]["primary"], "#112233")

    def test_library_font_sound_logo(self):
        reel = self.dir / "reel"
        reel.mkdir()
        f = library.add_file(FONT, name="My Bold")
        s = library.add_file(self.wav(), name="My pop")
        i = library.add_file(self.png(), name="Logo")
        brand.save_settings({"font_files": {"headline": f["id"]}, "graphics_font": "body",
                             "sound_map": {"headline": s["id"]},
                             "logo": {"id": i["id"], "position": "top_left"}}, "reel", reel)
        eff = brand.effective(reel)
        self.assertEqual(eff["fonts"]["headline"], "Impact")
        self.assertEqual(eff["fonts"]["headline_file"], f["path"])
        self.assertEqual(eff["fonts"]["graphics"], eff["fonts"]["body"])
        self.assertEqual(eff["sfx"]["sounds"], {"headline": s["id"]})
        self.assertEqual(eff["logo"]["position"], "top_left")

    def test_rejects_unknown_assets_and_keys(self):
        with self.assertRaises(brand.AnswerError):
            brand.save_settings({"sound_map": {"headline": "s-nope"}}, "reel", self.dir)
        with self.assertRaises(brand.AnswerError):
            brand.save_settings({"reference_reel": "/x"}, "reel", self.dir)

    def test_onboarding_answer_keeps_library_settings(self):
        s = library.add_file(self.wav(), name="My pop")
        brand.save_settings({"sound_map": {"emoji": s["id"]}}, "default")
        brand.answer("pacing", "tight")
        self.assertIn("sound_map", brand.load_progress()["answers"])


class Sounds(Env):
    def test_custom_sound_used_exactly_never_default(self):
        s = library.add_file(self.wav(), name="My pop")
        gfx = [{"id": "g1", "type": "text_callouts", "role": "headline", "start": 0.0, "end": 2},
               {"id": "g2", "type": "keyword_cards", "start": 3.0, "end": 4}]
        out = planner.plan_sfx([], gfx, 10, {"events": ["headline", "graphic_in"],
                                             "sounds": {"headline": s["id"]}, "gain_db": -10})
        self.assertEqual(out[0]["file"], s["path"])
        self.assertTrue(out[0]["custom"])
        self.assertTrue(out[1]["file"].endswith("pop.wav"))   # no custom sound chosen there

    def test_missing_custom_sound_is_reported_not_replaced(self):
        s = library.add_file(self.wav(), name="My pop")
        Path(s["path"]).unlink()
        out = planner.plan_sfx([], [{"id": "g1", "type": "text_callouts", "role": "headline",
                                     "start": 0, "end": 2}], 10,
                               {"events": ["headline"], "sounds": {"headline": s["id"]}})
        self.assertIsNone(out[0]["file"])
        self.assertTrue(out[0]["missing_custom"])


class ChooseForMe(unittest.TestCase):
    def test_picks_strongest_suggestion(self):
        from laine_reel import review
        from laine_reel.project import Reel
        d = Path(tempfile.mkdtemp())
        (d / "review").mkdir()
        (d / "review" / "suggestions.json").write_text(json.dumps({"headlines": ["best", "ok"]}))
        self.assertEqual(review.choose_headline(Reel(d)), "best")
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
