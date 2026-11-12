"""Regression tests for the acceptance-review blockers and high findings."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from helpers import FakeRunner, SCRIPTS_DIR  # noqa: F401

from media_title_lib import scan as scan_mod
from media_title_lib.apply import ApplyError, apply_plan, reconcile
from media_title_lib.paths import lstat_state, protected_root, subtree_fingerprint
from media_title_lib.plan import PlanError, build_plan, content_hash
from media_title_lib.rollback import RollbackError, rollback_plan
from media_title_lib.session import (
    append_jsonl,
    atomic_write_json,
    ensure_session,
    read_jsonl,
    session_files,
)


def write(path, data="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(data)


def scan_with_fake(path, **kwargs):
    with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: FakeRunner()):
        return scan_mod.scan_path(path, md_bin="fake", **kwargs)


def manual_plan(root, units):
    sid = "20260101T000000Z-abcdef12"
    session = ensure_session(root, sid)
    plan = {
        "schema_version": "1",
        "session_id": sid,
        "session_token": session["session_token"],
        "state_dir": session["state_dir"],
        "generated_at": "2026-01-01T00:00:00Z",
        "tool_version": "0.1.0",
        "root": root,
        "mode": "test",
        "options": {},
        "units": units,
        "unplanned": [],
        "skipped": [],
        "errors": [],
        "warnings": [],
        "summary": {},
    }
    plan["plan_id"] = content_hash(plan)
    return plan


class ScanRegressionTests(unittest.TestCase):
    def test_movie_directory_input_is_directory_unit(self):
        with tempfile.TemporaryDirectory() as root:
            movie = os.path.join(root, "Movies", "Inception (2010)")
            write(os.path.join(movie, "Inception.2010.mkv"))
            result = scan_with_fake(movie)
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertEqual(unit["input_kind"], "directory")
            self.assertEqual(unit["root"], os.path.dirname(movie))
            plan = build_plan(result)
            target = plan["units"][0]["target"]["path"]
            self.assertEqual(os.path.dirname(target), os.path.dirname(movie))
            self.assertFalse(target.startswith(movie + os.sep))

    def test_directory_scan_marks_non_contiguous_multi_episode(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Show.S01E01E03.mkv"))
            result = scan_with_fake(base)
            self.assertFalse(result["units"])
            self.assertIn("unsupported_multi_episode",
                          [item["reason_code"] for item in result["unplanned"]])

    def test_movie_collection_targets_are_under_library_root(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Movies")
            write(os.path.join(base, "Collection", "Inception (2010)",
                               "Inception.2010.mkv"))
            write(os.path.join(base, "Collection", "Interstellar (2014)",
                               "Interstellar.2014.mkv"))
            result = scan_with_fake(base, mode="library")
            plan = build_plan(result)
            self.assertEqual(len(plan["units"]), 2)
            for unit in plan["units"]:
                self.assertEqual(os.path.dirname(unit["target"]["path"]), base)

    def test_show_name_is_cleaned_and_container_mismatch_uses_title(self):
        with tempfile.TemporaryDirectory() as root:
            show = os.path.join(root, "TV", "Show.2019.1080p")
            write(os.path.join(show, "Season 01", "Show.S01E01.mkv"))
            result = scan_with_fake(os.path.join(root, "TV"), mode="library")
            self.assertEqual(result["units"][0]["context"]["show"], "Show")
            self.assertEqual(result["units"][0]["context"]["year"], 2019)
            renamed = os.path.join(root, "TV", "RandomFolder")
            write(os.path.join(renamed, "Season 01", "Show.S01E02.mkv"))
            result = scan_with_fake(os.path.join(root, "TV"), mode="library")
            show_context = [u["context"] for u in result["units"]
                            if u["source_root"] == renamed][0]
            self.assertEqual(show_context["show"], "Show")

    def test_hidden_entries_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "TV")
            write(os.path.join(base, ".hidden-show", "Show.S01E01.mkv"))
            write(os.path.join(base, "Visible Show", "Season 01", "Show.S01E01.mkv"))
            write(os.path.join(base, ".hidden.mkv"))
            result = scan_with_fake(base, mode="library")
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["context"]["show"], "Visible Show")

    def test_sidecar_follows_its_video_season(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S00-S01.1080p")
            write(os.path.join(base, "Some.Show.S00E01.mkv"))
            write(os.path.join(base, "Some.Show.S00E01.zh.srt"))
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            write(os.path.join(base, "Some.Show.S01E01.zh.srt"))
            plan = build_plan(scan_with_fake(base))
            moves = {op["from"]: op["to"] for op in plan["units"][0]["operations"]
                     if op["op"] == "move"}
            self.assertIn(os.path.join("Season 00"), moves[os.path.join(
                base, "Some.Show.S00E01.zh.srt")])
            self.assertIn(os.path.join("Season 01"), moves[os.path.join(
                base, "Some.Show.S01E01.zh.srt")])

    def test_poster_does_not_hide_show_directory(self):
        with tempfile.TemporaryDirectory() as root:
            show = os.path.join(root, "TV", "Show.2019")
            write(os.path.join(show, "Season 01", "Show.S01E01.mkv"))
            write(os.path.join(show, "poster.jpg"))
            result = scan_with_fake(os.path.join(root, "TV"), mode="library")
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["source_root"], show)
            plan = build_plan(result)
            self.assertEqual(plan["units"][0]["target"]["path"],
                             os.path.join(root, "TV", "Show (2019)"))

    def test_non_generic_mixed_library_root_is_supported(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Media Library")
            write(os.path.join(base, "Movies", "Inception (2010)",
                               "Inception.2010.mkv"))
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            result = scan_with_fake(base, mode="library")
            self.assertTrue(result["units"])
            tv = [u for u in result["units"] if u["kind"] == "tv"]
            self.assertTrue(tv)
            self.assertIsNone(tv[0].get("source_root"))

    def test_directory_movie_multipart_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            movie = os.path.join(root, "Movies", "Inception 2010")
            write(os.path.join(movie, "Inception.2010.CD1.mkv"))
            result = scan_with_fake(movie)
            self.assertFalse(result["units"])
            self.assertIn("unsupported_multipart",
                          [item["reason_code"] for item in result["unplanned"]])

    def test_movie_extras_is_part_of_parent_directory(self):
        with tempfile.TemporaryDirectory() as root:
            movie = os.path.join(root, "Movies", "Inception (2010)")
            write(os.path.join(movie, "Inception.2010.mkv"))
            write(os.path.join(movie, "Extras", "featurette.mkv"))
            result = scan_with_fake(movie)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["input_kind"], "directory")
            plan = build_plan(result)
            self.assertFalse(any("featurette" in (op.get("to") or "")
                                 for op in plan["units"][0]["operations"]))

    def test_nonmatching_show_dir_without_seasons_uses_title(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "TV", "RandomFolder")
            write(os.path.join(base, "Show.S01E01.mkv"))
            result = scan_with_fake(os.path.join(root, "TV"), mode="library")
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["context"]["show"], "Show")
            self.assertIn("container_name_ignored", result["units"][0]["warnings"])

    def test_mixed_root_groups_loose_episodes(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Movies")
            write(os.path.join(base, "Inception (2010)", "Inception.2010.mkv"))
            write(os.path.join(base, "Show.S01E01.mkv"))
            write(os.path.join(base, "Show.S01E02.mkv"))
            result = scan_with_fake(base, mode="library")
            kinds = [(unit["kind"], unit["input_kind"]) for unit in result["units"]]
            self.assertIn(("movie", "directory"), kinds)
            self.assertIn(("tv", "files"), kinds)
            tv = [unit for unit in result["units"] if unit["kind"] == "tv"]
            self.assertEqual(len(tv), 1)
            self.assertEqual(len(tv[0]["source_paths"]), 2)

    def test_flat_season_in_library_is_split_from_show_name(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "TV", "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            write(os.path.join(base, "Some.Show.S01E02.mkv"))
            result = scan_with_fake(os.path.join(root, "TV"), mode="library")
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["context"]["show"], "Some Show")
            plan = build_plan(result)
            self.assertEqual(plan["units"][0]["target"]["path"],
                             os.path.join(root, "TV", "Some Show"))
            self.assertTrue(any(op["op"] == "remove_empty_dir" and op["path"] == base
                                for op in plan["units"][0]["operations"]))

    def test_keep_empty_source_disables_remove(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            plan = build_plan(scan_with_fake(base), {"keep_empty_source": True})
            self.assertFalse(any(op["op"] == "remove_empty_dir"
                                 for op in plan["units"][0]["operations"]))

    def test_duplicate_move_target_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S01.1080p")
            write(os.path.join(base, "Some.Show.S01E01.mkv"))
            write(os.path.join(base, "Some.Show.S1E1.mkv"))
            plan = build_plan(scan_with_fake(base), {"rename_episodes": True})
            self.assertFalse(plan["units"])
            self.assertIn("duplicate_target",
                          [item["reason_code"] for item in plan["unplanned"]])

    def test_scan_truncated_rejects_plan(self):
        scan = {
            "schema_version": "1", "session_id": "s", "session_token": "t",
            "state_dir": "/tmp/x", "root": "/tmp/x", "mode": "library",
            "options": {}, "units": [], "unplanned": [], "skipped": [],
            "errors": [], "warnings": [{"code": "scan.truncated"}],
        }
        with self.assertRaises(PlanError) as ctx:
            build_plan(scan)
        self.assertEqual(ctx.exception.code, "E_SCAN_TRUNCATED")

    def test_unknown_extension_blocks_directory_rename(self):
        with tempfile.TemporaryDirectory() as root:
            movie = os.path.join(root, "Movies", "Inception (2010)")
            write(os.path.join(movie, "Inception.2010.mkv"))
            write(os.path.join(movie, "Inception.2010.exe"))
            result = scan_with_fake(movie)
            self.assertEqual(result["units"][0]["input_kind"], "files")

    def test_season_zero_is_not_promoted_to_one(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Some.Show.S00.1080p")
            write(os.path.join(base, "Some.Show.S00E01.mkv"))
            result = scan_with_fake(base)
            plan = build_plan(result)
            moves = [op["to"] for op in plan["units"][0]["operations"]
                     if op["op"] == "move"]
            self.assertTrue(moves)
            self.assertIn(os.path.join("Season 00"), moves[0])
            self.assertNotIn(os.path.join("Season 01"), moves[0])

    def test_show_and_season_rename_is_unplanned(self):
        with tempfile.TemporaryDirectory() as root:
            show = os.path.join(root, "TV", "Show.2019")
            write(os.path.join(show, "S1", "Show.S01E01.mkv"))
            result = scan_with_fake(show, mode="library")
            self.assertFalse(result["units"])
            self.assertIn("needs_directory_mode",
                          [item["reason_code"] for item in result["unplanned"]])

    def test_match_on_is_used_for_loose_movies(self):
        class Recorder(FakeRunner):
            def __init__(self):
                self.modes = []

            def detect(self, path, match="off", probe="off", max_files=5000):
                self.modes.append(match)
                return super().detect(path, match, probe, max_files)

        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "Downloads")
            write(os.path.join(base, "Inception.2010.mkv"))
            write(os.path.join(base, "Interstellar.2014.mkv"))
            rec = Recorder()
            with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: rec):
                result = scan_mod.scan_path(base, md_bin="fake", match="on")
            self.assertEqual(len(result["units"]), 2)
            self.assertIn("on", rec.modes)

    def test_match_off_is_passed_through(self):
        class Recorder(FakeRunner):
            def __init__(self):
                self.modes = []

            def detect(self, path, match="off", probe="off", max_files=5000):
                self.modes.append(match)
                return super().detect(path, match, probe, max_files)

        with tempfile.TemporaryDirectory() as root:
            video = os.path.join(root, "Downloads", "Inception.2010.mkv")
            write(video)
            rec = Recorder()
            with patch.object(scan_mod, "MediaDetectRunner", lambda _bin: rec):
                scan_mod.scan_path(video, md_bin="fake", match="off")
            self.assertTrue(rec.modes)
            self.assertTrue(all(mode == "off" for mode in rec.modes), rec.modes)

    def test_protected_tmp_is_recognized_on_macos(self):
        self.assertTrue(protected_root("/tmp"))
        self.assertTrue(protected_root("/var"))
        self.assertTrue(protected_root("/etc"))


class ApplyRegressionTests(unittest.TestCase):
    def _retry_plan(self, root):
        src_a = os.path.join(root, "a.mkv")
        src_b = os.path.join(root, "b.mkv")
        write(src_a)
        write(src_b)
        target = os.path.join(root, "Out")
        target_a = os.path.join(target, "a.mkv")
        target_b = os.path.join(target, "b.mkv")
        unit = {
            "id": "u1", "kind": "movie", "status": "planned",
            "sources": [
                {"path": src_a, "kind": "file", "state": lstat_state(src_a)},
                {"path": src_b, "kind": "file", "state": lstat_state(src_b)},
            ],
            "target": {"path": target, "kind": "directory"},
            "operations": [
                {"op": "mkdir", "path": target, "pre_exists": False, "pre_state": None},
                {"op": "move", "from": src_a, "to": target_a,
                 "from_state": lstat_state(src_a)},
                {"op": "move", "from": src_b, "to": target_b,
                 "from_state": lstat_state(src_b)},
            ],
        }
        plan = manual_plan(root, [unit])
        return plan, src_a, src_b, target, target_a, target_b

    def _write_done(self, plan, records):
        path = session_files(plan["state_dir"])["apply_log"]
        for record in records:
            record.update({
                "session_id": plan["session_id"],
                "session_token": plan["session_token"],
                "plan_id": plan["plan_id"],
                "state_dir": plan["state_dir"],
                "unit": "u1",
                "phase": "done",
            })
            append_jsonl(path, record)
        atomic_write_json(session_files(plan["state_dir"])["state"],
                          {"schema_version": "1", "session_id": plan["session_id"],
                           "session_token": plan["session_token"],
                           "state_dir": plan["state_dir"], "plan_id": plan["plan_id"],
                           "units": {"u1": {"status": "failed"}}})

    def test_retry_skips_completed_operations(self):
        with tempfile.TemporaryDirectory() as root:
            plan, src_a, src_b, target, target_a, target_b = self._retry_plan(root)
            os.mkdir(target)
            os.rename(src_a, target_a)
            self._write_done(plan, [
                {"op": "mkdir", "path": target, "created": True},
                {"op": "move", "from": src_a, "to": target_a,
                 "from_state": lstat_state(target_a), "to_state": lstat_state(target_a)},
            ])
            result = apply_plan(plan, plan["plan_id"], "u1", retry_failed=True)
            self.assertEqual(result["applied"], ["u1"])
            self.assertTrue(os.path.exists(target_b))
            self.assertFalse(os.path.exists(src_b))

    def test_reconcile_records_directory_subtree_hash(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "Show")
            write(os.path.join(src, "Season 01", "E01.mkv"))
            dst = os.path.join(root, "Show (2019)")
            digest, count = subtree_fingerprint(src)
            state = lstat_state(src)
            unit = {
                "id": "u1", "kind": "tv", "status": "planned",
                "sources": [{"path": src, "kind": "directory", "state": state}],
                "target": {"path": dst, "kind": "directory"},
                "operations": [{"op": "move", "from": src, "to": dst,
                                "from_state": state}],
            }
            plan = manual_plan(root, [unit])
            append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "move",
                "from": src, "to": dst, "from_state": state,
                "from_subtree_hash": digest, "entry_count": count,
            })
            os.rename(src, dst)
            reconcile(plan)
            records = [record for record in read_jsonl(
                session_files(plan["state_dir"])["apply_log"])
                if record.get("phase") == "done"]
            self.assertTrue(records)
            self.assertEqual(records[-1].get("to_subtree_hash"), digest)
            write(os.path.join(dst, "Season 01", "new.mkv"))
            with self.assertRaises(RollbackError) as ctx:
                rollback_plan(plan, plan["plan_id"])
            self.assertEqual(ctx.exception.code, "E_ROLLBACK_CONFLICT")

    def test_rollback_reconciles_interrupted_reverse_move(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write(src)
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
                "target": {"path": dst, "kind": "file"},
                "operations": [{"op": "move", "from": src, "to": dst,
                                "from_state": lstat_state(src)}],
            }
            plan = manual_plan(root, [unit])
            apply_plan(plan, plan["plan_id"], "u1")
            append_jsonl(session_files(plan["state_dir"])["rollback_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "move",
                "from": dst, "to": src, "from_state": lstat_state(dst),
            })
            os.link(dst, src)  # link succeeded, unlink(crash) not yet
            result = rollback_plan(plan, plan["plan_id"])
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(src))
            self.assertFalse(os.path.exists(dst))

    def test_retry_runs_unrelated_unit_despite_intent_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            a = os.path.join(root, "a.mkv")
            b = os.path.join(root, "b.mkv")
            c = os.path.join(root, "c.mkv")
            d = os.path.join(root, "d.mkv")
            write(a)
            write(b)
            write(c)
            units = [
                {"id": "u1", "kind": "movie", "status": "planned",
                 "sources": [{"path": a, "kind": "file", "state": lstat_state(a)}],
                 "target": {"path": b, "kind": "file"},
                 "operations": [{"op": "move", "from": a, "to": b,
                                 "from_state": lstat_state(a)}]},
                {"id": "u2", "kind": "movie", "status": "planned",
                 "sources": [{"path": c, "kind": "file", "state": lstat_state(c)}],
                 "target": {"path": d, "kind": "file"},
                 "operations": [{"op": "move", "from": c, "to": d,
                                 "from_state": lstat_state(c)}]},
            ]
            plan = manual_plan(root, units)
            append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "move",
                "from": a, "to": b, "from_state": lstat_state(a),
            })
            result = apply_plan(plan, plan["plan_id"], "u2", retry_failed=True)
            self.assertEqual(result["applied"], ["u2"])
            self.assertTrue(os.path.exists(d))
            self.assertFalse(os.path.exists(c))

    def test_reconcile_same_path_never_unlinks(self):
        with tempfile.TemporaryDirectory() as root:
            victim = os.path.join(root, "victim.bin")
            write(victim)
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [], "target": {"path": root, "kind": "directory"},
                "operations": [],
            }
            plan = manual_plan(root, [unit])
            append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "move",
                "from": victim, "to": victim, "from_state": lstat_state(victim),
            })
            conflicts = reconcile(plan, strict=False)
            self.assertTrue(conflicts)
            self.assertTrue(os.path.exists(victim))

    def test_cross_unit_path_overlap_is_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as root:
            show = os.path.join(root, "Show 2019")
            write(os.path.join(show, "Season 01", "Show.S01E01.mkv"))
            loose = os.path.join(root, "Show.2019.S02E01.mkv")
            write(loose)
            target_show = os.path.join(root, "Show (2019)")
            season2 = os.path.join(target_show, "Season 02")
            units = [
                {"id": "u1", "kind": "tv", "status": "planned",
                 "sources": [{"path": show, "kind": "directory",
                              "state": lstat_state(show)}],
                 "target": {"path": target_show, "kind": "directory"},
                 "operations": [{"op": "move", "from": show, "to": target_show,
                                 "from_state": lstat_state(show)}]},
                {"id": "u2", "kind": "tv", "status": "planned",
                 "sources": [{"path": loose, "kind": "file",
                              "state": lstat_state(loose)}],
                 "target": {"path": target_show, "kind": "directory"},
                 "operations": [
                     {"op": "mkdir", "path": target_show, "pre_exists": False,
                      "pre_state": None},
                     {"op": "mkdir", "path": season2, "pre_exists": False,
                      "pre_state": None},
                     {"op": "move", "from": loose,
                      "to": os.path.join(season2, "Show.2019.S02E01.mkv"),
                      "from_state": lstat_state(loose)}]},
            ]
            plan = manual_plan(root, units)
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "all")
            self.assertEqual(ctx.exception.code, "E_TARGET_IN_SOURCE")
            self.assertTrue(os.path.exists(show))
            self.assertTrue(os.path.exists(loose))

    def test_new_same_group_movie_video_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "Inception.2010.mkv")
            write(src)
            target = os.path.join(root, "Inception (2010)")
            target_file = os.path.join(target, "Inception.2010.mkv")
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
                "sibling_snapshot": {root: ["Inception.2010.mkv"]},
                "target": {"path": target, "kind": "directory"},
                "evidence": {"title": "Inception", "original_title": "Inception",
                             "year": 2010},
                "operations": [
                    {"op": "mkdir", "path": target, "pre_exists": False, "pre_state": None},
                    {"op": "move", "from": src, "to": target_file,
                     "from_state": lstat_state(src)}],
            }
            plan = manual_plan(root, [unit])
            write(os.path.join(root, "Inception.2010.2160p.mkv"))
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_SOURCE_STATE_MISMATCH")
            self.assertTrue(os.path.exists(src))

    def test_precheck_rejects_existing_same_inode_target(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write(src)
            os.link(src, dst)
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
                "target": {"path": root, "kind": "directory"},
                "operations": [{"op": "move", "from": src, "to": dst,
                                "from_state": lstat_state(src)}],
            }
            plan = manual_plan(root, [unit])
            with self.assertRaises(ApplyError) as ctx:
                apply_plan(plan, plan["plan_id"], "u1")
            self.assertEqual(ctx.exception.code, "E_TARGET_EXISTS")
            self.assertTrue(os.path.exists(src))
            self.assertTrue(os.path.exists(dst))

    def test_rollback_rejects_foreign_rollback_log(self):
        with tempfile.TemporaryDirectory() as root:
            victim = os.path.join(root, "victim.bin")
            write(victim)
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [], "target": {"path": root, "kind": "directory"},
                "operations": [],
            }
            plan = manual_plan(root, [unit])
            append_jsonl(session_files(plan["state_dir"])["rollback_log"], {
                "session_id": "other", "session_token": "0" * 32,
                "plan_id": "sha256:" + "0" * 64, "state_dir": "/tmp/other",
                "unit": "u1", "phase": "intent", "op": "move",
                "from": victim, "to": victim, "from_state": lstat_state(victim),
            })
            with self.assertRaises(RollbackError) as ctx:
                rollback_plan(plan, plan["plan_id"])
            self.assertEqual(ctx.exception.code, "E_SESSION_STATE_MISSING")
            self.assertTrue(os.path.exists(victim))

    def test_rollback_select_shared_parent_fails_before_changes(self):
        with tempfile.TemporaryDirectory() as root:
            s1 = os.path.join(root, "Show.S01E01.mkv")
            s2 = os.path.join(root, "Show.S02E01.mkv")
            write(s1)
            write(s2)
            show = os.path.join(root, "Show")
            units = [
                {"id": "u1", "kind": "tv", "status": "planned",
                 "sources": [{"path": s1, "kind": "file", "state": lstat_state(s1)}],
                 "target": {"path": show, "kind": "directory"},
                 "operations": [
                     {"op": "mkdir", "path": show, "pre_exists": False, "pre_state": None},
                     {"op": "mkdir", "path": os.path.join(show, "Season 01"),
                      "pre_exists": False, "pre_state": None},
                     {"op": "move", "from": s1,
                      "to": os.path.join(show, "Season 01", "Show.S01E01.mkv"),
                      "from_state": lstat_state(s1)}]},
                {"id": "u2", "kind": "tv", "status": "planned",
                 "sources": [{"path": s2, "kind": "file", "state": lstat_state(s2)}],
                 "target": {"path": show, "kind": "directory"},
                 "operations": [
                     {"op": "mkdir", "path": show, "pre_exists": False, "pre_state": None},
                     {"op": "mkdir", "path": os.path.join(show, "Season 02"),
                      "pre_exists": False, "pre_state": None},
                     {"op": "move", "from": s2,
                      "to": os.path.join(show, "Season 02", "Show.S02E01.mkv"),
                      "from_state": lstat_state(s2)}]},
            ]
            plan = manual_plan(root, units)
            apply_plan(plan, plan["plan_id"], "all")
            with self.assertRaises(RollbackError) as ctx:
                rollback_plan(plan, plan["plan_id"], select="u1")
            self.assertEqual(ctx.exception.code, "E_ROLLBACK_CONFLICT")
            self.assertTrue(os.path.exists(
                os.path.join(show, "Season 01", "Show.S01E01.mkv")))
            self.assertTrue(os.path.exists(
                os.path.join(show, "Season 02", "Show.S02E01.mkv")))

    def test_reconcile_never_unlinks_outside_root(self):
        with tempfile.TemporaryDirectory() as root:
            with tempfile.TemporaryDirectory() as outside:
                src = os.path.join(outside, "s.bin")
                dst = os.path.join(outside, "d.bin")
                write(src)
                os.link(src, dst)
                unit = {
                    "id": "u1", "kind": "movie", "status": "planned",
                    "sources": [], "target": {"path": root, "kind": "directory"},
                    "operations": [],
                }
                plan = manual_plan(root, [unit])
                append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                    "session_id": plan["session_id"],
                    "session_token": plan["session_token"],
                    "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                    "unit": "u1", "phase": "intent", "op": "move",
                    "from": src, "to": dst, "from_state": lstat_state(src),
                })
                conflicts = reconcile(plan, strict=False)
                self.assertTrue(conflicts)
                self.assertTrue(os.path.exists(src))
                self.assertTrue(os.path.exists(dst))

    def test_reconcile_mkdir_marks_created(self):
        with tempfile.TemporaryDirectory() as root:
            created = os.path.join(root, "Show", "Season 01")
            unit = {
                "id": "u1", "kind": "tv", "status": "planned",
                "sources": [], "target": {"path": created, "kind": "directory"},
                "operations": [],
            }
            plan = manual_plan(root, [unit])
            append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "mkdir",
                "path": created, "pre_exists": False,
            })
            os.makedirs(created)
            reconcile(plan)
            done = [record for record in read_jsonl(
                session_files(plan["state_dir"])["apply_log"])
                if record.get("phase") == "done"]
            self.assertTrue(done and done[-1].get("created"))

    def test_shared_show_target_is_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            s1 = os.path.join(root, "Show.S01E01.mkv")
            s2 = os.path.join(root, "Show.S02E01.mkv")
            write(s1)
            write(s2)
            show = os.path.join(root, "Show")
            units = [
                {"id": "u1", "kind": "tv", "status": "planned",
                 "sources": [{"path": s1, "kind": "file", "state": lstat_state(s1)}],
                 "target": {"path": show, "kind": "directory"},
                 "operations": [
                     {"op": "mkdir", "path": show, "pre_exists": False, "pre_state": None},
                     {"op": "mkdir", "path": os.path.join(show, "Season 01"),
                      "pre_exists": False, "pre_state": None},
                     {"op": "move", "from": s1,
                      "to": os.path.join(show, "Season 01", "Show.S01E01.mkv"),
                      "from_state": lstat_state(s1)}]},
                {"id": "u2", "kind": "tv", "status": "planned",
                 "sources": [{"path": s2, "kind": "file", "state": lstat_state(s2)}],
                 "target": {"path": show, "kind": "directory"},
                 "operations": [
                     {"op": "mkdir", "path": show, "pre_exists": False, "pre_state": None},
                     {"op": "mkdir", "path": os.path.join(show, "Season 02"),
                      "pre_exists": False, "pre_state": None},
                     {"op": "move", "from": s2,
                      "to": os.path.join(show, "Season 02", "Show.S02E01.mkv"),
                      "from_state": lstat_state(s2)}]},
            ]
            plan = manual_plan(root, units)
            result = apply_plan(plan, plan["plan_id"], "all")
            self.assertEqual(result["applied"], ["u1", "u2"])

    def test_rollback_reverses_done_units_despite_unresolved_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            src_a = os.path.join(root, "a.mkv")
            dst_a = os.path.join(root, "b.mkv")
            src_b = os.path.join(root, "c.mkv")
            dst_b = os.path.join(root, "d.mkv")
            for path in (src_a, src_b, dst_b):
                write(path)
            units = [
                {"id": "u1", "kind": "movie", "status": "planned",
                 "sources": [{"path": src_a, "kind": "file", "state": {}}],
                 "target": {"path": dst_a, "kind": "file"},
                 "operations": [{"op": "move", "from": src_a, "to": dst_a,
                                 "from_state": {}}]},
                {"id": "u2", "kind": "movie", "status": "planned",
                 "sources": [{"path": src_b, "kind": "file", "state": {}}],
                 "target": {"path": dst_b, "kind": "file"},
                 "operations": [{"op": "move", "from": src_b, "to": dst_b,
                                 "from_state": {}}]},
            ]
            plan = manual_plan(root, units)
            from_state = lstat_state(src_a)
            os.rename(src_a, dst_a)
            log = session_files(plan["state_dir"])["apply_log"]
            append_jsonl(log, {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "done", "op": "move",
                "from": src_a, "to": dst_a, "from_state": from_state,
                "to_state": lstat_state(dst_a),
            })
            # u2's move is unresolved and now conflicts: both endpoints exist.
            append_jsonl(log, {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u2", "phase": "intent", "op": "move",
                "from": src_b, "to": dst_b, "from_state": lstat_state(src_b),
            })
            result = rollback_plan(plan, plan["plan_id"])
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(src_a))
            self.assertFalse(os.path.exists(dst_a))
            self.assertTrue(result["conflicts"])

    def test_non_strict_reconcile_reports_conflict_instead_of_blocking(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "a.mkv")
            dst = os.path.join(root, "b.mkv")
            write(src)
            write(dst)
            unit = {
                "id": "u1", "kind": "movie", "status": "planned",
                "sources": [{"path": src, "kind": "file", "state": lstat_state(src)}],
                "target": {"path": dst, "kind": "file"},
                "operations": [{"op": "move", "from": src, "to": dst,
                                "from_state": lstat_state(src)}],
            }
            plan = manual_plan(root, [unit])
            append_jsonl(session_files(plan["state_dir"])["apply_log"], {
                "session_id": plan["session_id"], "session_token": plan["session_token"],
                "plan_id": plan["plan_id"], "state_dir": plan["state_dir"],
                "unit": "u1", "phase": "intent", "op": "move",
                "from": src, "to": dst, "from_state": lstat_state(src),
            })
            conflicts = reconcile(plan, strict=False)
            self.assertEqual(len(conflicts), 1)


if __name__ == "__main__":
    unittest.main()
