import os
import tempfile
import unittest
from unittest.mock import patch

from helpers import FakeRunner, SCRIPTS_DIR  # noqa: F401

from media_title_lib import scan as scan_mod
from media_title_lib.plan import build_plan, content_hash


def write(path, data="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(data)


def scan_with_fake(path, **kwargs):
    with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: FakeRunner()):
        return scan_mod.scan_path(path, md_bin="fake", **kwargs)


class PlanTests(unittest.TestCase):
    def test_movie_file_plan_includes_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            video = os.path.join(base, "Inception.2010.mkv")
            write(video)
            write(os.path.join(base, "Inception.2010.zh.srt"))
            scan = scan_with_fake(video)
            plan = build_plan(scan)
            self.assertEqual(len(plan["units"]), 1)
            unit = plan["units"][0]
            self.assertEqual(unit["id"], "u1")
            self.assertEqual(unit["target"]["path"],
                             os.path.join(base, "Inception (2010) {tt1234567}"))
            sources = {s["path"] for s in unit["sources"]}
            self.assertIn(video, sources)
            self.assertIn(os.path.join(base, "Inception.2010.zh.srt"), sources)
            self.assertEqual(plan["plan_id"], content_hash(plan))

    def test_tv_flat_season_plan(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            write(os.path.join(base, "Some.Show.S01E02.mkv"))
            scan = scan_with_fake(base)
            plan = build_plan(scan)
            self.assertEqual(len(plan["units"]), 1)
            unit = plan["units"][0]
            show_dir = os.path.join(os.path.dirname(base), "Some Show")
            season_dir = os.path.join(show_dir, "Season 01")
            self.assertEqual(unit["target"]["path"], show_dir)
            targets = [op["to"] for op in unit["operations"] if op["op"] == "move"]
            self.assertTrue(all(t.startswith(season_dir + os.sep) for t in targets))
            self.assertTrue(any(op["op"] == "mkdir" and op["path"] == show_dir
                                for op in unit["operations"]))
            self.assertTrue(any(op["op"] == "mkdir" and op["path"] == season_dir
                                for op in unit["operations"]))

    def test_rename_episodes(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            scan = scan_with_fake(base)
            plan = build_plan(scan, {"rename_episodes": True})
            moves = [op for op in plan["units"][0]["operations"] if op["op"] == "move"]
            self.assertTrue(moves)
            self.assertEqual(os.path.basename(moves[0]["to"]), "Some Show - S01E01.mkv")

    def test_rename_episode_range_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01-E03.mkv"))
            scan = scan_with_fake(base)
            plan = build_plan(scan, {"rename_episodes": True})
            moves = [op for op in plan["units"][0]["operations"] if op["op"] == "move"]
            self.assertTrue(moves)
            self.assertEqual(os.path.basename(moves[0]["to"]),
                             "Some Show - S01E01-E03.mkv")

    def test_plan_hash_detects_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Inception.2010.mkv"))
            plan = build_plan(scan_with_fake(os.path.join(base, "Inception.2010.mkv")))
            original = plan["plan_id"]
            plan["units"][0]["target"]["path"] = "/tmp/elsewhere"
            self.assertNotEqual(original, content_hash(plan))


if __name__ == "__main__":
    unittest.main()
