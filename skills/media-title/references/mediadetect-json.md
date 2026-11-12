# MediaDetect JSON fields used by media-title

The skill only consumes the documented, read-only JSON contract.

| Field | Use |
| --- | --- |
| `schema_version` | Must be `"1"`; otherwise `E_SCHEMA_UNSUPPORTED` |
| `media_type` | `movie`, `tv_episode`, `tv_season`, `tv_series`, `mixed`, ... |
| `files[].path` | NFC-normalized relative path; must be mapped back to raw path |
| `files[].role` | `feature` for the main movie video |
| `files[].media_type` | File-level classification |
| `files[].title_candidates` | Local title hints; first value is used only when unique |
| `files[].year_candidates` | Local year hints |
| `files[].season` | Per-file season; `summary.seasons` is never used to fill it |
| `files[].episode` | Per-file episode |
| `files[].season_episode` | `SxxExx` or range |
| `files[].group_key` | Movie grouping key |
| `files[].match.best` | Per-file TMDB best candidate |
| `match.best` | Directory-level TMDB best candidate |
| `detection.truncated` | `--max-files` reached; never plan from truncated output |
| `detection.warnings[]` | Warning codes such as `scan.truncated` |

## Known limits

- MediaDetect is read-only. It never moves, renames, or deletes media.
- TV matching is local only; no TMDB TV API is used.
- `files[].path` is NFC-normalized. The skill enumerates raw names with
  `os.scandir` and refuses ambiguous NFC mappings.
- `summary.seasons` may include seasons from other files; it is not a
  per-file fallback.
- CJK `第 N 集` often has `season=null`; do not merge it into a neighboring
  season.
