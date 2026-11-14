#!/usr/bin/env python3
"""media-title command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

from media_title_lib import __version__
from media_title_lib.apply import ApplyError, apply_plan
from media_title_lib.fsops import FsError
from media_title_lib.plan import PlanError, build_plan, content_hash
from media_title_lib.rollback import RollbackError, rollback_plan
from media_title_lib.scan import ScanError, scan_path
from media_title_lib.session import (
    SessionError,
    assert_state_dir,
    atomic_write_json,
    read_json,
    session_files,
)


def _json_out(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def _err(code: str, message: str) -> None:
    sys.stderr.write("%s: %s\n" % (code, message))


def _read(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write(path: str, obj: Dict[str, Any]) -> None:
    atomic_write_json(path, obj)


def cmd_scan(args: argparse.Namespace) -> int:
    md_bin = args.md_bin or os.environ.get("MD_BIN") or "mediadetect"
    scan = scan_path(
        args.path,
        md_bin=md_bin,
        mode=args.mode,
        root=args.root,
        match=args.match,
        probe=args.probe,
        max_files=args.max_files,
        session_id=args.session,
        include_organized=args.include_organized,
    )
    files = session_files(scan["state_dir"])
    _write(files["scan"], scan)
    if args.out:
        _write(os.path.abspath(args.out), scan)
    if args.json:
        _json_out(scan)
    else:
        _human_scan(scan)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    scan = _read(args.scan)
    state_dir = scan.get("state_dir")
    if not state_dir:
        raise PlanError("E_SESSION_STATE_MISSING", "scan has no state_dir")
    assert_state_dir(scan.get("root") or "", scan.get("session_id") or "", state_dir)
    files = session_files(state_dir)
    if os.path.exists(files["plan"]):
        raise PlanError("E_SESSION_HAS_PLAN", "session already has a plan; start a new session")
    plan = build_plan(scan, {
        "rename_episodes": args.rename_episodes,
        "keep_empty_source": args.keep_empty_source,
    })
    _write(files["plan"], plan)
    if args.out:
        _write(os.path.abspath(args.out), plan)
    if args.json:
        _json_out(plan)
    else:
        _human_plan(plan)
    return 0


def _no_replace_mode(args: argparse.Namespace) -> str:
    if getattr(args, "no_replace", None):
        return args.no_replace
    if os.environ.get("MEDIA_TITLE_ALLOW_CHECK_RENAME") == "1":
        return "check"
    return "strict"


def cmd_apply(args: argparse.Namespace) -> int:
    if not args.yes:
        raise ApplyError("E_USAGE", "--yes is required", exit_code=1)
    if not args.select:
        raise ApplyError("E_USAGE", "--select is required", exit_code=1)
    plan = _read(args.plan)
    result = apply_plan(plan, args.expect_plan_id, args.select, args.retry_failed,
                        no_replace=_no_replace_mode(args))
    if args.json:
        _json_out(result)
    else:
        _human_apply(result)
    return 0


def _load_rollback_plan(args: argparse.Namespace) -> Dict[str, Any]:
    candidates = []
    if args.plan:
        candidates.append(args.plan)
    if args.session_dir:
        candidates.append(os.path.join(args.session_dir, "applied-plan.json"))
    last_error: Optional[Exception] = None
    mismatch: Optional[str] = None
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            plan = _read(candidate)
        except Exception as exc:
            last_error = exc
            continue
        try:
            actual = content_hash(plan)
        except Exception as exc:
            last_error = exc
            continue
        if plan.get("plan_id") != actual:
            mismatch = "E_PLAN_HASH_MISMATCH"
            continue
        if plan.get("plan_id") != args.expect_plan_id:
            mismatch = "E_EXPECT_PLAN_MISMATCH"
            continue
        return plan
    if mismatch:
        raise RollbackError(mismatch, "rollback plan does not match --expect-plan-id",
                            exit_code=3)
    if last_error:
        raise RollbackError("E_SESSION_STATE_MISSING", str(last_error))
    raise RollbackError("E_SESSION_STATE_MISSING", "no matching plan or applied-plan.json")


def cmd_rollback(args: argparse.Namespace) -> int:
    if not args.yes:
        raise RollbackError("E_USAGE", "--yes is required", exit_code=1)
    plan = _load_rollback_plan(args)
    result = rollback_plan(plan, args.expect_plan_id, args.select,
                           no_replace=_no_replace_mode(args))
    if args.json:
        _json_out(result)
    else:
        _human_rollback(result)
    return 0


def _human_scan(scan: Dict[str, Any]) -> None:
    print("session: %s" % scan.get("session_id"))
    print("root: %s  mode: %s" % (scan.get("root"), scan.get("mode")))
    print("units: %d  unplanned: %d  skipped: %d" % (
        len(scan.get("units") or []), len(scan.get("unplanned") or []),
        len(scan.get("skipped") or []),
    ))
    for unit in scan.get("units") or []:
        print("  %s  %s  %s" % (unit.get("kind"), unit.get("input_kind"),
                                unit.get("source_root") or ",".join(unit.get("source_paths") or [])))
    for item in scan.get("unplanned") or []:
        print("  unplanned %s  %s  %s" % (item.get("reason_code"), item.get("path"), item.get("reason")))
    for item in scan.get("skipped") or []:
        print("  skipped %s  %s  %s" % (item.get("reason_code"), item.get("path"), item.get("reason")))
    _human_warnings(scan.get("warnings") or [])


def _human_warnings(warnings: Any) -> None:
    for item in warnings or []:
        if isinstance(item, dict):
            print("  warning %s  %s  %s" % (
                item.get("code"), item.get("file") or "", item.get("detail") or ""))
        else:
            print("  warning %s" % item)


def _human_plan(plan: Dict[str, Any]) -> None:
    print("session: %s   plan: %s" % (plan.get("session_id"), plan.get("plan_id")))
    for unit in plan.get("units") or []:
        print("  %s  %s  %s -> %s" % (
            unit.get("id"), unit.get("kind"),
            (unit.get("sources") or [{}])[0].get("path", ""),
            (unit.get("target") or {}).get("path", ""),
        ))
    for item in plan.get("unplanned") or []:
        print("  unplanned %s  %s  %s" % (item.get("reason_code"), item.get("path"), item.get("reason")))
    _human_warnings(plan.get("warnings") or [])


def _print_warnings(result: Dict[str, Any]) -> None:
    for warning in result.get("warnings") or []:
        print("warning: %s  %s  method=%s  atomic=%s" % (
            warning.get("code"), warning.get("path"), warning.get("method"),
            warning.get("atomic")))


def _human_apply(result: Dict[str, Any]) -> None:
    print("applied: %s" % (", ".join(result.get("applied") or []) or "-"))
    if result.get("already_applied"):
        print("already applied: %s" % ", ".join(result["already_applied"]))
    _print_warnings(result)


def _human_rollback(result: Dict[str, Any]) -> None:
    print("rolled back: %s" % (", ".join(result.get("rolled_back") or []) or "-"))
    _print_warnings(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="media-title")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("--json", action="store_true", help="emit JSON on stdout")
    scan.add_argument("path")
    scan.add_argument("--out")
    scan.add_argument("--mode", choices=["auto", "single", "library"], default="auto")
    scan.add_argument("--root")
    scan.add_argument("--session")
    scan.add_argument("--md-bin", default=os.environ.get("MD_BIN", "mediadetect"))
    scan.add_argument("--match", choices=["auto", "on", "off"], default="auto")
    scan.add_argument("--probe", choices=["off", "auto"], default="off")
    scan.add_argument("--max-files", type=int, default=5000)
    scan.add_argument("--include-organized", action="store_true",
                      help="re-detect entries whose names contain {tt...}/{tmdb...}")
    scan.set_defaults(func=cmd_scan)

    plan = sub.add_parser("plan")
    plan.add_argument("--json", action="store_true", help="emit JSON on stdout")
    plan.add_argument("--scan", required=True)
    plan.add_argument("--out")
    plan.add_argument("--rename-episodes", action="store_true")
    plan.add_argument("--keep-empty-source", action="store_true")
    plan.set_defaults(func=cmd_plan)

    apply = sub.add_parser("apply")
    apply.add_argument("--json", action="store_true", help="emit JSON on stdout")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--expect-plan-id", required=True)
    apply.add_argument("--select", required=True)
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--retry-failed", action="store_true")
    apply.add_argument("--no-replace", choices=["strict", "check"], default=None,
                       help="strict: atomic no-replace only; check: opt-in non-atomic fallback")
    apply.set_defaults(func=cmd_apply)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--json", action="store_true", help="emit JSON on stdout")
    rollback.add_argument("--plan")
    rollback.add_argument("--session-dir")
    rollback.add_argument("--expect-plan-id", required=True)
    rollback.add_argument("--select")
    rollback.add_argument("--yes", action="store_true")
    rollback.add_argument("--no-replace", choices=["strict", "check"], default=None,
                          help="must be check when apply logs used check-then-rename")
    rollback.set_defaults(func=cmd_rollback)
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ScanError, PlanError, ApplyError, RollbackError, SessionError, FsError) as exc:
        code = getattr(exc, "code", "E_INTERNAL")
        exit_code = getattr(exc, "exit_code", 3)
        if args.json:
            _json_out({"ok": False, "error": {"code": code, "message": str(exc)}})
        else:
            _err(code, str(exc))
        return exit_code
    except Exception as exc:
        if args.json:
            _json_out({"ok": False, "error": {"code": "E_INTERNAL", "message": str(exc)}})
        else:
            _err("E_INTERNAL", str(exc))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
