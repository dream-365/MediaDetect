# Naming rules

## Movies

```text
<title>[ <original_title>][ (<year>)][ {<imdb_id>|tmdb<id>}]
```

- `original_title` is omitted when empty or equal to `title`.
- The year segment is omitted when the year is unknown or zero.
- `{tt...}` is preferred; otherwise `{tmdb<id>}`.
- A movie directory is renamed as a directory only after passing the
  single-movie-directory check: one feature group, only attributable entries,
  a basename matching the title, and a non-generic container name.
- Otherwise each movie file becomes a file unit and is moved into a newly
  created target directory.

## TV

```text
<show>[ (<year>)]/Season <NN>/<original filename>
```

With `--rename-episodes`:

```text
<show> - S<NN>E<MM>[ - <episode title>].<ext>
<show> - S<NN>E<MM>-E<NN>.ext
```

- Season 0 is `Season 00`.
- CJK `第 N 集` keeps its original filename.
- A range keeps the range spelling.
- A show directory is only trusted when the directory name and the file title
  candidates agree. A generic container such as `Downloads` is never used as a
  show name.
- Loose episodes are grouped by normalized `(title, year)`. Multiple titles or
  multiple non-zero years are `unplanned/ambiguous_loose_shows`.

## Ambiguity

These are deliberately not guessed:

- `CD1/CD2`, `Disc1/Disc2`, `Part.A/Part.B`, `1of2`, `上/下集`
- `S01E01E03`, `S01E01E02E04` (non-contiguous multi-episode)
- a season directory whose parent is not a trusted show container
- a single episode inside a show/season tree whose names need renaming
- a generic download folder with loose files from more than one show
