"""Dated history of saved defaults, and each reel keeping the brand it was made with."""

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from laine_reel import brand, config, versions  # noqa: E402
from laine_reel.project import Reel, write_json  # noqa: E402
from test_library import Env  # noqa: E402


class BrandHistory(Env):

    def test_each_default_change_is_kept_with_a_date(self):
        brand.save_settings({"zoom_frequency": "frequent"}, "default")
        brand.save_settings({"caption_size": "small"}, "default")
        h = brand.history()
        self.assertEqual(len(h), 2)
        self.assertTrue(all(e["saved_at"] for e in h))
        # newest first: the set just before "large" differs from now only in caption size
        self.assertEqual([d["id"] for d in h[0]["differs_from_now"]], ["caption_size"])
        self.assertEqual({d["id"] for d in h[1]["differs_from_now"]}, {"caption_size", "zoom_frequency"})

    def test_restore_brings_back_earlier_defaults_and_can_be_undone(self):
        orig = config.load_brand()["answers"]
        brand.save_settings({"zoom_frequency": "frequent", "caption_case": "upper"}, "default")
        first = brand.history()[-1]["id"]
        brand.restore_history(first)
        self.assertEqual(config.load_brand()["answers"], orig)
        self.assertEqual(brand.load_progress()["answers"], orig)
        # the set that was replaced by the restore is in the history too
        self.assertTrue(any(e["answers"].get("caption_case") == "upper" for e in brand.history()))

    def test_restore_rejects_unknown_or_unsafe_ids(self):
        for bad in ("", "../brand", "20260101-000000"):
            with self.assertRaises(brand.AnswerError):
                brand.restore_history(bad)


class ReelSnapshot(Env):

    def make_reel(self, name):
        root = self.dir / name
        root.mkdir()
        write_json(root / "reel.json", {"slug": name})
        return root

    def test_older_reel_keeps_its_brand_after_defaults_change(self):
        old = self.make_reel("old-reel")
        before = brand.effective(old)["zooms"]["frequency"]          # pins today's defaults
        self.assertTrue((old / brand.SNAPSHOT).exists())
        brand.save_settings({"zoom_frequency": "frequent"}, "default")
        self.assertEqual(brand.effective(old)["zooms"]["frequency"], before)
        new = self.make_reel("new-reel")
        self.assertEqual(brand.effective(new)["zooms"]["frequency"], "frequent")
        self.assertEqual([d["id"] for d in brand.snapshot_info(old)["differs"]], ["zoom_frequency"])

    def test_saving_defaults_from_a_reel_updates_only_those_keys_there(self):
        r = self.make_reel("this-reel")
        other = self.make_reel("other-reel")
        brand.effective(r), brand.effective(other)
        brand.save_settings({"caption_case": "upper"}, "default")          # from elsewhere
        brand.save_settings({"zoom_frequency": "frequent"}, "default", r)  # from this reel
        eff = brand.effective(r)
        self.assertEqual(eff["zooms"]["frequency"], "frequent")
        self.assertNotEqual(eff["answers"].get("caption_case"), "upper")  # not pulled in
        self.assertNotEqual(brand.effective(other)["zooms"]["frequency"], "frequent")

    def test_use_current_defaults_repins(self):
        r = self.make_reel("r")
        brand.effective(r)
        brand.save_settings({"zoom_frequency": "frequent"}, "default")
        self.assertEqual(brand.use_current_defaults(r), ["zoom_frequency"])
        self.assertEqual(brand.effective(r)["zooms"]["frequency"], "frequent")
        self.assertEqual(brand.snapshot_info(r)["differs"], [])

    def test_reel_only_changes_sit_on_top_of_the_snapshot(self):
        r = self.make_reel("r")
        brand.save_settings({"caption_size": "large"}, "reel", r)
        brand.save_settings({"zoom_frequency": "frequent"}, "default")
        eff = brand.effective(r)
        self.assertEqual(eff["captions"]["size"], "large")
        self.assertNotEqual(eff["zooms"]["frequency"], "frequent")

    def test_test_brand_never_pinned_into_a_real_reel(self):
        real_like = config.PROJECT_ROOT / "workspace" / "zz-not-a-test-reel"
        self.assertFalse(brand._may_pin(real_like))
        self.assertTrue(brand._may_pin(config.PROJECT_ROOT / "workspace" / "_tests" / "x"))

    def test_version_restore_brings_back_that_versions_brand(self):
        r = self.make_reel("vr")
        reel = Reel(r)
        for n in ("edl.json",):
            write_json(r / n, {"stats": {"output_duration": 1.0}})
        (r / "output").mkdir()
        final = r / "output" / "vr-final.mp4"
        final.write_bytes(b"v1")
        brand.effective(r)
        snap1 = (r / brand.SNAPSHOT).read_text()
        reel.update_manifest = lambda **k: None
        versions.snapshot(reel, final)
        brand.use_current_defaults(r)
        write_json(r / brand.SNAPSHOT, {"pinned_at": "x", "profile": {"answers": {}}})
        (r / "brand.answers.json").write_text(json.dumps({"caption_size": "large"}))
        versions.restore(reel, 1, final)
        self.assertEqual((r / brand.SNAPSHOT).read_text(), snap1)
        self.assertFalse((r / "brand.answers.json").exists())


if __name__ == "__main__":
    unittest.main()
