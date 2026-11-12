import os
import tempfile
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.fsops import (
    FsError,
    make_dir,
    probe_no_replace,
    remove_empty_dir,
    safe_move,
)


class FsOpsTests(unittest.TestCase):
    def test_safe_move_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            with open(src, "w") as fh:
                fh.write("x")
            safe_move(src, dst)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(dst))
            with open(src, "w") as fh:
                fh.write("y")
            with self.assertRaises(FsError) as ctx:
                safe_move(src, dst)
            self.assertEqual(ctx.exception.code, "E_TARGET_EXISTS")

    def test_safe_move_directory(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "Show")
            dst = os.path.join(root, "Show (2008)")
            os.mkdir(src)
            with open(os.path.join(src, "file.txt"), "w") as fh:
                fh.write("x")
            safe_move(src, dst)
            self.assertTrue(os.path.isdir(dst))
            self.assertFalse(os.path.exists(src))

    def test_probe(self):
        with tempfile.TemporaryDirectory() as root:
            probe_no_replace(root, "file")
            probe_no_replace(root, "directory")

    def test_mkdir_and_remove(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "a")
            created, ino = make_dir(path)
            self.assertTrue(created)
            self.assertTrue(ino)
            created_again, ino_again = make_dir(path)
            self.assertFalse(created_again)
            self.assertEqual(ino, ino_again)
            removed, result = remove_empty_dir(path)
            self.assertTrue(removed)
            self.assertEqual(result, "removed")

    def test_remove_non_empty_is_leftover(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "a")
            os.mkdir(path)
            with open(os.path.join(path, "x"), "w") as fh:
                fh.write("x")
            removed, result = remove_empty_dir(path)
            self.assertFalse(removed)
            self.assertEqual(result, "leftover")


if __name__ == "__main__":
    unittest.main()
