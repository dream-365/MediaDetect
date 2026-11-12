import os
import tempfile
import unittest

from helpers import SCRIPTS_DIR  # noqa: F401

from media_title_lib.apply import apply_plan
from media_title_lib.paths import lstat_state
from media_title_lib.plan import content_hash
from media_title_lib.rollback import RollbackError, rollback_plan
from media_title_lib.session import ensure_session, read_json, session_files


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
        "tool_version": "0.1.0",
        "root": root,
        "mode": "file",
        "options": {},
        "units": [{
            "id": "u1",
            "kind": "movie",
            "status": "planned",
            "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
            "source_hash": "sha256:test",
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


class RollbackTests(unittest.TestCase):
    def test_rollback_restores_source_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src, target, target_file = build_plan(root)
            apply_plan(plan, plan["plan_id"], "u1")
            result = rollback_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(result["rolled_back"], ["u1"])
            self.assertTrue(os.path.exists(src))
            self.assertFalse(os.path.exists(target_file))
            state = read_json(session_files(plan["state_dir"])["state"])
            self.assertEqual(state["units"]["u1"]["status"], "rolled_back")
            second = rollback_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(second["rolled_back"], [])
            self.assertTrue(os.path.exists(src))

    def test_rollback_conflicts_on_new_nested_file(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src, target, target_file = build_plan(root)
            apply_plan(plan, plan["plan_id"], "u1")
            with open(os.path.join(target, "new.txt"), "w") as fh:
                fh.write("new")
            with self.assertRaises(RollbackError) as ctx:
                rollback_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_ROLLBACK_CONFLICT")
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(target_file))

    def test_rollback_without_apply(self):
        with tempfile.TemporaryDirectory() as root:
            plan, _src, _target, _target_file = build_plan(root)
            with self.assertRaises(RollbackError) as ctx:
                rollback_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_NOTHING_TO_ROLLBACK")


if __name__ == "__main__":
    unittest.main()
