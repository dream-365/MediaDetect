"""Read-only scan and unit extraction.

The scanner calls the MediaDetect CLI and never mutates media files. It stores
raw paths in scan.json; NFC strings are used only for matching.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import __version__, naming
from .paths import (
    MOVIE_LEVEL_DIRS,
    MOVIE_LEVEL_FILES,
    SIDECAR_EXTS,
    VIDEO_EXTS,
    PathIdentityError,
    build_raw_map,
    cjk_episode_any,
    clean_component,
    episode_marker_any,
    is_generic_container,
    is_hidden_name,
    is_organized_name,
    is_symlink,
    is_within,
    nfc,
    protected_root,
    normalize_title,
    multipart_token,
    part_movie_number,
    part_title_matches,
    read_entries,
    resolve_nfc,
    season_marker_any,
    season_marker_whole,
    title_matches_dir,
)
from .session import read_json, utc_now


class ScanError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


class MediaDetectRunner:
    def __init__(self, md_bin: str):
        self.md_bin = md_bin

    def _run(self, args: List[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [self.md_bin] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
            )
        except FileNotFoundError:
            raise ScanError(
                "E_INPUT_MISSING",
                "mediadetect not found: %s; install it or set --md-bin/MD_BIN" % self.md_bin,
            )

    def version(self) -> Dict[str, Any]:
        proc = self._run(["--version"])
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ScanError("E_SCHEMA_UNSUPPORTED", "mediadetect --version is not JSON")
        if proc.returncode != 0:
            raise ScanError(
                "E_SCHEMA_UNSUPPORTED",
                "mediadetect --version exited %d" % proc.returncode,
            )
        if obj.get("schema_version") != "1":
            raise ScanError(
                "E_SCHEMA_UNSUPPORTED",
                "unsupported mediadetect schema_version: %r" % obj.get("schema_version"),
            )
        return obj

    def detect(
        self,
        path: str,
        match: str = "off",
        probe: str = "off",
        max_files: int = 5000,
    ) -> Dict[str, Any]:
        proc = self._run(
            [
                "--match=" + match,
                "--probe=" + probe,
                "--max-depth", "0",
                "--max-files", str(max_files),
                "--",
                path,
            ]
        )
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ScanError(
                "E_INTERNAL",
                "mediadetect returned invalid JSON for %s (exit %d)" % (path, proc.returncode),
                exit_code=5,
            )
        if proc.returncode == 2:
            raise ScanError(
                "E_INPUT_MISSING",
                "mediadetect could not read %s: %s" % (path, (proc.stderr or "").strip()),
            )
        # Exit 4 means --match=on infrastructure failed, but stdout still
        # contains the complete local detection result. The skill degrades to
        # local naming with a warning instead of discarding it.
        if proc.returncode not in (0, 1, 4):
            return {"ok": False, "error": {"code": "ERR_MD", "message": proc.stderr.strip()}, "files": []}
        return obj


def _safe_name(path: str) -> str:
    return os.path.basename(path.rstrip(os.sep)) or path


def _title_candidates(file_obj: Dict[str, Any]) -> List[str]:
    return [nfc(x) for x in (file_obj.get("title_candidates") or []) if x]


def _year_candidates(file_obj: Dict[str, Any]) -> List[int]:
    out = []
    for value in file_obj.get("year_candidates") or []:
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if year > 0:
            out.append(year)
    return out


def _first_title(file_obj: Dict[str, Any]) -> Optional[str]:
    values = _title_candidates(file_obj)
    return values[0] if values else None


def _first_year(file_obj: Dict[str, Any]) -> Optional[int]:
    values = _year_candidates(file_obj)
    return values[0] if values else None


def _is_feature(file_obj: Dict[str, Any]) -> bool:
    return file_obj.get("role") == "feature" and file_obj.get("media_type") == "movie"


def _is_tv(file_obj: Dict[str, Any]) -> bool:
    return file_obj.get("media_type") == "tv_episode"


def _is_aux(file_obj: Dict[str, Any]) -> bool:
    return file_obj.get("media_type") in ("auxiliary", "non_feature")


def _resolve_files(result: Dict[str, Any], base: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Attach raw paths to MediaDetect file results."""
    files = list(result.get("files") or [])
    if os.path.isfile(base):
        out = []
        for item in files:
            copied = dict(item)
            copied["raw_path"] = base
            copied["rel_path"] = os.path.basename(base)
            out.append(copied)
        return out, []
    mapping = build_raw_map(base)
    out = []
    errors = []
    for item in files:
        copied = dict(item)
        rel = (item.get("path") or item.get("name") or "").replace("\\", "/")
        try:
            copied["raw_path"] = resolve_nfc(base, rel, mapping)
            copied["rel_path"] = rel
            out.append(copied)
        except PathIdentityError as exc:
            errors.append({
                "path": rel,
                "kind": "file",
                "reason_code": "E_PATH_IDENTITY",
                "reason": str(exc),
            })
    return out, errors


MULTI_EPISODE_RE = re.compile(r"(?i)s(\d{1,2})[._-]?e(\d{1,3})((?:[._~-]?e\d{1,3})+)")
MULTI_TAIL_RE = re.compile(r"(?i)([._~-]?)e(\d{1,3})")


def _unsafe_multi_episode(name: str) -> bool:
    m = MULTI_EPISODE_RE.search(name)
    if not m:
        return False
    first = int(m.group(2))
    parts = MULTI_TAIL_RE.findall(m.group(3))
    if not parts:
        return False
    if any(separator in ("-", "~") for separator, _number in parts):
        # A single dash-prefixed tail is the classic explicit range
        # (S01E01-E03); a dash after a repeated E run is ambiguous.
        return len(parts) != 1
    numbers = [first] + [int(number) for _separator, number in parts]
    for index in range(1, len(numbers)):
        if numbers[index] != numbers[index - 1] + 1:
            return True
    return False


def _looks_tv(name: str) -> bool:
    return episode_marker_any(name) is not None or cjk_episode_any(name) is not None


def _unsafe_multi_file(file_obj: Dict[str, Any]) -> bool:
    path = file_obj.get("raw_path") or file_obj.get("name") or ""
    return _unsafe_multi_episode(os.path.basename(path))


def _split_unsafe_multi(
    files: List[Dict[str, Any]],
    kind: str,
    unplanned: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    safe = []
    for file_obj in files:
        if _unsafe_multi_file(file_obj):
            path = file_obj.get("raw_path") or file_obj.get("name") or ""
            unplanned.append(_unplanned(
                path, kind, "unsupported_multi_episode",
                "non-contiguous or ambiguous multi-episode filename",
            ))
            continue
        safe.append(file_obj)
    return safe


def _note_truncated(result: Dict[str, Any], opts: Dict[str, Any]) -> bool:
    if not result.get("detection", {}).get("truncated"):
        return False
    opts.setdefault("_warnings", []).append(
        {"code": "scan.truncated", "detail": "--max-files reached"}
    )
    return True


def _warning_abs_path(base: str, rel: Optional[str],
                      result: Dict[str, Any]) -> Optional[str]:
    if not rel:
        return None
    if os.path.isabs(rel):
        return os.path.normpath(rel)
    kind = (result.get("input") or {}).get("kind")
    anchor = os.path.dirname(base) if kind == "file" else base
    return os.path.normpath(os.path.join(anchor, rel))


def _public_warning(warning: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "code": warning.get("code") or "match.warning",
        "detail": warning.get("detail") or "",
        "file": warning.get("file"),
    }


def _warning_key(warning: Any) -> Tuple[Any, Any, Any]:
    if isinstance(warning, dict):
        return (warning.get("code"), warning.get("detail"), warning.get("file"))
    return (str(warning), "", None)


def _warning_matches_unit(unit: Dict[str, Any], warning: Dict[str, Any]) -> bool:
    abs_path = warning.get("_abs")
    rel = warning.get("file")
    raw_paths = [f.get("raw_path") for f in (unit.get("files") or [])
                 if f.get("raw_path")]
    if abs_path:
        abs_real = os.path.realpath(abs_path)
        for raw in raw_paths:
            if os.path.realpath(raw) == abs_real:
                return True
        for source in unit.get("source_paths") or []:
            if os.path.realpath(source) == abs_real:
                return True
        source_root = unit.get("source_root")
        if source_root and is_within(abs_path, source_root):
            return True
    if rel:
        # Fall back to basename matching for older log/scan shapes where the
        # warning file could not be resolved against the detection root.
        rel_base = os.path.basename(rel)
        if any(os.path.basename(raw) == rel_base for raw in raw_paths):
            return True
    return False


def _detect_with_mode(
    runner: MediaDetectRunner,
    path: str,
    opts: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    try:
        result = runner.detect(path, match=mode, probe=opts.get("probe", "off"),
                               max_files=opts.get("max_files", 5000))
    except ScanError as exc:
        raise exc
    _note_truncated(result, opts)
    if mode != "off":
        detection = result.get("detection") or {}
        for warning in detection.get("warnings") or []:
            if not isinstance(warning, dict):
                continue
            # SPEC-004 G2: only match.year_conflict is a stable match warning
            # in this scope. Do not absorb match.disabled/unavailable noise
            # from the local detection pass.
            if warning.get("code") != "match.year_conflict":
                continue
            item = _public_warning(warning)
            item["_abs"] = _warning_abs_path(path, item.get("file"), result)
            opts.setdefault("_match_warnings", []).append(item)
    return result


def _has_season_children(path: str) -> bool:
    for entry in read_entries(path):
        try:
            if (not is_hidden_name(entry.name)
                    and entry.is_dir(follow_symlinks=False)
                    and season_marker_whole(entry.name) is not None):
                return True
        except OSError:
            continue
    return False


def _result_with_files(result: Dict[str, Any], files: List[Dict[str, Any]]) -> Dict[str, Any]:
    updated = dict(result)
    updated["files"] = files
    return updated


def _under_organized_entry(path: str, base: str) -> bool:
    if is_organized_name(os.path.basename(path)):
        return True
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return False
    parts = rel.split(os.sep)
    return any(is_organized_name(part) for part in parts[:-1])


def _first_organized_ancestor(path: str) -> Optional[str]:
    current = os.path.abspath(path)
    while True:
        if is_organized_name(os.path.basename(current)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _filter_organized_files(
    files: List[Dict[str, Any]],
    base: str,
    opts: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Drop files under an already-organized entry and record one skip each."""
    if opts.get("include_organized"):
        return files
    kept: List[Dict[str, Any]] = []
    for file_obj in files:
        raw = file_obj.get("raw_path") or ""
        if not raw or not _under_organized_entry(raw, base):
            kept.append(file_obj)
            continue
        try:
            rel = os.path.relpath(raw, base)
        except ValueError:
            rel = os.path.basename(raw)
        skip_path = base
        for part in rel.split(os.sep):
            skip_path = os.path.join(skip_path, part)
            if is_organized_name(part):
                break
        opts.setdefault("_skipped", []).append(_organized_skip(skip_path))
    return kept


def _under_movie_level_dir(path: str, base: str) -> bool:
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return False
    parts = rel.split(os.sep)
    return any(part.casefold() in MOVIE_LEVEL_DIRS for part in parts[:-1])


def _has_cjk_episode(files: List[Dict[str, Any]]) -> bool:
    for f in files:
        if not _is_tv(f):
            continue
        name = f.get("name") or os.path.basename(f.get("raw_path") or "")
        if cjk_episode_any(name) is not None:
            return True
    return False


def _trusted_show_container(path: str, files: List[Dict[str, Any]]) -> bool:
    name = _safe_name(path)
    if is_generic_container(name):
        return False
    media_files = [f for f in files if _is_tv(f) or _is_feature(f)]
    titles = [_first_title(f) for f in media_files]
    titles = [t for t in titles if t]
    if not titles:
        # CJK "第 N 集" often has no title candidate. A non-generic parent
        # directory is still usable as the show name.
        return _has_cjk_episode(files)
    normalized = {normalize_title(t) for t in titles}
    if len(normalized) != 1:
        return False
    show = next(iter(normalized))
    dir_name = normalize_title(name)
    if dir_name == show or dir_name in show or show in dir_name:
        return True
    if _has_season_children(path):
        return True
    # A non-generic directory with a single consistent show title is usable;
    # the directory name is ignored in favour of title_candidates[0].
    return bool(dir_name)


def _show_from_container(path: str, files: List[Dict[str, Any]]) -> Optional[str]:
    if not _trusted_show_container(path, files):
        return None
    return clean_component(_safe_name(path))


def _year_from_files(files: List[Dict[str, Any]]) -> Optional[int]:
    years = sorted({y for f in files for y in _year_candidates(f)})
    return years[0] if len(years) == 1 else None


YEAR_IN_NAME_RE = re.compile(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)")


def _year_from_name(name: str) -> Optional[int]:
    m = YEAR_IN_NAME_RE.search(name or "")
    return int(m.group(1)) if m else None


RELEASE_TAG_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:2160p|1080p|720p|480p|bluray|blu-ray|web-?dl|webrip|"
    r"hdtv|dvdrip|brrip|bdrip|x264|x265|h264|h265|hevc|avc|aac|ac3|eac3|"
    r"dts(?:-hd)?|truehd|remux|proper|repack|extended|uncut)(?![a-z0-9])"
)


def _show_and_year_from_dir_name(name: str) -> Tuple[str, Optional[int]]:
    year = _year_from_name(name)
    cleaned = re.sub(r"(?i)[._\s-]*\(?(?:18|19|20)\d{2}\)?", " ", name or "")
    cleaned = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", cleaned)
    cleaned = RELEASE_TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[._]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    cleaned = clean_component(cleaned)
    if not cleaned:
        # A title that is itself a year (e.g. "1923") is not a year suffix.
        return clean_component(name), None
    return cleaned, year


def _container_show(
    path: str,
    files: List[Dict[str, Any]],
) -> Tuple[str, Optional[int], List[str]]:
    """Return the show name, year and warnings for a container directory."""
    dir_show, dir_year = _show_and_year_from_dir_name(_safe_name(path))
    year = _year_from_files(files) or dir_year
    media_files = [f for f in files if _is_tv(f) or _is_feature(f)]
    titles = [_first_title(f) for f in media_files]
    titles = [title for title in titles if title]
    normalized = {normalize_title(title) for title in titles}
    if len(normalized) == 1:
        candidate = titles[0]
        candidate_norm = next(iter(normalized))
        dir_norm = normalize_title(dir_show)
        if dir_norm and (dir_norm == candidate_norm
                         or dir_norm in candidate_norm
                         or candidate_norm in dir_norm):
            return dir_show, year, []
        # The container name is not the show name; use the file evidence.
        return clean_component(re.sub(r"[._]+", " ", candidate)), year, [
            "container_name_ignored"
        ]
    return dir_show, year, []


def _season_from_files(files: List[Dict[str, Any]], fallback_name: str = "") -> Optional[int]:
    for f in files:
        season = f.get("season")
        if season is not None:
            try:
                return int(season)
            except (TypeError, ValueError):
                pass
    value = season_marker_any(fallback_name)
    return value


def _episode_from_file(file_obj: Dict[str, Any], fallback_name: str = "") -> Optional[int]:
    episode = file_obj.get("episode")
    if episode is not None:
        try:
            return int(episode)
        except (TypeError, ValueError):
            pass
    marker = episode_marker_any(fallback_name)
    if marker:
        return marker[1]
    return cjk_episode_any(fallback_name)


RANGE_SUFFIX_RE = re.compile(
    r"(?i)s(\d{1,2})[._-]?e(\d{1,3})[-~]e?(\d{1,3})(?:[^a-z0-9]|$)"
)


def _range_end(file_obj: Dict[str, Any], name: str) -> Optional[int]:
    # Explicit range suffixes are valid even when the gap is more than one
    # episode (S01E01-E03), because the filename says it is a range.
    m = RANGE_SUFFIX_RE.search(name)
    if m:
        return int(m.group(3))
    marker = MULTI_EPISODE_RE.search(name)
    if not marker:
        return None
    first = int(marker.group(2))
    parts = MULTI_TAIL_RE.findall(marker.group(3))
    if not parts:
        return None
    numbers = [first] + [int(number) for _separator, number in parts]
    for index in range(1, len(numbers)):
        if numbers[index] != numbers[index - 1] + 1:
            return None
    return numbers[-1] if len(numbers) > 1 else None


def _unplanned(path: str, kind: str, code: str, reason: str) -> Dict[str, Any]:
    return {
        "path": path,
        "kind": kind,
        "reason_code": code,
        "reason": reason,
    }


def _skipped(path: str, code: str, reason: str) -> Dict[str, Any]:
    return {"path": path, "reason_code": code, "reason": reason}


def _organized_skip(path: str) -> Dict[str, Any]:
    return _skipped(path, "already_organized", "already organized")


def _detect_error(result: Dict[str, Any], path: str, kind: str = "dir") -> Dict[str, Any]:
    error = result.get("error") or {}
    return _unplanned(path, kind, "no_match",
                      error.get("message") or error.get("code") or "mediadetect failed")


def _best_from(result: Dict[str, Any], files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    match = result.get("match") or {}
    if match.get("status") == "multiple":
        return None
    best = match.get("best")
    if best:
        return best
    for f in files:
        fbest = (f.get("match") or {}).get("best")
        if fbest:
            return fbest
    return None


def _movie_group_key(file_obj: Dict[str, Any]) -> str:
    key = file_obj.get("group_key")
    if key:
        return str(key)
    title = normalize_title(_first_title(file_obj) or file_obj.get("name") or "")
    year = _first_year(file_obj) or 0
    return "%s|%d" % (title, year)


def _group_movies(files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        groups.setdefault(_movie_group_key(f), []).append(f)
    return groups


def _local_best(file_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = _first_title(file_obj)
    if not title:
        return None
    return {
        "title": title,
        "original_title": title,
        "year": _first_year(file_obj) or 0,
        "tmdb_id": 0,
        "imdb_id": None,
        "score": 0.0,
        "local": True,
    }


def _match_metadata(result: Dict[str, Any], file_obj: Dict[str, Any],
                    best: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    match = file_obj.get("match") or result.get("match") or {}
    top = result.get("match") or {}
    status = match.get("status") or top.get("status") or "unmatched"
    margin = match.get("margin")
    if margin is None:
        margin = top.get("margin")
    return {
        "match_status": status,
        "match_margin": margin,
        "match_score": (best or {}).get("score", 0),
        "title_hit": bool((best or {}).get("title_hit", False)),
    }


def _movie_best_for_group(
    result: Dict[str, Any], group: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if len(group) == 1:
        best = (group[0].get("match") or {}).get("best")
        if best:
            return best
    best = _best_from(result, group)
    if best:
        return best
    status = (group[0].get("match") or {}).get("status", "")
    if status in ("disabled", "unavailable", "error"):
        return _local_best(group[0])
    return None


def _positive_single_movie_dir(
    directory: str,
    result: Dict[str, Any],
    best: Optional[Dict[str, Any]],
) -> bool:
    files, _errors = _resolve_files(result, directory)
    files = [f for f in files
             if not _under_movie_level_dir(f.get("raw_path") or "", directory)]
    features = [f for f in files if _is_feature(f)]
    if len(features) != 1:
        return False
    feature_name = os.path.basename(features[0].get("raw_path") or "")
    if multipart_token(feature_name, allow_part=True):
        return False
    part = part_movie_number(feature_name)
    if part is not None and not part_title_matches(part, best):
        return False
    if any(_is_tv(f) for f in files):
        return False
    if not best or best.get("local"):
        # Spec 4.3.1.1: --match=off / no real best must not rename the whole
        # directory, even when a local title/year is available.
        return False
    if not title_matches_dir(_safe_name(directory), best.get("title"), best.get("original_title")):
        return False
    if is_generic_container(_safe_name(directory)):
        return False
    allowed_paths = {f.get("raw_path") for f in files if _is_feature(f) or _is_aux(f)}
    feature_stems = {os.path.splitext(os.path.basename(p))[0] for p in allowed_paths if p}
    for entry in read_entries(directory):
        try:
            name = entry.name
            lower = name.casefold()
            if entry.is_dir(follow_symlinks=False):
                if lower in MOVIE_LEVEL_DIRS:
                    continue
                return False
            if entry.is_symlink():
                return False
            ext = os.path.splitext(name)[1].casefold()
            if lower in MOVIE_LEVEL_FILES:
                continue
            if ext in SIDECAR_EXTS:
                continue
            if ext not in VIDEO_EXTS or ext == ".iso":
                # Unknown extensions and disk images (.exe/.iso/etc.) block an
                # overall rename even when the stem matches the feature.
                return False
            stem = os.path.splitext(name)[0]
            if stem in feature_stems:
                continue
            if entry.path in allowed_paths:
                continue
            return False
        except OSError:
            return False
    return True


def _canonical_show_dir(show: str, year: Optional[int]) -> str:
    try:
        return naming.show_target(show, year)
    except naming.NamingError:
        return ""


def _scan_tv_file(
    path: str,
    file_obj: Dict[str, Any],
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    name = _safe_name(path)
    parent = os.path.dirname(path)
    grandparent = os.path.dirname(parent)
    great = os.path.dirname(grandparent)
    if (season_marker_whole(_safe_name(parent)) is None
            and season_marker_any(_safe_name(parent)) is not None):
        return None, _unplanned(path, "tv", "needs_directory_mode",
                                "file is inside a flat season directory; scan the parent directory instead")
    season_hint = season_marker_whole(_safe_name(parent))
    show = _first_title(file_obj)
    year = _first_year(file_obj)
    season = _season_from_files([file_obj], name)
    episode = _episode_from_file(file_obj, name)
    file_obj["_range_end"] = _range_end(file_obj, name)

    if season_hint is not None:
        if not _trusted_show_container(grandparent, [file_obj]):
            return None, _unplanned(path, "tv", "ambiguous_season_parent",
                                    "season directory parent is not a trusted show container")
        show, year, show_warnings = _container_show(grandparent, [file_obj])
        season = season if season is not None else season_hint
        show_ok = _canonical_show_dir(show, year) == _safe_name(grandparent)
        season_ok = naming.season_dir(season) == _safe_name(parent)
        if not (show_ok and season_ok):
            return None, _unplanned(path, "tv", "needs_directory_mode",
                                    "show/season directory names need renaming; scan the show directory instead")
        return {
            "kind": "tv", "input_kind": "file", "source_paths": [path],
            "root": great, "files": [file_obj],
            "context": {"show": show, "year": year, "season": season, "episode": episode,
                        "range_end": _range_end(file_obj, name), "mode": "file"},
            "warnings": show_warnings,
        }, None

    if _trusted_show_container(parent, [file_obj]):
        show, year, show_warnings = _container_show(parent, [file_obj])
        if _canonical_show_dir(show, year) != _safe_name(parent):
            return None, _unplanned(path, "tv", "needs_directory_mode",
                                    "show directory needs renaming; scan the show directory instead")
        return {
            "kind": "tv", "input_kind": "file", "source_paths": [path],
            "root": grandparent, "files": [file_obj],
            "context": {"show": show, "year": year,
                        "season": season if season is not None else 1,
                        "episode": episode, "range_end": _range_end(file_obj, name),
                        "mode": "file", "season_inferred": season is None},
            "warnings": show_warnings + (["season_inferred"] if season is None else []),
        }, None

    flat_season = season_marker_any(_safe_name(parent))
    if flat_season is not None:
        return None, _unplanned(path, "tv", "needs_directory_mode",
                                "file is inside a flat season directory; scan the parent directory instead")

    if not show:
        return None, _unplanned(path, "tv", "no_match",
                                "no title candidate and no trusted show context")
    return {
        "kind": "tv", "input_kind": "file", "source_paths": [path],
        "root": parent, "files": [file_obj],
        "context": {"show": show, "year": year,
                    "season": season if season is not None else 1,
                    "episode": episode, "range_end": _range_end(file_obj, name),
                    "mode": "file", "season_inferred": season is None},
        "warnings": ["season_inferred"] if season is None else [],
    }, None


def _scan_movie_file(
    path: str,
    file_obj: Dict[str, Any],
    result: Dict[str, Any],
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    name = _safe_name(path)
    if multipart_token(name, allow_part=True):
        return None, _unplanned(path, "movie", "unsupported_multipart",
                                "multipart token in movie filename")
    match = file_obj.get("match") or result.get("match") or {}
    best = match.get("best") or result.get("match", {}).get("best")
    warnings: List[str] = []
    if not best and match.get("status") in ("disabled", "unavailable", "error"):
        best = _local_best(file_obj)
        if best:
            warnings.append("no_tmdb")
    if not best:
        return None, _unplanned(path, "movie", "no_match", "no usable TMDB match")
    if match.get("status") == "unmatched":
        warnings.append("weak_match")
    part = part_movie_number(name)
    if part is not None and not part_title_matches(part, best):
        return None, _unplanned(
            path, "movie", "unsupported_multipart",
            "Part %d is not proven by the TMDB title" % part)
    meta = _match_metadata(result, file_obj, best)
    parent = os.path.dirname(path)
    if is_generic_container(_safe_name(parent)):
        return {
            "kind": "movie", "input_kind": "file", "source_paths": [path],
            "root": parent, "files": [file_obj], "best": best,
            "context": {"mode": "file"}, "warnings": warnings, **meta,
        }, None
    try:
        parent_result = runner.detect(parent, match=opts.get("match", "auto"),
                                     probe=opts.get("probe", "off"),
                                     max_files=opts.get("max_files", 5000))
    except ScanError:
        parent_result = {"files": []}
    _note_truncated(parent_result, opts)
    if _positive_single_movie_dir(parent, parent_result, best):
        return {
            "kind": "movie", "input_kind": "directory", "source_root": parent,
            "root": os.path.dirname(parent), "files": [file_obj], "best": best,
            "context": {"mode": "directory"}, "warnings": warnings, **meta,
        }, None
    return {
        "kind": "movie", "input_kind": "file", "source_paths": [path],
        "root": parent, "files": [file_obj], "best": best,
        "context": {"mode": "file"}, "warnings": warnings, **meta,
    }, None


def _split_multipart_movies(
    files: List[Dict[str, Any]],
    unplanned: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    safe = []
    for file_obj in files:
        path = file_obj.get("raw_path") or file_obj.get("name") or ""
        if multipart_token(os.path.basename(path), allow_part=True):
            unplanned.append(_unplanned(
                path, "movie", "unsupported_multipart",
                "multipart token in movie filename"))
            continue
        safe.append(file_obj)
    return safe


def _detect_movie_file_objects(
    files: List[Dict[str, Any]],
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Re-detect safe movie files individually so excluded files never hit TMDB."""
    objects: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for file_obj in files:
        path = file_obj.get("raw_path")
        if not path:
            continue
        if multipart_token(os.path.basename(path), allow_part=True):
            errors.append(_unplanned(path, "movie", "unsupported_multipart",
                                     "multipart token in movie filename"))
            continue
        try:
            result = _detect_with_mode(runner, path, opts, opts.get("match", "auto"))
        except ScanError as exc:
            errors.append(_unplanned(path, "movie", "no_match", exc.message))
            continue
        detected, resolve_errors = _resolve_files(result, path)
        if resolve_errors:
            errors.extend(resolve_errors)
            continue
        if detected:
            objects.append(detected[0])
    return objects, errors


def _movie_units_from_result(
    result: Dict[str, Any],
    base: str,
    root: str,
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
    allow_directory_unit: bool = True,
    file_objects: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if file_objects is not None:
        files, errors = list(file_objects), []
    else:
        files, errors = _resolve_files(result, base)
    if errors:
        # Spec 4.3.4: a unit with any unmappable required source is all-or-nothing.
        return [], list(errors)
    unplanned: List[Dict[str, Any]] = []
    files = [f for f in files
             if not _under_movie_level_dir(f.get("raw_path") or "", base)]
    files = _split_unsafe_multi(files, "movie", unplanned)
    movie_files = [f for f in files if _is_feature(f)]
    movie_files = _split_multipart_movies(movie_files, unplanned)
    if not movie_files:
        return [], unplanned
    groups = _group_movies(movie_files)
    units: List[Dict[str, Any]] = []
    if allow_directory_unit and len(groups) == 1:
        best = _movie_best_for_group(result, movie_files)
        if best and _positive_single_movie_dir(base, result, best):
            units.append({
                "kind": "movie", "input_kind": "directory", "source_root": base,
                "root": os.path.dirname(base), "files": movie_files, "best": best,
                "context": {"mode": "directory"}, "warnings": [],
                **_match_metadata(result, movie_files[0], best),
            })
            return units, unplanned
    targets_seen: Dict[str, str] = {}
    for key, group in groups.items():
        if any(multipart_token(os.path.basename(f["raw_path"]), allow_part=True)
               for f in group):
            for f in group:
                unplanned.append(_unplanned(f["raw_path"], "movie", "unsupported_multipart",
                                            "multipart token in movie filename"))
            continue
        best = _movie_best_for_group(result, group)
        if not best:
            for f in group:
                unplanned.append(_unplanned(f["raw_path"], "movie", "no_match",
                                            "no usable TMDB match"))
            continue
        part_numbers = {
            number for number in (
                part_movie_number(os.path.basename(f["raw_path"])) for f in group
            ) if number is not None
        }
        if part_numbers:
            if (len(part_numbers) != 1
                    or not part_title_matches(next(iter(part_numbers)), best)):
                for f in group:
                    unplanned.append(_unplanned(
                        f["raw_path"], "movie", "unsupported_multipart",
                        "Part N is not proven by the TMDB title"))
                continue
        try:
            target = naming.movie_target(best)
        except naming.NamingError as exc:
            for f in group:
                unplanned.append(_unplanned(f["raw_path"], "movie", "no_match", exc.message))
            continue
        if target in targets_seen:
            for f in group:
                unplanned.append(_unplanned(f["raw_path"], "movie", "unsupported_multipart",
                                            "multiple movie groups resolve to the same target"))
            continue
        targets_seen[target] = key
        units.append({
            "kind": "movie", "input_kind": "files",
            "source_paths": [f["raw_path"] for f in group],
            "root": root, "files": group, "best": best,
            "context": {"mode": "files", "target_hint": target}, "warnings": [],
            **_match_metadata(result, group[0], best),
        })
    return units, unplanned


def _tv_units_from_loose(
    files: List[Dict[str, Any]],
    base: str,
    root: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    # Only episode files provide show-name evidence. Posters, NFOs, samples and
    # other sidecars stay in place and must not turn the group into a multi-show
    # ambiguity.
    episodes = []
    for file_obj in files:
        name = file_obj.get("name") or os.path.basename(file_obj.get("raw_path") or "")
        if _unsafe_multi_episode(name):
            continue
        if _is_tv(file_obj) or _looks_tv(name):
            episodes.append(file_obj)
    files = episodes
    if not files:
        return None, None
    titles = []
    years = set()
    for f in files:
        title = _first_title(f)
        if not title:
            return None, _unplanned(base, "tv", "ambiguous_loose_shows",
                                    "loose episode has no title candidate")
        titles.append(normalize_title(title))
        for y in _year_candidates(f):
            years.add(y)
    if len(set(titles)) != 1:
        return None, _unplanned(base, "tv", "ambiguous_loose_shows",
                                "loose episodes contain multiple show titles")
    if len(years) > 1:
        return None, _unplanned(base, "tv", "ambiguous_loose_shows",
                                "loose episodes contain multiple non-zero years")
    seasons = []
    unknown = []
    for f in files:
        season = f.get("season")
        if season is None:
            unknown.append(f)
        else:
            try:
                seasons.append(int(season))
            except (TypeError, ValueError):
                unknown.append(f)
    if unknown and seasons:
        return None, _unplanned(base, "tv", "season_unknown",
                                "loose episodes mix known and unknown seasons")
    dir_name = _safe_name(base)
    if not seasons:
        inferred = season_marker_any(dir_name)
        seasons = [inferred if inferred is not None else 1]
    show = clean_component(_first_title(files[0]) or "")
    if not show:
        return None, _unplanned(base, "tv", "ambiguous_loose_shows",
                                "cannot derive a show name")
    for f in files:
        f["_range_end"] = _range_end(f, f.get("name") or os.path.basename(f["raw_path"]))
    year = next(iter(years)) if len(years) == 1 else None
    if year is None:
        year = _year_from_name(dir_name)
    warnings = []
    if unknown:
        warnings.append("season_inferred")
    if not is_generic_container(dir_name) and normalize_title(dir_name) != normalize_title(show):
        warnings.append("container_name_ignored")
    source_root = None
    if (not is_generic_container(dir_name)
            and os.path.realpath(base) != os.path.realpath(root)):
        source_root = base
    unit = {
        "kind": "tv", "input_kind": "files", "source_paths": [f["raw_path"] for f in files],
        "root": root, "files": files,
        "context": {"show": show, "year": year, "seasons": sorted(set(seasons)),
                    "mode": "files"},
        "warnings": warnings,
    }
    if source_root:
        unit["source_root"] = source_root
    return unit, None


def _season_children(path: str) -> List[Tuple[str, int, str]]:
    out: List[Tuple[str, int, str]] = []
    for entry in read_entries(path):
        try:
            if is_hidden_name(entry.name) or not entry.is_dir(follow_symlinks=False):
                continue
            marker = season_marker_whole(entry.name)
            if marker is not None:
                out.append((entry.path, marker, entry.name))
        except OSError:
            continue
    return sorted(out, key=lambda item: item[1])


def _files_under(files: List[Dict[str, Any]], directory: str) -> List[Dict[str, Any]]:
    return [f for f in files
            if f.get("raw_path") and is_within(f["raw_path"], directory)]


def _tv_units_for_show_dir(
    show_dir: str,
    root: str,
    files: List[Dict[str, Any]],
    unplanned: List[Dict[str, Any]],
    skipped: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build units for a show directory with whole-name season subdirectories."""
    if not _trusted_show_container(show_dir, files):
        unplanned.append(_unplanned(show_dir, "tv", "ambiguous_season_parent",
                                    "show directory name is not a trusted show container"))
        return []
    children = _season_children(show_dir)
    if not children:
        return []
    show_name, year, show_warnings = _container_show(show_dir, files)
    show_ok = _canonical_show_dir(show_name, year) == _safe_name(show_dir)
    seasons_ok = all(naming.season_dir(marker) == name for _p, marker, name in children)
    units: List[Dict[str, Any]] = []
    if not show_ok and not seasons_ok:
        unplanned.append(_unplanned(show_dir, "tv", "needs_directory_mode",
                                    "show and season names both need renaming"))
        return []
    if not show_ok or seasons_ok:
        units.append({
            "kind": "tv", "input_kind": "directory", "source_root": show_dir,
            "root": root, "files": files,
            "context": {"show": show_name, "year": year, "mode": "show"},
            "warnings": list(show_warnings),
        })
        return units
    for child, marker, name in children:
        if naming.season_dir(marker) == name:
            skipped.append(_skipped(child, "already_organized",
                                    "season directory already canonical"))
            continue
        child_files = _files_under(files, child)
        if not child_files:
            continue
        units.append({
            "kind": "tv", "input_kind": "directory", "source_root": child,
            "root": root, "files": child_files,
            "context": {"show": show_name, "year": year,
                        "season": marker, "mode": "season"},
            "warnings": list(show_warnings),
        })
    return units


def _classify_dir(
    path: str,
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    units: List[Dict[str, Any]] = []
    unplanned: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    result = _detect_with_mode(runner, path, opts, "off")
    if result.get("ok") is False:
        return [], [_detect_error(result, path)], skipped, warnings
    files, errors = _resolve_files(result, path)
    files = [f for f in files
             if not _under_movie_level_dir(f.get("raw_path") or "", path)]
    if not opts.get("include_organized"):
        files = [f for f in files
                 if not _under_organized_entry(f.get("raw_path") or "", path)]
    if errors:
        # A single library unit is all-or-nothing: never plan a partial tree.
        return [], list(errors), skipped, warnings
    if result.get("detection", {}).get("truncated"):
        warnings.append({"code": "scan.truncated", "detail": "--max-files reached"})
        return [], unplanned, skipped, warnings
    files = _split_unsafe_multi(files, "tv", unplanned)
    result = _result_with_files(result, files)

    season_hint = season_marker_whole(_safe_name(path))
    parent = os.path.dirname(path)
    show_parent = os.path.dirname(parent)
    if season_hint is not None:
        if not _trusted_show_container(parent, files):
            unplanned.append(_unplanned(path, "tv", "ambiguous_season_parent",
                                        "season directory parent is not a trusted show container"))
            return units, unplanned, skipped, warnings
        show, year, show_warnings = _container_show(parent, files)
        season = season_hint
        show_ok = _canonical_show_dir(show, year) == _safe_name(parent)
        season_ok = naming.season_dir(season) == _safe_name(path)
        if not show_ok and not season_ok:
            unplanned.append(_unplanned(path, "tv", "needs_directory_mode",
                                        "show and season names both need renaming"))
        elif show_ok and not season_ok:
            units.append({
                "kind": "tv", "input_kind": "directory", "source_root": path,
                "root": show_parent, "files": files,
                "context": {"show": show, "year": year, "season": season, "mode": "season"},
                "warnings": list(show_warnings),
            })
        elif not show_ok and season_ok:
            units.append({
                "kind": "tv", "input_kind": "directory", "source_root": parent,
                "root": show_parent, "files": files,
                "context": {"show": show, "year": year, "season": season, "mode": "show"},
                "warnings": list(show_warnings),
            })
        else:
            units.append({
                "kind": "tv", "input_kind": "directory", "source_root": path,
                "root": show_parent, "files": files,
                "context": {"show": show, "year": year, "season": season, "mode": "season"},
                "warnings": list(show_warnings),
            })
        return units, unplanned, skipped, warnings

    entries = read_entries(path)
    dirs = []
    direct_files = []
    visible = 0
    for entry in entries:
        try:
            if is_hidden_name(entry.name):
                continue
            visible += 1
            if entry.is_symlink():
                continue
            if (not opts.get("include_organized")
                    and is_organized_name(entry.name)):
                skipped.append(_organized_skip(entry.path))
                continue
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry.path)
            else:
                direct_files.append(entry.path)
        except OSError:
            continue
    if visible and not dirs and not direct_files:
        return units, unplanned, skipped, warnings

    season_dirs = [d for d in dirs if season_marker_whole(_safe_name(d)) is not None]
    direct_media = [p for p in direct_files
                    if os.path.splitext(p)[1].casefold() in VIDEO_EXTS]
    if dirs and len(season_dirs) == len(dirs) and season_dirs and not direct_media:
        units.extend(_tv_units_for_show_dir(path, parent, files, unplanned, skipped))
        return units, unplanned, skipped, warnings

    if dirs:
        for child in dirs:
            child_name = _safe_name(child)
            try:
                child_result = _detect_with_mode(runner, child, opts, "off")
            except ScanError as exc:
                unplanned.append(_unplanned(child, "dir", "no_match", exc.message))
                continue
            if child_result.get("detection", {}).get("truncated"):
                warnings.append({"code": "scan.truncated", "detail": "--max-files reached: %s" % child})
                continue
            media = child_result.get("media_type")
            if media in ("movie", "movie_collection", "mixed"):
                child_files, child_errors = _resolve_files(child_result, child)
                if child_errors:
                    unplanned.extend(child_errors)
                    continue
            if media in ("tv_season", "tv_series", "tv_episode"):
                child_files, child_errors = _resolve_files(child_result, child)
                if child_errors:
                    unplanned.extend(child_errors)
                    continue
                child_files = _split_unsafe_multi(child_files, "tv", unplanned)
                whole = season_marker_whole(child_name)
                any_marker = season_marker_any(child_name)
                if whole is None and any_marker is not None:
                    unit, bad = _tv_units_from_loose(child_files, child, path)
                    if unit:
                        units.append(unit)
                    if bad:
                        unplanned.append(bad)
                elif whole is not None:
                    if not _trusted_show_container(path, child_files):
                        unplanned.append(_unplanned(
                            child, "tv", "ambiguous_season_parent",
                            "season directory parent is not a trusted show container"))
                    else:
                        show_name, year, show_warnings = _container_show(path, child_files)
                        show_ok = _canonical_show_dir(show_name, year) == _safe_name(path)
                        season_ok = naming.season_dir(whole) == child_name
                        if not show_ok and not season_ok:
                            unplanned.append(_unplanned(child, "tv", "needs_directory_mode",
                                                        "show and season names both need renaming"))
                        elif show_ok and not season_ok:
                            units.append({
                                "kind": "tv", "input_kind": "directory", "source_root": child,
                                "root": path, "files": child_files,
                                "context": {"show": show_name, "year": year,
                                            "season": whole, "mode": "season"},
                                "warnings": list(show_warnings),
                            })
                        elif not show_ok and season_ok:
                            unplanned.append(_unplanned(child, "tv", "needs_directory_mode",
                                                        "show directory needs renaming; scan the show directory"))
                        else:
                            skipped.append(_skipped(child, "already_organized",
                                                    "season directory already canonical"))
                elif _season_children(child):
                    units.extend(_tv_units_for_show_dir(child, path, child_files,
                                                        unplanned, skipped))
                else:
                    if not _trusted_show_container(child, child_files):
                        unplanned.append(_unplanned(child, "tv", "no_match",
                                                    "show directory name is not a trusted show container"))
                    else:
                        show_name, year, show_warnings = _container_show(child, child_files)
                        units.append({
                            "kind": "tv", "input_kind": "directory", "source_root": child,
                            "root": path, "files": child_files,
                            "context": {"show": show_name, "year": year, "mode": "show"},
                            "warnings": list(show_warnings),
                        })
            elif media in ("movie", "movie_collection"):
                child_safe = _split_unsafe_multi(child_files, "movie", unplanned)
                multipart_bad: List[Dict[str, Any]] = []
                child_safe = _split_multipart_movies(child_safe, multipart_bad)
                unplanned.extend(multipart_bad)
                unsafe_child = len(child_safe) != len(child_files)
                movie_result = child_result
                file_objects = None
                allow_directory_unit = True
                movie_errors: List[Dict[str, Any]] = []
                if opts.get("match", "auto") != "off":
                    if unsafe_child:
                        file_objects, movie_errors = _detect_movie_file_objects(
                            child_safe, runner, opts)
                        allow_directory_unit = False
                    else:
                        try:
                            movie_result = _detect_with_mode(
                                runner, child, opts, opts["match"])
                        except ScanError as exc:
                            unplanned.append(_unplanned(
                                child, "movie", "no_match", exc.message))
                            continue
                child_units, child_unplanned = _movie_units_from_result(
                    movie_result, child, path, runner, opts,
                    allow_directory_unit=allow_directory_unit,
                    file_objects=file_objects,
                )
                units.extend(child_units)
                unplanned.extend(movie_errors)
                unplanned.extend(child_unplanned)
            elif media == "mixed":
                unplanned.append(_unplanned(
                    child, "mixed", "ambiguous_loose_shows",
                    "mixed movie/TV directory needs a separate scan"))
            else:
                skipped.append(_skipped(child, "not_media", "no movie or TV files"))
        direct_set = set(direct_files)
        direct_objects = [f for f in files if f.get("raw_path") in direct_set]
        tv_direct = [f for f in direct_objects if _is_tv(f)]
        tv_paths = {f.get("raw_path") for f in tv_direct}
        if tv_direct:
            unit, bad = _tv_units_from_loose(tv_direct, path, path)
            if unit:
                units.append(unit)
            if bad:
                unplanned.append(bad)
        for file_path in direct_files:
            if file_path in tv_paths:
                continue
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_name)[1].casefold()
            if (file_name.casefold() in MOVIE_LEVEL_FILES
                    or file_ext in SIDECAR_EXTS):
                skipped.append(_skipped(file_path, "auxiliary", "not a feature"))
                continue
            unit, bad = _scan_direct_file(file_path, runner, opts, root_override=path)
            if unit:
                units.append(unit)
            if bad:
                unplanned.append(bad)
        if direct_files:
            warnings.append({"code": "mixed_root", "detail": "scattered files in a library root"})
        return units, unplanned, skipped, warnings

    tv_files = [f for f in files if _is_tv(f)]
    movie_files = [f for f in files if _is_feature(f)]
    movie_files = _split_multipart_movies(movie_files, unplanned)
    if tv_files and not movie_files:
        unit, bad = _tv_units_from_loose(tv_files, path, path)
        if unit:
            units.append(unit)
        if bad:
            unplanned.append(bad)
        return units, unplanned, skipped, warnings
    movie_objects = None
    if opts.get("match", "auto") != "off":
        movie_objects, movie_errors = _detect_movie_file_objects(
            movie_files, runner, opts)
        unplanned.extend(movie_errors)
    if movie_files and not tv_files:
        units2, bad = _movie_units_from_result(
            result, path, path, runner, opts, allow_directory_unit=True,
            file_objects=movie_objects)
        units.extend(units2)
        unplanned.extend(bad)
        return units, unplanned, skipped, warnings
    if movie_files and tv_files:
        units2, bad = _movie_units_from_result(
            result, path, path, runner, opts, allow_directory_unit=False,
            file_objects=movie_objects)
        units.extend(units2)
        unplanned.extend(bad)
        unit, bad = _tv_units_from_loose(tv_files, path, path)
        if unit:
            units.append(unit)
        if bad:
            unplanned.append(bad)
        warnings.append({"code": "mixed_loose_files", "detail": "movie and TV files in one root"})
        return units, unplanned, skipped, warnings
    for f in files:
        if _is_aux(f):
            skipped.append(_skipped(f.get("raw_path", path), "auxiliary", "not a feature"))
    return units, unplanned, skipped, warnings


def _scan_direct_file(
    path: str,
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
    root_override: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not opts.get("include_organized"):
        organized = _first_organized_ancestor(path)
        if organized:
            opts.setdefault("_skipped", []).append(_organized_skip(organized))
            return None, None
    try:
        result = _detect_with_mode(runner, path, opts, "off")
    except ScanError as exc:
        return None, _unplanned(path, "file", "no_match", exc.message)
    if result.get("ok") is False:
        return None, _detect_error(result, path, "file")
    files, errors = _resolve_files(result, path)
    if errors:
        return None, errors[0]
    if not files:
        return None, _unplanned(path, "file", "no_match", "no media file detected")
    file_obj = files[0]
    name = _safe_name(path)
    if _unsafe_multi_episode(name):
        return None, _unplanned(path, "file", "unsupported_multi_episode",
                                "non-contiguous multi-episode filename")
    if _is_tv(file_obj) or _looks_tv(name):
        unit, bad = _scan_tv_file(path, file_obj, runner, opts)
        if unit and root_override:
            unit["root"] = root_override
        return unit, bad
    if _is_feature(file_obj):
        if multipart_token(name, allow_part=True):
            return None, _unplanned(path, "movie", "unsupported_multipart",
                                    "multipart token in movie filename")
        movie_result = result
        if opts.get("match", "auto") != "off":
            try:
                movie_result = _detect_with_mode(runner, path, opts, opts["match"])
            except ScanError as exc:
                return None, _unplanned(path, "file", "no_match", exc.message)
            movie_files, movie_errors = _resolve_files(movie_result, path)
            if movie_errors:
                return None, movie_errors[0]
            if movie_files:
                file_obj = movie_files[0]
        unit, bad = _scan_movie_file(path, file_obj, movie_result, runner, opts)
        if unit and root_override:
            unit["root"] = root_override
        return unit, bad
    return None, _unplanned(path, "file", "no_match", "not a movie or TV episode")


def scan_path(
    path: str,
    md_bin: str,
    mode: str = "auto",
    root: Optional[str] = None,
    match: str = "auto",
    probe: str = "off",
    max_files: int = 5000,
    session_id: Optional[str] = None,
    session_token: Optional[str] = None,
    include_organized: bool = False,
) -> Dict[str, Any]:
    from .session import ensure_session

    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise ScanError("E_INPUT_MISSING", "input path does not exist: %s" % path)
    if is_symlink(path):
        raise ScanError("E_INPUT_SYMLINK", "input root is a symlink: %s" % path)

    explicit_root = os.path.abspath(root) if root else None
    if explicit_root and not os.path.isdir(explicit_root):
        raise ScanError("E_INPUT_MISSING", "root does not exist: %s" % explicit_root)

    if not include_organized and is_organized_name(os.path.basename(path.rstrip(os.sep))):
        final_root = explicit_root or (path if os.path.isdir(path) else os.path.dirname(path))
        if not is_within(path, final_root):
            raise ScanError("E_OUTSIDE_ROOT", "input is outside --root: %s" % path)
        if protected_root(final_root):
            raise ScanError("E_PROTECTED_ROOT", "refusing protected root: %s" % final_root)
        session = ensure_session(final_root, session_id, session_token)
        return {
            "schema_version": "1",
            "session_id": session["session_id"],
            "session_token": session["session_token"],
            "state_dir": session["state_dir"],
            "generated_at": utc_now(),
            "tool_version": __version__,
            "input": {"path": path, "kind": "file" if os.path.isfile(path) else "directory"},
            "root": final_root,
            "mode": "single" if (os.path.isfile(path) or mode == "single") else "library",
            "mode_reason": "already_organized",
            "options": {"match_mode": match, "probe_mode": probe,
                        "max_files": max_files,
                        "include_organized": include_organized},
            "md_version": None,
            "units": [],
            "unplanned": [],
            "skipped": [_organized_skip(path)],
            "errors": [],
            "warnings": [],
        }

    runner = MediaDetectRunner(md_bin)
    version = runner.version()

    opts = {"probe": probe, "max_files": max_files, "match": match,
            "include_organized": include_organized}
    units: List[Dict[str, Any]] = []
    unplanned: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    mode_reason = mode

    if os.path.isfile(path):
        unit, bad = _scan_direct_file(path, runner, opts)
        if unit:
            units.append(unit)
        if bad:
            unplanned.append(bad)
        if unit and unit.get("input_kind") == "directory":
            root = unit.get("root", root)
        mode_reason = "file"
    else:
        if mode == "single":
            unit, bad = _scan_single_dir(path, runner, opts)
            if unit:
                units.append(unit)
            if bad:
                unplanned.append(bad)
            mode_reason = "single"
        elif mode == "library":
            units, unplanned, skipped, warnings = _classify_dir(path, runner, opts)
            mode_reason = "library"
        else:
            unit, bad, reason = _auto_dir(path, runner, opts)
            if unit:
                units.append(unit)
            if bad:
                unplanned.append(bad)
            if reason == "library":
                units, unplanned, skipped, warnings = _classify_dir(path, runner, opts)
                mode_reason = "library"
            elif reason == "all_organized":
                mode_reason = "library"
            else:
                mode_reason = reason

    match_warnings = opts.get("_match_warnings") or []
    for unit in units:
        unit_warnings = list(unit.get("warnings") or [])
        unit_keys = {_warning_key(warning) for warning in unit_warnings}
        for warning in match_warnings:
            if not _warning_matches_unit(unit, warning):
                continue
            item = _public_warning(warning)
            key = _warning_key(item)
            if key in unit_keys:
                continue
            unit_warnings.append(item)
            unit_keys.add(key)
        unit["warnings"] = unit_warnings
    warnings.extend(opts.get("_warnings") or [])
    warnings.extend(_public_warning(warning) for warning in match_warnings)
    for unit in units:
        normalized = []
        for warning in unit.get("warnings") or []:
            if isinstance(warning, dict):
                normalized.append(warning)
            else:
                normalized.append({"code": str(warning), "detail": "", "file": None})
        unit["warnings"] = normalized
    unplanned.extend(opts.get("_unplanned") or [])
    skipped.extend(opts.get("_skipped") or [])
    seen_skipped = set()
    unique_skipped = []
    for item in skipped:
        path_key = item.get("path")
        if path_key in seen_skipped:
            continue
        seen_skipped.add(path_key)
        unique_skipped.append(item)
    skipped = unique_skipped
    seen_unplanned = set()
    unique_unplanned = []
    for item in unplanned:
        key = (item.get("path"), item.get("reason_code"))
        if key in seen_unplanned:
            continue
        seen_unplanned.add(key)
        unique_unplanned.append(item)
    unplanned = unique_unplanned
    seen_warnings = set()
    unique_warnings = []
    for item in warnings:
        key = ((item.get("code"), item.get("detail"), item.get("file"))
               if isinstance(item, dict) else (str(item), "", None))
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        unique_warnings.append(item)
    warnings = unique_warnings

    if explicit_root:
        final_root = explicit_root
    elif os.path.isdir(path) and mode_reason == "library":
        roots = {unit.get("root") for unit in units if unit.get("root")}
        if (len(roots) == 1
                and os.path.realpath(next(iter(roots))) != os.path.realpath(path)
                and is_within(path, next(iter(roots)))):
            # A show directory whose direct children are all season directories
            # is a single show unit; its root is the show's parent.
            final_root = next(iter(roots))
        else:
            final_root = path
    elif units:
        final_root = units[0].get("root") or (path if os.path.isdir(path) else os.path.dirname(path))
    else:
        final_root = path if os.path.isdir(path) else os.path.dirname(path)

    # The session root must contain the input and every unit root.
    for unit in units:
        unit_root = unit.get("root") or final_root
        if not is_within(unit_root, final_root) or not is_within(path, final_root):
            raise ScanError("E_OUTSIDE_ROOT", "unit root is outside --root: %s" % unit_root)
    if os.path.isdir(path) and not is_within(path, final_root):
        raise ScanError("E_OUTSIDE_ROOT", "input is outside --root: %s" % path)
    if is_symlink(final_root):
        raise ScanError("E_INPUT_SYMLINK", "root is a symlink: %s" % final_root)
    if protected_root(final_root):
        raise ScanError("E_PROTECTED_ROOT", "refusing protected root: %s" % final_root)

    session = ensure_session(final_root, session_id, session_token)
    for unit in units:
        source_root = unit.get("source_root")
        if source_root and is_within(session["state_dir"], source_root):
            raise ScanError("E_STATE_DIR_INSIDE_UNIT",
                            "session state directory is inside a unit source: %s" % source_root)
    scan = {
        "schema_version": "1",
        "session_id": session["session_id"],
        "session_token": session["session_token"],
        "state_dir": session["state_dir"],
        "generated_at": utc_now(),
        "tool_version": __version__,
        "input": {"path": path, "kind": "file" if os.path.isfile(path) else "directory"},
        "root": final_root,
        "mode": mode_reason,
        "mode_reason": mode_reason,
        "options": {"match_mode": match, "probe_mode": probe, "max_files": max_files,
                    "include_organized": include_organized},
        "md_version": version,
        "units": units,
        "unplanned": unplanned,
        "skipped": skipped,
        "errors": [],
        "warnings": warnings,
    }
    return scan


def _scan_single_dir(
    path: str,
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not opts.get("include_organized"):
        organized = _first_organized_ancestor(path)
        if organized:
            opts.setdefault("_skipped", []).append(_organized_skip(organized))
            return None, None
    result = _detect_with_mode(runner, path, opts, "off")
    if result.get("ok") is False:
        return None, _detect_error(result, path)
    media = result.get("media_type")
    if media == "mixed":
        raise ScanError("E_MODE_MISMATCH",
                        "--mode single cannot split mixed movie/TV input: %s" % path)
    if media in ("tv_season", "tv_series", "tv_episode"):
        files, errors = _resolve_files(result, path)
        if errors:
            return None, errors[0]
        all_files = files
        files = _filter_organized_files(files, path, opts)
        if not files and all_files:
            return None, None
        unsafe: List[Dict[str, Any]] = []
        files = _split_unsafe_multi(files, "tv", unsafe)
        if unsafe:
            opts.setdefault("_unplanned", []).extend(unsafe)
        if not files:
            return None, (unsafe[0] if unsafe else
                          _unplanned(path, "tv", "no_match", "no TV episode detected"))
        name = _safe_name(path)
        season = season_marker_whole(name)
        if season is None and season_marker_any(name) is not None:
            return _tv_units_from_loose(files, path, os.path.dirname(path))
        if season is not None:
            parent = os.path.dirname(path)
            show_parent = os.path.dirname(parent)
            if not _trusted_show_container(parent, files):
                return None, _unplanned(path, "tv", "ambiguous_season_parent",
                                        "season directory parent is not a trusted show container")
            show_name, year, show_warnings = _container_show(parent, files)
            show_ok = _canonical_show_dir(show_name, year) == _safe_name(parent)
            season_ok = naming.season_dir(season) == name
            if not show_ok and not season_ok:
                return None, _unplanned(path, "tv", "needs_directory_mode",
                                        "show and season names both need renaming")
            if not show_ok:
                return {
                    "kind": "tv", "input_kind": "directory", "source_root": parent,
                    "root": show_parent, "files": files,
                    "context": {"show": show_name, "year": year,
                                "season": season, "mode": "show"},
                    "warnings": list(show_warnings),
                }, None
            return {
                "kind": "tv", "input_kind": "directory", "source_root": path,
                "root": show_parent, "files": files,
                "context": {"show": show_name, "year": year,
                            "season": season, "mode": "season"},
                "warnings": list(show_warnings),
            }, None
        show_name, year, show_warnings = _container_show(path, files)
        local_unplanned: List[Dict[str, Any]] = []
        local_skipped: List[Dict[str, Any]] = []
        units = _tv_units_for_show_dir(path, os.path.dirname(path), files,
                                       local_unplanned, local_skipped)
        if len(units) > 1:
            return None, _unplanned(path, "tv", "needs_directory_mode",
                                    "multiple season directories need renaming")
        if units:
            return units[0], None
        if local_unplanned:
            return None, local_unplanned[0]
        return {
            "kind": "tv", "input_kind": "directory", "source_root": path,
            "root": os.path.dirname(path), "files": files,
            "context": {"show": show_name, "year": year, "mode": "show"},
            "warnings": list(show_warnings),
        }, None
    movie_result = result
    file_objects = None
    allow_directory_unit = True
    movie_errors: List[Dict[str, Any]] = []
    resolved, resolve_errors = _resolve_files(result, path)
    if resolve_errors:
        return None, resolve_errors[0]
    filtered = _filter_organized_files(resolved, path, opts)
    organized_filtered = len(filtered) != len(resolved)
    if organized_filtered and not any(_is_feature(f) for f in filtered):
        return None, None
    if opts.get("match", "auto") != "off":
        unsafe_movies: List[Dict[str, Any]] = []
        safe_movies = _split_unsafe_multi(filtered, "movie", unsafe_movies)
        multipart_movies: List[Dict[str, Any]] = []
        safe_movies = _split_multipart_movies(safe_movies, multipart_movies)
        if unsafe_movies or multipart_movies or organized_filtered:
            opts.setdefault("_unplanned", []).extend(unsafe_movies)
            opts["_unplanned"].extend(multipart_movies)
            file_objects, movie_errors = _detect_movie_file_objects(
                safe_movies, runner, opts)
            allow_directory_unit = False
        else:
            try:
                movie_result = _detect_with_mode(runner, path, opts, opts["match"])
            except ScanError as exc:
                return None, _unplanned(path, "movie", "no_match", exc.message)
    elif organized_filtered:
        # --match=off still must not move an already-organized entry, and it
        # must not rename the directory that contains it.
        file_objects = filtered
        allow_directory_unit = False
    units, bad = _movie_units_from_result(
        movie_result, path, os.path.dirname(path), runner, opts,
        allow_directory_unit=allow_directory_unit, file_objects=file_objects)
    bad = movie_errors + list(bad)
    if len(bad) > 1:
        opts.setdefault("_unplanned", []).extend(bad[1:])
    if len(units) > 1:
        raise ScanError("E_MODE_MISMATCH",
                        "--mode single found multiple movie units in %s" % path)
    if units:
        return units[0], bad[0] if bad else None
    return None, bad[0] if bad else _unplanned(path, "dir", "no_match", "no media unit")


def _auto_dir(
    path: str,
    runner: MediaDetectRunner,
    opts: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    season = season_marker_whole(_safe_name(path))
    if season is not None:
        unit, bad = _scan_single_dir(path, runner, opts)
        return unit, bad, "single"
    all_entries = [e for e in read_entries(path) if not is_hidden_name(e.name)]
    entries = []
    organized_skips = []
    for entry in all_entries:
        if (not opts.get("include_organized")
                and is_organized_name(entry.name)):
            organized_skips.append(_organized_skip(entry.path))
            continue
        entries.append(entry)
    if organized_skips:
        opts.setdefault("_skipped", []).extend(organized_skips)
    if all_entries and not entries:
        return None, None, "all_organized"
    dirs = [e.path for e in entries if e.is_dir(follow_symlinks=False)]
    direct_files = [e.path for e in entries if e.is_file(follow_symlinks=False)]
    meaningful_dirs = [
        d for d in dirs if _safe_name(d).casefold() not in MOVIE_LEVEL_DIRS
    ]
    if meaningful_dirs:
        return None, None, "library"
    result = _detect_with_mode(runner, path, opts, "off")
    if result.get("ok") is False:
        return None, _detect_error(result, path), "single"
    files, errors = _resolve_files(result, path)
    files = [f for f in files
             if not _under_movie_level_dir(f.get("raw_path") or "", path)]
    if not opts.get("include_organized"):
        files = [f for f in files
                 if not _under_organized_entry(f.get("raw_path") or "", path)]
    if errors:
        return None, errors[0], "single"
    unsafe: List[Dict[str, Any]] = []
    files = _split_unsafe_multi(files, "file", unsafe)
    if unsafe:
        opts.setdefault("_unplanned", []).extend(unsafe)
    result = _result_with_files(result, files)
    tv_files = [f for f in files if _is_tv(f)]
    movie_files = [f for f in files if _is_feature(f)]
    multipart_bad: List[Dict[str, Any]] = []
    movie_files = _split_multipart_movies(movie_files, multipart_bad)
    if multipart_bad:
        opts.setdefault("_unplanned", []).extend(multipart_bad)
    if tv_files and not movie_files:
        unit_root = path
        if (not is_generic_container(_safe_name(path))
                or season_marker_any(_safe_name(path)) is not None):
            unit_root = os.path.dirname(path)
        unit, bad = _tv_units_from_loose(tv_files, path, unit_root)
        return unit, bad, "single"
    if movie_files and not tv_files:
        if len(_group_movies(movie_files)) <= 1:
            movie_result = result
            file_objects = None
            allow_directory_unit = True
            errors: List[Dict[str, Any]] = []
            if opts.get("match", "auto") != "off":
                if unsafe:
                    # Never send a directory containing an unsafe multi-episode
                    # file to TMDB; detect only the safe movie files.
                    file_objects, errors = _detect_movie_file_objects(
                        movie_files, runner, opts)
                    allow_directory_unit = False
                else:
                    try:
                        movie_result = _detect_with_mode(
                            runner, path, opts, opts["match"])
                    except ScanError as exc:
                        return None, _unplanned(path, "movie", "no_match",
                                                exc.message), "single"
            units, bad = _movie_units_from_result(
                movie_result, path, path, runner, opts,
                allow_directory_unit=allow_directory_unit,
                file_objects=file_objects)
            bad = errors + list(bad)
            if len(units) == 1:
                return units[0], bad[0] if bad else None, "single"
        return None, None, "library"
    if movie_files and tv_files:
        return None, None, "library"
    if unsafe or multipart_bad:
        return None, None, "single"
    return None, _unplanned(path, "dir", "no_match", "no media files found"), "single"
