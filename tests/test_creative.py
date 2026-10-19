"""Stage 3: Claude's creative plan - validation, planning, re-anchoring."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, creative, planner  # noqa: E402
from test_library import Env  # noqa: E402

TEXT = ("Here are three tips for better videos. First, film near a window. Second, use the back camera. "
        "Third, edit in under 10 minutes. Did you know 80% of creators quit? What is stopping you? "
        "Comment guide below.")


def words_of(text, gap=0.36):
    return [{"text": t, "start": round(i * gap, 3), "end": round(i * gap + gap * .8, 3)}
            for i, t in enumerate(text.split())]


W = words_of(TEXT)
DUR = W[-1]["end"] + 0.5


def good():
    return {"version": 1, "summary": "Three quick tips for better videos, then a nudge to start",
            "tone": "practical, encouraging",
            "beats": [{"type": "hook", "from": 0, "to": 6}, {"type": "step", "from": 7, "to": 22},
                      {"type": "proof", "from": 23, "to": 29}, {"type": "cta", "from": 34, "to": 36}],
            "key_words": [5, 11, 16, 21, 26],
            "moments": [
                {"intent": "hook", "from": 0, "to": 6, "quote": "Here are three tips for better videos.",
                 "text": "3 tips for better videos", "why": "the promise"},
                {"intent": "list", "from": 7, "to": 22, "why": "they enumerate three tips",
                 "items": [{"text": "Film near a window", "at_word": 7}, {"text": "Use the back camera", "at_word": 12},
                           {"text": "Edit in under 10 minutes", "at_word": 17}]},
                {"intent": "stat", "from": 23, "to": 29, "text": "80% of creators quit", "why": "proof beat"},
                {"intent": "cta", "from": 34, "to": 36, "text": "Comment GUIDE", "why": "the ask"}],
            "no_graphics": [{"from": 30, "to": 33, "why": "a direct question to the viewer: face only"}],
            "zooms": [{"from": 23, "to": 29, "kind": "punch", "why": "the number lands"}]}


class Creative(Env):

    def prof(self, **a):
        base = dict(graphics_elements=["text_callouts", "keyword_cards", "lists", "cta_card", "emoji", "arrows"],
                    headline="opening_hook", sfx="playful")
        base.update(a)
        return brand.compile_profile(dict(brand.load_progress()["answers"], **base))

    def problems(self, brief, prof=None):
        try:
            creative.validate(brief, W, prof or self.prof(), DUR)
            return []
        except creative.BriefError as e:
            return e.problems

    # -- accepted plans --------------------------------------------------------------
    def test_good_plan_validates_and_becomes_the_graphics(self):
        p = self.prof()
        self.assertEqual(self.problems(good(), p), [])
        plan = planner.plan(W, DUR, [], p, brief=good())
        g = [x for x in plan["graphics"] if x["source"] == "brief"]
        self.assertEqual([x["brief_intent"] for x in g], ["hook", "list", "stat", "cta"])
        self.assertEqual(g[0]["text"], "3 tips for better videos")
        self.assertEqual(g[0]["role"], "headline")
        self.assertEqual([round(i["at"], 2) for i in g[1]["items"]], [W[7]["start"], W[12]["start"], W[17]["start"]])
        self.assertEqual(g[2]["start"], W[23]["start"])
        self.assertEqual(g[3]["end"], round(DUR, 3))             # a CTA stays to the end
        self.assertTrue(all(x["why"] for x in g))
        self.assertEqual([z["reason"] for z in plan["zooms"]], ["the number lands"])
        self.assertEqual(plan["zooms"][0]["type"], "punch")

    def test_key_words_drive_caption_highlights(self):
        plan = planner.plan(W, DUR, [], self.prof(), brief=good())
        hi = [w["text"].strip(".,?") for c in plan["captions"]["items"] for w in c["words"] if w.get("emphasis")]
        self.assertEqual(hi, ["better", "window", "camera", "10", "80%"])

    def test_spoken_captions_never_change(self):
        a = planner.plan(W, DUR, [], self.prof())
        b = planner.plan(W, DUR, [], self.prof(), brief=good())
        strip = lambda p: [(w["text"], w["start"], w["end"]) for c in p["captions"]["items"] for w in c["words"]]
        self.assertEqual(strip(a), strip(b))

    def test_nothing_is_a_valid_choice(self):
        p = self.prof(headline="none")
        b = dict(good(), moments=[])
        self.assertEqual(self.problems(b, p), [])
        plan = planner.plan(W, DUR, [], p, brief=b)
        self.assertEqual([x for x in plan["graphics"] if x["source"] == "brief"], [])

    def test_customer_wording_and_requests_are_allowed(self):
        b = good()
        b["moments"][0].update(text="Stop scrolling, creator", source="customer")
        b["moments"].append({"intent": "lower_third", "from": 30, "to": 33, "text": "@yourbrand",
                             "source": "customer", "why": "she asked for her handle here"})
        self.assertEqual(self.problems(b), [])   # lower_third isn't one of her elements, but she asked

    def test_review_edits_apply_on_top_and_styles_draw_it(self):
        p = self.prof(style={"pack": "bold"})
        plan = planner.plan(W, DUR, [], p, overrides={"set": {"g3": {"text": "80% QUIT"}}}, brief=good())
        stat = next(x for x in plan["graphics"] if x["id"] == "g3")
        self.assertEqual(stat["text"], "80% QUIT")
        self.assertEqual(stat["component"], "bold.stat")

    # -- rejected plans ------------------------------------------------------------------
    def assertRejects(self, brief, needle, prof=None):
        probs = self.problems(brief, prof)
        self.assertTrue(any(needle in x for x in probs), f"expected '{needle}' in {probs}")

    def test_invented_numbers_rejected(self):
        b = good(); b["moments"][2]["text"] = "90% of creators quit"
        self.assertRejects(b, "never invent numbers")

    def test_invented_words_rejected(self):
        b = good(); b["moments"][2]["text"] = "80% of influencers fail"
        self.assertRejects(b, "words not said")

    def test_too_long_to_read_rejected(self):
        b = good(); b["moments"][0]["text"] = "Here are three tips for better videos that work"
        self.assertRejects(b, "too long to read")

    def test_rules_and_brand_choices_enforced(self):
        b = good()
        b["moments"].append({"intent": "reaction", "from": 30, "to": 31, "emoji": "😮", "why": "surprise"})
        self.assertRejects(b, "not available", self.prof(creative_rules={"flags": ["no_emojis"]}))
        b2 = good()
        b2["moments"].append({"intent": "pointer", "from": 34, "to": 36, "direction": "down", "why": "points"})
        self.assertRejects(b2, "not available", self.prof(graphics_elements=["text_callouts", "lists", "cta_card"]))

    def test_every_choice_needs_a_reason(self):
        b = good(); b["moments"][3]["why"] = ""
        self.assertRejects(b, "needs a \"why\"")

    def test_no_crowding(self):
        b = good(); b["moments"][2].update({"from": 20, "to": 29})
        self.assertRejects(b, "overlap")

    def test_headline_required_when_the_brand_has_one(self):
        b = good(); b["moments"] = b["moments"][1:]
        self.assertRejects(b, "opening headline")

    def test_quote_must_match_and_key_words_must_matter(self):
        b = good(); b["moments"][0]["quote"] = "here are four tips"
        self.assertRejects(b, "quote doesn't match")
        b = good(); b["key_words"] = [1]
        self.assertRejects(b, "filler word")

    def test_quiet_stretches_stay_quiet(self):
        plan = planner.plan(W, DUR, [], self.prof(), brief=good())
        stat = next(x for x in plan["graphics"] if x.get("brief_intent") == "stat")
        self.assertLessEqual(stat["end"], W[30]["start"])        # ends before the questions begin
        b = good(); b["no_graphics"] = [{"from": 25, "to": 33, "why": "face only"}]
        self.assertRejects(b, "marked for no graphic")

    def test_stat_needs_its_number(self):
        b = good(); b["moments"][2]["text"] = "Most creators quit"
        self.assertRejects(b, "needs the number")

    # -- re-cuts ------------------------------------------------------------------------
    def test_new_plan_is_for_the_current_cut(self):
        b = good()
        b["moments"][1].pop("quote", None)
        b2, fresh = creative.complete(copy.deepcopy(b), W)
        self.assertTrue(fresh)
        self.assertEqual(b2["cut_signature"], creative.cut_signature(W))
        self.assertTrue(b2["moments"][1]["quote"].startswith("First, film"))
        b3, notes = creative.reanchor(b2, W)
        self.assertEqual(notes, [])
        self.assertEqual(b3["key_words"], b["key_words"])

    def test_recut_reanchors_by_quote(self):
        b = good(); b["moments"][2]["quote"] = "Did you know 80% of creators quit?"
        b = creative.save.__wrapped__(b) if hasattr(creative.save, "__wrapped__") else dict(b, cut_signature=creative.cut_signature(W))
        cut = words_of(" ".join(w["text"] for w in W[7:]))       # the hook sentence was cut
        b2, notes = creative.reanchor(copy.deepcopy(b), cut)
        stat = next(m for m in b2["moments"] if m["intent"] == "stat")
        self.assertEqual((stat["from"], stat["to"]), (16, 22))
        self.assertTrue(any("dropped hook" in n for n in notes))
        self.assertTrue(any("key words reset" in n for n in notes))
        self.assertNotIn("zooms", b2)


if __name__ == "__main__":
    unittest.main()
