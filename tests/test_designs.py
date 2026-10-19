"""Stage 6: design variety - every design is drawn, choices are deterministic,
vary across a customer's reels, stay consistent within a reel, follow the plan,
and "Try another design" changes one graphic only. Classic never changes."""

import copy
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from laine_reel import brand, creative, designs, planner, styles  # noqa: E402
from laine_reel.project import read_json  # noqa: E402
from test_creative import DUR, W, good  # noqa: E402
from test_library import Env  # noqa: E402

SIX = ["luxe", "playful", "magazine", "minimal", "bold", "energetic"]
INTENTS = ["hook", "list", "stat", "cta", "quote", "contrast", "tip"]


class FakeReel:
    def __init__(self, base, name):
        self.root = Path(base) / name
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, n):
        return self.root / n


def _drawn_variants(js, comp):
    """Design ids a component draws: the top-level keys of its pick({...})."""
    i = js.find(f"reg('{comp}', pick({{")
    if i < 0:
        return set()
    i = js.index("{", i) + 1
    depth, top = 0, ""
    while depth >= 0:
        c = js[i]
        depth += c in "{([" and 1 or c in "})]" and -1 or 0
        if depth == 0 and c not in "})]":
            top += c
        i += 1
    return set(re.findall(r"(?:^|,)\s*(\w+)\s*(?=[:,]|$)", top.rstrip("}").strip()))


class Registry(unittest.TestCase):

    def test_every_listed_design_is_drawn(self):
        for pid in SIX:
            js = (ROOT / "styles" / pid / "1.0.0" / "components.js").read_text()
            variants = styles.load_pack(pid)["aspects"]["components"]["variants"]
            for intent, vs in variants.items():
                comp = styles.load_pack(pid)["aspects"]["components"]["by_intent"][intent].split(".", 1)[1]
                drawn = _drawn_variants(js, comp)
                for v in vs:
                    self.assertIn(v["id"], drawn, f"{pid}.{comp} design {v['id']}")

    def test_every_style_offers_all_seven_intents(self):
        for pid in SIX:
            variants = styles.load_pack(pid)["aspects"]["components"]["variants"]
            self.assertEqual(set(INTENTS) - set(variants), set(), pid)
            # the four core content intents each have at least two designs
            for intent in ("hook", "list", "stat", "cta"):
                self.assertGreaterEqual(len(variants[intent]), 2, f"{pid}.{intent}")

    def test_classic_has_no_designs(self):
        self.assertFalse(styles.load_pack("classic")["aspects"].get("components", {}).get("variants"))

    def test_suitability(self):
        bar = {"id": "bar", "fits": {"needs_percent": True}}
        self.assertTrue(designs.suits(bar, {"text": "80% of creators quit"}))
        self.assertFalse(designs.suits(bar, {"text": "3 tips"}))
        self.assertTrue(designs.suits({"id": "numeral"}, {"text": "3 tips"}))


class Selection(Env):

    def prof(self, pack="magazine", **a):
        base = dict(graphics_elements=["text_callouts", "keyword_cards", "lists", "cta_card", "emoji", "arrows"],
                    headline="opening_hook", sfx="playful", style={"pack": pack})
        base.update(a)
        return brand.compile_profile(dict(brand.load_progress()["answers"], **base))

    def edit(self, prof, brief=None):
        b = copy.deepcopy(brief or good())
        b, _ = creative.complete(b, W)
        creative.validate(b, W, prof, DUR)
        return planner.plan(W, DUR, [], prof, {}, brief=b)

    def reel(self, name):
        return FakeReel(self.dir / "reels", name)

    def chosen(self, e, intent):
        return next(g["variant"] for g in e["graphics"] if g.get("intent") == intent)

    def test_deterministic(self):
        # same reel, same plan, no history: the same designs every time (no chance involved)
        p = self.prof()
        r = self.reel("r1")
        first = designs.assign(r, self.edit(p), p)
        r.path("designs.json").unlink()
        self.assertEqual(designs.assign(r, self.edit(p), p), first)

    def test_varies_across_consecutive_reels(self):
        p = self.prof()
        seen = []
        for i in range(3):
            r, e = self.reel(f"reel{i}"), self.edit(p)
            designs.assign(r, e, p)
            designs.record(r, e, p)
            seen.append(self.chosen(e, "hook"))
        # magazine has three hook designs: three reels in a row use all three
        self.assertEqual(len(set(seen)), 3, seen)

    def test_pinned_reel_never_changes_when_others_are_made(self):
        p = self.prof()
        r1, e1 = self.reel("first"), self.edit(p)
        designs.assign(r1, e1, p)
        designs.record(r1, e1, p)
        before = self.chosen(e1, "hook")
        for i in range(3):
            r, e = self.reel(f"later{i}"), self.edit(p)
            designs.assign(r, e, p)
            designs.record(r, e, p)
        again = self.edit(p)
        designs.assign(r1, again, p)
        self.assertEqual(self.chosen(again, "hook"), before)

    def test_one_look_per_intent_within_a_reel(self):
        p = self.prof()
        b = good()
        b["moments"].append({"intent": "cta", "from": 30, "to": 33, "text": "What is stopping you?",
                             "why": "second ask", "source": "customer"})
        b["no_graphics"] = []
        e = self.edit(p, b)
        designs.assign(self.reel("one"), e, p)
        ctas = {g["variant"] for g in e["graphics"] if g.get("intent") == "cta"}
        self.assertEqual(len(ctas), 1)

    def test_plan_design_is_honoured_and_checked(self):
        p = self.prof()
        b = good()
        b["moments"][2]["design"] = "bar"            # "80% of creators quit": a bar suits a percentage
        e = self.edit(p, b)
        designs.assign(self.reel("planned"), e, p)
        self.assertEqual(self.chosen(e, "stat"), "bar")
        b["moments"][2]["design"] = "pie"
        with self.assertRaises(creative.BriefError) as cm:
            creative.validate(creative.complete(b, W)[0], W, p, DUR)
        self.assertTrue(any("pie" in x for x in cm.exception.problems))

    def test_bar_only_for_percentages(self):
        p = self.prof()
        b = good()
        # "under 10 minutes" is a number but not a percentage: a bar would mean nothing
        b["moments"][2].update(text="under 10 minutes", design="bar", **{"from": 17, "to": 22})
        del b["moments"][1]
        e = self.edit(p, b)
        designs.assign(self.reel("nobar"), e, p)
        self.assertEqual(self.chosen(e, "stat"), "numeral")

    def test_try_another_changes_one_graphic_only(self):
        p = self.prof()
        r, e = self.reel("another"), self.edit(p)
        designs.assign(r, e, p)
        before = {g["id"]: g["variant"] for g in e["graphics"] if g.get("variant")}
        hook = next(g for g in e["graphics"] if g.get("intent") == "hook")
        old, new = designs.another(r, e, hook["id"], p)
        self.assertNotEqual(old, new)
        e2 = self.edit(p)
        designs.assign(r, e2, p)
        after = {g["id"]: g["variant"] for g in e2["graphics"] if g.get("variant")}
        changed = {k for k in before if before[k] != after.get(k)}
        self.assertEqual(changed, {hook["id"]})
        # pressing it again keeps cycling through the style's hook designs
        for _ in range(2):
            designs.another(r, e2, hook["id"], p)
            e2 = self.edit(p)
            designs.assign(r, e2, p)
        self.assertEqual(next(g for g in e2["graphics"] if g["id"] == hook["id"])["variant"], before[hook["id"]])

    def test_classic_plan_is_untouched(self):
        p = self.prof(pack="classic")
        e = self.edit(p)
        snapshot = copy.deepcopy(e)
        r = self.reel("classic")
        self.assertEqual(designs.assign(r, e, p), {})
        self.assertEqual(e, snapshot)
        self.assertFalse(r.path("designs.json").exists())
        designs.record(r, e, p)
        self.assertFalse(designs.history_path().exists())

    def test_context_lists_designs_and_recent_reels(self):
        p = self.prof()
        r, e = self.reel("ctx"), self.edit(p)
        designs.assign(r, e, p)
        designs.record(r, e, p)
        ctx = creative.context(W, DUR, p, None, "next-reel")
        self.assertTrue(ctx["designs"]["available"])
        self.assertIn("bar", [v["id"] for v in ctx["designs"]["by_intent"]["stat"]])
        self.assertEqual(len(ctx["designs"]["recent_reels"]), 1)
        self.assertFalse(creative.context(W, DUR, self.prof(pack="classic"))["designs"]["available"])

    def test_new_intents_validate(self):
        p = self.prof()
        b = good()
        b["moments"] = b["moments"][:1] + [
            {"intent": "contrast", "from": 23, "to": 29, "before": "creators quit", "after": "you keep going",
             "text": "x", "why": "contrast"}]
        probs = []
        try:
            creative.validate(creative.complete(b, W)[0], W, p, DUR)
        except creative.BriefError as e:
            probs = e.problems
        # "you keep going" was never said: the editor must refuse invented words
        self.assertTrue(any("keep" in x or "said" in x for x in probs), probs)
        b["moments"][1].update(after="80% of creators quit")
        b["moments"][1]["before"] = "better videos"
        creative.validate(creative.complete(b, W)[0], W, p, DUR)
        e = self.edit(p, b)
        g = next(x for x in e["graphics"] if x.get("intent") == "contrast")
        self.assertEqual((g["before"], g["after"]), ("better videos", "80% of creators quit"))
        self.assertEqual(g["component"], "magazine.contrast")


if __name__ == "__main__":
    unittest.main()
