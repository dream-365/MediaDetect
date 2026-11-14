import errno
import os
import tempfile
import unittest
from unittest.mock import patch

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib import fsops
from media_title_lib.fsops import (
    MOVE_CHECK,
    FsError,
    make_dir,
    probe_no_replace,
    remove_empty_dir,
    safe_move,
)


def write_file(path, data="x"):
    with open(path, "w") as fh:
        fh.write(data)


def read_file(path):
    with open(path) as fh:
        return fh.read()


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

    def _no_native_no_link(self):
        return (
            patch.object(fsops, "_rename_noreplace",
                         side_effect=OSError(errno.ENOTSUP, "not supported")),
            patch.object(fsops.os, "link",
                         side_effect=OSError(errno.EPERM, "hard links disabled")),
        )

    def test_check_rename_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write_file(src)
            native, link = self._no_native_no_link()
            with native, link:
                with self.assertRaises(FsError) as ctx:
                    safe_move(src, dst)
                self.assertEqual(ctx.exception.code, "E_NO_REPLACE_UNSUPPORTED")
                self.assertTrue(os.path.exists(src))
                self.assertFalse(os.path.exists(dst))
                info = safe_move(src, dst, allow_check=True)
            self.assertEqual(info["method"], MOVE_CHECK)
            self.assertFalse(info["atomic"])
            self.assertTrue(os.path.exists(dst))
            self.assertFalse(os.path.exists(src))

    def test_check_rename_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write_file(src, "source")
            write_file(dst, "target")
            native, link = self._no_native_no_link()
            with native, link:
                with self.assertRaises(FsError) as ctx:
                    safe_move(src, dst, allow_check=True)
            self.assertEqual(ctx.exception.code, "E_TARGET_EXISTS")
            self.assertEqual(read_file(src), "source")
            self.assertEqual(read_file(dst), "target")

    def test_check_rename_directory(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "Show")
            dst = os.path.join(root, "Show (2019)")
            os.mkdir(src)
            write_file(os.path.join(src, "E01.mkv"))
            with patch.object(fsops, "_rename_noreplace",
                              side_effect=OSError(errno.ENOTSUP, "not supported")):
                info = safe_move(src, dst, allow_check=True)
            self.assertEqual(info["method"], MOVE_CHECK)
            self.assertEqual(info["validation"], "portable_subtree")
            self.assertTrue(os.path.isdir(dst))

    def test_probe_reports_check_capability(self):
        with tempfile.TemporaryDirectory() as root:
            native, link = self._no_native_no_link()
            with native, link:
                with self.assertRaises(FsError) as ctx:
                    probe_no_replace(root, "file")
                self.assertEqual(ctx.exception.code, "E_NO_REPLACE_UNSUPPORTED")
            native, link = self._no_native_no_link()
            with native, link:
                self.assertEqual(probe_no_replace(root, "file", allow_check=True),
                                 MOVE_CHECK)
            with patch.object(fsops, "_rename_noreplace",
                              side_effect=OSError(errno.ENOTSUP, "not supported")):
                self.assertEqual(probe_no_replace(root, "directory", allow_check=True),
                                 MOVE_CHECK)

    def test_check_rename_validation_failure_restores_source(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write_file(src)
            real_state = fsops.lstat_state

            def fake_state(path):
                state = real_state(path)
                if path == dst:
                    state = dict(state)
                    state["size"] = int(state.get("size", 0)) + 1
                return state

            native, link = self._no_native_no_link()
            with native, link, patch.object(fsops, "lstat_state", side_effect=fake_state):
                with self.assertRaises(FsError) as ctx:
                    safe_move(src, dst, allow_check=True)
            self.assertEqual(ctx.exception.code, "E_NON_ATOMIC_MOVE_FAILED")
            self.assertTrue(os.path.exists(src))
            self.assertFalse(os.path.exists(dst))

    def test_check_rename_mtime_rewrite_is_content_validated(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write_file(src, "payload")
            real_rename = os.rename
            real_utime = os.utime

            def rewriting_rename(a, b):
                real_rename(a, b)
                st = os.stat(b)
                real_utime(b, ns=(st.st_mtime_ns + 1_000_000_000,
                                  st.st_mtime_ns + 1_000_000_000))

            native, link = self._no_native_no_link()
            with native, link, \
                    patch.object(fsops.os, "rename", side_effect=rewriting_rename), \
                    patch.object(fsops.os, "utime",
                                 side_effect=OSError(errno.EPERM, "utime denied")):
                info = safe_move(src, dst, allow_check=True)
            self.assertEqual(info["method"], MOVE_CHECK)
            self.assertEqual(info["validation"], "size_content")
            self.assertEqual(read_file(dst), "payload")
            self.assertFalse(os.path.exists(src))

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
