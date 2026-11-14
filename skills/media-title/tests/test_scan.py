import os
import tempfile
import unittest
from unittest.mock import patch

from helpers import FakeRunner, SCRIPTS_DIR  # noqa: F401

from media_title_lib import scan as scan_mod


def write(path, data="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(data)


class CountingRunner(FakeRunner):
    def __init__(self):
        self.calls = []

    def detect(self, path, match="off", probe="off", max_files=5000):
        self.calls.append(path)
        return super().detect(path, match, probe, max_files)


class ScanTests(unittest.TestCase):
    def run_scan(self, path, **kwargs):
        with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: FakeRunner()):
            return scan_mod.scan_path(path, md_bin="fake", **kwargs)

    def run_counting_scan(self, path, **kwargs):
        runner = CountingRunner()
        with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: runner):
            result = scan_mod.scan_path(path, md_bin="fake", **kwargs)
        return result, runner.calls

    def test_organized_directory_is_skipped_without_detect(self):
        with tempfile.TemporaryDirectory() as root:
            tagged = os.path.join(root, "Movies", "X (2020) {tt1234567}")
            write(os.path.join(tagged, "X.2020.mkv"))
            result, calls = self.run_counting_scan(tagged)
            self.assertEqual(result["units"], [])
            self.assertEqual(result["unplanned"], [])
            self.assertEqual(result["skipped"][0]["path"], tagged)
            self.assertEqual(result["skipped"][0]["reason_code"], "already_organized")
            self.assertEqual(calls, [])

    def test_organized_file_is_skipped_without_detect(self):
        with tempfile.TemporaryDirectory() as root:
            tagged = os.path.join(root, "X (2020) {tmdb42}.mkv")
            write(tagged)
            result, calls = self.run_counting_scan(tagged)
            self.assertEqual(result["units"], [])
            self.assertEqual(result["skipped"][0]["path"], tagged)
            self.assertEqual(calls, [])

    def test_organized_child_is_not_detected_or_recursed(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Movies")
            tagged = os.path.join(base, "X (2020) {tt1234567}")
            write(os.path.join(tagged, "Season 01", "X.S01E01.mkv"))
            normal = os.path.join(base, "Y (2021)")
            write(os.path.join(normal, "Y.2021.mkv"))
            result, calls = self.run_counting_scan(base, mode="library")
            self.assertIn(tagged, [item["path"] for item in result["skipped"]])
            self.assertNotIn(tagged, calls)
            self.assertFalse(any(path.startswith(tagged + os.sep) for path in calls))
            self.assertTrue(any(path == normal for path in calls))
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["source_root"], normal)

    def test_include_organized_forces_detection(self):
        with tempfile.TemporaryDirectory() as root:
            tagged = os.path.join(root, "Movies", "X (2020) {tt1234567}")
            write(os.path.join(tagged, "X.2020.mkv"))
            _result, calls = self.run_counting_scan(tagged, include_organized=True)
            self.assertIn(tagged, calls)

    def test_generic_downloads_single_movie_stays_file_unit(self):
        with tempfile.TemporaryDirectory() as root:
            downloads = os.path.join(root, "Downloads")
            write(os.path.join(downloads, "Inception.2010.mkv"))
            write(os.path.join(downloads, "Inception.2010.zh.srt"))
            write(os.path.join(downloads, "other.iso"))
            result = self.run_scan(os.path.join(downloads, "Inception.2010.mkv"))
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertEqual(unit["input_kind"], "file")
            self.assertEqual(unit["root"], downloads)
            self.assertFalse(result["unplanned"])

    def test_single_movie_directory_is_directory_unit(self):
        with tempfile.TemporaryDirectory() as root:
            movie = os.path.join(root, "Movies", "Inception (2010)")
            write(os.path.join(movie, "Inception.2010.mkv"))
            result = self.run_scan(os.path.join(movie, "Inception.2010.mkv"))
            self.assertEqual(result["units"][0]["input_kind"], "directory")
            self.assertEqual(result["units"][0]["source_root"], movie)
            self.assertEqual(result["root"], os.path.dirname(movie))

    def test_show_directory_with_season_children_is_show_unit(self):
        with tempfile.TemporaryDirectory() as root:
            show_dir = os.path.join(root, "TV", "Show (2019)")
            write(os.path.join(show_dir, "Season 01", "Show.S01E01.mkv"))
            result = self.run_scan(show_dir)
            self.assertEqual(result["root"], os.path.join(root, "TV"))
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["input_kind"], "directory")
            self.assertEqual(result["units"][0]["source_root"], show_dir)

    def test_episode_in_canonical_season_tree(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "TV", "Show (2019)", "Season 01", "Show.S01E01.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertEqual(unit["input_kind"], "file")
            self.assertEqual(unit["root"], os.path.join(root, "TV"))
            self.assertEqual(unit["context"]["season"], 1)

    def test_episode_file_in_flat_season_dir_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "Some.Show.S01.1080p", "Some.Show.S01E01.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertFalse(result["units"])
            self.assertEqual(result["unplanned"][0]["reason_code"], "needs_directory_mode")

    def test_episode_in_noncanonical_season_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "TV", "Show (2019)", "Season 1", "Show.S01E01.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertFalse(result["units"])
            self.assertEqual(result["unplanned"][0]["reason_code"], "needs_directory_mode")

    def test_multiple_loose_shows_are_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Breaking.Bad.S01E01.mkv"))
            write(os.path.join(base, "The.Office.S01E01.mkv"))
            result = self.run_scan(base)
            self.assertFalse(result["units"])
            self.assertEqual(result["unplanned"][0]["reason_code"], "ambiguous_loose_shows")

    def test_same_title_different_years_are_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Show.2004.S01E01.mkv"))
            write(os.path.join(base, "Show.1978.S01E01.mkv"))
            result = self.run_scan(base)
            self.assertFalse(result["units"])
            self.assertEqual(result["unplanned"][0]["reason_code"], "ambiguous_loose_shows")

    def test_multipart_movie_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Movie.2020.CD1.mkv"))
            write(os.path.join(base, "Movie.2020.CD2.mkv"))
            result = self.run_scan(base)
            self.assertFalse(result["units"])
            self.assertTrue(all(x["reason_code"] == "unsupported_multipart"
                                for x in result["unplanned"]))

    def test_explicit_range_is_not_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "Downloads", "Show.S01E01-E03.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["kind"], "tv")

    def test_non_contiguous_multi_episode_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "Downloads", "Show.S01E01E03.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertFalse(result["units"])
            self.assertEqual(result["unplanned"][0]["reason_code"],
                             "unsupported_multi_episode")

    def test_cjk_episode_in_show_directory(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "某剧", "第01集.mkv")
            write(path)
            result = self.run_scan(path)
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertEqual(unit["context"]["show"], "某剧")
            self.assertEqual(unit["context"]["season"], 1)
            self.assertTrue(unit["context"]["season_inferred"])

    def test_flat_season_directory_is_tv_unit(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            write(os.path.join(base, "Some.Show.S01E02.mkv"))
            result = self.run_scan(base)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["kind"], "tv")
            self.assertEqual(result["units"][0]["context"]["show"], "Some Show")


if __name__ == "__main__":
    unittest.main()
