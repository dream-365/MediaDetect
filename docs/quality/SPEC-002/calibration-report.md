# SPEC-002 MediaDetect 校准报告

- 日期：2026-11-11
- Spec：`docs/specs/SPEC-002-media-type-detection/spec.md`（Approved）
- 冻结样本：`parser/testdata/filenames.txt`（公开版本为合成/匿名 fixture）
- 样本哈希：`384168a05d6153950d1e0431278da1061f187df4f34e5f30920c2dcc1f2e989f`
- 样本来源：SPEC-001 Rollout 0 采集的 231 条文件名（228 视频 + 3 字幕），2026-11-10 冻结；原始语料与绝对路径只保留在 MStruct 私有仓库，公开仓库使用同计数、同结构的合成 fixture
- 运行环境：2026-11-11 报告首次生成时 SMB 根未挂载；后续第 9 节完成 10 个真实文件抽测。第 2–7 节的统计基于脱敏前的冻结真实语料，公开版本不包含原始片名

## 1. 口径与限制

| 项目 | 说明 |
| --- | --- |
| 类型样本 | 231 条真实文件名，文件级；不含目录聚合真实样本 |
| 已知限制桶 | 3 条裸数字集号样本 `Example.Documentary.01/02/03`（匿名化），按 SPEC-002 附录 B 不计入准确率门槛，但单独报告 |
| 匹配样本 | 沿用 SPEC-001 Rollout 0 的 225 个 feature 文件基线；本次未重跑真实 TMDB |
| 匹配 mock | `TestDetectMockMatchAndIMDb`、`TestDetectCandidatesOnlyBestHasIMDb` 等覆盖 `imdb_id`、候选与零请求契约 |
| 目录聚合 | `TestAggregateRows` 覆盖 SPEC-002 4.5.2 的 9 行 fixture，不代表真实目录准确率 |

## 2. 本地类型：混淆矩阵

人工标签来自冻结语料的真实文件名语义：222 部电影、3 集裸数字集号纪录片、3 个 keynote/OVA 非正片、3 个字幕。

| 真实 \ 预测 | movie | tv_episode | non_feature | auxiliary | other | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| movie | 222 | 0 | 0 | 0 | 0 | 222 |
| tv_episode（已知限制） | 3 | 0 | 0 | 0 | 0 | 3 |
| non_feature | 0 | 0 | 3 | 0 | 0 | 3 |
| auxiliary | 0 | 0 | 0 | 3 | 0 | 3 |
| other | 0 | 0 | 0 | 0 | 0 | 0 |
| 合计 | 225 | 0 | 3 | 3 | 0 | 231 |

## 3. 本地类型：指标

| 指标 | 数值 |
| --- | --- |
| 总体准确率（不含已知限制桶） | 228 / 228 = **100.0%** |
| 总体准确率（含已知限制桶） | 228 / 231 = **98.7%** |
| 剧集召回（含裸数字限制） | 0 / 3 = 0.0%，全部落入附录 B 已知限制桶 |
| 剧集召回（显式 `SxxExx`/中文“第 N 集”契约测试） | 100.0% |

逐类 precision / recall（不含裸数字桶）：

| 类型 | 真阳性 | 假阳性 | 假阴性 | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| movie | 222 | 3（裸数字剧集） | 0 | 222 / 225 = 98.7% | 222 / 222 = 100% |
| non_feature | 3 | 0 | 0 | 100% | 100% |
| auxiliary | 3 | 0 | 0 | 100% | 100% |
| tv_episode | 0 | 0 | 3（裸数字限制） | — | 0% |
| other | 0 | 0 | 0 | — | — |

## 4. 契约与 fixture 覆盖

| 覆盖项 | 测试 | 结果 |
| --- | --- | --- |
| 4.5.1 映射表 9 行 | `TestMapFile` | 通过 |
| 4.5.2 目录聚合 9 行 | `TestAggregateRows` | 通过 |
| 季集展示与标题剥离 | `TestSeasonDisplay` | 通过 |
| summary 恒等式 | `TestSummaryIdentity` | 通过 |
| 辅助类型优先 | `TestParserFixes/subtitle_keeps_auxiliary_role_despite_SxxExx` | 通过 |
| `sample`/`OAD` 词边界 | `TestParserFixes/sample_*`、`TestParserFixes/OAD_*` | 通过 |
| `Nova` 不误报 OVA | `TestParserFixes/Nova_is_not_an_OVA` | 通过 |
| `1x01` / `S01.E01` | `TestParserFixes/1x01_is_normalized`、`TestParserFixes/S01.E01_is_normalized` | 通过 |
| `S01E01-E03` range | `TestParserFixes/S01E01-E03_keeps_the_full_range` | 通过 |

`TestParseSampleCorpus` 只锁定 231/228/3 等总数与类别计数，不逐条断言人工标签；第 2 节的混淆矩阵来自冻结文件名语料的人工标注统计，不是该测试直接生成的断言。

## 5. 电影匹配与 IMDb（G4）

沿用 SPEC-001 Rollout 0 阶段 B3 的冻结基线（同一批 225 个 feature 文件）：

| 指标 | 基线 | SPEC-002 门槛 | 本次结论 |
| --- | ---: | ---: | --- |
| high（文件级，225） | 194 / 225 = 86.2% | ≥86.2% | 沿用基线，本次未复测 |
| high + medium（文件级，225） | 207 / 225 = 92.0% | ≥90% | 沿用基线，本次未复测 |
| high（组级，221） | 192 / 221 = 86.9% | ≥86.9% | 沿用基线，本次未复测 |
| high + medium（组级，221） | 209 / 221 = 94.6% | ≥94.6% | 沿用基线，本次未复测 |

本次实现没有新增匹配规则；`mediadetect` 直接迁移 matcher 并只补一次 `Details` 取 `imdb_id`。mock TMDB 测试确认：

- `best.imdb_id` 非空；`candidates[].imdb_id=null`。
- 同一 TMDB ID 的不同 `GroupKey` union 后 `distinct_movies=1`。
- 剧集/非正片/附属文件不发送 `/search/movie`。
- `--match=off` 计数 transport 请求数为 0。

真实样本的 high `imdb_id` 非空率本次未重测：SMB 根未挂载，无法对 225 个文件重新执行 `Details`。该项在根恢复挂载后用以下命令补测：

```bash
go test ./... -run TestMatch
source ~/.zprofile
HTTPS_PROXY=http://127.0.0.1:1087 mediadetect --match=on --probe=off <sample-root>
```

## 6. 错误清单

| 文件 | 标签 | 预测 | 原因 | 处理 |
| --- | --- | --- | --- | --- |
| `Example.Documentary.01`（匿名） | tv_episode | movie | 裸数字集号未识别 | 附录 B 已知限制 |
| `Example.Documentary.02`（匿名） | tv_episode | movie | 同上 | 附录 B 已知限制 |
| `Example.Documentary.03`（匿名） | tv_episode | movie | 同上 | 附录 B 已知限制 |

除上述已知限制外，冻结语料没有其他类型错误。

## 7. 复现命令

```bash
go test ./parser -run TestParseSampleCorpus
go test ./parser -run TestParserFixes
go test . -run 'TestMapFile|TestAggregate|TestSeasonDisplay|TestSummaryIdentity'
go test . -run 'TestDetectMockMatchAndIMDb|TestDetectUnionByMovieID|TestDetectCandidatesOnlyBestHasIMDb|TestDetectMixedOnlySearchesMovieTitles'
```

## 8. 结论与后续

1. 冻结文件名样本上，本地类型准确率超过 G3 的 95% 门槛；3 条裸数字剧集是唯一已知限制错误。
2. 目录聚合只经过 fixture 契约测试，真实目录样本待 SMB 根挂载后补测。
3. 匹配与 IMDb 的回归下限沿用 SPEC-001 B3 基线，本次未重跑真实 TMDB，因此不把基线数字表述为本次实测；真实 `imdb_id` 非空率待补测。
4. 本报告不把 mock/fixture 结果冒充真实世界准确率；未测项明确标为待补。

## 9. SMB 恢复后的 10 部电影抽测

2026-11-11 SMB 根恢复挂载后，随机抽取 10 个电影文件做真实探测与 TMDB 匹配抽测。为保护影库隐私，公开报告只保留匿名序号与聚合结果，不记录真实文件名、TMDB ID 或 IMDb ID。命令：

```bash
HTTPS_PROXY=http://127.0.0.1:1087 mediadetect "<file>"
```

默认 `--probe=auto --match=auto`，`ffprobe` 与 `exiftool` 均在 10s 总预算内返回。

| # | 类型 | 置信度 | probe | 匹配 | IMDb 非空 |
| ---: | --- | --- | --- | --- | --- |
| 1–10 | movie | high | ok | 8 high / 1 medium / 1 low | 10 / 10 |

汇总：

| 指标 | 结果 |
| --- | --- |
| 本地类型准确率 | 10 / 10 = **100%**，全部 `movie` / `high` |
| probe 成功 | 10 / 10 |
| 匹配 high | 8 / 10 |
| 匹配 medium（best 正确，标题部分匹配） | 1 / 10 |
| 匹配 low（best 正确，但 margin 被第二名压低） | 1 / 10 |
| 匹配 unmatched | 0 / 10 |
| `best.imdb_id` 非空 | 10 / 10 |

抽测发现：

1. 全角斜杠样本的 `/` 在标题归一化时被压成空格，TMDB 对该查询返回 0 条；修复后标题候选保留 `/`，并为长标题生成去前缀/截断搜索变体；matcher 再用 NFKC，把 TMDB 的 `½` 与 `1/2` 统一。真实复测命中正确条目，`match.status=medium`（`title_score=0.66`，`score=0.762`）。
2. 一个低 margin 样本的 best 是正确条目且 `score=1`，但第二名得分 0.914，`margin=0.086` 低于 0.10，按 matcher 现有阈值降为 `low`；不是错配。
3. 一个导演剪辑版样本命中的条目作品正确，但 TMDB 年份与文件名年份相差 17 年；当前 matcher 因 alt_title 与 runtime 命中仍判 `high`，年份证据未参与降级。
4. 本抽测只有 10 个文件，不替代 T9 要求的 ≥100 个真实文件/目录样本；目录聚合与真实 `imdb_id` 非空率仍需继续补测。

## 10. 对抗性评审修复（2026-11-11）

三路独立只读评审（CLI/JSON 契约、检测正确性、安全/集成）后完成以下修复，并补了对应回归测试：

| 级别 | 修复 | 回归测试 |
| --- | --- | --- |
| P1 | root 级 `WalkDir` 错误不再被当成空目录；scanner 在存在不可读项时跳过 `MarkMissing`；未变化文件重新出现时恢复 `active` | `TestCollectRootWalkFailure`、`TestScanReactivatesUnchangedFile` |
| P2 | 展示层剥离 `S01.E01`/`1x01`/CJK 集号；`tv_season` 用目录季号补齐 `summary.seasons`；probe 使用 WalkDir 原始路径，避免 NFD 路径被 NFC 重建 | `TestDisplayTitlesStripEpisodeForms`、`TestSeasonDirectoryFillsSummary` |
| P3 | `probe.unavailable` 仅在两个工具都不可执行时产生；`--verbose` 输出 best；`evidence` 分数三位小数；无实际 TMDB 请求时 `attribution=null`；`--pretty` 作用于错误与 version；`1x01` 误报防护；NUL 路径错误码；探测后取消检查 | `TestProbeUnavailableOnlyWhenBothToolsMissing`、`TestCLIMockTMDB`、`TestDetectEvidenceRoundsScores`、`TestDetectAttributionRequiresRequest`、`TestCLIPrettyAppliesToErrorsAndVersion`、`TestEpisodeXFalsePositives`、`TestDetectNULPathIsInvalid`、`TestCollectCancelAfterProbe` |
| 集成 | mstruct 的 TMDB wrapper 保持 20s 单请求超时；README 说明不发布独立仓库，外部 `go install` 不支持 | `internal/tmdb` contract 测试、README |
| Spec 遗留 | parser 第五项修正保留 `/`，`示例片1／2` 标题候选变为 `示例片1/2`；长标题生成去前缀/截断搜索变体；matcher `normalizeTitle` 用 NFKC 统一 `½` 与 `1/2`；union 规则改为 union 后 `distinct_movies>1` 才 `multiple`；顶层 `error` 明确仅 `ok=false` 时出现 | `TestFullWidthSlashKeptInTitle`、`TestDetectFullWidthSlashQueryKeepsSlash`、`TestUnicodeFractionTitleNormalization`、`TestDetectUnionByMovieID` |

仍未改变、属于既有行为或附录 B 的项：一个导演剪辑版样本的年份差异仍判 high、一个低 margin 样本的置信度降为 low、裸数字集号、`S01E01E02`、`Show S01` 目录。前两项已作为 matcher 既有行为写入附录 B；以上不是本轮实现回归。
