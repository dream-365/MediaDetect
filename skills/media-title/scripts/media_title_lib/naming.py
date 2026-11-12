"""Deterministic movie and TV naming rules."""

from __future__ import annotations

import os
from typing import Optional

from .paths import clean_component


class NamingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _component(value: Optional[str], field: str) -> str:
    text = clean_component(value or "")
    if not text:
        raise NamingError("E_INTERNAL", "empty %s component" % field)
    return text


def movie_target(best: dict) -> str:
    title = _component(best.get("title"), "title")
    original = clean_component(best.get("original_title") or "")
    year = int(best.get("year") or 0)
    imdb_id = best.get("imdb_id") or ""
    tmdb_id = int(best.get("tmdb_id") or best.get("id") or 0)

    parts = [title]
    if original and original.casefold() != title.casefold():
        parts.append(original)
    if year > 0:
        parts.append("(%d)" % year)
    if imdb_id:
        parts.append("{%s}" % clean_component(imdb_id))
    elif tmdb_id > 0:
        parts.append("{tmdb%d}" % tmdb_id)
    return " ".join(parts)


def show_target(show: str, year: Optional[int] = None) -> str:
    name = _component(show, "show")
    if year and int(year) > 0:
        return "%s (%d)" % (name, int(year))
    return name


def season_dir(season: int) -> str:
    try:
        value = int(season)
    except (TypeError, ValueError):
        value = 1
    if value < 0:
        value = 0
    return "Season %02d" % value


def episode_target(
    show: str,
    season: int,
    episode: int,
    ext: str,
    episode_title: Optional[str] = None,
    range_end: Optional[int] = None,
) -> str:
    name = _component(show, "show")
    ext = ext if ext.startswith(".") else "." + ext
    if range_end is not None:
        stem = "%s - S%02dE%02d-E%02d" % (name, int(season), int(episode), int(range_end))
    else:
        stem = "%s - S%02dE%02d" % (name, int(season), int(episode))
    title = clean_component(episode_title or "")
    if title:
        stem += " - " + title
    return stem + ext


def split_ext(name: str) -> tuple:
    stem, ext = os.path.splitext(name)
    return stem, ext
