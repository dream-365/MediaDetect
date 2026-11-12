"""Raw path handling, NFC defence and filesystem metadata helpers."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm",
    ".ts", ".m2ts", ".mpg", ".mpeg", ".vob", ".rmvb", ".rm", ".3gp",
    ".iso",
}
SIDECAR_EXTS = {
    ".srt", ".ass", ".ssa", ".sub", ".idx", ".nfo",
    ".jpg", ".jpeg", ".png", ".webp",
}
MOVIE_LEVEL_FILES = {
    "poster.jpg", "fanart.jpg", "banner.jpg", "logo.png", "movie.nfo",
    ".ds_store", "thumbs.db", "desktop.ini",
}
MOVIE_LEVEL_DIRS = {
    "subs", "subtitles", "字幕", "extras", "featurettes", "trailers",
}
GENERIC_CONTAINERS = {
    "downloads", "download", "incoming", "temp", "tmp", "new folder",
    "movies", "movie", "films", "media", "video", "videos",
    "tv", "tv shows", "shows", "剧集", "电视剧", "电影", "影片", "下载", "临时",
}

SEASON_WHOLE_RES = (
    re.compile(r"^season\s*0?(\d{1,2})$", re.IGNORECASE),
    re.compile(r"^s0?(\d{1,2})$", re.IGNORECASE),
    re.compile(r"^第\s*(\d{1,2})\s*季$"),
)
SEASON_ANY_RE = re.compile(r"(?i)(?:^|[._\s-])(?:season\s*0?(\d{1,2})|s0?(\d{1,2}))(?:$|[._\s-])")
CJK_SEASON_ANY_RE = re.compile(r"第\s*(\d{1,2})\s*季")
EPISODE_ANY_RE = re.compile(r"(?i)s(\d{1,2})\s*[._-]?\s*e(\d{1,3})((?:\s*[._-]?\s*e\d{1,3})*)")
CJK_EPISODE_ANY_RE = re.compile(r"第\s*(\d{1,3})\s*集")
MULTIPART_RES = (
    re.compile(r"(?i)(?:^|[._\s-])(?:cd|disc|disk)\s*[._-]?\s*(\d{1,2})(?:$|[._\s-])"),
    re.compile(r"(?i)(?:^|[._\s-])(?:part|pt)\s*[._-]?\s*([a-z0-9]{1,2})(?:$|[._\s-])"),
    re.compile(r"(?i)(?:^|[._\s-])\d+\s*of\s*\d+(?:$|[._\s-])"),
    re.compile(r"(?:上集|下集|上部|下部|前篇|后篇)"),
    re.compile(r"(?i)[._\s-][ab](?:$|[._\s-])"),
)
RELEASE_TAG_RE = re.compile(
    r"(?i)(?:^|[._\s-])("
    r"2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|web-dl|webrip|hdtv|dvdrip|"
    r"x264|x265|h264|h265|hevc|avc|aac|ac3|dts|truehd|atmos|"
    r"proper|repack|extended|remastered|directors?\.?cut|"
    r"hdr|sdr|10bit|8bit|dolby\.?vision"
    r")(?:$|[._\s-])"
)


class PathIdentityError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "E_PATH_IDENTITY"


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text or "")


def casefold(text: str) -> str:
    return nfc(text).casefold()


def is_hidden_name(name: str) -> bool:
    return name.startswith(".")


def iter_raw_tree(
    root: str,
    skip_hidden: bool = True,
    skip_symlinks: bool = True,
) -> Iterator[Tuple[str, str, bool]]:
    """Yield (absolute_path, relative_path, is_dir) using os.scandir.

    Raw names are preserved. Hidden entries and symlinks are skipped by default,
    mirroring MediaDetect's collector.
    """

    root = os.path.abspath(root)
    stack: List[Tuple[str, str]] = [(root, "")]
    while stack:
        current, rel = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if skip_hidden and is_hidden_name(name):
                continue
            try:
                if skip_symlinks and entry.is_symlink():
                    continue
                child_rel = os.path.join(rel, name) if rel else name
                is_dir = entry.is_dir(follow_symlinks=False)
                yield os.path.join(current, name), child_rel, is_dir
                if is_dir:
                    stack.append((os.path.join(current, name), child_rel))
            except OSError:
                continue


def build_raw_map(root: str) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for abs_path, rel, _is_dir in iter_raw_tree(root):
        key = nfc(rel)
        mapping.setdefault(key, []).append(abs_path)
    return mapping


def resolve_nfc(root: str, rel_path: str, mapping: Optional[Dict[str, List[str]]] = None) -> str:
    mapping = mapping if mapping is not None else build_raw_map(root)
    key = nfc(rel_path.replace(os.sep, "/"))
    matches = mapping.get(key, [])
    if len(matches) != 1:
        raise PathIdentityError("cannot uniquely map NFC path %r under %s" % (key, root))
    return matches[0]


def same_path(a: str, b: str) -> bool:
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.realpath(a) == os.path.realpath(b)


def is_within(child: str, parent: str) -> bool:
    child_real = os.path.realpath(child)
    parent_real = os.path.realpath(parent)
    try:
        return os.path.commonpath([child_real, parent_real]) == parent_real
    except ValueError:
        return False


def protected_root(path: str, home: Optional[str] = None) -> bool:
    home = home or os.path.expanduser("~")
    real = os.path.realpath(path)
    # Normalize the candidate set too: on macOS /tmp, /var and /etc are
    # symlinks into /private, so a literal comparison misses them.
    candidates = {
        os.path.realpath(item) for item in (
            "/", home, "/Users", "/Volumes", "/mnt", "/media", "/home",
            "/private", "/tmp", "/var", "/etc", "/System", "/Library",
            "/Applications", "/usr", "/bin", "/sbin", "/opt", "/dev", "/proc",
        )
    }
    return real in candidates


def lstat_state(path: str) -> Dict[str, int]:
    st = os.lstat(path)
    state = {
        "dev": int(st.st_dev),
        "ino": int(st.st_ino),
        "mtime_ns": int(st.st_mtime_ns),
    }
    if stat.S_ISREG(st.st_mode):
        state["size"] = int(st.st_size)
    return state


def is_dir(path: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def is_regular(path: str) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def is_symlink(path: str) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


def nearest_existing(path: str) -> str:
    current = os.path.abspath(path)
    while not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            return current
        current = parent
    return current


def subtree_fingerprint(path: str) -> Tuple[str, int]:
    """SHA-256 over sorted relative metadata of a directory subtree."""
    root = os.path.abspath(path)
    lines: List[str] = []
    count = 0
    for abs_path, rel, is_directory in iter_raw_tree(root, skip_hidden=False, skip_symlinks=True):
        try:
            state = lstat_state(abs_path)
        except OSError:
            continue
        kind = "d" if is_directory else "f"
        line = "%s\t%s\t%d\t%d\t%d\t%d" % (
            kind, rel, state["dev"], state["ino"],
            state.get("size", 0), state["mtime_ns"],
        )
        lines.append(line)
        count += 1
    lines.sort()
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return digest, count


def clean_component(text: str, max_bytes: int = 240) -> str:
    text = nfc(text or "")
    text = text.replace("/", "-").replace(":", " -")
    text = "".join(" " if ord(ch) < 32 else ch for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(". ")
    if not text or text in (".", ".."):
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        # Truncate on a character boundary; keep the tail for ID/year segments.
        cut = encoded[:max_bytes]
        while cut:
            try:
                text = cut.decode("utf-8")
                break
            except UnicodeDecodeError:
                cut = cut[:-1]
        text = text.rstrip(". ")
    return text


def normalize_title(text: str) -> str:
    text = nfc(text or "").casefold()
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = RELEASE_TAG_RE.sub(" ", text)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def title_matches_dir(dir_name: str, title: str, original_title: Optional[str] = None) -> bool:
    d = normalize_title(dir_name)
    titles = [normalize_title(t) for t in (title, original_title) if t]
    if not d or not titles:
        return False
    return any(d == t or d in t or t in d for t in titles if t)


def season_marker_whole(name: str) -> Optional[int]:
    base = nfc(name).strip()
    for regex in SEASON_WHOLE_RES:
        m = regex.match(base)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                return None
    return None


def season_marker_any(name: str) -> Optional[int]:
    m = SEASON_ANY_RE.search(nfc(name))
    if m:
        value = m.group(1) or m.group(2)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    m = CJK_SEASON_ANY_RE.search(nfc(name))
    if m:
        return int(m.group(1))
    return None


def episode_marker_any(name: str) -> Optional[Tuple[int, int, List[int]]]:
    m = EPISODE_ANY_RE.search(nfc(name))
    if m:
        season = int(m.group(1))
        first = int(m.group(2))
        tail = m.group(3) or ""
        nums = [int(x) for x in re.findall(r"(?i)e(\d{1,3})", tail)]
        return season, first, nums
    return None


def cjk_episode_any(name: str) -> Optional[int]:
    m = CJK_EPISODE_ANY_RE.search(nfc(name))
    return int(m.group(1)) if m else None


def multipart_token(name: str) -> Optional[str]:
    text = nfc(name)
    for index, regex in enumerate(MULTIPART_RES):
        m = regex.search(text)
        if m:
            return "multipart_%d" % index
    return None


def is_generic_container(name: str) -> bool:
    base = nfc(name).casefold()
    base = re.sub(r"[._]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return False
    for generic in GENERIC_CONTAINERS:
        g = re.sub(r"\s+", " ", nfc(generic).casefold()).strip()
        if not g:
            continue
        # English container names match as a whole name, optionally followed
        # by a number ("Downloads 2"). Do not treat a show called "The Show"
        # as a generic "Shows" container just because it contains the word.
        if base == g or re.fullmatch(re.escape(g) + r"\s*\d*", base):
            return True
        # CJK container words are commonly embedded ("影视下载", "我的剧集").
        if any(ord(ch) > 0x2E80 for ch in g) and g in base:
            return True
    return False


def read_entries(path: str) -> List[os.DirEntry]:
    try:
        return list(os.scandir(path))
    except OSError:
        return []


def file_stem(name: str) -> str:
    stem, _ext = os.path.splitext(name)
    return stem
