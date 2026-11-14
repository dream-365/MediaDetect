---
type: spec
status: Approved
owner: alang
depends_on:
  - docs/specs/SPEC-001-media-type-detection/spec.md
updated_at: 2026-11-14
---

# 匹配安全子集：硬年份封顶与端到端门控

| 字段 | 内容 |
| --- | --- |
| 标题 | 匹配安全子集：硬年份封顶与端到端门控 |
| 主笔 | alang |
| 评审人 | alang；两轮独立评审（算法/对抗性/规范） |
| 创建日期 | 2026-11-12 |
| 目标版本 | MediaDetect v0.2.2；media-title v0.1.1 |
| 关联资源 | `matcher/`；`match.go`；`skills/media-title/`；`/Users/alang/Workspace/MediaLib/NG/*.md` |

## 1. 背景与范围

真实负样本确认：

- A1 `Give.Me.Five.2022` 命中 1984 年条目，score 0.76/medium，正确 2022 条目 0.44；medium 进入可执行计划。
- A2 `诗人.BARDO...2022` 在 MediaDetect 已是 low/margin≈0.086，但 media-title plan 用 best.score 重算为 high/1.0。
- 低分单元（0.14/0.438/0.445）仍被 planned。
- SMB check-then-rename 因服务端改写 mtime 全部 `E_NON_ATOMIC_MOVE_FAILED`。

两轮独立评审确认：**全量匹配校准（超集/续集/别名）需要冻结 fixture 和重新基线，不适合本轮硬塞**。本 Spec 只做可验证的安全子集：

1. MediaDetect 硬年份冲突封顶；
2. warning 通道；
3. media-title plan 继承 status、低分门控、warning 透传；
4. SMB check 模式 mtime 兼容。

B1 跨语言召回、B2 TV、超集/续集/别名规则、短片/赛事/语言过滤仍是已知限制。

## 2. 目标与非目标

### 2.1 目标

* **G1 - 硬年份封顶**：best 的 `|TMDB year - primaryYear| > 5` 时，若 runtime 证据不成立（`|runtime_delta| > 180s` 或无 runtime），confidence 最高 low，并输出 `match.year_conflict`。runtime 证据成立时保留原 confidence，但仍输出 warning。`|delta| <= 5` 不封顶（保护 `蚁人2.2022` delta=4）。无文件名年份不封顶。
* **G2 - warning 通道**：`matcher.Result` 新增 `Warnings []MatchWarning{Code, Detail}`；根包 `buildMatch` 补代表文件相对路径后写入 `detection.warnings[]`；稳定 code 仅 `match.year_conflict`（本轮）。
* **G3 - plan 状态继承与低分门控**：scan 保存文件级 `match.status`/`margin`/`score`/`title_hit`；plan 取“文件级 status 与 score 推导 status 的较低者”，不得提升。以下进入 `unplanned/low_confidence`，不生成 unit/operations：
  - 真实 TMDB 状态为 `low`/`unmatched`；
  - `title_hit=false` 且状态不是 `disabled`/`unavailable`；
  - `score < 0.6` 且状态不是 `disabled`/`unavailable`。
  `disabled`/`unavailable` 的本地降级命名不受该闸门影响；`medium` 且 `title_hit=true` 可 planned，并显示已有 warning。
* **G4 - SMB mtime 兼容**：check-then-rename 后先按 size + 不含 mtime 的内容指纹校验（文件 size；目录相对路径+类型+size）；一致则尝试 `os.utime` 恢复 mtime；恢复成功时文件 `validation=size_mtime`、目录 `validation=portable_subtree`，失败时两者均为 `validation=size_content` + `mtime_rewritten` warning，仍成功。内容指纹不一致 → `E_NON_ATOMIC_MOVE_FAILED`。rollback 同策略，并恢复到 `from_state.mtime_ns`（尽力）。
* **G5 - 回归保护**：A1 不得在 plan 中成为 medium/high；A2 不得在 plan 中成为 high；D `蚁人2`（delta=4）保持 medium；现有 96 项 Python 测试和 Go 测试更新后全绿。

### 2.2 非目标

* **NG1 - 超集/子串标题规则**：`Little Blue → little blue clown`、`Hear Me → Now Hear Me Out!`、`Dangal → One Championship: Dangal` 等本轮不新增规则；依赖 `title_hit=false` 门控，未覆盖的写入已知限制。
* **NG2 - 续集编号规则**：`无间道II/III` 本轮不新增；写入已知限制。
* **NG3 - 别名/短标题规则**：不做短别名封顶，避免误伤 `分贝`/`一一`/`她`/`鬼灭之刃`。
* **NG4 - B1/B2**：跨语言召回、TV 检索不做。
* **NG5 - 短片/IMDb/语言过滤**：不做；u68 (`Her Story→Herstory`) 与 R3-u44 (`Eye for an Eye`) 仍会 high，写入已知限制。
* **NG6 - 重写 title score/召回**：不做。
* **NG7 - 225 基线重放**：历史 225 真实语料不在仓库，本轮不硬性重放；报告历史基线与有意降级清单。

## 3. 设计

### 3.1 年份封顶

1. 使用现有 `primaryYear(hints.YearCandidates)` 与最终 `best.Movie.Year()` 计算 delta；不改变候选排序或查询。
2. `|delta| <= 5` 或无文件名年份/TMDB 年份：不封顶。
3. `|delta| > 5`：
   - 若 `runtimeCondition`（`|runtime_delta| <= 180s`）成立：保留原 confidence，warning `match.year_conflict`。
   - 否则：confidence 最高 low，warning。
4. clamp 只降不升；在最终 best、aliasRescue、runtime 重排、probeFailed 降级之后应用。
5. A1 delta=38 且无 runtime → low；`蚁人2` delta=4 → 不封顶，保持 medium。
6. Remaster/DC 正确样本若 runtime 命中可保留原 confidence；若文件名只有版本年份且无 runtime，则可能 unplanned，写入已知限制。

### 3.2 warning 通道

* `matcher.Result` 新增 `Warnings []MatchWarning{Code, Detail}`；matcher 只产出 code/detail。
* `match.go` 的 `buildMatch` 把 warning 写入 `warningSet`，`file` 使用代表文件相对路径；去重按 `(code,detail,file)`。
* `match.year_conflict` detail 含 `year_delta`、`file_year`、`tmdb_year`、`runtime_ok`。
* detail 字段名稳定，逐字内容不作为契约；同一文件可同时有其他 code。
* 无候选/disabled/unavailable 不产生该 warning。

### 3.3 plan 门控（media-title）

* scan movie unit 保存 `match_status`、`match_margin`、`match_score`、`title_hit`。
* status 全序：`high > medium > low > unmatched`；`disabled`/`unavailable` 作为“本地降级”特殊状态，不参与 TMDB 门控。
* `final_status = min(file_status, score_status)`；score_status 阈值沿用现有：≥0.8 high、≥0.5 medium、否则 low。
* 门控：
  - `disabled`/`unavailable`：保留现有本地命名计划。
  - `low`/`unmatched`：`unplanned/low_confidence`。
  - `title_hit=false` 或 `score<0.6`：`unplanned/low_confidence`。
  - `medium` 且 `title_hit=true`：可 planned，显示 warning；`high` 可 planned。
* 该门控在 `_movie_unit` 前执行，不生成 target/operations。
* A2 文件级 low → plan 不再 high；A1 硬年份 low → unplanned。

### 3.4 SMB mtime 兼容

1. check-then-rename 前记录 `from_state`（含 mtime）。
2. 移动后计算：
   - 文件：size 必须一致；
   - 目录：内容指纹 = 相对路径 + 类型 + size（不含 mtime/dev/ino）必须一致。
3. 一致后尝试 `os.utime(dst, ns=(before.mtime_ns, before.mtime_ns))`；成功时文件 `validation=size_mtime`、目录 `validation=portable_subtree`。
4. utime 失败或 mtime 仍不一致：允许成功，`validation=size_content`，warning `mtime_rewritten`。
5. size/内容指纹不一致：`E_NON_ATOMIC_MOVE_FAILED`，尝试恢复源。
6. rollback 使用同一策略；反向移动后尝试把源 mtime 恢复到 `record.from_state.mtime_ns`。rollback 预检/崩溃对账对 `validation=size_content` 忽略 mtime，按 size/内容指纹比较。
7. strict 默认行为不变；只有 `--no-replace=check` 进入该路径。

### 3.5 已知限制

* `Her Story→Herstory`、`Eye for an Eye→Eye for an Eye 2` 等 delta≤1、title_hit=true 的错误不会被本轮规则拦截。
* 超集/子串、续集编号、TV、跨语言召回仍可能误配；建议后续独立校准 Spec。
* 低分门控会降低召回；D 0.44 正确样本会进入 unplanned。
* 历史 225 基线无法离线重放；只报告原则性降级清单。

## 4. 任务与验收

* T1：硬年份封顶、warning、更新两条 delta=14 测试（带 runtime 的保留原 confidence）。
* T2：warning 从 matcher 到 `detection.warnings`。
* T3：SPEC-003 T12 plan 门控与 warning 透传。
* T4：SPEC-003 T13 SMB mtime。
* T5：A1/A2/D 回归、文档、版本 0.2.2/0.1.1、CI。

验收：
1. A1 在 plan 中不是 medium/high；A2 不是 high/medium；均进入 unplanned/low_confidence。
2. `蚁人2` 保持 medium；`分贝`、`原样复制`、`喜欢妳是妳`、`秒速5厘米` 不因新门控降级（使用现有真实样本/离线 fixture）。
3. 低分 0.14/0.438/0.445 不再 planned；disabled/unavailable 本地命名仍可用。
4. warning 在 MediaDetect JSON、scan unit、plan warnings、human 输出四层可见。
5. SMB mock rename 改写 mtime 时 apply/rollback 成功且 warning 正确；内容不一致仍失败。
6. `go test ./...`、`go vet`、`gofmt`、`go mod tidy -diff`、Python 技能测试全绿。
7. 生产代码不包含 A1/A2/NG 文件名或 TMDB ID 的硬编码。

## 5. 风险

* 硬年份封顶 + 低分门控会减少 planned 数量，可能把正确低分/年份错误样本转 unplanned。
* 超集/续集/TV 等残余误配未修复，只能靠后续校准。
* `size_content` 弱化 mtime 检测；必须保留 `mtime_rewritten` warning 和日志。
* 版本 0.2.2 是行为变更，需要更新现有 matcher 测试和 README 已知限制。
