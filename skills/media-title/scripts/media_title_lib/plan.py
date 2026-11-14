"""Build a deterministic, content-hashed plan from scan.json."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import __version__, naming
from .paths import (
    SIDECAR_EXTS,
    is_generic_container,
    is_organized_name,
    lstat_state,
    nfc,
    same_path,
)
from .session import utc_now


class PlanError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(obj: Dict[str, Any]) -> str:
    body = {k: v for k, v in obj.items() if k not in ("plan_id", "generated_at")}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def _state(path: str) -> Dict[str, int]:
    try:
        return lstat_state(path)
    except OSError:
        return {}


def _source_hash(sources: List[Dict[str, Any]]) -> str:
    parts = []
    for source in sources:
        parts.append([source.get("path"), source.get("kind"), source.get("state")])
    return "sha256:" + hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()


def _sidecars(video_path: str, exclude: set) -> List[str]:
    parent = os.path.dirname(video_path)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    out = []
    try:
        entries = os.scandir(parent)
    except OSError:
        return out
    with entries:
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                name = entry.name
                if entry.path in exclude:
                    continue
                e_stem, ext = os.path.splitext(name)
                if (e_stem == stem or e_stem.startswith(stem + ".")) and ext.casefold() in SIDECAR_EXTS:
                    out.append(entry.path)
            except OSError:
                continue
    return sorted(out)


def _source_entry(path: str, kind: str) -> Dict[str, Any]:
    return {"path": path, "kind": kind, "state": _state(path)}


def _mk_operation_mkdir(path: str) -> Dict[str, Any]:
    exists = os.path.isdir(path)
    return {
        "op": "mkdir",
        "path": path,
        "pre_exists": exists,
        "pre_state": _state(path) if exists else None,
    }


def _mk_operation_move(src: str, dst: str, kind: str) -> Dict[str, Any]:
    return {
        "op": "move",
        "from": src,
        "to": dst,
        "from_state": _state(src),
        "kind": kind,
    }


def _mk_operation_remove(path: str) -> Dict[str, Any]:
    return {
        "op": "remove_empty_dir",
        "path": path,
        "pre_empty": True,
        "removed_state": _state(path),
    }


def _clean_show(value: Optional[str]) -> str:
    text = re.sub(r"[._]+", " ", value or "")
    try:
        return naming.show_target(text, None)
    except naming.NamingError:
        return ""


def _episode_filename(
    source_name: str,
    show: str,
    season: int,
    episode: Optional[int],
    range_end: Optional[int],
    rename_episodes: bool,
) -> str:
    if not rename_episodes or episode is None:
        return source_name
    if re.search(r"第\s*\d+\s*集", source_name):
        return source_name
    _stem, ext = os.path.splitext(source_name)
    return naming.episode_target(show, season, episode, ext, None, range_end)


def _already_organized_movie(path: str) -> bool:
    return is_organized_name(os.path.basename(path.rstrip(os.sep)))


def _normalized_component(name: str) -> str:
    return nfc(name or "").casefold().strip()


def _comparison_key(value: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", _normalized_component(value))


def _parent_is_target_dir(parent: str, target_name: str) -> bool:
    """True when moving into <parent>/<target_name> would nest a second copy."""
    return (_comparison_key(os.path.basename(parent)) == _comparison_key(target_name)
            or _already_organized_movie(parent))


def _move_target_key(path: str) -> str:
    return nfc(os.path.realpath(path)).casefold()


def _sibling_snapshot(sources: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Record plan-time siblings so apply does not mistake them for new files."""
    snapshot: Dict[str, List[str]] = {}
    for source in sources:
        path = source.get("path")
        if not path or source.get("kind") != "file" or not os.path.isfile(path):
            continue
        parent = os.path.dirname(path)
        if parent in snapshot:
            continue
        names: List[str] = []
        try:
            entries = os.scandir(parent)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
                except OSError:
                    continue
        snapshot[parent] = sorted(names)
    return snapshot


_STATUS_RANK = {"unmatched": 0, "low": 1, "medium": 2, "high": 3}


def _score_status(score: Any) -> str:
    try:
        value = float(score or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def _final_movie_status(unit: Dict[str, Any], best: Dict[str, Any]) -> str:
    file_status = str(unit.get("match_status") or "")
    if file_status in ("disabled", "unavailable"):
        return file_status
    if file_status not in _STATUS_RANK:
        file_status = _score_status(unit.get("match_score", best.get("score", 0)))
    score_status = _score_status(unit.get("match_score", best.get("score", 0)))
    if _STATUS_RANK[score_status] < _STATUS_RANK[file_status]:
        return score_status
    return file_status


def _warning_key(warning: Any) -> Tuple[Any, Any, Any]:
    if isinstance(warning, dict):
        return (warning.get("code"), warning.get("detail"), warning.get("file"))
    return (str(warning), "", None)


def _warning_obj(warning: Any) -> Dict[str, Any]:
    if isinstance(warning, dict):
        return warning
    return {"code": str(warning), "detail": "", "file": None}


def _unit_warning_file(unit: Dict[str, Any]) -> Optional[str]:
    files = unit.get("files") or []
    raw = next((f.get("raw_path") for f in files if f.get("raw_path")), None)
    if not raw:
        return None
    root = unit.get("root")
    if root:
        try:
            rel = os.path.relpath(raw, root)
            if not rel.startswith(".."):
                return rel
        except ValueError:
            pass
    return os.path.basename(raw)


def _low_confidence(unit: Dict[str, Any], best: Dict[str, Any]) -> bool:
    status = _final_movie_status(unit, best)
    if status in ("disabled", "unavailable"):
        return False
    if status in ("low", "unmatched"):
        return True
    if not bool(unit.get("title_hit", True)):
        return True
    try:
        score = float(unit.get("match_score", best.get("score", 0)) or 0)
    except (TypeError, ValueError):
        score = 0.0
    return score < 0.6


def _movie_unit(unit: Dict[str, Any], options: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    best = unit.get("best") or {}
    if _low_confidence(unit, best):
        return None, [{
            "path": unit.get("source_root") or ",".join(unit.get("source_paths", [])),
            "kind": "movie", "reason_code": "low_confidence",
            "reason": "low or unproven TMDB match; review manually",
        }]
    status = _final_movie_status(unit, best)
    warnings_out = list(unit.get("warnings") or [])
    if status == "medium":
        if not any(_warning_key(w)[0] == "medium_confidence" for w in warnings_out):
            warnings_out.append({
                "code": "medium_confidence",
                "detail": "medium confidence; review before applying",
                "file": _unit_warning_file(unit),
            })
    try:
        target_name = naming.movie_target(best)
    except naming.NamingError as exc:
        return None, [{"path": unit.get("source_root") or ",".join(unit.get("source_paths", [])),
                       "kind": "movie", "reason_code": "no_match", "reason": exc.message}]
    input_kind = unit.get("input_kind")
    sources: List[Dict[str, Any]] = []
    operations: List[Dict[str, Any]] = []
    target_path = ""
    if input_kind == "directory":
        source_root = unit["source_root"]
        if _already_organized_movie(source_root):
            return {"skipped": {"path": source_root, "reason_code": "already_organized",
                                "reason": "movie directory already has an ID tag"}}, []
        target_path = os.path.join(os.path.dirname(source_root), target_name)
        sources.append(_source_entry(source_root, "directory"))
        if same_path(source_root, target_path):
            return {"skipped": {"path": source_root, "reason_code": "already_organized",
                                "reason": "source already equals target"}}, []
        operations.append(_mk_operation_move(source_root, target_path, "directory"))
    else:
        source_paths = list(unit.get("source_paths") or [])
        if not source_paths:
            return None, [{"path": unit.get("root"), "kind": "movie", "reason_code": "no_match",
                           "reason": "movie unit has no sources"}]
        parent = unit.get("root") or os.path.dirname(source_paths[0])
        for source in source_paths:
            if _parent_is_target_dir(os.path.dirname(source), target_name):
                return {"skipped": {"path": os.path.dirname(source),
                                    "reason_code": "already_organized",
                                    "reason": "movie file already sits in a directory with the target name"}}, []
        target_path = os.path.join(parent, target_name)
        operations.append(_mk_operation_mkdir(target_path))
        exclude = set(source_paths)
        all_sources = list(source_paths)
        for source in source_paths:
            all_sources.extend(_sidecars(source, exclude))
        seen = set()
        for source in all_sources:
            if source in seen:
                continue
            seen.add(source)
            target_file = os.path.join(target_path, os.path.basename(source))
            if same_path(source, target_file):
                continue
            sources.append(_source_entry(source, "file"))
            operations.append(_mk_operation_move(source, target_file, "file"))
        if not sources:
            return {"skipped": {"path": source_paths[0], "reason_code": "already_organized",
                                "reason": "movie file already in its target directory"}}, []
    target = {"path": target_path, "kind": "directory"}
    return {
        "id": None,
        "kind": "movie",
        "status": "planned",
        "confidence": (unit.get("best") or {}).get("score", 0),
        "match_status": status,
        "sources": sources,
        "source_hash": _source_hash(sources),
        "sibling_snapshot": _sibling_snapshot(sources),
        "target": target,
        "operations": operations,
        "warnings": warnings_out,
        "evidence": {k: best.get(k) for k in (
            "tmdb_id", "imdb_id", "score", "year", "title", "original_title"
        ) if k in best},
    }, []


def _tv_unit(unit: Dict[str, Any], options: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    ctx = unit.get("context") or {}
    show = _clean_show(ctx.get("show"))
    year = ctx.get("year")
    if not show:
        return None, [{"path": unit.get("source_root") or ",".join(unit.get("source_paths", [])),
                       "kind": "tv", "reason_code": "no_match", "reason": "no show name"}]
    try:
        show_dir_name = naming.show_target(show, year)
    except naming.NamingError as exc:
        return None, [{"path": unit.get("source_root") or "", "kind": "tv",
                       "reason_code": "no_match", "reason": exc.message}]
    mode = ctx.get("mode")
    sources: List[Dict[str, Any]] = []
    operations: List[Dict[str, Any]] = []
    target_path = ""

    if mode in ("show", "season") and unit.get("source_root"):
        source_root = unit["source_root"]
        if mode == "show":
            target_path = os.path.join(os.path.dirname(source_root), show_dir_name)
            sources.append(_source_entry(source_root, "directory"))
            if same_path(source_root, target_path):
                return {"skipped": {"path": source_root, "reason_code": "already_organized",
                                    "reason": "show directory already canonical"}}, []
            operations.append(_mk_operation_move(source_root, target_path, "directory"))
        else:
            show_root = os.path.dirname(source_root)
            target_show = os.path.join(os.path.dirname(show_root), show_dir_name)
            season_value = ctx.get("season")
            season = int(season_value) if season_value is not None else 1
            target_season = os.path.join(target_show, naming.season_dir(season))
            show_needs = not same_path(show_root, target_show)
            season_needs = not same_path(source_root, target_season)
            if show_needs and season_needs:
                return None, [{"path": source_root, "kind": "tv",
                               "reason_code": "needs_directory_mode",
                               "reason": "show and season names both need renaming"}]
            if show_needs:
                # The unit is the show directory, not the season directory.
                target_path = target_show
                sources.append(_source_entry(show_root, "directory"))
                operations.append(_mk_operation_move(show_root, target_show, "directory"))
            else:
                target_path = target_season
                sources.append(_source_entry(source_root, "directory"))
                if not season_needs:
                    return {"skipped": {"path": source_root, "reason_code": "already_organized",
                                        "reason": "season directory already canonical"}}, []
                operations.append(_mk_operation_move(source_root, target_season, "directory"))
        return {
            "id": None, "kind": "tv", "status": "planned", "confidence": "high",
            "match_status": "not_applicable", "sources": sources,
            "source_hash": _source_hash(sources), "sibling_snapshot": _sibling_snapshot(sources),
            "target": {"path": target_path, "kind": "directory"},
            "operations": operations, "warnings": list(unit.get("warnings") or []),
            "evidence": {"show": show, "year": year},
        }, []

    source_paths = list(unit.get("source_paths") or [])
    if not source_paths:
        return None, [{"path": unit.get("root"), "kind": "tv", "reason_code": "no_match",
                       "reason": "TV unit has no sources"}]
    root = unit.get("root") or os.path.dirname(source_paths[0])
    show_root = os.path.join(root, show_dir_name)
    seasons = ctx.get("seasons")
    if seasons is None:
        season_value = ctx.get("season")
        seasons = [season_value if season_value is not None else 1]
    season_dirs = {int(s): os.path.join(show_root, naming.season_dir(int(s))) for s in seasons}
    operations.append(_mk_operation_mkdir(show_root))
    for season_dir in sorted(set(season_dirs.values())):
        operations.append(_mk_operation_mkdir(season_dir))
    exclude = set(source_paths)
    file_by_path = {f.get("raw_path"): f for f in (unit.get("files") or [])}
    all_items: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    for source in source_paths:
        owner = file_by_path.get(source)
        all_items.append((source, owner))
        for sidecar in _sidecars(source, exclude):
            all_items.append((sidecar, owner))
    seen = set()
    for source, file_obj in all_items:
        if source in seen:
            continue
        seen.add(source)
        season = None
        episode = None
        range_end = None
        if file_obj is not None:
            season = file_obj.get("season")
            episode = file_obj.get("episode")
            range_end = file_obj.get("_range_end") or ctx.get("range_end")
        if season is None:
            season = seasons[0] if len(seasons) == 1 else 1
        try:
            season = int(season)
        except (TypeError, ValueError):
            season = 1
        season_dir = season_dirs.get(season) or os.path.join(show_root, naming.season_dir(season))
        name = _episode_filename(os.path.basename(source), show, season, episode,
                                 range_end, bool(options.get("rename_episodes")))
        target_file = os.path.join(season_dir, name)
        if same_path(source, target_file):
            continue
        sources.append(_source_entry(source, "file"))
        operations.append(_mk_operation_move(source, target_file, "file"))
    if not sources:
        return {"skipped": {"path": source_paths[0], "reason_code": "already_organized",
                            "reason": "episodes already in their target directory"}}, []
    # Clean a flat season root after moving its files, but never a generic container.
    if (unit.get("input_kind") == "files" and unit.get("source_root")
            and not options.get("keep_empty_source")):
        src_root = unit["source_root"]
        if not is_generic_container(os.path.basename(src_root)) and not same_path(src_root, root):
            operations.append(_mk_operation_remove(src_root))
    target_path = show_root
    return {
        "id": None, "kind": "tv", "status": "planned", "confidence": "high",
        "match_status": "not_applicable", "sources": sources,
        "source_hash": _source_hash(sources), "sibling_snapshot": _sibling_snapshot(sources),
        "target": {"path": target_path, "kind": "directory"},
        "operations": operations, "warnings": list(unit.get("warnings") or []),
        "evidence": {"show": show, "year": year},
    }, []


def build_plan(scan: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    if scan.get("schema_version") != "1":
        raise PlanError("E_SCHEMA_UNSUPPORTED", "unsupported scan schema_version")
    for warning in scan.get("warnings") or []:
        if isinstance(warning, dict) and warning.get("code") == "scan.truncated":
            raise PlanError("E_SCAN_TRUNCATED",
                            "scan was truncated by --max-files; increase it or narrow the input",
                            exit_code=2)
    units_out: List[Dict[str, Any]] = []
    skipped = list(scan.get("skipped") or [])
    unplanned = list(scan.get("unplanned") or [])
    errors = list(scan.get("errors") or [])
    warnings = list(scan.get("warnings") or [])

    for unit in scan.get("units") or []:
        kind = unit.get("kind")
        if kind == "movie":
            built, bad = _movie_unit(unit, options)
        elif kind == "tv":
            built, bad = _tv_unit(unit, options)
        else:
            built, bad = None, [{"path": unit.get("source_root") or "", "kind": kind,
                                 "reason_code": "no_match", "reason": "unknown unit kind"}]
        if bad:
            unplanned.extend(bad)
        if built is None:
            continue
        if "skipped" in built:
            skipped.append(built["skipped"])
            continue
        units_out.append(built)

    # A move target must be unique across the whole plan. Two episodes that
    # resolve to the same SxxExx (for example two resolutions of one episode)
    # would otherwise execute partially and then fail with E_TARGET_EXISTS.
    owners: Dict[str, int] = {}
    conflicting: set = set()
    for index, unit in enumerate(units_out):
        for op in unit.get("operations") or []:
            if op.get("op") != "move":
                continue
            key = _move_target_key(op["to"])
            if key in owners:
                conflicting.add(owners[key])
                conflicting.add(index)
            else:
                owners[key] = index
    if conflicting:
        kept: List[Dict[str, Any]] = []
        for index, unit in enumerate(units_out):
            if index not in conflicting:
                kept.append(unit)
                continue
            unplanned.append({
                "path": (unit.get("target") or {}).get("path") or "",
                "kind": unit.get("kind") or "",
                "reason_code": "duplicate_target",
                "reason": "multiple sources resolve to the same move target",
            })
        units_out = kept

    # Warnings attached to units (including match diagnostics and the
    # medium-confidence review hint) must also be visible at plan level.
    seen_warning_keys = {_warning_key(warning) for warning in warnings}
    for unit in units_out:
        for warning in unit.get("warnings") or []:
            item = _warning_obj(warning)
            key = _warning_key(item)
            if key in seen_warning_keys:
                continue
            warnings.append(item)
            seen_warning_keys.add(key)

    for index, unit in enumerate(units_out, start=1):
        unit["id"] = "u%d" % index

    plan = {
        "schema_version": "1",
        "session_id": scan.get("session_id"),
        "session_token": scan.get("session_token"),
        "state_dir": scan.get("state_dir"),
        "generated_at": utc_now(),
        "tool_version": __version__,
        "root": scan.get("root"),
        "mode": scan.get("mode"),
        "options": {
            "match_mode": (scan.get("options") or {}).get("match_mode", "auto"),
            "probe_mode": (scan.get("options") or {}).get("probe_mode", "off"),
            "rename_episodes": bool(options.get("rename_episodes")),
            "keep_empty_source": bool(options.get("keep_empty_source")),
        },
        "units": units_out,
        "unplanned": unplanned,
        "skipped": skipped,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "units": len(units_out),
            "planned": len(units_out),
            "skipped": len(skipped),
            "unplanned": len(unplanned),
            "operations": sum(len(u.get("operations") or []) for u in units_out),
        },
    }
    plan["plan_id"] = content_hash(plan)
    return plan
