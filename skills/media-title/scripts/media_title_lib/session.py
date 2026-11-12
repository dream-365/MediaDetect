"""Session directory, locking and atomic JSON helpers.

The skill keeps all mutable state under <root>/.media-title/sessions/<id>/.
Nothing in this module touches media files.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SESSION_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
STATE_DIR_NAME = ".media-title"
SESSIONS_DIR_NAME = "sessions"


class SessionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s" % (stamp, secrets.token_hex(4))


def new_session_token() -> str:
    return secrets.token_hex(16)


def validate_session_id(session_id: str) -> None:
    if not SESSION_ID_RE.match(session_id or ""):
        raise SessionError("E_USAGE", "invalid session id: %r" % (session_id,))


def validate_session_token(token: str) -> None:
    if not SESSION_TOKEN_RE.match(token or ""):
        raise SessionError("E_SESSION_STATE_MISSING", "invalid session token")


def sessions_root(root: str) -> str:
    return os.path.join(os.path.abspath(root), STATE_DIR_NAME, SESSIONS_DIR_NAME)


def session_dir(root: str, session_id: str) -> str:
    validate_session_id(session_id)
    return os.path.join(sessions_root(root), session_id)


def session_files(state_dir: str) -> Dict[str, str]:
    return {
        "scan": os.path.join(state_dir, "scan.json"),
        "plan": os.path.join(state_dir, "plan.json"),
        "applied_plan": os.path.join(state_dir, "applied-plan.json"),
        "state": os.path.join(state_dir, "state.json"),
        "apply_log": os.path.join(state_dir, "apply.log.jsonl"),
        "rollback_log": os.path.join(state_dir, "rollback.log.jsonl"),
        "lock": os.path.join(state_dir, "apply.lock"),
    }


def ensure_session(
    root: str,
    session_id: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    session_id = session_id or new_session_id()
    validate_session_id(session_id)
    state_dir = session_dir(root, session_id)
    os.makedirs(state_dir, exist_ok=True)
    files = session_files(state_dir)
    if session_token is None:
        scan_path = files["scan"]
        if os.path.exists(scan_path):
            try:
                existing = read_json(scan_path)
                session_token = existing.get("session_token")
            except Exception:
                session_token = None
    if session_token is None:
        session_token = new_session_token()
    validate_session_token(session_token)
    return {
        "session_id": session_id,
        "session_token": session_token,
        "state_dir": state_dir,
        "files": files,
    }


def assert_state_dir(root: str, session_id: str, state_dir: str) -> None:
    expected = session_dir(root, session_id)
    if os.path.realpath(state_dir) != os.path.realpath(expected):
        raise SessionError(
            "E_SESSION_STATE_MISSING",
            "state_dir does not match root/session_id: %s" % state_dir,
        )


def atomic_write_json(path: str, obj: Any) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


@contextlib.contextmanager
def session_lock(state_dir: str, blocking: bool = False) -> Iterator[None]:
    """Exclusive lock for apply/rollback of one session."""
    files = session_files(state_dir)
    os.makedirs(state_dir, exist_ok=True)
    fd = os.open(files["lock"], os.O_CREAT | os.O_RDWR, 0o600)
    try:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            raise SessionError("E_SESSION_BUSY", "session is busy")
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
