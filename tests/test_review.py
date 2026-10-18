"""Phase 4: review feedback, applying it, and the local review server."""

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from laine_reel import planner, review, timeline  # noqa: E402
from laine_reel.project import Reel, read_json, write_json  # noqa: E402
from laine_reel.review_server import make_handler  # noqa: E402

KEEP = [[0.0, 2.0], [3.0, 6.0]]


def W(i, text, s, e):
    return {"text": text, "start": s, "end": e, "i": i}


def make_reel(root):
    """A tiny reel folder with just the files the review needs."""
    root = Path(root)
    for d in ("source", "output", "work"):
        (root / d).mkdir(parents=True)
    (root / "output" / "tiny-final.mp4").write_bytes(b"0123456789" * 100)
    write_json(root / "reel.json", {"name": "tiny", "original": "source/original.mov",
                                    "input": {"sha256": "x"}, "stages": {}})
    words = [{"text": t, "start": s, "end": e} for t, s, e in
             [("Hello", 0.2, 0.6), ("there,", 0.7, 1.2), ("um", 1.4, 1.6),
              ("friends.", 3.2, 3.8), ("Comment", 4.0, 4.4), ("now.", 4.5, 4.9)]]
    write_json(root / "transcript.json", {"words": words})
    out = [dict(w, i=i, start=timeline.source_to_output(w["start"], KEEP),
                end=timeline.source_to_output(w["end"], KEEP), source_start=w["start"],
                source_end=w["end"]) for i, w in enumerate(words) if i != 2]
    write_json(root / "transcript.cut.json", {"words": out})
    write_json(root / "edl.json", {"keep": KEEP, "cuts": [{"start": 2.0, "end": 3.0, "kind": "pause"}],
                                   "stats": {"output_duration": 5.0}, "fps": "24"})
    write_json(root / "cleanup.json", {"candidates": [
        {"id": "c1", "type": "filler", "words": [2, 2], "text": "um", "auto": True,
         "decision": {"applied": True}}], "removed_words": [2]})
    write_json(root / "edit.json", {"captions": {"items": [], "style": {}}, "zooms": [], "sfx": [],
                                    "graphics": [{"id": "g1", "type": "text_callouts", "role": "headline",
                                                  "start": 0, "end": 2, "text": "draft", "style": {}},
                                                 {"id": "g2", "type": "emoji", "start": 3.5, "end": 4.5,
                                                  "emoji": "📸", "style": {}}]})
    return Reel(root)


class Times(unittest.TestCase):
    def test_output_to_source_inverts(self):
        for t in (0.0, 1.5, 2.0, 2.5, 4.9):
            src = review.output_to_source(t, KEEP)
            self.assertAlmostEqual(timeline.source_to_output(src, KEEP), t, places=3)


class Apply(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.reel = make_reel(Path(self.dir) / "tiny")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_full_feedback(self):
        fb = {"notes": [{"t": 1.0, "text": "make it pop here"}],
              "cuts": {"keep": ["c1"], "remove": [], "remove_words": [[4, 4]], "cut_pauses": [1]},
              "captions": {"0": {"text": "Hallo"}, "3": {"start_out": 2.3}},
              "headline": {"text": "you need this"},
              "graphics": {"g2": {"emoji": "🎬", "background": "#FFFFFF", "animation": "bounce"}},
              "add": {"graphics": [{"type": "emoji", "t": 1.0, "duration": 2, "emoji": "🔥"}],
                      "zooms": [{"type": "push", "t": 3.0, "duration": 2}],
                      "sfx": [{"kind": "pop", "t": 1.0}]}}
        review.save_feedback(self.reel, fb)
        res = review.apply_feedback(self.reel)
        self.assertEqual(res["needs"], "recut")
        self.assertEqual([n["text"] for n in res["notes"]], ["make it pop here"])
        rv = read_json(self.reel.path("cleanup.review.json"))
        self.assertIn("c1", rv["keep"])
        self.assertEqual([(r["from"], r["to"]) for r in rv["remove"]], [(4, 4)])
        self.assertEqual(rv["pause_cuts"], [1])
        fixes = read_json(self.reel.path("transcript.fixes.json"))["words"]
        self.assertEqual(fixes["0"]["text"], "Hallo")
        self.assertAlmostEqual(fixes["3"]["start"], review.output_to_source(2.3, KEEP))
        ov = read_json(self.reel.path("edit.overrides.json"))
        self.assertEqual(ov["headline"]["text"], "you need this")
        self.assertEqual(ov["set"]["g2"]["style"], {"custom_background": "#FFFFFF",
                                                    "animation_in": "bounce"})
        self.assertEqual(ov["add"]["graphics"][0]["emoji"], "🔥")
        # saved feedback is marked applied; nothing left to apply
        self.assertIsNone(review.apply_feedback(self.reel)["file"])

    def test_tick_boxes_add_a_click_per_item(self):
        e = read_json(self.reel.path("edit.json"))
        e["graphics"].append({"id": "g3", "type": "lists", "start": 3.0, "end": 5.0, "style": {},
                              "items": [{"text": "Film", "at": 3.1}, {"text": "Edit", "at": 3.6}]})
        write_json(self.reel.path("edit.json"), e)
        review.save_feedback(self.reel, {"graphics": {"g3": {"checks": True, "paper": "lined"},
                                                      "g2": {"place": "above_head"}}})
        review.apply_feedback(self.reel)
        ov = read_json(self.reel.path("edit.overrides.json"))
        self.assertEqual(ov["set"]["g3"]["style"], {"custom_paper": "lined", "checks": True})
        self.assertEqual(ov["set"]["g2"]["place"], "above_head")
        # the planner turns "checks" into one click per item, timed from the items
        planner.apply_overrides(e, ov)
        clicks = [s["at"] for s in e["sfx"] if s["kind"] == "click"]
        self.assertEqual(clicks, [3.22, 3.72])

    def test_previous_files_are_backed_up(self):
        write_json(self.reel.path("edit.overrides.json"), {"set": {"g1": {"text": "old"}}})
        review.save_feedback(self.reel, {"headline": {"text": "new"}})
        review.apply_feedback(self.reel)
        backups = list((self.reel.root / "review" / "history").glob("*/edit.overrides.json"))
        self.assertEqual(read_json(backups[0]), {"set": {"g1": {"text": "old"}}})

    def test_two_saved_rounds_both_apply(self):
        review.save_feedback(self.reel, {"headline": {"text": "first round"}})
        review.save_feedback(self.reel, {"add": {"sfx": [{"kind": "pop", "t": 1.0}]}})
        res = review.apply_all(self.reel)
        self.assertEqual(len(res["files"]), 2)
        ov = read_json(self.reel.path("edit.overrides.json"))
        self.assertEqual(ov["headline"]["text"], "first round")
        self.assertEqual(len(ov["add"]["sfx"]), 1)
        self.assertEqual(review.unapplied(self.reel), [])

    def test_new_brand_sound_beats_old_one_off_swap(self):
        import os
        e = read_json(self.reel.path("edit.json"))
        e["sfx"] = [{"id": "s1", "at": 0.0, "kind": "pop", "event": "headline", "for": "g1"}]
        write_json(self.reel.path("edit.json"), e)
        write_json(self.reel.path("edit.overrides.json"), {"set": {"s1": {"kind": "whoosh"}}})
        from unittest import mock
        with mock.patch("laine_reel.brand.effective",
                        return_value={"sfx": {"sounds": {"headline": "s-mine"}}}):
            out = review.settings_supersede(self.reel, ["sound_map"])
        self.assertTrue(out)
        self.assertNotIn("s1", read_json(self.reel.path("edit.overrides.json")).get("set", {}))

    def test_headline_only_needs_final_render(self):
        review.save_feedback(self.reel, {"headline": {"text": "short"}})
        self.assertEqual(review.apply_feedback(self.reel)["needs"], "final")

    def test_feedback_files_never_overwritten(self):
        a = review.save_feedback(self.reel, {"notes": [{"t": 1, "text": "a"}]})
        b = review.save_feedback(self.reel, {"notes": [{"t": 1, "text": "b"}]})
        self.assertNotEqual(a, b)
        self.assertEqual(read_json(a)["notes"][0]["text"], "a")


class Overrides(unittest.TestCase):
    def edit(self):
        return {"captions": {"items": []}, "zooms": [], "sfx": [],
                "graphics": [{"id": "g1", "type": "text_callouts", "role": "headline", "start": 0,
                              "end": 2, "text": "draft", "draft": True, "reason": "x (draft - y)",
                              "style": {"font": "Didot"}},
                             {"id": "g2", "type": "emoji", "start": 5.0, "end": 6, "emoji": "📸",
                              "reason": "", "style": {"animation_in": "pop"}}]}

    def test_match_survives_id_shift_and_styles_merge(self):
        e = self.edit()
        e["graphics"][1]["id"] = "g3"     # a re-plan renumbered it
        e["graphics"][1]["start"] = 5.4   # and the cut moved it a little
        planner.apply_overrides(e, {"set": {"g2": {"emoji": "🎬", "style": {"custom_text": "#000"},
                                                   "_match": {"type": "emoji", "start": 5.0}}}})
        g = e["graphics"][1]
        self.assertEqual(g["emoji"], "🎬")
        self.assertEqual(g["style"], {"animation_in": "pop", "custom_text": "#000"})

    def test_headline_by_role_and_additions(self):
        e = self.edit()
        planner.apply_overrides(e, {"headline": {"text": "real one"},
                                    "add": {"zooms": [{"type": "punch", "start": 1, "end": 3, "scale": 1.2}],
                                            "sfx": [{"at": 1.0, "kind": "pop"}]}})
        self.assertEqual(e["graphics"][0]["text"], "real one")
        self.assertFalse(e["graphics"][0]["draft"])
        self.assertEqual(e["zooms"][0]["source"], "review")
        self.assertTrue(e["sfx"][0]["file"])

    def test_requested_items_follow_the_speech_after_a_recut(self):
        ov = {"add": {"graphics": [{"type": "emoji", "start": 4.0, "end": 5.0, "src_start": 5.0}]}}
        review.retime_additions(ov, [[0.0, 2.0], [3.5, 6.0]])   # 0.5 s less was cut
        self.assertAlmostEqual(ov["add"]["graphics"][0]["start"], 3.5)
        self.assertAlmostEqual(ov["add"]["graphics"][0]["end"], 4.5)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.reel = make_reel(Path(cls.dir) / "tiny")
        (Path(cls.dir) / "secret.mp4").write_bytes(b"nope")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.reel))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.dir)

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, b"", {}

    def test_page_and_data(self):
        code, body, _ = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Review your reel", body)
        code, body, _ = self.get("/api/reel")
        d = json.loads(body)
        self.assertEqual(d["video"], "/media/output/tiny-final.mp4")
        self.assertEqual(d["headline"]["id"], "g1")

    def test_video_seeking(self):
        code, body, h = self.get("/media/output/tiny-final.mp4", {"Range": "bytes=10-19"})
        self.assertEqual(code, 206)
        self.assertEqual(body, b"0123456789")
        self.assertEqual(h["Content-Range"], "bytes 10-19/1000")

    def test_nothing_outside_the_reel(self):
        self.assertEqual(self.get("/media/../secret.mp4")[0], 404)
        self.assertEqual(self.get("/media/%2e%2e/secret.mp4")[0], 404)
        self.assertEqual(self.get("/media/reel.json")[0], 403)
        self.assertEqual(self.get("/app/../../scripts/reel.py")[0], 404)

    def test_save_feedback_and_draft(self):
        def post(path, obj):
            req = urllib.request.Request(self.base + path, data=json.dumps(obj).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        post("/api/draft", {"notes": [{"t": 1, "text": "draft"}]})
        self.assertTrue((self.reel.root / "review" / "draft.json").exists())
        res = post("/api/feedback", {"notes": [{"t": 1, "text": "final"}]})
        self.assertTrue(res["ok"])
        self.assertTrue((self.reel.root / res["file"]).exists())
        self.assertFalse((self.reel.root / "review" / "draft.json").exists())


if __name__ == "__main__":
    unittest.main()


class Versions(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.reel = make_reel(Path(self.dir) / "tiny")
        self.final = self.reel.output / "tiny-final.mp4"

    def tearDown(self):
        shutil.rmtree(self.dir)

    def render(self, content):
        self.final.unlink()
        self.final.write_bytes(content)   # a new file, like ffmpeg's replace

    def test_snapshot_restore_approve(self):
        from laine_reel import versions
        write_json(self.reel.path("edit.overrides.json"), {"headline": {"text": "one"}})
        self.assertEqual(versions.snapshot(self.reel, self.final), 1)
        self.render(b"second render" * 50)
        write_json(self.reel.path("edit.overrides.json"), {"headline": {"text": "two"}})
        self.assertEqual(versions.snapshot(self.reel, self.final), 2)
        self.assertEqual([v["n"] for v in versions.list_versions(self.reel)], [1, 2])
        # restore 1: its video and its edits come back; v2 is still there
        versions.restore(self.reel, 1, self.final)
        self.assertEqual(self.final.read_bytes(), b"0123456789" * 100)
        self.assertEqual(read_json(self.reel.path("edit.overrides.json"))["headline"]["text"], "one")
        self.assertEqual(versions.current_number(self.reel), 1)
        self.assertEqual(len(versions.list_versions(self.reel)), 2)
        before = list((self.reel.root / "review" / "history").glob("*-before-restore"))
        self.assertEqual(read_json(before[0] / "edit.overrides.json")["headline"]["text"], "two")
        # approve 2 -> output/approved/, marked approved
        dest = versions.approve(self.reel, 2)
        self.assertEqual(dest.read_bytes(), b"second render" * 50)
        self.assertTrue(versions.list_versions(self.reel)[1]["approved"])

    def test_status(self):
        from laine_reel import versions
        versions.snapshot(self.reel, self.final)
        versions.set_status(self.reel, "working", "Rendering")
        review.save_feedback(self.reel, {"notes": [{"t": 1, "text": "x"}]})
        st = versions.get_status(self.reel)
        self.assertEqual((st["state"], st["latest_version"], len(st["pending_feedback"])),
                         ("working", 1, 1))

    def test_timestamps_use_the_version_that_was_watched(self):
        from laine_reel import versions
        # version 1 was cut differently from the current edit
        versions.snapshot(self.reel, self.final)
        snap = versions.vdir(self.reel) / "v001" / "state" / "edl.json"
        e = read_json(snap)
        e["keep"] = [[0.0, 1.0], [3.0, 6.0]]        # v1: 1 s kept before the cut
        write_json(snap, e)
        review.save_feedback(self.reel, {"version": 1, "captions": {"3": {"start_out": 1.5}}})
        review.apply_feedback(self.reel)
        fix = read_json(self.reel.path("transcript.fixes.json"))["words"]["3"]
        self.assertAlmostEqual(fix["start"], 3.5)   # 1.5 s on v1's timeline = 3.5 s source

    def test_graphic_retime_follows_the_speech(self):
        ov = {"set": {"g2": {"start": 4.0, "src_start": 5.0}}}
        review.retime_additions(ov, [[0.0, 2.0], [3.5, 6.0]])
        self.assertAlmostEqual(ov["set"]["g2"]["start"], 3.5)


class ServerVersions(Server):
    def test_status_restore_finalize_download(self):
        from laine_reel import versions
        final = self.reel.output / "tiny-final.mp4"
        versions.snapshot(self.reel, final)

        def post(path, obj):
            req = urllib.request.Request(self.base + path, data=json.dumps(obj).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        st = json.loads(self.get("/api/status")[1])
        self.assertEqual(st["latest_version"], 1)
        self.assertTrue(post("/api/restore", {"version": 1})["ok"])
        res = post("/api/finalize", {"version": 1})
        code, body, h = self.get(res["download"])
        self.assertEqual(code, 200)
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertEqual(body, b"0123456789" * 100)
        self.assertEqual(self.get("/download/../reel.json")[0], 404)
