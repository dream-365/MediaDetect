"""Preflight and execute a confirmed plan."""

from __future__ import annotations

import os
import stat
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import fsops
from .paths import (
    SIDECAR_EXTS,
    VIDEO_EXTS,
    is_symlink,
    is_within,
    lstat_state,
    nfc,
    normalize_title,
    protected_root,
    same_path,
    subtree_fingerprint,
)
from .plan import content_hash
from .session import (
    append_jsonl,
    assert_state_dir,
    atomic_write_json,
    read_json,
    read_jsonl,
    session_files,
    session_lock,
    utc_now,
)


class ApplyError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 3):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _now() -> str:
    return utc_now()


def _base_log(plan: Dict[str, Any], unit_id: str, **extra: Any) -> Dict[str, Any]:
    record = {
        "ts": _now(),
        "session_id": plan.get("session_id"),
        "session_token": plan.get("session_token"),
        "plan_id": plan.get("plan_id"),
        "state_dir": plan.get("state_dir"),
        "unit": unit_id,
    }
    record.update(extra)
    return record


def _state_path(plan: Dict[str, Any]) -> str:
    return session_files(plan["state_dir"])["state"]


def load_state(plan: Dict[str, Any]) -> Dict[str, Any]:
    path = _state_path(plan)
    if os.path.exists(path):
        return read_json(path)
    return {
        "schema_version": "1",
        "session_id": plan.get("session_id"),
        "session_token": plan.get("session_token"),
        "state_dir": plan.get("state_dir"),
        "plan_id": plan.get("plan_id"),
        "units": {},
    }


def save_state(plan: Dict[str, Any], state: Dict[str, Any]) -> None:
    atomic_write_json(_state_path(plan), state)


def _set_unit(state: Dict[str, Any], unit_id: str, status: str, **extra: Any) -> None:
    item = state.setdefault("units", {}).setdefault(unit_id, {})
    item["status"] = status
    item.update(extra)
    item["updated_at"] = _now()


def _unit_status(state: Dict[str, Any], unit_id: str) -> str:
    return (state.get("units", {}).get(unit_id) or {}).get("status", "pending")


def _op_key(unit_id: str, op: Dict[str, Any]) -> Tuple[str, str, str, str]:
    kind = op.get("op")
    return (
        unit_id,
        kind,
        op.get("from") or op.get("path") or "",
        op.get("to") or "",
    )


def _done_keys(plan: Dict[str, Any]) -> set:
    log_path = session_files(plan["state_dir"])["apply_log"]
    return {
        (record.get("unit"), record.get("op"),
         record.get("from") or record.get("path") or "", record.get("to") or "")
        for record in read_jsonl(log_path)
        if record.get("phase") == "done"
    }


def _promote_applied_units(plan: Dict[str, Any], state: Dict[str, Any]) -> None:
    log_path = session_files(plan["state_dir"])["apply_log"]
    records = read_jsonl(log_path)
    done = {
        (record.get("unit"), record.get("op"),
         record.get("from") or record.get("path") or "", record.get("to") or "")
        for record in records
        if record.get("phase") == "done"
    }
    changed = False
    for unit in plan.get("units") or []:
        uid = unit.get("id")
        status = _unit_status(state, uid)
        if status in ("applied", "rolled_back"):
            continue
        operations = unit.get("operations") or []
        if not operations:
            continue
        if all(_op_key(uid, op) in done for op in operations):
            _set_unit(state, uid, "applied")
            changed = True
    if changed:
        save_state(plan, state)


def validate_plan(plan: Dict[str, Any], expect_plan_id: str) -> None:
    actual = content_hash(plan)
    if plan.get("plan_id") != actual:
        raise ApplyError("E_PLAN_HASH_MISMATCH", "plan content hash mismatch")
    if expect_plan_id != plan.get("plan_id"):
        raise ApplyError("E_EXPECT_PLAN_MISMATCH", "expect-plan-id does not match plan")
    if plan.get("schema_version") != "1":
        raise ApplyError("E_SCHEMA_UNSUPPORTED", "unsupported plan schema_version")


def _same_state(path: str, expected: Optional[Dict[str, Any]],
                portable: bool = False) -> bool:
    if not expected:
        return os.path.exists(path)
    try:
        current = lstat_state(path)
    except OSError:
        return False
    if portable:
        keys = ("size", "mtime_ns") if not os.path.isdir(path) else ("mtime_ns",)
    else:
        keys = ("dev", "ino", "size", "mtime_ns")
    for key in keys:
        if key in expected and current.get(key) != expected.get(key):
            return False
    return True


def _same_size(path: str, expected: Optional[Dict[str, Any]]) -> bool:
    if not expected:
        return os.path.exists(path)
    try:
        current = lstat_state(path)
    except OSError:
        return False
    return "size" not in expected or current.get("size") == expected.get("size")


def _target_key(path: str) -> str:
    return nfc(os.path.realpath(path)).casefold()


def _source_attrs(unit: Dict[str, Any]) -> List[str]:
    out = []
    for source in unit.get("sources") or []:
        path = source.get("path")
        if path:
            out.append(path)
    return out


def _check_new_sidecars(unit: Dict[str, Any]) -> None:
    sources = set(_source_attrs(unit))
    snapshot = unit.get("sibling_snapshot") or {}
    for source in list(sources):
        if not os.path.isfile(source):
            continue
        parent = os.path.dirname(source)
        known = snapshot.get(parent)
        if known is None:
            # Plans created before sibling snapshots cannot tell a new sibling
            # from a pre-existing one; do not reject legitimate mixed roots.
            continue
        known_names = set(known)
        stem = os.path.splitext(os.path.basename(source))[0]
        try:
            entries = os.scandir(parent)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.name in known_names:
                        continue
                    e_stem, ext = os.path.splitext(entry.name)
                    if ((e_stem == stem or e_stem.startswith(stem + "."))
                            and ext.casefold() in SIDECAR_EXTS
                            and entry.path not in sources):
                        raise ApplyError(
                            "E_SOURCE_STATE_MISMATCH",
                            "new sidecar appeared after planning: %s" % entry.path,
                        )
                    if (unit.get("kind") == "tv" and ext.casefold() in VIDEO_EXTS
                            and entry.path not in sources):
                        show = normalize_title(
                            (unit.get("evidence") or {}).get("show") or "")
                        # A new unrelated video in the same download folder must
                        # not block this unit; only a likely same-show episode is
                        # a plan-time source change.
                        if show and show not in normalize_title(entry.name):
                            continue
                        raise ApplyError(
                            "E_SOURCE_STATE_MISMATCH",
                            "new episode appeared after planning: %s" % entry.path,
                        )
                    if (unit.get("kind") == "movie" and ext.casefold() in VIDEO_EXTS
                            and entry.path not in sources):
                        evidence = unit.get("evidence") or {}
                        titles = [
                            normalize_title(evidence.get("title") or ""),
                            normalize_title(evidence.get("original_title") or ""),
                            normalize_title(
                                os.path.splitext(os.path.basename(source))[0]),
                        ]
                        entry_title = normalize_title(entry.name)
                        if any(title and title in entry_title for title in titles):
                            raise ApplyError(
                                "E_SOURCE_STATE_MISMATCH",
                                "new video in the same movie group: %s" % entry.path,
                            )
                except OSError:
                    continue


def precheck(plan: Dict[str, Any], selected: List[Dict[str, Any]],
             retry: bool = False, allow_check: bool = False) -> Dict[Tuple[int, str], str]:
    root = plan.get("root") or "/"
    if protected_root(root):
        raise ApplyError("E_PROTECTED_ROOT", "refusing protected root: %s" % root)
    targets: Dict[str, str] = {}
    move_targets: Dict[str, str] = {}
    cross_entries: List[Tuple[str, str, str]] = []
    probes: Dict[Tuple[int, str], str] = {}
    for unit in selected:
        uid = unit.get("id")
        target = (unit.get("target") or {}).get("path")
        if target and not is_within(target, root):
            raise ApplyError("E_OUTSIDE_ROOT", "target outside root: %s" % target)
        if (target and unit.get("kind") == "movie" and os.path.exists(target)
                and not retry):
            raise ApplyError("E_TARGET_EXISTS", "movie target already exists: %s" % target)
        if target and unit.get("kind") == "movie":
            key = _target_key(target)
            if key in targets and targets[key] != uid:
                raise ApplyError("E_DUPLICATE_TARGET", "duplicate target: %s" % target)
            targets[key] = uid
        _check_new_sidecars(unit)
        for source in unit.get("sources") or []:
            path = source.get("path")
            kind = source.get("kind")
            if not path or is_symlink(path):
                raise ApplyError("E_SOURCE_SYMLINK", "source is missing or a symlink: %s" % path)
            if not os.path.exists(path):
                raise ApplyError("E_SOURCE_MISSING", "source missing: %s" % path)
            if kind == "directory":
                try:
                    current = lstat_state(path)
                except OSError:
                    raise ApplyError("E_SOURCE_MISSING", "source missing: %s" % path)
                expected = source.get("state") or {}
                if (not allow_check and expected.get("ino")
                        and current.get("ino") != expected.get("ino")):
                    raise ApplyError("E_SOURCE_STATE_MISMATCH", "source inode changed: %s" % path)
                if expected.get("mtime_ns") and current.get("mtime_ns") != expected.get("mtime_ns"):
                    raise ApplyError("E_SOURCE_STATE_MISMATCH", "source directory changed: %s" % path)
            else:
                if not _same_state(path, source.get("state"), portable=allow_check):
                    raise ApplyError("E_SOURCE_STATE_MISMATCH", "source changed: %s" % path)
        for op in unit.get("operations") or []:
            if op.get("op") != "move":
                continue
            src = op["from"]
            dst = op["to"]
            move_key = _target_key(dst)
            if move_key in move_targets:
                raise ApplyError("E_DUPLICATE_TARGET", "duplicate move target: %s" % dst)
            move_targets[move_key] = uid
            cross_entries.append((uid, "move_from", src))
            cross_entries.append((uid, "move_to", dst))
            # A legitimate plan never moves onto an existing directory entry;
            # same_path sources are skipped during plan construction.
            if os.path.lexists(dst):
                raise ApplyError("E_TARGET_EXISTS", "target exists: %s" % dst)
            if is_within(dst, src) or is_within(src, dst):
                if not same_path(src, dst):
                    raise ApplyError("E_TARGET_IN_SOURCE", "source/target overlap: %s -> %s" % (src, dst))
            if not is_within(src, root) or not is_within(dst, root):
                raise ApplyError("E_OUTSIDE_ROOT", "move outside root: %s -> %s" % (src, dst))
            try:
                src_dev = os.lstat(src).st_dev
                parent = os.path.dirname(dst)
                while parent and not os.path.exists(parent):
                    parent = os.path.dirname(parent)
                if not parent or not os.path.isdir(parent):
                    raise ApplyError("E_TARGET_EXISTS",
                                     "move target parent is not a directory: %s" % dst)
                dst_dev = os.lstat(parent).st_dev
            except OSError:
                raise ApplyError("E_SOURCE_MISSING", "cannot stat move: %s -> %s" % (src, dst))
            if src_dev != dst_dev:
                raise ApplyError("E_CROSS_DEVICE", "cross-device move: %s -> %s" % (src, dst))
            kind = "directory" if stat.S_ISDIR(os.lstat(src).st_mode) else "file"
            key = (int(src_dev), kind)
            if key not in probes:
                try:
                    probes[key] = fsops.probe_no_replace(
                        parent, kind, allow_check=allow_check)
                except fsops.FsError as exc:
                    raise ApplyError(exc.code, exc.message, exc.exit_code)
    # mkdir/remove_empty_dir paths may share parents; verify root containment.
    for unit in selected:
        for op in unit.get("operations") or []:
            if op.get("op") not in ("mkdir", "remove_empty_dir"):
                continue
            path = op["path"]
            cross_entries.append((unit.get("id"), op["op"], path))
            if not is_within(path, root):
                raise ApplyError("E_OUTSIDE_ROOT", "%s outside root: %s" % (op["op"], path))
            if os.path.lexists(path) and not os.path.isdir(path):
                raise ApplyError("E_TARGET_EXISTS",
                                 "%s target is not a directory: %s" % (op["op"], path))
            if op.get("op") == "mkdir":
                parent = os.path.dirname(path)
                while parent and not os.path.exists(parent):
                    parent = os.path.dirname(parent)
                if not parent or not os.path.isdir(parent):
                    raise ApplyError("E_TARGET_EXISTS",
                                     "mkdir parent is not a directory: %s" % path)

    # Cross-unit source/target overlap: a directory move or a move source must
    # not contain another selected unit's paths. Shared mkdir ancestors are the
    # only allowed overlap.
    for index, (uid_a, role_a, path_a) in enumerate(cross_entries):
        for uid_b, role_b, path_b in cross_entries[index + 1:]:
            if uid_a == uid_b:
                continue
            if role_a == "mkdir" and role_b == "mkdir":
                continue
            if not (is_within(path_a, path_b) or is_within(path_b, path_a)):
                continue
            if role_a == "mkdir" and role_b == "move_to":
                continue
            if role_b == "mkdir" and role_a == "move_to":
                continue
            raise ApplyError(
                "E_TARGET_IN_SOURCE",
                "overlapping paths across units: %s (%s) and %s (%s)"
                % (path_a, role_a, path_b, role_b))
    return probes


def _reconcile_move(record: Dict[str, Any], log_path: str,
                    plan: Dict[str, Any], root: str) -> Optional[Dict[str, Any]]:
    src = record.get("from")
    dst = record.get("to")
    if not src or not dst or not is_within(src, root) or not is_within(dst, root):
        raise ApplyError("E_OUTSIDE_ROOT",
                         "log move path is outside plan root: %s -> %s" % (src, dst))
    from_state = record.get("from_state") or {}
    to_state = record.get("to_state") or {}
    method = record.get("move_method") or fsops.MOVE_NATIVE
    portable = method == fsops.MOVE_CHECK
    # An intent is written before we know whether utime will succeed. SMB may
    # rewrite mtime during the crash window, so reconciliation must compare
    # content only, regardless of the validation value guessed in the intent.
    content_only = portable and (
        record.get("validation") == "size_content"
        or record.get("phase") == "intent")
    src_exists = os.path.lexists(src) if src else False
    dst_exists = os.path.lexists(dst) if dst else False
    if src_exists and not dst_exists:
        return None
    if dst_exists and not src_exists:
        current = lstat_state(dst)
        if portable:
            if content_only:
                if os.path.isdir(dst):
                    expected = record.get("from_content_hash")
                    current_hash, _ = subtree_fingerprint(
                        dst, portable=True, include_mtime=False)
                    if expected and current_hash != expected:
                        raise ApplyError("E_NON_ATOMIC_MOVE_FAILED",
                                         "check-then-rename content mismatch: %s" % dst,
                                         exit_code=4)
                elif not _same_size(dst, from_state):
                    raise ApplyError("E_NON_ATOMIC_MOVE_FAILED",
                                     "check-then-rename size mismatch: %s" % dst,
                                     exit_code=4)
            elif not _same_state(dst, from_state, portable=True):
                raise ApplyError("E_NON_ATOMIC_MOVE_FAILED",
                                 "check-then-rename target state mismatch: %s" % dst,
                                 exit_code=4)
        elif from_state.get("dev") is not None and from_state.get("ino") is not None:
            # rename() and link+unlink both preserve the inode; a different
            # object at the target means someone replaced it after the move.
            if (current.get("dev") != from_state.get("dev")
                    or current.get("ino") != from_state.get("ino")):
                raise ApplyError("E_APPLY_FAILED", "move target identity mismatch: %s" % dst,
                                 exit_code=4)
        elif not _same_state(dst, to_state):
            raise ApplyError("E_APPLY_FAILED", "move target state mismatch: %s" % dst, exit_code=4)
        extra: Dict[str, Any] = {
            "move_method": method,
            "atomic": not portable,
            "validation": "size_content" if content_only else (
                record.get("validation") or (
                    "portable_subtree" if portable and os.path.isdir(dst)
                    else "size_mtime")),
        }
        if os.path.isdir(dst):
            expected_hash = (record.get("from_content_hash") if content_only
                             else record.get("from_subtree_hash"))
            current_hash, count = subtree_fingerprint(
                dst, portable=portable, include_mtime=not content_only)
            if expected_hash:
                extra.update({"to_subtree_hash": expected_hash,
                              "entry_count": record.get("entry_count")})
                if current_hash != expected_hash:
                    extra["subtree_mismatch"] = True
            else:
                extra.update({"to_subtree_hash": current_hash, "entry_count": count})
            if content_only and record.get("from_content_hash"):
                extra["to_content_hash"] = record.get("from_content_hash")
        done = _base_log(plan, record.get("unit"), phase="done", op="move",
                         **{"from": src, "to": dst, "from_state": from_state,
                            "to_state": current, "reconciled": True, **extra})
        append_jsonl(log_path, done)
        return done
    if src_exists and dst_exists:
        try:
            same_entry = os.path.realpath(src) == os.path.realpath(dst)
        except OSError:
            same_entry = True
        if same_entry:
            # Never unlink when from and to are the same directory entry; that
            # would delete the only copy. Hard links share an inode but have
            # different paths, so realpath is the right test here.
            raise ApplyError("E_APPLY_FAILED",
                             "move source and target are the same path: %s" % src,
                             exit_code=4)
        if portable:
            # check-then-rename never creates hard links; both endpoints
            # existing is an unresolvable conflict.
            raise ApplyError("E_NON_ATOMIC_MOVE_FAILED",
                             "check-then-rename left both endpoints: %s -> %s" % (src, dst),
                             exit_code=4)
        try:
            same = os.path.samefile(src, dst)
        except OSError:
            same = False
        if same:
            try:
                before = lstat_state(dst)
            except OSError:
                raise ApplyError("E_APPLY_FAILED",
                                 "cannot stat link+unlink target: %s" % dst, exit_code=4)
            if (from_state.get("dev") is None or from_state.get("ino") is None
                    or before.get("dev") != from_state.get("dev")
                    or before.get("ino") != from_state.get("ino")):
                raise ApplyError("E_APPLY_FAILED",
                                 "link+unlink target identity mismatch: %s" % dst,
                                 exit_code=4)
            try:
                os.unlink(src)
                current = lstat_state(dst)
            except OSError:
                raise ApplyError("E_APPLY_FAILED",
                                 "link+unlink recovery failed: %s -> %s" % (src, dst),
                                 exit_code=4)
            done = _base_log(plan, record.get("unit"), phase="done", op="move",
                             **{"from": src, "to": dst, "from_state": from_state,
                                "to_state": current, "reconciled": True})
            append_jsonl(log_path, done)
            return done
        raise ApplyError("E_APPLY_FAILED", "move conflict: %s -> %s" % (src, dst), exit_code=4)
    raise ApplyError("E_APPLY_FAILED", "both move endpoints missing: %s -> %s" % (src, dst), exit_code=4)


def reconcile(plan: Dict[str, Any], strict: bool = True) -> List[Dict[str, Any]]:
    log_path = session_files(plan["state_dir"])["apply_log"]
    records = read_jsonl(log_path)
    intents: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    done_keys = set()
    for record in records:
        if record.get("session_token") != plan.get("session_token"):
            raise ApplyError("E_SESSION_STATE_MISSING", "log belongs to another session")
        if record.get("plan_id") != plan.get("plan_id"):
            raise ApplyError("E_SESSION_STATE_MISSING", "log belongs to another plan")
        op = record.get("op")
        key = (record.get("unit"), op, record.get("from") or record.get("path") or "", record.get("to") or "")
        if record.get("phase") == "intent":
            intents[key] = record
        elif record.get("phase") == "done":
            done_keys.add(key)
    conflicts: List[Dict[str, Any]] = []
    root = plan.get("root") or "/"
    for key, record in intents.items():
        if key in done_keys:
            continue
        op = record.get("op")
        try:
            if op == "move":
                _reconcile_move(record, log_path, plan, root)
            elif op == "mkdir":
                path = record.get("path")
                if not os.path.exists(path):
                    continue
                if not os.path.isdir(path):
                    raise ApplyError("E_APPLY_FAILED",
                                     "mkdir path is not a directory: %s" % path, exit_code=4)
                try:
                    ino = int(os.lstat(path).st_ino)
                except OSError:
                    ino = None
                # Spec 4.8: pre_exists=false plus a present directory means
                # this run created it; rollback should remove it when empty.
                done = _base_log(plan, record.get("unit"), phase="done", op="mkdir",
                                 path=path, created=not bool(record.get("pre_exists")),
                                 ino=ino, reconciled=True)
                append_jsonl(log_path, done)
            elif op == "remove_empty_dir":
                path = record.get("path")
                if not os.path.exists(path):
                    done = _base_log(plan, record.get("unit"), phase="done", op="remove_empty_dir",
                                     path=path, removed_state=record.get("removed_state"),
                                     result="missing", reconciled=True)
                    append_jsonl(log_path, done)
        except ApplyError as exc:
            if strict:
                raise
            conflicts.append({"code": exc.code, "message": exc.message,
                              "unit": record.get("unit"), "op": op,
                              "path": record.get("from") or record.get("path") or ""})
    return conflicts


def _select_units(plan: Dict[str, Any], select: str) -> List[Dict[str, Any]]:
    units = list(plan.get("units") or [])
    if select == "all":
        return units
    wanted = [x.strip() for x in select.split(",") if x.strip()]
    if not wanted:
        raise ApplyError("E_USAGE", "--select is empty", exit_code=1)
    by_id = {u.get("id"): u for u in units}
    selected = []
    seen = set()
    for unit_id in wanted:
        if unit_id not in by_id:
            raise ApplyError("E_UNKNOWN_UNIT", "unknown unit: %s" % unit_id, exit_code=1)
        if unit_id in seen:
            continue
        seen.add(unit_id)
        selected.append(by_id[unit_id])
    return selected


def _write_applied_plan(plan: Dict[str, Any]) -> None:
    path = session_files(plan["state_dir"])["applied_plan"]
    if not os.path.exists(path):
        atomic_write_json(path, plan)


def apply_plan(
    plan: Dict[str, Any],
    expect_plan_id: str,
    select: str,
    retry_failed: bool = False,
    no_replace: str = "strict",
) -> Dict[str, Any]:
    if no_replace not in ("strict", "check"):
        raise ApplyError("E_USAGE", "--no-replace must be strict or check", exit_code=1)
    allow_check = no_replace == "check"
    validate_plan(plan, expect_plan_id)
    assert_state_dir(plan.get("root") or "", plan.get("session_id") or "", plan.get("state_dir") or "")
    state_dir = plan.get("state_dir")
    if not state_dir or not os.path.isdir(state_dir):
        raise ApplyError("E_SESSION_STATE_MISSING", "session state directory is missing")
    if protected_root(plan.get("root") or "/"):
        raise ApplyError("E_PROTECTED_ROOT",
                         "refusing protected root: %s" % plan.get("root"))
    with session_lock(state_dir):
        state = load_state(plan)
        if state.get("session_token") != plan.get("session_token"):
            raise ApplyError("E_SESSION_STATE_MISSING", "state token mismatch")
        if state.get("plan_id") != plan.get("plan_id"):
            raise ApplyError("E_EXPECT_PLAN_MISMATCH", "state plan_id mismatch")
        conflicts = reconcile(plan, strict=False)
        _promote_applied_units(plan, state)
        selected = _select_units(plan, select)
        selected_ids = {unit.get("id") for unit in selected}
        blocking = [item for item in conflicts if item.get("unit") in selected_ids]
        if blocking and not retry_failed:
            raise ApplyError("E_UNIT_STATE_CONFLICT",
                             "unresolved apply intent for %s; use --retry-failed or rollback"
                             % ",".join(sorted(str(item.get("unit")) for item in blocking)),
                             exit_code=4)
        done_keys = _done_keys(plan)
        done_units = {key[0] for key in done_keys}
        to_run: List[Dict[str, Any]] = []
        already = []
        for unit in selected:
            uid = unit.get("id")
            status = _unit_status(state, uid)
            if status in ("rolled_back", "rolling_back"):
                raise ApplyError("E_UNIT_STATE_CONFLICT",
                                 "unit %s is %s; create a new plan or finish rollback"
                                 % (uid, status))
            if status == "applied":
                if uid not in done_units:
                    raise ApplyError("E_SESSION_STATE_MISSING",
                                     "unit %s is applied but has no apply log" % uid)
                already.append(uid)
                continue
            if status in ("failed", "applying") and not retry_failed:
                raise ApplyError("E_UNIT_STATE_CONFLICT",
                                 "unit %s is %s; use --retry-failed or rollback first" % (uid, status))
            pending = [op for op in (unit.get("operations") or [])
                       if _op_key(uid, op) not in done_keys]
            if not pending:
                _set_unit(state, uid, "applied")
                save_state(plan, state)
                already.append(uid)
                continue
            run_unit = dict(unit)
            run_unit["operations"] = pending
            pending_sources = {
                op.get("from") for op in pending if op.get("op") == "move"
            }
            run_unit["sources"] = [
                source for source in (unit.get("sources") or [])
                if source.get("path") in pending_sources
            ]
            to_run.append(run_unit)
        if not to_run:
            return {"ok": True, "applied": [], "already_applied": already,
                    "conflicts": conflicts, "warnings": [], "plan_id": plan.get("plan_id")}
        capabilities = precheck(plan, to_run, retry=retry_failed, allow_check=allow_check)
        _write_applied_plan(plan)
        log_path = session_files(state_dir)["apply_log"]
        applied = []
        warnings: List[Dict[str, Any]] = []
        for unit in to_run:
            uid = unit.get("id")
            _set_unit(state, uid, "applying")
            save_state(plan, state)
            try:
                for op in unit.get("operations") or []:
                    kind = op.get("op")
                    if kind == "mkdir":
                        intent = _base_log(plan, uid, phase="intent", op="mkdir",
                                           path=op["path"], pre_exists=bool(op.get("pre_exists")),
                                           pre_state=op.get("pre_state"))
                        append_jsonl(log_path, intent)
                        created, ino = fsops.make_dir(op["path"])
                        done = _base_log(plan, uid, phase="done", op="mkdir",
                                         path=op["path"], created=created, ino=ino, result="ok")
                        append_jsonl(log_path, done)
                    elif kind == "move":
                        source = op["from"]
                        is_dir = os.path.isdir(source)
                        try:
                            source_dev = int(os.lstat(source).st_dev)
                        except OSError:
                            raise ApplyError("E_SOURCE_MISSING",
                                             "source missing before move: %s" % source)
                        capability = capabilities.get(
                            (source_dev, "directory" if is_dir else "file"),
                            fsops.MOVE_NATIVE)
                        portable = capability == fsops.MOVE_CHECK
                        validation = (
                            "portable_subtree" if portable and is_dir
                            else "size_mtime" if portable else "dev_ino")
                        if not _same_state(source, op.get("from_state"), portable=portable):
                            raise ApplyError("E_SOURCE_STATE_MISMATCH",
                                             "source changed before move: %s" % source)
                        intent_extra: Dict[str, Any] = {
                            "from": source, "to": op["to"],
                            "from_state": op.get("from_state"), "to_absent": True,
                            "move_method": capability,
                            "atomic": not portable,
                            "validation": validation,
                        }
                        if is_dir:
                            digest, count = subtree_fingerprint(source, portable=portable)
                            intent_extra.update({
                                "from_subtree_hash": digest,
                                "entry_count": count,
                            })
                            if portable:
                                content_hash, _ = subtree_fingerprint(
                                    source, portable=True, include_mtime=False)
                                intent_extra["from_content_hash"] = content_hash
                        intent = _base_log(plan, uid, phase="intent", op="move",
                                           **intent_extra)
                        append_jsonl(log_path, intent)
                        move_info = fsops.safe_move(source, op["to"], allow_check=allow_check)
                        actual_method = move_info["method"]
                        to_state = lstat_state(op["to"])
                        extra = {
                            "move_method": actual_method,
                            "atomic": bool(move_info["atomic"]),
                            "validation": move_info["validation"],
                        }
                        if is_dir:
                            extra.update({
                                "to_subtree_hash": intent_extra.get("from_subtree_hash"),
                                "entry_count": intent_extra.get("entry_count"),
                            })
                            if intent_extra.get("from_content_hash"):
                                extra["to_content_hash"] = intent_extra["from_content_hash"]
                        if actual_method == fsops.MOVE_CHECK:
                            warnings.append({
                                "code": "non_atomic_move",
                                "path": op["to"],
                                "method": fsops.MOVE_CHECK,
                                "atomic": False,
                                "validation": move_info["validation"],
                            })
                            if move_info["validation"] == "size_content":
                                warnings.append({
                                    "code": "mtime_rewritten",
                                    "path": op["to"],
                                    "method": fsops.MOVE_CHECK,
                                    "atomic": False,
                                })
                        done = _base_log(plan, uid, phase="done", op="move",
                                         **{"from": source, "to": op["to"],
                                            "from_state": op.get("from_state"),
                                            "to_state": to_state, "result": "ok", **extra})
                        append_jsonl(log_path, done)
                    elif kind == "remove_empty_dir":
                        intent = _base_log(plan, uid, phase="intent", op="remove_empty_dir",
                                           path=op["path"], pre_empty=bool(op.get("pre_empty")),
                                           removed_state=op.get("removed_state"))
                        append_jsonl(log_path, intent)
                        removed, result = fsops.remove_empty_dir(op["path"])
                        done = _base_log(plan, uid, phase="done", op="remove_empty_dir",
                                         path=op["path"], removed=removed, result=result,
                                         removed_state=op.get("removed_state"))
                        append_jsonl(log_path, done)
                _set_unit(state, uid, "applied")
                save_state(plan, state)
                applied.append(uid)
            except Exception as exc:
                _set_unit(state, uid, "failed", error=str(exc))
                save_state(plan, state)
                if isinstance(exc, ApplyError):
                    raise
                if isinstance(exc, fsops.FsError):
                    raise ApplyError(exc.code, exc.message, exc.exit_code)
                raise ApplyError("E_APPLY_FAILED", str(exc), exit_code=4)
        return {"ok": True, "applied": applied, "already_applied": already,
                "conflicts": conflicts, "warnings": warnings,
                "plan_id": plan.get("plan_id")}
