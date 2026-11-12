import json
import os
import tempfile
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.session import (
    SessionError,
    atomic_write_json,
    ensure_session,
    read_json,
    session_files,
    validate_session_id,
)


class SessionTests(unittest.TestCase):
    def test_session_layout_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            session = ensure_session(root, "20260101T000000Z-abcdef12")
            self.assertEqual(session["session_id"], "20260101T000000Z-abcdef12")
            self.assertRegex(session["session_token"], r"^[0-9a-f]{32}$")
            files = session_files(session["state_dir"])
            self.assertTrue(os.path.isdir(session["state_dir"]))
            path = files["scan"]
            atomic_write_json(path, {"ok": True, "n": 1})
            self.assertEqual(read_json(path), {"n": 1, "ok": True})

    def test_invalid_session_id(self):
        with self.assertRaises(SessionError):
            validate_session_id("../escape")
        with self.assertRaises(SessionError):
            validate_session_id("bad/id")

    def test_existing_token_is_reused(self):
        with tempfile.TemporaryDirectory() as root:
            sid = "20260101T000000Z-abcdef12"
            first = ensure_session(root, sid)
            files = session_files(first["state_dir"])
            atomic_write_json(files["scan"], {"session_token": first["session_token"]})
            second = ensure_session(root, sid)
            self.assertEqual(first["session_token"], second["session_token"])


if __name__ == "__main__":
    unittest.main()
