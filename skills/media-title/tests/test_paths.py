import os
import tempfile
import unicodedata
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.paths import (
    build_raw_map,
    clean_component,
    is_generic_container,
    multipart_token,
    nfc,
    part_movie_number,
    part_title_matches,
    resolve_nfc,
    season_marker_any,
    season_marker_whole,
    subtree_fingerprint,
)


class PathTests(unittest.TestCase):
    def test_nfc_mapping_preserves_raw_name(self):
        with tempfile.TemporaryDirectory() as root:
            nfd_name = unicodedata.normalize("NFD", "café.mkv")
            with open(os.path.join(root, nfd_name), "w") as fh:
                fh.write("x")
            mapping = build_raw_map(root)
            raw = resolve_nfc(root, unicodedata.normalize("NFC", nfd_name), mapping)
            self.assertEqual(os.path.basename(raw), nfd_name)

    def test_clean_component(self):
        self.assertEqual(clean_component(" A/B:C "), "A-B -C")
        self.assertEqual(clean_component(".."), "")

    def test_season_markers(self):
        self.assertEqual(season_marker_whole("Season 1"), 1)
        self.assertEqual(season_marker_whole("S02"), 2)
        self.assertIsNone(season_marker_whole("Some.Show.S01.1080p"))
        self.assertEqual(season_marker_any("Some.Show.S01.1080p"), 1)

    def test_generic_container(self):
        self.assertTrue(is_generic_container("Downloads"))
        self.assertTrue(is_generic_container("Downloads 2"))
        self.assertTrue(is_generic_container("影视下载"))
        self.assertFalse(is_generic_container("Breaking Bad"))

    def test_multipart(self):
        self.assertIsNotNone(multipart_token("Movie.CD1.mkv"))
        self.assertIsNotNone(multipart_token("Movie.Part.A.mkv"))
        self.assertIsNotNone(multipart_token("Movie.1of2.mkv"))
        self.assertIsNone(multipart_token("Movie.2020.mkv"))

    def test_multipart_hard_and_part_tokens(self):
        hard = [
            "Movie.CD1.mkv", "Movie.CD2.mkv", "Movie.Part.A.mkv",
            "Movie.1of2.mkv", "Movie.A.mkv", "Movie.B.mkv",
            "Movie.A.1080p.mkv", "Movie-A.1080p.mkv", "Movie-B.1080p.mkv",
            "Movie.1-2.mkv", "Movie.2-2.mkv",
            "Movie.上集.mkv", "Movie.下集.mkv",
        ]
        for name in hard:
            self.assertIsNotNone(multipart_token(name), name)
            self.assertIsNotNone(multipart_token(name, allow_part=True), name)
        for name in ["Movie.Part.1.mkv", "Movie.Part1.mkv", "Movie.pt2.mkv"]:
            self.assertIsNotNone(multipart_token(name), name)
            self.assertIsNone(multipart_token(name, allow_part=True), name)
            self.assertIsNotNone(part_movie_number(name), name)
        for name in [
            "A.City.of.Sadness.1989.mkv",
            "A.Clockwork.Orange.1971.mkv",
            "Perfume.The.Story.of.a.Murderer.2006.mkv",
            "B.for.Busy.2021.mkv",
            "War.Horse.2011.AC3.5.1-PTH.mkv",
            "A.Better.Jianghu.2026.mkv",
            "Movie.2020-2021.mkv",
            "3月のライオン.後編.March.Comes.In.Like.A.Lion.2.2017.mp4",
        ]:
            self.assertIsNone(multipart_token(name, allow_part=True), name)

    def test_part_title_proof_requires_tmdb(self):
        best = {"title": "Harry Potter and the Deathly Hallows: Part 1",
                "original_title": "Harry Potter and the Deathly Hallows: Part 1"}
        self.assertTrue(part_title_matches(1, best))
        self.assertFalse(part_title_matches(2, best))
        local = {"title": "Movie Part 1", "local": True}
        self.assertFalse(part_title_matches(1, local))
        no_part = {"title": "A City of Sadness", "original_title": "悲情城市"}
        self.assertFalse(part_title_matches(1, no_part))

    def test_subtree_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "a.mkv"), "w") as fh:
                fh.write("a")
            first, count = subtree_fingerprint(root)
            self.assertGreaterEqual(count, 1)
            with open(os.path.join(root, "b.srt"), "w") as fh:
                fh.write("b")
            second, _ = subtree_fingerprint(root)
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
