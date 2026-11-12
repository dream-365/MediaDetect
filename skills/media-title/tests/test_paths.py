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
