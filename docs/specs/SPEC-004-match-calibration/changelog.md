---
type: changelog
status: Published
owner: alang
depends_on: []
updated_at: 2026-11-12
---

# Changelog: SPEC-004 匹配校准

## [2026-11-14] - T5 文档口径修订

- **修改类型**: Changed
- **影响范围**: §2.1 G2/G4；§3.2；§3.4；`tasks.md` 的 `spec_sha256`
- **变更原因**: 完成 T5 收尾，修正验收发现的 Spec 内部口径冲突。按 CLAUDE.md，先把本 Spec 状态回退为 `In Review`、更新 `updated_at`、记录变更；修订后恢复 `Approved`。
- **具体内容**:
  - warning 去重键统一为 `(code,detail,file)`，与 SPEC-003 §4.3.6 和实现一致。
  - SMB validation 口径明确：utime 成功时文件 `size_mtime`、目录 `portable_subtree`；失败时两者 `size_content`。
  - T5 完成：MediaDetect `0.2.2`、media-title `0.1.1`；README/CI/`defaultVersion`/`SKILL.md` 同步；A1/A2 增加离线 fixture，D 保留 matcher 单测；Python 108 项通过。
  - 重算 `tasks.md` 的 `spec_sha256`。

## [2026-11-12] - 初始草案（In Review）

- **修改类型**: Added
- **影响范围**: 新建 SPEC-004；`matcher/`；`docs/specs/README.md`；后续 SPEC-001/SPEC-002 版本口径
- **变更原因**: 真实负样本出现 A1 年份冲突 medium 误匹配、A2 短别名 1.00 high 误匹配；C 标定不单调；需要在不扩大召回的前提下封顶高置信度错误。
- **具体内容**:
  - G1：年份 delta 分级 none/soft/hard；soft 最高 medium、hard 最高 low，新增 `match.year_conflict`。
  - G2：短别名 + 长组合候选的区分 token 校验；无匹配则最高 low，新增 `match.ambiguous_title`；用 title/original 做确定性判断，不新增网络依赖。
  - G3/G4：A1/A2 负样本 high 误报为 0；D 正样本（含「分贝」「蚁人2」）不被误伤；warning 出现在 MediaDetect `warnings[]`。
  - 明确非目标：B1 跨语言召回、B2 TV 匹配、评分算法重写、自动执行策略。
  - 状态 `In Review`，等待用户批准后再改生产代码。

## [2026-11-12] - 三路独立评审修订

- **修改类型**: Changed
- **影响范围**: SPEC-004 spec/tasks；SPEC-003 T12/T13；依赖 SPEC-001/SPEC-002 版本口径
- **变更原因**: 三路独立评审均 BLOCK，并补充 4 份 NG 负样本。确认原方案有三处根因误判：A2 是 media-title plan 层提升而非 MediaDetect high；短别名规则会误伤 `分贝/Decibel`、`一一/Yi Yi`、`她/Her`、`鬼灭之刃/Demon Slayer`；只改 MediaDetect status 不影响实际 planned 单元。
- **具体内容**:
  - A2 描述改为 MediaDetect low/margin≈0.086、plan high；新增 G5 plan 门控任务 T4。
  - 删除短别名封顶，改为超集标题额外显著 token 防护（G2）和续集编号约束（G3）。
  - 年份改为“取与 best 最接近的文件名年份”，soft 2–4、hard ≥5；硬冲突无 runtime 证据 → low；runtime+alt_title 例外最高 medium。
  - 新增 `match.year_unknown`、`match.title_superset`、`match.sequel_mismatch`；warning 由 matcher 产出、根包补 file。
  - 低分/低 margin/title_hit=false 在 media-title plan 进入 `unplanned/low_confidence`，不再与 high 一起批量执行。
  - SMB check-then-rename 增加 utime 恢复/`size_portable` 容忍与 `mtime_rewritten` warning（T5/SPEC-003 T13）。
  - G4 旧比例门槛改为“冻结负样本 high 误报 0 + D 正样本不下降 + 允许降级清单”，在 T6 重放并修订 SPEC-001。
  - 版本目标明确为 MediaDetect v0.3.0；版本文件、CI、SPEC-001/002 回退列入 T6。
  - 明确非目标：B1/B2、短片/赛事/语言过滤、title score 重写、自动执行策略。

## [2026-11-12] - 收缩为安全关键子集

- **修改类型**: Changed
- **影响范围**: SPEC-004 spec/tasks；SPEC-003 T12/T13；版本 0.2.2/0.1.1
- **变更原因**: 第二轮两路复审仍 BLOCK。全量超集/续集/别名规则需要冻结 fixture 与重新基线，且 u68/R3-u44 在“不引入 runtime/IMDb/短片过滤”的非目标下不可满足；继续全量会导致验收不可执行。
- **具体内容**:
  - 只保留 G1 硬年份 `|delta|>5` 封顶（runtime 成立则保留原 confidence + warning），删除 soft 年份、超集/续集/短别名规则。
  - G3 plan 门控：status 继承、low/unmatched/title_hit=false/score<0.6 → `unplanned/low_confidence`；disabled/unavailable 例外。
  - G4 SMB：size/内容指纹（不含 mtime）+ utime 恢复；失败 `size_content` + `mtime_rewritten`；rollback 同策略。
  - G5 回归只覆盖 A1/A2/D 与低分/disabled；u68/R3-u44、超集/续集/TV/B1/B2 写入已知限制。
  - 225 真实基线不重放；报告历史基线与允许降级原则。
  - 版本改为 MediaDetect 0.2.2、media-title 0.1.1，避免 minor 破坏性口径。

## [2026-11-12] - T1–T4 实现完成

- **修改类型**: Implemented
- **影响范围**: `matcher/matcher.go`, `matcher/matcher_test.go`, `match.go`, `match_detect_test.go`, `skills/media-title/{scan,plan,fsops,apply,rollback}.py`, tests
- **变更原因**: 实现安全关键子集。
- **具体内容**:
  - matcher：`|year_delta|>5` 且 runtime 不成立时 confidence 最高 low，输出 `match.year_conflict`；runtime 成立保留原 confidence + warning；delta≤5 不封顶。
  - root：matcher warnings 转入 `detection.warnings[]`，`file` 使用代表文件相对路径。
  - media-title scan：movie unit 保存 `match_status`/`match_margin`/`match_score`/`title_hit`；匹配 warning 进入 scan warnings。
  - plan：取文件级与 score 推导 status 的较低者；low/unmatched/score<0.6/title_hit=false → `unplanned/low_confidence`；disabled/unavailable 例外；medium+title_hit=true 可 planned。
  - warning 统一为 `{code,detail,file}` 对象；scan/plan human 输出显示 warning。
  - SMB：check 模式先按 size/内容指纹（不含 mtime）校验，utime 恢复 mtime；失败 `size_content` + `mtime_rewritten`；rollback 同策略并恢复 from_state mtime。
  - 测试：Go 新增硬/软年份与 root warning；Python 新增 low_confidence、disabled 例外、warning 透传、SMB mtime rewrite；Python 101 项通过。
  - 版本 bump 与 SPEC-001/002 重放留待 T5 发布阶段，当前不改变 `--version` 0.2.1。

## [2026-11-14] - 提交前验收修复

- **修改类型**: Fixed
- **影响范围**: `scan.py`, `plan.py`, `apply.py`, `paths.py`, `fsops.py`, `warnings.go`, tests, README/SKILL 文档
- **变更原因**: 四个独立验收智能体发现 warning 解析断链、SMB 崩溃对账仍比较 mtime、`--mode single` 已整理条目未跳过，以及分卷 A/B 连字符和 `1-2` 后缀缺口。
- **具体内容**:
  - scan 改读 `detection.warnings[]`，只吸收 `match.year_conflict`；warning 挂到对应 unit，并汇总到 scan/plan/human。
  - plan 为 medium planned 单元补 `medium_confidence` 提示，并把 unit warning 汇总到 plan 顶层。
  - check-then-rename 的崩溃 intent 一律按 size/内容指纹对账，不要求 mtime；done 记录 `validation=size_content`。
  - `--mode single` 的目录内容与直接文件均按已整理条目跳过并写 `skipped/already_organized`。
  - 分卷 A/B 支持连字符分隔；补 `1-2`/`2-2` 分数式硬分卷。
  - warning 去重键改为 `(code,detail,file)`；`E_NO_REPLACE_UNSUPPORTED` 同时提示 CLI 与环境变量。
  - 版本 bump 仍未执行，留待 T5。
