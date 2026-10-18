"""Unit tests for content cleanup (repeats, fillers, restarts)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import cleanup, config, pauses  # noqa: E402

NATURAL = config.PACING["natural"]


def words_from(spec):
    """'Some@6.64-6.82 of@6.82-7.0' -> word dicts."""
    out = []
    for item in spec.split():
        text, t = item.rsplit("@", 1)
        a, b = t.split("-")
        out.append({"text": text.replace("_", " "), "start": float(a), "end": float(b)})
    return out


def W(texts):
    return [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, t in enumerate(texts)]


def auto(cands):
    return [(c["type"], c["words"]) for c in cands if c["auto"]]


class Detect(unittest.TestCase):
    def test_triple_restart_keeps_last(self):
        w = W("Some of y'all, some of y'all, some of y'all are not waiting".split())
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [0, 5])])

    def test_two_word_restart(self):
        w = W("random? The real, the real skill is".split())
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [1, 2])])

    def test_stutter_single_word(self):
        w = W("I think the the camera".split())
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [2, 2])])

    def test_emphatic_double_kept(self):
        self.assertEqual(auto(cleanup.detect(W("it is very very good".split()))), [])
        self.assertEqual(auto(cleanup.detect(W("no no no".split()))), [])

    def test_repeated_full_sentence_kept(self):
        # deliberate rhetorical repetition of a complete sentence
        self.assertEqual(auto(cleanup.detect(W("Stop scrolling. Stop scrolling.".split()))), [])

    def test_fillers(self):
        c = cleanup.detect(W("So, um, the uh thing".split()))
        self.assertEqual(auto(c), [("filler", [1, 1]), ("filler", [3, 3])])

    def test_style_words_only_flagged(self):
        c = cleanup.detect(W("standing there like, okay".split()))
        self.assertEqual(auto(c), [])
        self.assertEqual([x["type"] for x in c], ["soft_filler"])

    def test_cut_off_restart(self):
        w = W("So I was going- So the point is light.".split())
        self.assertEqual(auto(cleanup.detect(w)), [("false_start", [0, 3])])

    def test_cut_off_restart_after_a_comma(self):
        # real case: "...your audience has, building trust or giving a people-
        #             building trust or giving people a reason to buy"
        w = W("a problem your audience has, building trust or giving a people- building "
              "trust or giving people a reason to buy,".split())
        self.assertEqual(auto(cleanup.detect(w)), [("false_start", [5, 10])])

    def test_cut_off_without_restart_only_flagged(self):
        c = cleanup.detect(W("It was the- honestly it works.".split()))
        self.assertEqual(auto(c), [])
        self.assertIn("false_start", [x["type"] for x in c])

    def test_review_adds_and_vetoes(self):
        w = W("Meet me Tuesday, I mean Wednesday, at noon. the the end".split())
        cands = cleanup.detect(w)
        review = {"remove": [{"from": 2, "to": 4, "reason": "self-correction"}],
                  "keep": [cands[0]["id"]]}
        merged = cleanup.merge_review(cands, review, w)
        self.assertEqual(auto(merged), [("review", [2, 4])])


class CaptionFixesDontChangeCuts(unittest.TestCase):
    def test_curly_apostrophe_still_a_repeat(self):
        w = W("Some of y'all, some of y\u2019all, some of y'all are here".split())
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [0, 5])])

    def test_fixed_spelling_uses_what_was_heard(self):
        w = W("the the camera".split())
        w[1] = dict(w[1], text="THE", heard="the")
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [0, 0])])
        w[1] = dict(w[1], text="lens", heard="the")  # a caption fix, not speech
        self.assertEqual(auto(cleanup.detect(w)), [("repeat", [0, 0])])


class RequestedPauseCut(unittest.TestCase):
    words = words_from("record.@16.92-17.058 And@24.6-24.8")
    # silence, a 65 ms breath, more silence: the real shape from the test clip
    quiet = [{"start": 17.058, "end": 17.546}, {"start": 17.611, "end": 24.394}]

    def test_breath_inside_a_requested_pause_goes_too(self):
        cut, why = cleanup.pause_cut(self.words, 0, self.quiet, NATURAL)
        self.assertEqual(why, "ok")
        self.assertLess(cut["start"], 17.546)   # starts before the breath
        self.assertGreater(cut["end"], 24.0)    # ends after it
        remaining = (24.394 - 17.058) - (cut["end"] - cut["start"])
        self.assertAlmostEqual(remaining, cleanup.REQUESTED_KEEP, delta=0.01)

    def test_real_sound_stops_the_cut(self):
        quiet = [{"start": 17.058, "end": 17.546}, {"start": 18.2, "end": 24.394}]
        cut, _ = cleanup.pause_cut(self.words, 0, quiet, NATURAL)
        self.assertLessEqual(cut["end"], 17.546)


class Place(unittest.TestCase):
    # Real timings from the test clip ("Some of y'all" x3).
    words = words_from("Some@6.64-6.82 of@6.82-7.0 y'all,@7.0-7.88 some@7.88-8.04 "
                       "of@8.04-8.09 y'all,@8.24-8.423 some@9.06-9.12 of@9.26-9.38 "
                       "y'all@9.38-9.62 are@9.62-9.78")
    gaps = [{"start": 0.0, "end": 6.322}, {"start": 7.244, "end": 7.59},
            {"start": 8.423, "end": 8.788}, {"start": 9.9, "end": 10.2}]

    def test_restart_cut_lands_in_gaps(self):
        cands = cleanup.detect(self.words)
        cuts, dec = cleanup.place(cands, self.words, self.gaps, NATURAL)
        self.assertTrue(dec["c1"]["applied"])
        (cut,) = cuts
        self.assertEqual(cut["start"], 0.0)
        self.assertTrue(8.423 <= cut["end"] <= 8.788)  # inside the gap before "some are"

    def test_no_gap_means_left_in(self):
        cands = cleanup.detect(self.words)
        cuts, dec = cleanup.place(cands, self.words, self.gaps[:2], NATURAL)
        self.assertEqual(cuts, [])
        self.assertFalse(dec["c1"]["applied"])
        self.assertIn("gap", dec["c1"]["why"])

    def test_too_much_speech_between_gaps_means_left_in(self):
        # "the the" with no pause between them: the nearest gaps enclose far
        # more speech than one word, so the cut would eat real words.
        w = words_from("I@1.0-1.2 think@1.2-1.5 the@1.5-1.6 the@1.6-1.7 camera@1.7-2.2 "
                       "is@2.2-2.4 key.@2.4-2.9")
        gaps = [{"start": 0.0, "end": 0.95}, {"start": 2.95, "end": 3.5}]
        cuts, dec = cleanup.place(cleanup.detect(w), w, gaps, NATURAL)
        self.assertEqual(cuts, [])
        self.assertFalse(list(dec.values())[0]["applied"])

    def test_planner_merges_content_and_pause_cuts(self):
        cands = cleanup.detect(self.words)
        cuts, _ = cleanup.place(cands, self.words, self.gaps, NATURAL)
        plan = pauses.plan_cuts(12.0, [{"start": 0.0, "end": 6.322}], NATURAL, fps=24,
                                extra_cuts=cuts, quiet=self.gaps)
        self.assertEqual(plan["stats"]["content_cuts"], 1)
        self.assertTrue(8.4 <= plan["keep"][0][0] <= 8.8)


class Tokens(unittest.TestCase):
    def test_quotes_split(self):
        self.assertEqual(cleanup.tokens([{"text": 'comment"content".'}]), ["comment", "content"])


if __name__ == "__main__":
    unittest.main()
