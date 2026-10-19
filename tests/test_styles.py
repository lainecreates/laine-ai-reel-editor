"""Stage 1: style packs, priority/provenance resolver, rules, motion primitives."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, conformance, overlay, planner, styles  # noqa: E402
from test_library import Env  # noqa: E402


def fake_pack(d, pid, version="1.0.0", **aspects):
    p = d / pid / version
    p.mkdir(parents=True)
    (p / "pack.json").write_text(json.dumps({"id": pid, "version": version, "name": pid.title(),
                                             "aspects": aspects}))


class Packs(Env):

    def test_classic_is_the_default_and_pinned(self):
        prof = brand.compile_profile(brand.load_progress()["answers"])
        self.assertEqual((prof["style"]["pack"], prof["style"]["version"]), ("classic", "1.0.0"))
        self.assertTrue(styles.resolve(prof)["legacy"])

    def test_old_profiles_resolve_to_classic_1_0_0(self):
        prof = brand.compile_profile(brand.load_progress()["answers"])
        prof.pop("style")
        r = styles.resolve(prof)
        self.assertEqual((r["pack"], r["version"]), ("classic", "1.0.0"))

    def test_classic_keeps_the_original_values(self):
        c = styles.load_pack("classic", "1.0.0")["aspects"]
        self.assertEqual(c["shape"]["tokens_by_aesthetic"]["soft_luxe"]["corner_radius"], 28)
        self.assertEqual(c["motion"]["entrance_by_aesthetic"]["playful"], "bounce")
        self.assertEqual(c["sound"]["by_event"]["cta"], "ding")
        self.assertTrue(all(c["decorations"].values()))

    def test_unknown_or_unsafe_pack_names(self):
        for bad in ("nope", "../brand", ""):
            with self.assertRaises(ValueError):
                styles.load_pack(bad)


class Resolver(Env):

    def setUp(self):
        super().setUp()
        self.sd = self.dir / "styles"
        shutil.copytree(ROOT / "styles", self.sd)
        os.environ["LAINE_STYLES_DIR"] = str(self.sd)
        styles._cache.clear()
        fake_pack(self.sd, "plainpack", decorations={}, motion={"entrance_default": "rise"})
        fake_pack(self.sd, "plainpack", "1.1.0", decorations={"caption_glow": True})

    def tearDown(self):
        os.environ.pop("LAINE_STYLES_DIR", None)
        styles._cache.clear()
        super().tearDown()

    def prof(self, **answers):
        return brand.compile_profile(dict(brand.load_progress()["answers"], **answers))

    def test_engine_default_is_plain(self):
        r = styles.resolve(self.prof(style={"pack": "plainpack"}))
        # latest plainpack (1.1.0) turns only the glow on; everything else stays off
        self.assertEqual({d for d, v in r["decorations"].items() if v["on"]}, {"caption_glow"})
        self.assertEqual(r["decorations"]["caption_outline"]["source"], "engine")

    def test_version_pinned_in_profile_survives_newer_pack(self):
        p = self.prof(style={"pack": "plainpack"})
        p["style"]["version"] = "1.0.0"
        r = styles.resolve(p)
        self.assertFalse(r["decorations"]["caption_glow"]["on"])   # 1.0.0 had no glow

    def test_mix_takes_aspects_from_another_pack(self):
        r = styles.resolve(self.prof(style={"pack": "classic",
                                            "mix": [{"pack": "plainpack", "aspects": ["decorations", "motion"]}]}))
        self.assertEqual(r["aspect_sources"]["motion"], "pack:plainpack")
        self.assertEqual(r["aspect_sources"]["shape"], "pack:classic")
        self.assertFalse(r["decorations"]["graphic_box"]["on"])

    def test_priority_rules_beat_brand_beat_pack(self):
        p = self.prof(caption_outline={"enabled": True, "thickness": "thin"},
                      style={"pack": "plainpack", "decorations": {"graphic_shadow": True}},
                      creative_rules={"flags": ["no_outlines", "no_emojis", "no_sound_effects"],
                                      "notes": "keep it calm"})
        r = styles.resolve(p)
        self.assertEqual(r["decorations"]["caption_outline"], {"on": False, "source": "rule:no_outlines"})
        self.assertEqual(r["decorations"]["graphic_shadow"], {"on": True, "source": "brand"})
        self.assertIn("reaction", r["blocked_intents"])
        self.assertTrue(r["sound_off"])
        self.assertEqual(r["rules"]["notes"], "keep it calm")

    def test_brand_outline_beats_pack_default(self):
        r = styles.resolve(self.prof(caption_outline={"enabled": False}))
        self.assertEqual(r["decorations"]["caption_outline"], {"on": False, "source": "brand"})

    def test_phase_a_profiles_keep_their_outline(self):
        p = self.prof(caption_outline={"enabled": False})
        p["captions"].pop("outline_source")          # saved before outlines had a source
        p["style"] = {"pack": "classic", "version": "1.0.0", "mix": [], "decorations": {}}
        self.assertFalse(styles.resolve(p)["decorations"]["caption_outline"]["on"])

    def test_direction_kept_for_the_creative_brief(self):
        p = self.prof(style={"pack": "classic", "direction": "Soft, editorial, like a calm magazine"})
        self.assertIn("calm magazine", styles.resolve(p)["direction"])

    def test_validation(self):
        for bad in ({"pack": "nope"}, {"mix": [{"pack": "plainpack"}]},
                    {"decorations": {"sparkles": True}}):
            with self.assertRaises(brand.AnswerError):
                brand._validate_extra("style", bad)
        with self.assertRaises(brand.AnswerError):
            brand._validate_extra("creative_rules", {"flags": ["no_fun"]})

    def test_rules_reach_the_plan_and_the_render_check(self):
        p = self.prof(graphics_elements=["emoji", "text_callouts"], sfx="playful",
                      creative_rules={"flags": ["no_emojis", "no_sound_effects"]})
        words = [{"text": t, "start": i * .4, "end": i * .4 + .3} for i, t in
                 enumerate("I love my camera so much. It costs 500 dollars.".split())]
        plan = planner.plan(words, 6.0, [], p)
        self.assertFalse([g for g in plan["graphics"] if g["type"] == "emoji"])
        self.assertEqual(plan["sfx"], [])
        self.assertTrue(all(g.get("intent") for g in plan["graphics"]))
        plan["graphics"].append({"id": "gx", "type": "emoji", "start": 1, "end": 2})
        page = overlay.page_data(dict(plan, graphics=[]), {"graphics": {}, "captions": {"y": 1300}}, p, 30)
        probs = conformance.check(plan, page, p)
        self.assertTrue(any("creative rule" in x for x in probs))

    def test_page_decorations_follow_rules(self):
        p = self.prof(creative_rules={"flags": ["no_glow", "no_boxes"]})
        page = overlay.page_data({"graphics": [], "captions": {"style": {}, "items": []}},
                                 {"graphics": {}, "captions": {"y": 1300}}, p, 30)
        self.assertFalse(page["decorations"]["caption_glow"])
        self.assertFalse(page["decorations"]["graphic_box"])
        self.assertTrue(page["decorations"]["caption_shadow"])


class Motion(unittest.TestCase):

    def node(self, js):
        r = subprocess.run(["node", "-e", f"const M = require({str(ROOT / 'tools' / 'motion.js')!r});{js}"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_every_primitive_ends_at_rest_and_is_deterministic(self):
        out = self.node("const o={}; for (const k of M.kinds) { o[k]=[M.css(M.state(k,1,k,1)), M.css(M.state(k,.37,k,1)), M.css(M.state(k,.37,k,1))]; } console.log(JSON.stringify(o));")
        self.assertGreaterEqual(len(out), 15)
        for k, (end, a, b) in out.items():
            self.assertEqual(a, b, k)                                       # same input, same output
            self.assertEqual(end["opacity"], "1", k)
            self.assertIn(end["clipPath"], ("none", "inset(0% 0 0 0)", "inset(0 0% 0 0)",
                                            "inset(0 0 0 0%)", "inset(0 0 0% 0)", "inset(0% 0 0% 0)"), k)
            self.assertEqual(end["filter"], "none", k)
            self.assertIn("scale(1, 1)", end["transform"], k)

    def test_fades_grow_and_exits_reverse(self):
        out = self.node("console.log(JSON.stringify([0,.25,.5,.75,1].map(p=>+M.css(M.state('rise',p,'fade',1)).opacity).concat([+M.css(M.state('rise',1,'fade',.3)).opacity])))")
        self.assertEqual(out[:5], sorted(out[:5]))
        self.assertLess(out[5], 1)

    def test_counter_and_stagger(self):
        out = self.node("console.log(JSON.stringify([M.counter('37%',1), M.counter('37%',0), M.counter('2.5x',1), M.stagger(1.2,1,2,.1,.3)]))")
        self.assertEqual(out[:3], ["37%", "0%", "2.5x"])
        self.assertAlmostEqual(out[3], 0.0, 3)

    def test_page_includes_motion_but_classic_kinds_unchanged(self):
        self.assertIn("/*MOTION*/", overlay.TEMPLATE)
        self.assertIn("LEGACY_MOTION", overlay.TEMPLATE)


if __name__ == "__main__":
    unittest.main()
