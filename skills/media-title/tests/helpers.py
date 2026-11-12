"""Shared test helpers and a deterministic fake MediaDetect result."""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm", ".ts", ".iso"}
TV_RE = re.compile(r"(?i)s(\d{1,2})\s*[._-]?\s*e(\d{1,3})((?:\s*[._-]?\s*e\d{1,3})*)")
CJK_RE = re.compile(r"第\s*(\d{1,3})\s*集")
YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
CLEAN_RE = re.compile(r"(?i)(?:^|[._\s-])(?:2160p|1080p|720p|480p|bluray|web-dl|webrip|hdtv|x264|x265|h264|h265|hevc|aac|ac3|dts)(?:$|[._\s-])")


def clean_title(name: str) -> List[str]:
    stem = os.path.splitext(name)[0]
    stem = TV_RE.sub(" ", stem)
    stem = CJK_RE.sub(" ", stem)
    stem = YEAR_RE.sub(" ", stem)
    stem = re.sub(r"[\[\{][^\]\}]*[\]\}]", " ", stem)
    stem = CLEAN_RE.sub(" ", stem)
    stem = re.sub(r"(?i)(?:^|[._\s-])(?:cd|disc|disk|part|pt)\s*[._-]?\s*[a-z0-9]{1,2}(?:$|[._\s-])", " ", stem)
    stem = re.sub(r"[._]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return [stem] if stem else []


def years(name: str) -> List[int]:
    return [int(x) for x in YEAR_RE.findall(name)]


def tv_info(name: str) -> Optional[Dict[str, Any]]:
    m = TV_RE.search(name)
    if m:
        season = int(m.group(1))
        first = int(m.group(2))
        tail = [int(x) for x in re.findall(r"(?i)e(\d{1,3})", m.group(3) or "")]
        numbers = [first] + tail
        se = "S%02dE%02d" % (season, first)
        if len(numbers) > 1:
            se += "-E%02d" % numbers[-1]
        return {"season": season, "episode": first, "season_episode": se, "numbers": numbers}
    m = CJK_RE.search(name)
    if m:
        return {"season": None, "episode": int(m.group(1)), "season_episode": None,
                "numbers": [int(m.group(1))]}
    return None


def file_result(path: str, rel: str, match_mode: str = "off") -> Dict[str, Any]:
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    info = tv_info(name)
    media = "tv_episode" if info else "movie"
    if ext in (".srt", ".ass", ".ssa", ".sub", ".idx", ".nfo", ".jpg", ".jpeg", ".png", ".webp"):
        media = "auxiliary"
    titles = clean_title(name)
    year_list = years(name)
    best = None
    match_status = "not_applicable"
    if media == "movie" and match_mode != "off":
        title = titles[0] if titles else os.path.splitext(name)[0]
        best = {
            "source": "tmdb",
            "tmdb_id": 12345,
            "imdb_id": "tt1234567",
            "title": title,
            "original_title": title,
            "year": year_list[0] if year_list else 0,
            "score": 0.95,
            "matched_by": "title",
            "release_date": "",
            "runtime_sec": 0,
            "popularity": 0,
            "title_score": 1,
            "year_delta": 0,
            "runtime_delta_sec": 0,
            "title_hit": True,
            "expanded": False,
            "query": title,
            "evidence": {},
        }
        match_status = "high"
    elif media == "movie":
        match_status = "disabled"
    return {
        "path": rel.replace(os.sep, "/"),
        "name": name,
        "ext": ext,
        "role": "feature" if media == "movie" else ("auxiliary" if media == "auxiliary" else "episode"),
        "media_type": media,
        "confidence": "high",
        "title_candidates": titles,
        "year_candidates": year_list,
        "edition": None,
        "resolution": None,
        "source": None,
        "codec": None,
        "release_group": None,
        "season_episode": info.get("season_episode") if info else None,
        "season": info.get("season") if info else None,
        "episode": info.get("episode") if info else None,
        "auxiliary_kind": None,
        "group_key": (titles[0].lower().replace(" ", "-") + "|" + str(year_list[0] if year_list else 0))
        if media == "movie" else None,
        "probe_status": "skipped",
        "duration_sec": None,
        "match": {
            "status": match_status,
            "reason": None,
            "file": None,
            "margin": None,
            "best": best,
            "candidates": [best] if best else [],
            "error": None,
        },
    }


def fake_result(path: str, match_mode: str = "off") -> Dict[str, Any]:
    path = os.path.abspath(path)
    if os.path.isfile(path):
        files = [file_result(path, os.path.basename(path), match_mode)]
        media = files[0]["media_type"]
        if media == "auxiliary":
            media = "auxiliary"
        match = files[0]["match"].copy()
        return {
            "schema_version": "1",
            "ok": True,
            "input": {"path": path, "kind": "file"},
            "media_type": media,
            "confidence": "high",
            "title": files[0]["title_candidates"][0] if files[0]["title_candidates"] else None,
            "year": files[0]["year_candidates"][0] if files[0]["year_candidates"] else None,
            "summary": {"total_files": 1, "movie_files": 1 if media == "movie" else 0,
                        "episode_files": 1 if media == "tv_episode" else 0,
                        "non_feature_files": 0, "auxiliary_files": 0, "other_files": 0,
                        "distinct_movies": 1 if media == "movie" else 0,
                        "seasons": [], "skipped_hidden": 0, "skipped_symlinks": 0,
                        "unreadable": 0, "unmatched_movie_groups": 0},
            "files": files,
            "match": match,
            "detection": {"probe_mode": "off", "match_mode": match_mode, "warnings": [], "truncated": False},
            "attribution": None,
        }
    files = []
    for root, dirs, names in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, path)
            files.append(file_result(full, rel, match_mode))
    movies = [f for f in files if f["media_type"] == "movie"]
    tvs = [f for f in files if f["media_type"] == "tv_episode"]
    aux = [f for f in files if f["media_type"] == "auxiliary"]
    if movies and tvs:
        media = "mixed"
    elif tvs:
        media = "tv_series"
    elif movies:
        media = "movie"
    elif aux:
        media = "auxiliary"
    else:
        media = "other"
    top_match = None
    for f in movies:
        if f["match"].get("best"):
            top_match = f["match"].copy()
            break
    if top_match is None:
        top_match = {"status": "disabled" if match_mode == "off" else "not_applicable",
                     "reason": None, "file": None, "margin": None, "best": None,
                     "candidates": [], "error": None}
    seasons = sorted({f["season"] for f in tvs if f["season"] is not None})
    return {
        "schema_version": "1",
        "ok": True,
        "input": {"path": path, "kind": "directory"},
        "media_type": media,
        "confidence": "high",
        "title": movies[0]["title_candidates"][0] if movies and movies[0]["title_candidates"] else None,
        "year": movies[0]["year_candidates"][0] if movies and movies[0]["year_candidates"] else None,
        "summary": {
            "total_files": len(files),
            "movie_files": len(movies),
            "episode_files": len(tvs),
            "non_feature_files": 0,
            "auxiliary_files": len(aux),
            "other_files": 0,
            "distinct_movies": len({f["group_key"] for f in movies}),
            "seasons": seasons,
            "skipped_hidden": 0,
            "skipped_symlinks": 0,
            "unreadable": 0,
            "unmatched_movie_groups": 0,
        },
        "files": files,
        "match": top_match,
        "detection": {"probe_mode": "off", "match_mode": match_mode, "warnings": [], "truncated": False},
        "attribution": None,
    }


class FakeRunner:
    def version(self) -> Dict[str, Any]:
        return {"name": "mediadetect", "schema_version": "1", "version": "0.2.1"}

    def detect(self, path: str, match: str = "off", probe: str = "off", max_files: int = 5000) -> Dict[str, Any]:
        return fake_result(path, match)
