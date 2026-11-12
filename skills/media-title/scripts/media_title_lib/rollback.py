"""Reverse a previously applied plan using intent/done logs."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from . import fsops
from .apply import (
    ApplyError,
    _reconcile_move,
    load_state,
    reconcile,
    save_state,
    validate_plan,
)
from .paths import is_within, lstat_state, protected_root, same_path, subtree_fingerprint
from .session import (
    append_jsonl,
    assert_state_dir,
    read_jsonl,
    session_files,
    session_lock,
    utc_now,
)


class RollbackError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 4):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _base(plan: Dict[str, Any], unit_id: str, **extra: Any) -> Dict[str, Any]:
    record = {
        "ts": utc_now(),
        "session_id": plan.get("session_id"),
        "session_token": plan.get("session_token"),
        "plan_id": plan.get("plan_id"),
        "state_dir": plan.get("state_dir"),
        "unit": unit_id,
        "direction": "rollback",
    }
    record.update(extra)
    return record


def _reconcile_rollback_log(plan: Dict[str, Any]) -> None:
    """Finish an interrupted reverse operation before a second rollback."""
    log_path = session_files(plan["state_dir"])["rollback_log"]
    records = read_jsonl(log_path)
    intents: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    done = set()
    for record in records:
        if (record.get("session_id") != plan.get("session_id")
                or record.get("session_token") != plan.get("session_token")
                or record.get("plan_id") != plan.get("plan_id")
                or record.get("state_dir") != plan.get("state_dir")):
            raise RollbackError("E_SESSION_STATE_MISSING",
                                "rollback log belongs to another session or plan")
        key = (record.get("unit"), record.get("op"),
               record.get("from") or record.get("path") or "", record.get("to") or "")
        if record.get("phase") == "intent":
            intents[key] = record
        elif record.get("phase") == "done":
            done.add(key)
    root = plan.get("root") or "/"
    for key, record in intents.items():
        if key in done:
            continue
        op = record.get("op")
        try:
            if op == "move":
                _reconcile_move(record, log_path, plan, root)
            elif op == "remove_empty_dir":
                path = record.get("path")
                if path and not os.path.exists(path):
                    append_jsonl(log_path, _base(plan, record.get("unit"),
                                                 phase="done", op=op, path=path,
                                                 result="missing", reconciled=True))
            elif op == "mkdir":
                path = record.get("path")
                if path and os.path.isdir(path):
                    append_jsonl(log_path, _base(plan, record.get("unit"),
                                                 phase="done", op=op, path=path,
                                                 created=False,
                                                 ino=int(os.lstat(path).st_ino),
                                                 reconciled=True))
        except (ApplyError, OSError):
            continue


def _done_records(plan: Dict[str, Any], select: Optional[str]) -> List[Dict[str, Any]]:
    records = read_jsonl(session_files(plan["state_dir"])["apply_log"])
    selected_ids = None
    if select and select != "all":
        selected_ids = {x.strip() for x in select.split(",") if x.strip()}
    out = []
    seen = set()
    for record in records:
        if record.get("phase") != "done":
            continue
        if record.get("session_token") != plan.get("session_token"):
            raise RollbackError("E_SESSION_STATE_MISSING", "log token mismatch")
        if record.get("plan_id") != plan.get("plan_id"):
            raise RollbackError("E_SESSION_STATE_MISSING", "log plan mismatch")
        if selected_ids is not None and record.get("unit") not in selected_ids:
            continue
        key = (record.get("unit"), record.get("op"),
               record.get("from") or record.get("path") or "", record.get("to") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _dir_only_allowed(path: str, allowed: set, created_dirs: Optional[set] = None) -> bool:
    try:
        entries = list(os.scandir(path))
    except OSError:
        return False
    for entry in entries:
        if entry.path in allowed:
            continue
        if (entry.is_dir(follow_symlinks=False) and created_dirs is not None
                and entry.path in created_dirs
                and _dir_only_allowed(entry.path, allowed, created_dirs)):
            continue
        return False
    return True


def _check_done_record(
    record: Dict[str, Any],
    root: str,
    allowed_targets: Optional[set] = None,
    created_dirs: Optional[set] = None,
) -> str:
    """Return 'already', 'reverse' or raise a conflict."""
    op = record.get("op")
    if op == "move":
        src = record.get("from")
        dst = record.get("to")
        if not src or not dst or not is_within(src, root) or not is_within(dst, root):
            raise RollbackError("E_ROLLBACK_CONFLICT",
                                "move path is outside plan root: %s -> %s" % (src, dst))
        from_state = record.get("from_state") or {}
        to_state = record.get("to_state") or {}
        src_exists = os.path.lexists(src)
        dst_exists = os.path.lexists(dst)
        if src_exists and not dst_exists:
            if _state_matches(src, from_state):
                return "already"
            raise RollbackError("E_ROLLBACK_CONFLICT", "source changed: %s" % src)
        if not dst_exists:
            raise RollbackError("E_ROLLBACK_CONFLICT", "target missing: %s" % dst)
        if not _state_matches(dst, to_state):
            raise RollbackError("E_ROLLBACK_CONFLICT", "target state changed: %s" % dst)
        if os.path.isdir(dst):
            expected_hash = record.get("to_subtree_hash")
            if expected_hash:
                current_hash, _count = subtree_fingerprint(dst)
                if current_hash != expected_hash:
                    raise RollbackError("E_ROLLBACK_CONFLICT", "target subtree changed: %s" % dst)
        if src_exists:
            raise RollbackError("E_ROLLBACK_CONFLICT", "reverse target already exists: %s" % src)
        return "reverse"
    if op == "mkdir":
        path = record.get("path")
        if not path or not is_within(path, root):
            raise RollbackError("E_ROLLBACK_CONFLICT", "mkdir path is outside plan root: %s" % path)
        if not os.path.exists(path):
            return "already"
        if not record.get("created"):
            return "already"
        if not os.path.isdir(path):
            raise RollbackError("E_ROLLBACK_CONFLICT", "mkdir path is not a directory: %s" % path)
        if allowed_targets is not None and not _dir_only_allowed(path, allowed_targets, created_dirs):
            raise RollbackError("E_ROLLBACK_CONFLICT",
                                "created directory contains unplanned entries: %s" % path)
        expected_ino = record.get("ino")
        if expected_ino:
            try:
                if int(os.lstat(path).st_ino) != int(expected_ino):
                    raise RollbackError("E_ROLLBACK_CONFLICT", "created directory inode changed: %s" % path)
            except OSError:
                raise RollbackError("E_ROLLBACK_CONFLICT", "cannot stat directory: %s" % path)
        return "reverse"
    if op == "remove_empty_dir":
        path = record.get("path")
        if not path or not is_within(path, root):
            raise RollbackError("E_ROLLBACK_CONFLICT",
                                "remove_empty_dir path is outside plan root: %s" % path)
        if os.path.exists(path):
            return "already"
        return "reverse"
    return "already"


def _state_matches(path: str, expected: Dict[str, Any]) -> bool:
    if not expected:
        return False
    try:
        current = lstat_state(path)
    except OSError:
        return False
    keys = ("dev", "ino") if os.path.isdir(path) else ("dev", "ino", "size", "mtime_ns")
    for key in keys:
        if key in expected and current.get(key) != expected.get(key):
            return False
    return True


def _reverse(plan: Dict[str, Any], record: Dict[str, Any], log_path: str) -> None:
    op = record.get("op")
    unit = record.get("unit")
    if op == "move":
        src = record["from"]
        dst = record["to"]
        intent = _base(plan, unit, phase="intent", op="move",
                       **{"from": dst, "to": src, "from_state": record.get("to_state"),
                          "to_absent": True})
        append_jsonl(log_path, intent)
        fsops.safe_move(dst, src)
        done = _base(plan, unit, phase="done", op="move",
                     **{"from": dst, "to": src, "from_state": record.get("to_state"),
                        "to_state": lstat_state(src), "result": "ok"})
        append_jsonl(log_path, done)
    elif op == "mkdir":
        path = record["path"]
        intent = _base(plan, unit, phase="intent", op="remove_empty_dir", path=path)
        append_jsonl(log_path, intent)
        removed, result = fsops.remove_empty_dir(path)
        if not removed:
            raise RollbackError("E_ROLLBACK_CONFLICT", "created directory is not empty: %s" % path)
        done = _base(plan, unit, phase="done", op="remove_empty_dir", path=path,
                     result=result)
        append_jsonl(log_path, done)
    elif op == "remove_empty_dir":
        path = record["path"]
        intent = _base(plan, unit, phase="intent", op="mkdir", path=path)
        append_jsonl(log_path, intent)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        done = _base(plan, unit, phase="done", op="mkdir", path=path,
                     created=True, ino=int(os.lstat(path).st_ino), result="ok")
        append_jsonl(log_path, done)


def rollback_plan(
    plan: Dict[str, Any],
    expect_plan_id: str,
    select: Optional[str] = None,
) -> Dict[str, Any]:
    validate_plan(plan, expect_plan_id)
    root = plan.get("root") or ""
    assert_state_dir(root, plan.get("session_id") or "", plan.get("state_dir") or "")
    if protected_root(root):
        raise RollbackError("E_PROTECTED_ROOT", "refusing protected root: %s" % root)
    state_dir = plan.get("state_dir")
    if not state_dir or not os.path.isdir(state_dir):
        raise RollbackError("E_SESSION_STATE_MISSING", "session state directory is missing")
    with session_lock(state_dir):
        state = load_state(plan)
        if state.get("session_token") != plan.get("session_token"):
            raise RollbackError("E_SESSION_STATE_MISSING", "state token mismatch")
        if state.get("plan_id") != plan.get("plan_id"):
            raise RollbackError("E_EXPECT_PLAN_MISMATCH", "state plan_id mismatch")
        conflicts = reconcile(plan, strict=False)
        _reconcile_rollback_log(plan)
        if select and select != "all":
            known = {unit.get("id") for unit in (plan.get("units") or [])}
            for unit_id in [x.strip() for x in select.split(",") if x.strip()]:
                if unit_id not in known:
                    raise RollbackError("E_UNKNOWN_UNIT", "unknown unit: %s" % unit_id,
                                        exit_code=1)
        records = _done_records(plan, select)
        if not records:
            applied_units = [
                uid for uid, item in (state.get("units") or {}).items()
                if item.get("status") in ("applied", "applying", "failed")
            ]
            if applied_units:
                raise RollbackError("E_SESSION_STATE_MISSING", "apply log is missing")
            raise RollbackError("E_NOTHING_TO_ROLLBACK", "nothing has been applied", exit_code=2)
        # For a partial rollback, only entries belonging to the selected units
        # may be treated as removable. Otherwise an early unit could remove a
        # shared parent that still contains another unit's season.
        scope_records = records if (select and select != "all") else _done_records(plan, "all")
        allowed_targets = {
            record.get("to") for record in scope_records
            if record.get("op") == "move" and record.get("to")
        }
        created_dirs = {
            record.get("path") for record in scope_records
            if record.get("op") == "mkdir" and record.get("created")
        }
        planned: List[Tuple[Dict[str, Any], str]] = []
        for record in records:
            planned.append((record, _check_done_record(
                record, root, allowed_targets, created_dirs)))
        touched = {record.get("unit") for record in records if record.get("unit")}
        for unit_id in touched:
            item = state.setdefault("units", {}).setdefault(unit_id, {})
            item["status"] = "rolling_back"
            item["updated_at"] = utc_now()
        save_state(plan, state)
        log_path = session_files(state_dir)["rollback_log"]
        rolled = []
        for record, action in reversed(planned):
            if action == "already":
                continue
            try:
                _reverse(plan, record, log_path)
            except RollbackError:
                raise
            except OSError as exc:
                raise RollbackError("E_ROLLBACK_FAILED", str(exc), exit_code=4)
            unit_id = record.get("unit")
            if unit_id and unit_id not in rolled:
                rolled.append(unit_id)
        touched = {record.get("unit") for record in records if record.get("unit")}
        for unit_id in touched:
            item = state.setdefault("units", {}).setdefault(unit_id, {})
            item["status"] = "rolled_back"
            item["updated_at"] = utc_now()
        save_state(plan, state)
        return {"ok": True, "rolled_back": rolled, "conflicts": conflicts,
                "plan_id": plan.get("plan_id")}
