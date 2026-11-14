---
type: tasks
status: Approved
owner: alang
depends_on:
  - docs/specs/SPEC-001-media-type-detection/spec.md
spec: ./spec.md
spec_sha256: "a25aace5354016fee4595bf39980b760cb396654d5d7f240f7ccfd026e481791"
updated_at: 2026-11-14
---

# 匹配安全子集执行拆解

| ID | 任务 | 覆盖 | 依赖 | 写入 | 完成标准 | 验证 |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | 硬年份封顶与 warning | G1, G2 | — | `matcher/matcher.go`, `matcher/matcher_test.go`, `matcher/calibration_test.go` | `|delta|>5` 且 runtime 不成立 → 最高 low + `match.year_conflict`；runtime 成立保留原 confidence + warning；delta≤5 不封顶；更新两条 delta=14 测试；clamp 只降不升 | `go test ./matcher`；A1/蚁人/delta14 用例 |
| T2 | warning 到根包 | G2 | T1 | `matcher/matcher.go`, `match.go`, `result.go`, `warnings.go`, `match_detect_test.go` | `matcher.Result.Warnings` 只含 code/detail；`buildMatch` 补代表文件相对路径；`detection.warnings[]` code/detail 稳定；offline/无候选无伪 warning | 根包测试；JSON warning；无 key |
| T3 | plan 状态继承与低分门控 | G3 | SPEC-003 T12 批准；T2 | `skills/media-title/scripts/media_title_lib/scan.py`, `plan.py`, `scripts/media_title.py`, `assets/plan.schema.json`, `tests/test_scan.py`, `tests/test_plan.py`, `tests/test_regressions.py` | scan 保存 status/margin/score/title_hit；plan 取较低 status；low/unmatched/title_hit=false/score<0.6 → `unplanned/low_confidence`；disabled/unavailable 例外；medium+title_hit=true 可 planned；warning 汇总/human 输出 | A1/A2 plan 断言；低分/disabled 用例；D 正样本 |
| T4 | SMB mtime 内容指纹 | G4 | SPEC-003 T13 批准 | `skills/media-title/scripts/media_title_lib/fsops.py`, `apply.py`, `rollback.py`, `tests/test_fsops.py`, `tests/test_regressions.py`, `tests/test_rollback.py` | check 后 size/内容指纹校验；utime 恢复 mtime；失败则 size_content + `mtime_rewritten`；rollback 同策略并恢复 from_state mtime；strict 不变 | mock rename 改写 mtime；内容不一致失败 |
| T5 | 回归、文档与版本收尾 | G5 | T1–T4 | `docs/quality/SPEC-004/calibration-report.md`, `README.md`, `cmd/mediadetect/config.go`, `cmd/mediadetect/main_test.go`, `.github/workflows/ci.yml`, `skills/media-title/SKILL.md`, `docs/specs/SPEC-001-media-type-detection/{spec,changelog,tasks}.md`, `docs/specs/SPEC-002-package-boundary/{spec,changelog,tasks}.md` | A1/A2/D 回归；历史基线说明；版本 0.2.2 / media-title 0.1.1；SPEC-001/002 按 CLAUDE.md 回退修订；CI 全绿 | 离线回归；`go test ./...`；CI |

> 状态：T1–T5 已完成（2026-11-14）。版本口径为 MediaDetect `0.2.2` / media-title `0.1.1`；A1/A2 用离线 fixture，D 用 matcher 单测覆盖，不访问 TMDB。

## 依赖关系

```text
T1 -> T2 -> T3 -> T4 -> T5
```

## 边界

- 不实现超集/续集/短别名/B1/B2；写入已知限制。
- 不重放 225 真实基线；只报告历史基线与允许降级原则。
- 不通过硬编码样本名/TMDB ID 达成回归。
- 低分 unplanned 是安全性取舍；D 0.44 类正确样本可能转 unplanned。
