---
name: media-title
description: Organize local movie and TV directories with MediaDetect. Use when the user asks to rename, sort, or clean up downloaded movies or shows, or to apply a consistent library naming scheme.
metadata:
  version: 0.1.1
---

# media-title

Use this skill when the user wants to organize **local** movie and TV files or
directories. MediaDetect is the only detection source; this skill is the
orchestration layer.

## Prerequisites

- Python 3.9+; the skill uses only the standard library.
- The `mediadetect` binary must be on `PATH`, or passed via `--md-bin` /
  `MD_BIN`. Install it with
  `go install github.com/dream-365/MediaTitle/cmd/mediadetect@v0.3.0`.
- `mediadetect` must report JSON `schema_version` `"1"`.
- Optional: `TMDB_API_KEY` enables TMDB matching.

## Safety contract

- Never modify media files before the user has seen a plan and explicitly
  confirmed the unit IDs.
- `high` confidence is **not** permission to execute. Always ask.
- Never use `mv`, `cp`, or `mkdir` yourself. Only call the helper script.
- Do not organize a path the user did not ask for.
- If anything is ambiguous, keep it `unplanned` and say why. Do not guess.
- Low/unmatched TMDB matches, `score < 0.6`, or `title_hit=false` are
  `unplanned/low_confidence`; do not try to force them into a plan. Local
  naming may still be used when TMDB is disabled/unavailable.
- A `medium` match with `title_hit=true` may be planned, but it carries a
  `medium_confidence` warning. Show that warning and ask the user to review.
- Moves are atomic no-replace by default. On SMB/NFS filesystems that support
  neither atomic no-replace nor hard links, the script refuses with
  `E_NO_REPLACE_UNSUPPORTED`. Do **not** enable the fallback on your own.
  Only if the user explicitly accepts the risk, pass
  `--no-replace=check` (or set `MEDIA_TITLE_ALLOW_CHECK_RENAME=1`) to `apply`
  and to the corresponding `rollback`. This uses a non-atomic
  check-then-rename: a target created by another process in the tiny window
  between the existence check and rename could be overwritten. The result
  must show `non_atomic_move`, and the logs record `move_method`/`atomic`/
  `validation`; report that warning to the user.

## Workflow

### 1. Scan

```bash
python3 scripts/media_title.py scan "<path>" --json
```

Read `session_id`, `root`, `units[]`, `unplanned[]`, and `skipped[]`.
If `unplanned` is non-empty, show every item and its `reason_code`.

By default, entries whose names contain `{tt...}`/`{tmdb...}` are not
detected: they are listed in `skipped[]` with `already_organized`, and their
children are not traversed. Only use `--include-organized` when the user
explicitly wants to force re-detection of those entries.

### 2. Plan

```bash
python3 scripts/media_title.py plan --scan "<state_dir>/scan.json" --json
```

The script writes `<state_dir>/plan.json`. Never edit it by hand.
`plan_id` is the content hash.

### 3. Show the plan

Show a compact table with `session_id`, `plan_id`, and unit IDs:

```text
session: 20261112T120000Z-a1b2c3d4   plan: sha256:...
ID   类型    当前                                 目标                                  置信度
u1   movie   流浪地球2.2023.1080p                  流浪地球2 The Wandering Earth II (2023)  high
u2   tv      Some.Show.S01.1080p                  Some Show/Season 01                    medium
```

Then list every `unplanned[]` and `skipped[]` entry with path and reason.
Do not hide them behind a count.

Ask exactly one of:

- “全部执行”
- “选择哪些 unit”
- “取消”

“我先看看” is not approval.

### 4. Apply

Only after explicit approval:

```bash
python3 scripts/media_title.py apply \
  --plan "<state_dir>/plan.json" \
  --expect-plan-id "<plan_id>" \
  --select "u1,u3" \
  --yes
```

`--select` accepts `all` or unit IDs, never row numbers. The plan hash and the
session token must match; mismatches abort.

If the user explicitly chose the SMB/NFS fallback, append
`--no-replace=check` to both apply and rollback. Otherwise omit it: the default
`strict` mode refuses unsupported filesystems rather than taking the race.

### 5. Report and rollback

Report executed units, skipped units, conflicts, and the session directory.
Give the user the full rollback command:

```bash
python3 scripts/media_title.py rollback \
  --plan "<state_dir>/plan.json" \
  --expect-plan-id "<plan_id>" \
  --select "u1,u3" \
  --yes
```

If the plan file was replaced or deleted, use `--session-dir <state_dir>`.
Rollback validates fingerprints before moving anything; a conflict means the
user or another process changed the target. If apply used
`--no-replace=check`, rollback must use the same flag or it returns
`E_NO_REPLACE_UNSUPPORTED` before changing anything.

## Rules the script enforces

- One session has at most one plan. To replan, start a new session.
- `--expect-plan-id`, `--select`, and `--yes` are required for apply.
- `--expect-plan-id` and `--yes` are required for rollback.
- No overwrite, no directory merge, no deletion of non-empty directories.
- Only `mkdir`, `move`, and `remove_empty_dir` operations exist.
- A move uses atomic no-replace semantics by default; unsupported filesystems
  are rejected. `--no-replace=check` is an explicit, non-atomic fallback for
  SMB/NFS and must never be enabled without user consent.
- Intent/done logs make crash recovery and rollback possible.

## When to stop

Stop and report instead of guessing when:

- the input is a generic download folder with loose files from multiple shows;
- a movie has multiple parts (`CD1/CD2`, `Part.A/Part.B`, `1of2`, 上/下集);
- a filename looks like a non-contiguous multi-episode (`S01E01E03`);
- a season directory has no trusted show parent;
- a single episode file is inside a show/season tree whose names need renaming
  (`unplanned/needs_directory_mode`);
- the plan contains `unplanned[]` items the user expected to be organized.

The correct answer may be “this part needs a manual decision”, not a forced move.
