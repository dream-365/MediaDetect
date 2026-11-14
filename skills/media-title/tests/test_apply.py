import os
import tempfile
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.apply import ApplyError, apply_plan
from media_title_lib.paths import lstat_state
from media_title_lib.plan import content_hash
from media_title_lib.session import (
    atomic_write_json,
    ensure_session,
    read_json,
    session_files,
)


def build_plan(root):
    sid = "20260101T000000Z-abcdef12"
    session = ensure_session(root, sid)
    src = os.path.join(root, "Inception.2010.mkv")
    with open(src, "w") as fh:
        fh.write("movie")
    target = os.path.join(root, "Inception (2010)")
    target_file = os.path.join(target, "Inception.2010.mkv")
    plan = {
        "schema_version": "1",
        "session_id": sid,
        "session_token": session["session_token"],
        "state_dir": session["state_dir"],
        "generated_at": "2026-01-01T00:00:00Z",
        "tool_version": "0.1.1",
        "root": root,
        "mode": "file",
        "options": {},
        "units": [{
            "id": "u1",
            "kind": "movie",
            "status": "planned",
            "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
            "source_hash": "sha256:test",
            "sibling_snapshot": {root: [os.path.basename(src)]},
            "target": {"path": target, "kind": "directory"},
            "operations": [
                {"op": "mkdir", "path": target, "pre_exists": False, "pre_state": None},
                {"op": "move", "from": src, "to": target_file, "from_state": lstat_state(src)},
            ],
            "warnings": [],
            "evidence": {},
        }],
        "unplanned": [],
        "skipped": [],
        "errors": [],
        "warnings": [],
        "summary": {"units": 1, "planned": 1, "skipped": 0, "unplanned": 0, "operations": 2},
    }
    plan["plan_id"] = content_hash(plan)
    return plan, src, target, target_file


class ApplyTests(unittest.TestCase):
    def test_apply_moves_and_records_state(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src, target, target_file = build_plan(root)
            result = apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(result["applied"], ["u1"])
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(target_file))
            state = read_json(session_files(plan["state_dir"])["state"])
            self.assertEqual(state["units"]["u1"]["status"], "applied")

    def test_target_exists_fails_before_changes(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src, target, _ = build_plan(root)
            os.mkdir(target)
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_TARGET_EXISTS")
            self.assertTrue(os.path.exists(src))

    def test_unknown_unit(self):
        with tempfile.TemporaryDirectory() as root:
            plan, _src, _target, _target_file = build_plan(root)
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "u9")
            self.assertEqual(ctx.exception.code, "E_UNKNOWN_UNIT")

    def test_second_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            plan, _src, _target, _target_file = build_plan(root)
            apply_plan(plan, plan["plan_id"], "u1")
            result = apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(result["applied"], [])
            self.assertEqual(result["already_applied"], ["u1"])

    def test_expect_plan_id_mismatch(self):
        with tempfile.TemporaryDirectory() as root:
            plan, _src, _target, _target_file = build_plan(root)
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, "sha256:" + "0" * 64, "u1")
            self.assertEqual(ctx.exception.code, "E_EXPECT_PLAN_MISMATCH")

    def test_done_before_state_is_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            plan, _src, _target, _target_file = build_plan(root)
            apply_plan(plan, plan["plan_id"], "u1")
            state_path = session_files(plan["state_dir"])["state"]
            state = read_json(state_path)
            state["units"]["u1"]["status"] = "applying"
            atomic_write_json(state_path, state)
            result = apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(result["applied"], [])
            self.assertEqual(result["already_applied"], ["u1"])

    def test_new_sidecar_after_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src, _target, _target_file = build_plan(root)
            with open(os.path.join(root, "Inception.2010.en.srt"), "w") as fh:
                fh.write("late")
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_SOURCE_STATE_MISMATCH")
            self.assertTrue(os.path.exists(src))


if __name__ == "__main__":
    unittest.main()
