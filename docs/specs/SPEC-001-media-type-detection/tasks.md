---
type: tasks
status: In Progress
owner: alang
depends_on: []
spec: ./spec.md
spec_sha256: "5129dbe5f7882074c96bca76332e08586ce4692fed767789b6721ef48c437c15"
updated_at: 2026-11-11
---

# MediaDetect v0.1.0 执行拆解

本文件记录独立仓库 v0.1.0 的交付范围与验收。T1–T7 与 T9 已完成；T8 的质量门槛还有真实样本待补。

| ID | 任务 | 覆盖 | 依赖 | 写入 | 完成标准 | 验证 |
|---|---|---|---|---|---|---|
| T1 | module、包结构与 CI | G2 | — | `go.mod`, `go.sum`, `.github/workflows/ci.yml`, `parser/`, `probe/`, `tmdb/`, `matcher/`, `internal/collect/`, `internal/llm/`, `cmd/mediadetect/` | module path 为 `github.com/dream-365/MediaDetect`；包含 parser/probe/tmdb/matcher/llm/collect/根包/cmd；不依赖私有项目；CI 覆盖 macOS + Linux | `go test ./...` |
| T2 | parser 五项最小修正 | G3 | T1 | `parser/` | 字幕保持 `subtitle`；`sample`/`OAD` 与非正片词边界生效；`Nova` 不误报 OVA；`1x01`/`S01.E01` 归一化；全角斜杠保留为 `/` | `go test ./parser` |
| T3 | collect 只读遍历与探测 | G2 | T1 | `internal/collect/` | 返回 `CollectedFile`/`Seen`/`Counts`；排序稳定；`MaxFiles` 截断置 `Truncated`；隐藏项/符号链接/不可读子项按计数跳过；root 不可读返回 error | `go test ./internal/collect` |
| T4 | 本地类型映射与目录聚合 | G3 | T1, T2 | `mapping.go`, `aggregate.go`, `mapping_test.go`, `helpers_test.go` | 4.5.1 映射表九行、4.5.2 聚合表九行均有测试；`mixed` 顶层为 `multiple/reason=mixed_types`；季集展示与 summary 恒等式成立 | `go test . -run 'TestMapFile\|TestAggregateRows\|TestSeasonDisplay\|TestSummaryIdentity'` |
| T5 | 电影匹配、union 与 imdb_id | G4 | T3, T4 | `match.go`, `match_detect_test.go` | mock TMDB 下 high 匹配 `best.imdb_id` 非空；剧集/非正片/附属不发送电影搜索；同一 TMDB ID union；无候选时 `margin=null`、`best=null` | `go test . -run 'TestDetectMockMatchAndIMDb\|TestDetectUnionByMovieID\|TestDetectCandidatesOnlyBestHasIMDb\|TestDetectMixedOnlySearchesMovieTitles'` |
| T6 | 降级、零请求与凭据脱敏 | G5 | T5 | `detect.go`, `detect_test.go`, `warnings.go`, `policy.go` | 无 key 的 auto/on、纯剧集、`--match=off` 零请求、错误路径不含 key/query/body 均有测试 | `go test ./... -run 'TestDetectNoKey\|TestDetectMatchOffMakesNoRequests\|TestDetectTVMakesNoRequests\|TestDetectAuxiliaryAndNonFeatureWithoutKey\|TestErrorsDoNotLeakKeyQueryOrBody'` |
| T7 | CLI：单 JSON、stdin、flags 与退出码 | G1 | T6 | `cmd/mediadetect/` | 文件/目录/stdin/缺参/路径不存在/无 key/`--match=off` 七类 golden 通过；stdout 恰好一个 JSON；`--version` 与 `--help` 行为符合契约；运行前后输入树快照一致 | `go test ./cmd/mediadetect` |
| T8 | 类型与匹配校准报告 | G3, G4 | T5, T7 | `docs/quality/SPEC-001/calibration-report.md` | 报告包含冻结样本、混淆矩阵、逐类 precision/recall、high/medium 匹配率、`imdb_id` 非空率、错误清单；已完成 10 部真实电影抽测为 `imdb_id` 10/10，≥100 个真实目录样本与 225 文件全量 `imdb_id` 复测待补 | `docs/quality/SPEC-001/calibration-report.md` |
| T9 | 发布与消费验证 | G2 | T1, T2, T3, T4, T5, T6, T7 | `—` | `v0.1.0` 的 tag 与 CI 在同一 SHA；干净缓存下 `go list -m` 与 `go install` 成功；`--version` 输出 `0.1.0` | `sh -c 'git tag --list v0.1.0'` |

## 后续

* T8 的真实样本校准：SMB 根可用时补测 ≥100 个真实文件/目录与 225 文件 `imdb_id` 非空率。
* 剧集 TMDB 匹配、全量 IMDb 数据集、批量/NDJSON 与持久缓存均在附录 A 中列为延后项。
