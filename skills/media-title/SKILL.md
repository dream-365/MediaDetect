---
name: media-title
description: Organize local movie and TV directories with MediaDetect. Use when the user asks to rename, sort, or clean up downloaded movies or shows, or to apply a consistent library naming scheme.
metadata:
  version: 0.1.0
---

# media-title

Use this skill when the user wants to organize **local** movie and TV files or
directories. MediaDetect is the only detection source; this skill is the
orchestration layer.

## Safety contract

- Never modify media files before the user has seen a plan and explicitly
  confirmed the unit IDs.
- `high` confidence is **not** permission to execute. Always ask.
- Never use `mv`, `cp`, or `mkdir` yourself. Only call the helper script.
- Do not organize a path the user did not ask for.
- If anything is ambiguous, keep it `unplanned` and say why. Do not guess.

## Workflow

### 1. Scan

```bash
python3 scripts/media_title.py scan "<path>" --json
```

Read `session_id`, `root`, `units[]`, `unplanned[]`, and `skipped[]`.
If `unplanned` is non-empty, show every item and its `reason_code`.

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
user or another process changed the target.

## Rules the script enforces

- One session has at most one plan. To replan, start a new session.
- `--expect-plan-id`, `--select`, and `--yes` are required for apply.
- `--expect-plan-id` and `--yes` are required for rollback.
- No overwrite, no directory merge, no deletion of non-empty directories.
- Only `mkdir`, `move`, and `remove_empty_dir` operations exist.
- A move uses no-replace semantics; unsupported filesystems are rejected.
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
