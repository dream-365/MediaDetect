"""No-replace moves, mkdir and empty-directory removal."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import stat
import tempfile
from typing import Optional, Tuple

from .paths import is_symlink, lstat_state, nearest_existing, subtree_fingerprint


class FsError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 3):
        if (code == "E_NO_REPLACE_UNSUPPORTED"
                and "no-replace=check" not in message):
            message += (" (on SMB/NFS, after confirming, use --no-replace=check "
                        "or MEDIA_TITLE_ALLOW_CHECK_RENAME=1 for apply and rollback)")
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


RENAME_NOREPLACE = 1
RENAME_EXCL = 0x00000004
AT_FDCWD = -100

MOVE_NATIVE = "native"
MOVE_LINK = "link_unlink"
MOVE_CHECK = "check_then_rename"


def _errno() -> int:
    return ctypes.get_errno()


def _linux_rename_noreplace(src: str, dst: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    func = getattr(libc, "renameat2", None)
    if func is None:
        raise OSError(errno.ENOSYS, "renameat2 unavailable")
    func.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    func.restype = ctypes.c_int
    if func(AT_FDCWD, os.fsencode(src), AT_FDCWD, os.fsencode(dst), RENAME_NOREPLACE) != 0:
        raise OSError(_errno(), os.strerror(_errno()))


def _darwin_rename_excl(src: str, dst: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    func = getattr(libc, "renamex_np", None)
    if func is None:
        raise OSError(errno.ENOSYS, "renamex_np unavailable")
    func.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    func.restype = ctypes.c_int
    if func(os.fsencode(src), os.fsencode(dst), RENAME_EXCL) != 0:
        raise OSError(_errno(), os.strerror(_errno()))


def _rename_noreplace(src: str, dst: str) -> None:
    system = platform.system()
    if system == "Linux":
        _linux_rename_noreplace(src, dst)
        return
    if system == "Darwin":
        _darwin_rename_excl(src, dst)
        return
    raise OSError(errno.ENOSYS, "no-replace rename unsupported on %s" % system)


def _link_fallback(src: str, dst: str) -> None:
    try:
        os.link(src, dst, follow_symlinks=False)
    except FileExistsError:
        raise FsError("E_TARGET_EXISTS", "target exists: %s" % dst)
    try:
        os.unlink(src)
    except OSError:
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise FsError("E_APPLY_FAILED", "link succeeded but unlink failed: %s" % src, exit_code=4)


UNSUPPORTED_ERRNOS = (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP)
LINK_UNSUPPORTED_ERRNOS = UNSUPPORTED_ERRNOS + (errno.EPERM,)


def _check_rename(src: str, dst: str) -> None:
    """Best-effort non-atomic move: check, then plain rename."""
    if os.path.lexists(dst):
        raise FsError("E_TARGET_EXISTS", "target exists: %s" % dst)
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            raise FsError("E_TARGET_EXISTS", "target exists: %s" % dst)
        if exc.errno == errno.ENOENT:
            raise FsError("E_SOURCE_MISSING", "source missing: %s" % src)
        if exc.errno == errno.EXDEV:
            raise FsError("E_CROSS_DEVICE", "cross-device move: %s -> %s" % (src, dst))
        raise


def _restore_check_move(src: str, dst: str) -> None:
    if os.path.lexists(src) or not os.path.lexists(dst):
        return
    try:
        os.rename(dst, src)
    except OSError:
        pass


def _move_result(method: str, validation: str, before: dict, after: dict) -> dict:
    return {
        "method": method,
        "atomic": method != MOVE_CHECK,
        "validation": validation,
        "from_state": before,
        "to_state": after,
    }


def safe_move(src: str, dst: str, allow_check: bool = False) -> dict:
    if is_symlink(src):
        raise FsError("E_SOURCE_SYMLINK", "source is a symlink: %s" % src)
    if not os.path.exists(src):
        raise FsError("E_SOURCE_MISSING", "source missing: %s" % src)
    if os.path.lexists(dst):
        raise FsError("E_TARGET_EXISTS", "target exists: %s" % dst)
    parent = os.path.dirname(dst)
    if not os.path.isdir(parent):
        raise FsError("E_TARGET_EXISTS", "target parent is not a directory: %s" % parent)
    before = lstat_state(src)
    is_dir = stat.S_ISDIR(os.lstat(src).st_mode)
    before_tree = (subtree_fingerprint(src, portable=True, include_mtime=False)
                   if is_dir and allow_check else None)
    method = MOVE_NATIVE
    try:
        _rename_noreplace(src, dst)
    except OSError as exc:
        if exc.errno in UNSUPPORTED_ERRNOS:
            if is_dir:
                if not allow_check:
                    raise FsError("E_NO_REPLACE_UNSUPPORTED",
                                  "directory no-replace rename unsupported: %s" % src)
                method = MOVE_CHECK
                _check_rename(src, dst)
            else:
                try:
                    _link_fallback(src, dst)
                    method = MOVE_LINK
                except FsError:
                    raise
                except OSError as link_exc:
                    if link_exc.errno not in LINK_UNSUPPORTED_ERRNOS or not allow_check:
                        raise FsError(
                            "E_NO_REPLACE_UNSUPPORTED",
                            "file no-replace/link unsupported: %s" % src)
                    method = MOVE_CHECK
                    _check_rename(src, dst)
        elif exc.errno == errno.EEXIST:
            raise FsError("E_TARGET_EXISTS", "target exists: %s" % dst)
        elif exc.errno == errno.ENOENT:
            raise FsError("E_SOURCE_MISSING", "source missing: %s" % src)
        elif exc.errno == errno.EXDEV:
            raise FsError("E_CROSS_DEVICE", "cross-device move: %s -> %s" % (src, dst))
        else:
            raise
    after = lstat_state(dst)
    if method == MOVE_CHECK:
        if is_dir:
            after_tree = subtree_fingerprint(dst, portable=True, include_mtime=False)
            if before_tree != after_tree:
                _restore_check_move(src, dst)
                raise FsError("E_NON_ATOMIC_MOVE_FAILED",
                              "check-then-rename content validation failed: %s -> %s"
                              % (src, dst), exit_code=4)
        elif before.get("size") != after.get("size"):
            _restore_check_move(src, dst)
            raise FsError("E_NON_ATOMIC_MOVE_FAILED",
                          "check-then-rename size validation failed: %s -> %s"
                          % (src, dst), exit_code=4)
        try:
            os.utime(dst, ns=(int(before["mtime_ns"]), int(before["mtime_ns"])))
        except OSError:
            pass
        after = lstat_state(dst)
        if before.get("mtime_ns") == after.get("mtime_ns"):
            validation = "size_mtime" if not is_dir else "portable_subtree"
        else:
            validation = "size_content"
        return _move_result(method, validation, before, after)
    if before.get("dev") != after.get("dev") or before.get("ino") != after.get("ino"):
        raise FsError("E_APPLY_FAILED", "inode changed during move: %s -> %s" % (src, dst), exit_code=4)
    return _move_result(method, "dev_ino", before, after)


def probe_no_replace(directory: str, kind: str, allow_check: bool = False) -> str:
    """Probe and return the move method supported by *directory*'s filesystem."""
    base = nearest_existing(directory)
    if not os.path.isdir(base):
        raise FsError("E_NO_REPLACE_UNSUPPORTED", "probe base is not a directory: %s" % base)
    if kind == "directory":
        tmp_src = tempfile.mkdtemp(prefix=".md-probe-", dir=base)
        tmp_dst = tmp_src + "-dst"
        try:
            try:
                _rename_noreplace(tmp_src, tmp_dst)
                return MOVE_NATIVE
            except OSError as exc:
                if exc.errno not in UNSUPPORTED_ERRNOS:
                    raise FsError("E_NO_REPLACE_UNSUPPORTED",
                                  "directory no-replace unsupported on %s: %s" % (base, exc))
                if not allow_check:
                    raise FsError("E_NO_REPLACE_UNSUPPORTED",
                                  "directory no-replace unsupported on %s" % base)
                _check_rename(tmp_src, tmp_dst)
                return MOVE_CHECK
        finally:
            for path in (tmp_src, tmp_dst):
                try:
                    os.rmdir(path)
                except OSError:
                    pass
    fd, tmp_src = tempfile.mkstemp(prefix=".md-probe-", dir=base)
    os.close(fd)
    tmp_dst = tmp_src + "-dst"
    try:
        try:
            _rename_noreplace(tmp_src, tmp_dst)
            return MOVE_NATIVE
        except OSError as exc:
            if exc.errno not in UNSUPPORTED_ERRNOS:
                raise FsError("E_NO_REPLACE_UNSUPPORTED",
                              "file no-replace unsupported on %s: %s" % (base, exc))
        try:
            os.link(tmp_src, tmp_dst)
            os.unlink(tmp_dst)
            return MOVE_LINK
        except OSError as exc:
            if exc.errno not in LINK_UNSUPPORTED_ERRNOS or not allow_check:
                raise FsError("E_NO_REPLACE_UNSUPPORTED",
                              "file no-replace/link unsupported on %s" % base)
        _check_rename(tmp_src, tmp_dst)
        return MOVE_CHECK
    finally:
        for path in (tmp_src, tmp_dst):
            try:
                os.unlink(path)
            except OSError:
                pass


def make_dir(path: str) -> Tuple[bool, Optional[int]]:
    try:
        os.mkdir(path)
        st = os.lstat(path)
        return True, int(st.st_ino)
    except FileExistsError:
        st = os.lstat(path)
        if not stat.S_ISDIR(st.st_mode):
            raise FsError("E_TARGET_EXISTS", "mkdir target is not a directory: %s" % path)
        return False, int(st.st_ino)


def remove_empty_dir(path: str) -> Tuple[bool, str]:
    try:
        entries = list(os.scandir(path))
    except FileNotFoundError:
        return True, "missing"
    if entries:
        return False, "leftover"
    try:
        os.rmdir(path)
        return True, "removed"
    except OSError:
        return False, "leftover"
