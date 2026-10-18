"""Unit tests for brand onboarding and edit planning (no media needed)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import brand, planner, reference  # noqa: E402

ANSWERS = [
    ("colors", "blush pink, #C9A227 and cream"), ("fonts", "2"), ("headline", "opening hook"),
    ("caption_style", "karaoke"), ("caption_position", "lower third"),
    ("caption_size", "large"), ("caption_animation", "pop"), ("caption_emphasis", "1"),
    ("caption_case", "as spoken"), ("caption_color", "1"), ("pacing", "tight"), ("zoom_style", "mixed"),
    ("zoom_frequency", "moderate"), ("graphics_density", "balanced"),
    ("graphics_elements", "sticky notes, text callouts, key-phrase cards, emoji, cta card"),
    ("sticky_font", "hand"), ("sfx", "subtle"), ("music", "soft"), ("aesthetic", "soft luxe"),
    ("personality", "warm, confident, real"), ("handle", "@test"), ("reference_reel", "skip"),
]


class TempBrand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("LAINE_BRAND_DIR")
        os.environ["LAINE_BRAND_DIR"] = self.dir

    def tearDown(self):
        if self.old is None:
            os.environ.pop("LAINE_BRAND_DIR", None)
        else:
            os.environ["LAINE_BRAND_DIR"] = self.old
        shutil.rmtree(self.dir)

    def onboard(self, overrides=None):
        for qid, text in ANSWERS:
            q = brand.next_question()
            if q is None:
                break
            if q["id"] != qid:
                continue
            brand.answer(qid, (overrides or {}).get(qid, text))
        return brand.finish()


class Parsing(unittest.TestCase):
    def test_colors_hex_and_names_in_order(self):
        self.assertEqual(brand.parse_colors("#e8b4b8, sage and black"),
                         ["#E8B4B8", "#A3B18A", "#111111"])
        self.assertEqual(brand.parse_colors("blush pink / gold"), ["#F2C6C2", "#C9A227"])
        self.assertEqual(brand.parse_colors("rose gold"), ["#B76E79"])

    def test_unknown_color_rejected_with_help(self):
        with self.assertRaises(brand.AnswerError) as e:
            brand.parse_colors("sparkly unicorn")
        self.assertIn("hex", str(e.exception))

    def test_choice_by_number_value_or_label(self):
        self.assertEqual(brand.parse_answer("pacing", "2"), "tight")
        self.assertEqual(brand.parse_answer("pacing", "fast"), "fast")
        self.assertEqual(brand.parse_answer("zoom_style", "Punchy snap zooms"), "punchy")
        with self.assertRaises(brand.AnswerError):
            brand.parse_answer("pacing", "glacial")

    def test_multi_select(self):
        self.assertEqual(brand.parse_answer("graphics_elements", "emoji, sticky notes and cta card"),
                         ["emoji", "sticky_notes", "cta_card"])

    def test_fonts(self):
        self.assertEqual(brand.parse_answer("fonts", "1"),
                         {"headline": "Montserrat", "body": "Inter"})
        self.assertEqual(brand.parse_answer("fonts", "Josefin Sans / Lato"),
                         {"headline": "Josefin Sans", "body": "Lato"})

    def test_caption_colour_answers(self):
        base = dict(ANSWERS)
        for key, (text, kw) in {"white_primary_keywords": ("#FFFFFF", "#F2C6C2"),
                                "white_accent_keywords": ("#FFFFFF", "#C9A227"),
                                "primary": ("#F2C6C2", None), "white": ("#FFFFFF", None)}.items():
            a = {k: brand.parse_answer(k, v) for k, v in base.items()
                 if k != "reference_reel"}
            a["caption_color"] = key
            p = brand.compile_profile(a)
            self.assertEqual((p["colors"]["caption_text"], p["colors"]["caption_keyword"]),
                             (text, kw), key)

    def test_contrast_picks_readable_text(self):
        self.assertEqual(brand.readable_on("#F5EFE6"), "#111111")
        self.assertEqual(brand.readable_on("#1B2A4A"), "#FFFFFF")


class Onboarding(TempBrand):
    def test_one_question_at_a_time_and_resume(self):
        q = brand.next_question()
        self.assertEqual((q["id"], q["number"]), ("colors", 1))
        brand.answer("colors", "navy, gold")
        # a fresh call (new session) resumes where we left off
        self.assertEqual(brand.next_question()["id"], "fonts")
        self.assertTrue((Path(self.dir) / "onboarding.json").exists())

    def test_total_is_stable(self):
        totals = set()
        for qid, text in ANSWERS:
            q = brand.next_question()
            if q is None:
                break
            totals.add(q["total"])
            brand.answer(q["id"], dict(ANSWERS)[q["id"]])
        self.assertEqual(len(totals), 1)

    def test_no_captions_skips_caption_questions(self):
        brand.answer("colors", "black, white")
        brand.answer("fonts", "1")
        brand.answer("headline", "none")
        brand.answer("caption_style", "none")
        self.assertEqual(brand.next_question()["id"], "pacing")

    def test_finish_writes_profile_and_summary(self):
        p = self.onboard()
        self.assertTrue((Path(self.dir) / "brand.json").exists())
        self.assertTrue((Path(self.dir) / "brand.md").exists())
        self.assertEqual(p["colors"]["primary"], "#F2C6C2")
        self.assertEqual(p["colors"]["accent"], "#C9A227")
        self.assertEqual(p["captions"]["style"], "karaoke")
        self.assertEqual(p["pacing"], "tight")
        self.assertIn("cta_card", p["graphics"]["elements"])

    def test_refinishing_keeps_previous_profile(self):
        self.onboard()
        brand.answer("pacing", "fast")
        brand.finish()
        prev = json.loads((Path(self.dir) / "brand.previous.json").read_text())
        self.assertEqual(prev["pacing"], "tight")

    def test_incomplete_cannot_finish(self):
        brand.answer("colors", "navy")
        with self.assertRaises(brand.AnswerError):
            brand.finish()


def W(text, start, dur=0.3, gap=0.05):
    out, t = [], start
    for tok in text.split():
        out.append({"text": tok, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + gap
    return out


class Planning(TempBrand):
    def setUp(self):
        super().setUp()
        self.profile = self.onboard()
        self.words = (W("Some of y'all are not waiting on a better camera.", 0.4)
                      + W("Where do I put it?", 4.5) + W("What angle do I get?", 6.5)
                      + W("That's why I made the Morning Light Studio.", 9.0)
                      + W('If you want it, comment "content".', 14.0))
        self.duration = 17.0
        self.joins = [4.4, 9.0, 13.9]

    def edit(self, **brand_changes):
        b = dict(self.profile, **brand_changes)
        return planner.plan(self.words, self.duration, self.joins, b)

    def test_captions_cover_every_word_in_order(self):
        e = self.edit()
        said = [w["text"] for c in e["captions"]["items"] for w in c["words"]]
        self.assertEqual(said, [w["text"] for w in self.words])
        for a, b in zip(e["captions"]["items"], e["captions"]["items"][1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-6)

    def test_short_word_does_not_ride_across_a_pause(self):
        from laine_reel import planner as P
        w = [{"text": "to", "start": 0.0, "end": 0.15}, {"text": "edit", "start": 0.6, "end": 0.9},
             {"text": "it.", "start": 0.92, "end": 1.1}]
        chunks = P._word_pop_chunks(w, [[0, 1, 2]])
        self.assertEqual(chunks, [[0], [1], [2]])
        w[1]["start"] = 0.2   # no pause: "to edit" together
        self.assertEqual(P._word_pop_chunks(w, [[0, 1, 2]]), [[0, 1], [2]])

    def test_caption_lines_fit_and_dont_dangle(self):
        e = self.edit()
        limit = self.profile["captions"]["max_chars_per_line"] * self.profile["captions"]["max_lines"]
        for c in e["captions"]["items"]:
            self.assertLessEqual(len(c["text"]), limit, c["text"])
            if len(c["words"]) > 1:
                self.assertNotIn(c["words"][-1]["text"].lower(), {"the", "a", "to", "of"})

    def test_one_emphasis_word_per_sentence_at_most(self):
        e = self.edit()
        per_sentence = {}
        for c in e["captions"]["items"]:
            for w in c["words"]:
                if w["emphasis"]:
                    per_sentence.setdefault(round(w["start"]), 0)
        self.assertTrue(per_sentence)

    def test_captions_off(self):
        caps = dict(self.profile["captions"], enabled=False)
        self.assertEqual(self.edit(captions=caps)["captions"]["items"], [])

    def test_graphics_from_transcript(self):
        g = {x["type"]: x for x in self.edit()["graphics"]}
        self.assertEqual(g["cta_card"]["text"], 'Comment "CONTENT"')
        self.assertEqual(len(g["sticky_notes"]["items"]), 2)
        self.assertEqual(g["keyword_cards"]["text"], "Morning Light Studio")
        self.assertTrue(g["text_callouts"]["draft"])  # hook: Claude rewrites it

    def test_each_emoji_once_and_only_counted_when_shown(self):
        words = (W("Post post post now.", 0.2) + W("Your content matters.", 4.0)
                 + W("Great content wins.", 9.0))
        gfx = dict(self.profile["graphics"], elements=["emoji"])
        e = planner.plan(words, 13.0, [], dict(self.profile, graphics=gfx,
                                               headline={"style": "opening_hook"}))
        emojis = [g["emoji"] for g in e["graphics"] if g["type"] == "emoji"]
        self.assertEqual(emojis.count("📲"), 1)   # shown once, not lost behind the headline

    def test_graphics_only_chosen_elements(self):
        gfx = dict(self.profile["graphics"], elements=["cta_card"])
        types = {x["type"] for x in self.edit(graphics=gfx)["graphics"]}
        # the headline is its own setting, not one of the graphics elements
        self.assertEqual(types, {"cta_card", "text_callouts"})

    def test_headline_follows_its_own_setting(self):
        none = {x["type"] for x in self.edit(headline={"style": "none"})["graphics"]}
        self.assertNotIn("text_callouts", none)
        hook = [g for g in self.edit(headline={"style": "opening_hook"})["graphics"]
                if g.get("role") == "headline"]
        self.assertEqual([g["type"] for g in hook], ["text_callouts"])
        self.assertLessEqual(hook[0]["end"], 3.5)
        both = [g["type"] for g in self.edit(headline={"style": "both"})["graphics"]
                if g.get("role") == "headline"]
        self.assertEqual(sorted(both), ["headline_bar", "text_callouts"])

    def test_headline_even_without_graphics(self):
        gfx = dict(self.profile["graphics"], elements=[])
        e = self.edit(graphics=gfx, headline={"style": "opening_hook"})
        self.assertEqual([g["type"] for g in e["graphics"]], ["text_callouts"])

    def test_spoken_list_becomes_checklist(self):
        words = W("I'll show you how to film, edit, and turn your content into gold.", 0.0)
        items = planner.spoken_list(words, list(range(len(words))))
        self.assertEqual([i["text"] for i in items], ["Film", "Edit", "Turn your content"])
        self.assertEqual(items[1]["at"], words[6]["start"])  # "edit,"
        gfx = dict(self.profile["graphics"], elements=["lists"])
        e = planner.plan(words, 6.0, [], dict(self.profile, graphics=gfx,
                                              headline={"style": "none"}))
        self.assertEqual([g["type"] for g in e["graphics"]], ["lists"])

    def test_zooms_hide_cuts_and_never_overlap_or_flicker(self):
        z = self.edit()["zooms"]
        self.assertTrue(any(x["reason"] == "hides the jump cut" for x in z))
        for a, b in zip(z, z[1:]):
            self.assertLessEqual(a["end"], b["start"])
        self.assertTrue(all(x["end"] - x["start"] >= planner.MIN_ZOOM_S for x in z))

    def test_no_zooms_when_off(self):
        zs = dict(self.profile["zooms"], style="none")
        self.assertEqual(self.edit(zooms=zs)["zooms"], [])

    def test_sfx_follow_profile_and_spacing(self):
        e = self.edit()
        kinds = {s["kind"] for s in e["sfx"]}
        self.assertTrue(kinds <= {"whoosh", "ding"})  # "subtle": no pops
        times = [s["at"] for s in e["sfx"]]
        self.assertTrue(all(b - a >= 1.2 for a, b in zip(times, times[1:])))
        self.assertTrue(all(s["file"] and not s["needs_asset"] for s in e["sfx"]))  # generated pack

    def test_overrides_survive_replanning(self):
        ov = {"remove": ["g1"], "set": {"g2": {"text": "Custom"}}}
        e = planner.plan(self.words, self.duration, self.joins, self.profile, ov)
        ids = {g["id"]: g for g in e["graphics"]}
        self.assertNotIn("g1", ids)
        self.assertEqual(ids["g2"]["text"], "Custom")

    def test_never_plans_drawtext(self):
        e = self.edit()
        methods = " ".join(r["method"] for r in e["render_requirements"])
        self.assertIn("overlay", methods)
        self.assertNotIn("drawtext", " ".join(" ".join(r["ffmpeg_filters"])
                                               for r in e["render_requirements"]))


class Reference(unittest.TestCase):
    def test_cut_detection_ignores_motion(self):
        # jump cuts at 2.0 and 5.0 among gentle motion noise
        scores = [(i / 24, 0.01 + (0.004 if i % 7 == 0 else 0)) for i in range(24 * 8)]
        scores[48] = (2.0, 0.09)
        scores[120] = (5.0, 0.12)
        scores[150] = (6.25, 0.035)  # below the floor: gesture, not a cut
        self.assertEqual(reference.find_cuts(scores), [2.0, 5.0])

    def test_suggestions(self):
        self.assertEqual(reference.suggest(4, 130)["pacing"], "natural")
        self.assertEqual(reference.suggest(12, 160)["pacing"], "tight")
        self.assertEqual(reference.suggest(25, 190)["zoom_frequency"], "frequent")


if __name__ == "__main__":
    unittest.main()
