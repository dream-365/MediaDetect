---
type: changelog
status: Published
owner: alang
depends_on: []
updated_at: 2026-11-12
---

# Changelog: SPEC-003 media-title 智能体技能

## [2026-11-14] - v0.1.1 版本口径与验收修复

- **修改类型**: Changed
- **影响范围**: 目标版本；`metadata.version` 示例；`tool_version` 示例；§4.10；CI 版本断言；`tasks.md` 的 `spec_sha256`
- **变更原因**: 完成 SPEC-004 T5 的 media-title `v0.1.1` 与 MediaDetect `v0.2.2` 收尾，并同步上一轮验收修复。按 CLAUDE.md，先把本 Spec 状态回退为 `In Review`、更新 `updated_at`、记录变更；修订后恢复 `Approved`。
- **具体内容**:
  - 目标版本改为 media-title `v0.1.1`、MediaDetect `v0.2.2`；保留 G6 的 `v0.2.1` 历史说明。
  - `metadata.version` 与 `tool_version` 示例更新为 `0.1.1`；CI 版本断言更新为 `0.2.2`。
  - §4.3.6 明确 medium planned 单元的 warning code 为 `medium_confidence`。
  - §4.10 增加当前发布口径，明确 G6 历史版本与当前版本的区别。
  - 同步上一轮验收修复：single 模式已整理跳过、A/B 连字符与 `1-2` 分卷、rollback SMB 提示。
  - 重算 `tasks.md` 的 `spec_sha256`。

## [2026-11-12] - 初始草案

- **修改类型**: Added
- **影响范围**: 新建 `skills/media-title/` 技能包；新增 SPEC-003；`docs/specs/README.md`；可选 CI `skills` job
- **变更原因**: `scripts/mediadetect-title.sh` 只能单条处理电影，无法面向媒体库和剧集目录；high 置信度直接执行且没有计划/回滚；命名逻辑内嵌在 Bash + jq 中，难以测试和扩展
- **具体内容**:
  - 定义通用 Agent Skill 包结构：`SKILL.md`、单文件 Python 辅助脚本、命名/JSON 参考文档、计划 schema、测试
  - 定义 `scan → plan → apply → rollback` 四段式工作流；扫描/计划只读，执行前逐项确认
  - 电影沿用 `title original_title (year) {imdb_id}` 命名，补齐 original_title/年份/ID 缺失、多电影目录、多分部、附属文件和弱匹配规则
  - 剧集使用 MediaDetect 本地识别生成 `剧名 (年份)/Season NN/`；默认保留原文件名，可选 `SxxExx` 重命名；不引入 TMDB TV
  - 定义计划 JSON、三种操作（`mkdir`/`move`/`remove_empty_dir`）、原子预检、错误码、JSONL 日志与逆序回滚
  - 明确 MediaDetect CLI 的消费字段与兼容边界；v1 不要求 CLI 变更，若实现阶段确需修改，只允许只增不改的只读扩展，且必须先修订 Spec 并重新批准
  - 规划单元测试、集成测试、CI 与验收矩阵

## [2026-11-12] - 架构与对抗性评审修订

- **修改类型**: Changed
- **影响范围**: 全 Spec；§1.1/§1.2/§1.4；§2.1（新增 G6）；§3.2–§3.4；§4.2–§4.11；§5–§6；附录 A–C；`tasks.md`；SPEC-001 与 README 的已知限制（待批准后修订）
- **变更原因**: 独立架构评审（APPROVE WITH CHANGES，A1–A9）与独立对抗性评审（BLOCK，R1–R12）发现数据丢失级缺口和与 MediaDetect 实际行为不符的假设。用户确认四项决策：本次一并修 CLI 多集解析；状态放媒体根下 `.media-title` 但按 session 独立；增加 `--mode auto|single|library`；v1 禁止目录合并。
- **具体内容**:
  - **安全移动**：新增 no-replace 原子移动（Linux `renameat2(RENAME_NOREPLACE)`、macOS `renamex_np(RENAME_EXCL)`、文件 `link+unlink` 回退）；目录无回退时拒绝；移动前后校验 dev/ino。对应 R1。
  - **计划完整性**：`plan_id` 改为规范化内容哈希；`apply`/`rollback` 校验；`--select` 只接受 unit ID/`all`，不接受序号；`--yes` 与 `--select` 必填。对应 A4/R2/R3。
  - **按 session 隔离状态**：`<root>/.media-title/sessions/<session_id>/` 存放 scan/plan/state/日志/锁；session ID 校验；`flock` 防同 session 并发；媒体树指纹排除 `.media-title`。对应用户决策与 A1。
  - **按 unit 完成状态**：`state.json` 支持分批 apply；已应用 unit 跳过；不再用整计划 `.applied` 标记。对应 R3。
  - **回滚可验证/幂等**：日志记录 `from_state`/`to_state`/`created`/`removed_state`；当前状态匹配 `to_state` 才反向；二次回滚跳过；`mkdir created=false` 不删除；`remove_empty_dir` 非空跳过。对应 R4/R5。
  - **多源单元**：`sources[]` + 每源 state + `source_hash`；多分部、散落剧集、侧车都按源记录。对应 A3/R7。
  - **原始路径映射**：用 `os.scandir` 取原始名，NFC 仅用于匹配；映射失败 `E_PATH_IDENTITY`。对应 R12。
  - **根模式**：新增 `--mode auto|single|library` 与确定性判定；多剧库根必须按子目录拆分，单集 `tv_episode` 显式处理。对应 A2/R10。
  - **防御性分类**：`summary.seasons` 不参与逐文件补季；CJK 季号未知不并入其他季；`title_candidates` 为空不造名；`match.status` 补齐 `multiple/not_applicable/error`；`--max-depth 0` 避免静默深度截断。对应 R9/A6/A8。
  - **禁止目录合并**：移除 `--merge-existing`；目录重命名目标必须不存在；只允许逐文件移入已存在 show/season 目录。对应 R6。
  - **命名/幂等**：父目录同名跳过；侧车唯一前缀匹配；非空目录不删；`leftover` 报告。对应 A7/R11。
  - **G6 CLI 修复**：parser 识别连续多集 `S01E01E02`/`S01E01E02E03`，输出 `S01E01-E02`/`S01E01-E03`；非连续不匹配；MediaDetect 发布 `v0.2.1`；按 CLAUDE.md 先回退/修订 SPEC-001 与 README。对应用户决策与 R8。
  - **可测试性**：模块拆分为 `scan/plan/apply/rollback/fsops/paths/session/naming`；`fsops`/`paths`/`session` 可 mock；跨设备与大小写冲突用 mock/平台测试。对应 A9。
  - 新增附录 C，逐条映射 A1–A9、R1–R12 到修订位置。

## [2026-11-12] - 第二轮评审修订与 unplanned 收敛

- **修改类型**: Changed
- **影响范围**: §1.3/§1.4；§2.1 G2/G3/G4/G6；§4.2–§4.10；§5.1；§6.1/§6.2；附录 A–C；`tasks.md`
- **变更原因**: 第二轮独立架构复审与对抗性复审仍为 BLOCK。主要缺口：用户确认的 plan 与执行 plan 未绑定；session 复用导致 rollback 跨 plan；move 成功到日志落盘之间崩溃；共享 mkdir 无法跨 unit 表达；根模式规则顺序会丢子目录/误判单剧；通用下载目录被当剧名；多分部未归组；no-replace 能力未探测；目录回滚带走新增文件；G6 后 `title_candidates` 仍残留 `E02`。用户选择“完整范围 + unplanned 兜底”。
- **具体内容**:
  - **计划绑定**：apply/rollback 新增必填 `--expect-plan-id`；与 plan/state 不一致返回 `E_EXPECT_PLAN_MISMATCH`；一个 session 最多一个 plan（`E_SESSION_HAS_PLAN`）。
  - **崩溃恢复**：日志改为 intent/done 两阶段；state 增加 `applying`；apply/rollback 启动时对账；rollback 默认从日志派生 unit，不再只信 state。
  - **并发**：apply/rollback 共用 `apply.lock`；同 session 并发 `E_SESSION_BUSY`。
  - **共享 mkdir**：允许跨 unit 重复 mkdir，apply 预检去重；只选 Season 02 时也会创建 Show 父目录；move 仍保持源/目标唯一。
  - **根模式**：重排 4.3.1 规则；单文件父目录已是单电影目录时 unit=父目录；多剧库根按子目录拆分；散落剧集只有唯一剧名才处理；多剧混放/通用下载目录 `unplanned`。
  - **可信剧容器**：通用容器名（Downloads/Movies/TV/剧集等）不作为剧名；否则用 `title_candidates`。
  - **多分部**：v1 标记 `unplanned/unsupported_multipart`，不拆、不猜。
  - **source 覆盖**：`unit.sources[]` 必须覆盖所有 move；移动 show 祖先时 source=祖先目录。
  - **no-replace**：session 目录内做能力探测；失败即拒绝；`link+unlink` 中断清理 dst；intent 先写。
  - **回滚**：目录用 `mtime_ns` 做冲突检查，避免带走执行后新增文件；mkdir 记录 ino；mkdir/remove 幂等补齐。
  - **指纹**：生产验收改为 relpath+size+mtime+ino 元数据指纹，避免全库内容哈希。
  - **G6**：mapping.go 的 `displayTitles`/`stripEpisode` 同步剥离连续 E 段；`defaultVersion` 升到 0.2.1；CI 断言 `--version`。
  - **命名/告警**：`{...}` 只跳过 `{tt...}`/`{tmdb...}`；同路径用 `samefile`/`realpath`；`scan.truncated` 统一命名。
  - 新增附录 C 第二轮映射表（A2-1…A8-2、R1-1…R10-2）。

## [2026-11-12] - 第三轮聚焦复审修订

- **修改类型**: Changed
- **影响范围**: §1.1；§2.1 G2/G3/G4/G6；§4.2–§4.10；§5.1/§5.4；§6.1–§6.3；附录 A–C；`tasks.md`
- **变更原因**: 第三轮独立架构与对抗性复审均 BLOCK。双方一致指出：单文件父目录缺少正面前置校验，会把 `Downloads` 当电影目录整体改名；mkdir/remove/link+unlink 的崩溃对账不完整；plan/session 可被替换/删除/复制；G6 的“连续”未定义为数值连续，且版本变更牵涉 SPEC-002 与 `main_test.go`；`unplanned` 只有计数没有条目契约。用户选择“第三轮修订，保留完整范围”。
- **具体内容**:
  - **单电影目录正面校验**：新增 4.3.1.1；父目录必须满足单一 feature 组、条目可归属、basename 与 title 匹配、非通用容器四条，否则按文件单元处理。修复 `Downloads/Inception.2010.mkv` 被整体改名和 `.iso`/`.part`/隐藏项被拖走的问题。
  - **混合散落根**：4.3.1 新增规则 7；同目录散落电影+剧集按 `library/mixed_loose_files` 拆分，不再落入 `E_AMBIGUOUS_MODE`。
  - **季目录与单集文件**：季标记改为整名匹配；扁平季目录走规则 5；季目录/show 目录内单集文件在名称不规范时 `unplanned/needs_directory_mode`，不越界、不嵌套；show/season 同时改名也走该兜底。
  - **散落剧集分组**：按 `(归一化剧名, 年份)` 分组，所有 `title_candidates[0]` 必须一致；同名不同年份、多剧名/多非零年份 → `unplanned/ambiguous_loose_shows`；通用容器名只作佐证。
  - **崩溃对账**：move/mkdir/remove 都有执行前 intent 快照；link+unlink 中断按“完成移动”处理（`unlink(from)`），不再删除 `to` 后假写 done；apply 启动提升已完整 done 的 applying unit，`--retry-failed` 处理 failed。
  - **plan/session 完整性**：新增 `session_token`、`state_dir`、`applied-plan.json`、`--session-dir`；日志逐行带 token；plan 被替换/删除时可从快照回滚，session 被复制/移动时 `E_SESSION_STATE_MISSING`。
  - **能力探测**：按 `st_dev` 和文件/目录分别在实际目标父目录所在文件系统探测，任一失败零媒体改动。
  - **目录回滚指纹**：目录 move 记录递归 `to_subtree_hash`/`entry_count`；回滚整体预检，新增嵌套文件即 `E_ROLLBACK_CONFLICT`。
  - **G6**：连续多集必须是集号数值连续；`S01E01E03`/`S01E01E02E04` 不匹配；2 段/3 段 `title_candidates` 均为 `["Show"]`；版本链加入 SPEC-002 与 `cmd/mediadetect/main_test.go`。
  - **多分部**：4.4.2 增加 token 表（CD/Disc/Disk、Part/Pt、1of2、上下/前后、字母后缀）；同一 TMDB id/目标/`(title, year)` 的多个 movie 单元全部 unplanned。
  - **unplanned 契约**：plan 新增 `unplanned[]`（path/kind/reason_code/reason）；4.6/5.4 要求逐条展示，不能只给计数。
  - **其他**：`--out` 明确为导出副本；rollback 示例补 `--expect-plan-id`；单元全有或全无；执行前重新枚举只比较归属该 unit 的条目；CJK `title_candidates` 断言修正。
  - 新增附录 C 第三轮映射表（A3-1…A3-15、R11-1…R11-15）。

## [2026-11-12] - 批准

- **修改类型**: Approved
- **影响范围**: SPEC-003 spec/tasks 状态；`docs/specs/README.md`
- **变更原因**: 用户明确批准第三轮修订后的完整范围，进入 T1–T8 实现。
- **具体内容**:
  - SPEC-003 与 `tasks.md` 状态改为 `Approved`。
  - 实现按 T1→T2→T3→T4→T5→T6 推进；T7 开始前按 CLAUDE.md 回退 SPEC-001、SPEC-002 并追加各自 changelog；T8 做集成测试与 CI。

## [2026-11-12] - 实现完成

- **修改类型**: Implemented
- **影响范围**: `skills/media-title/`、`parser/parser.go`、`mapping.go`、`cmd/mediadetect`、CI、README、SPEC-001/002 版本口径
- **变更原因**: 完成 T1–T8，并通过本地 Go/Python 测试与真实 CLI 冒烟。
- **具体内容**:
  - 新增通用 Agent Skill 包：`SKILL.md`、`scan/plan/apply/rollback/fsops/paths/session/naming`、schema、参考文档与 43 个 Python 测试
  - 电影/剧集计划、session 隔离、`--expect-plan-id`、intent/done 日志、no-replace 移动、目录子树指纹、unplanned 报告
  - G6：连续多集数值连续性、`displayTitles` 2/3 段清理、`v0.2.1` 版本口径；SPEC-001/002 已按约定回退、修订、恢复 `Approved`
  - CI 新增 `skills` job，覆盖 Ubuntu/macOS 的 Go 构建、`--version=0.2.1`、Python 编译与测试
  - 验证：`go test ./...`、`go vet ./...`、`gofmt`、`go mod tidy -diff`、Python 43 tests、真实 CLI scan→plan→apply→rollback 冒烟均通过

## [2026-11-12] - 独立验收修复

- **修改类型**: Fixed
- **影响范围**: `skills/media-title/scripts/media_title_lib/{scan,plan,apply,rollback,paths}.py`、`assets/plan.schema.json`、`tests/test_regressions.py`
- **变更原因**: 三路独立验收（规范符合性、对抗性安全、实现正确性）均返回 BLOCK，确认默认电影目录嵌套、目录扫描绕过非连续多集、兄弟剧集误判为新增、重复 move 目标导致部分执行，以及崩溃恢复后的目录回滚缺少子树指纹等 BLOCKER/HIGH 问题。
- **具体内容**:
  - 电影目录输入按用户 `--match` 重新检测；正面校验拒绝 `local` best 与未知扩展名；文件单元父目录已是目标名时跳过，避免 `Inception (2010)/Inception (2010)/` 嵌套。
  - 非连续多集防御前移到目录、库根、散落文件与电影分组入口；混合库根中的散落剧集按 `(title, year)` 成组，不再生成多个同目标单元。
  - 计划记录 `sibling_snapshot`；apply 只把计划后新增的兄弟文件视为变化，预先存在的兄弟集不再误报。
  - plan 对全部 `move.to` 做 NFC/大小写/realpath 去重，冲突单元整体 `unplanned/duplicate_target`；precheck 同样检查 op 级重复目标。
  - `--retry-failed` 按 apply log 的 done key 跳过已完成操作，只执行未完成操作；precheck 在重试时允许本单元已创建的目标目录。
  - move intent 记录 `from_subtree_hash`/`entry_count`；reconcile 校验目标 inode 并补写子树指纹，崩溃后的目录回滚仍会拒绝执行后新增文件。
  - rollback 以非严格模式对账未决 intent，不再因单个冲突阻塞已应用单元回滚；所有日志路径校验在 `root` 内；部分回滚后按日志派生单元统一标记 `rolled_back`。
  - `--match` 全链路透传；`--keep-empty-source` 生效；`scan.truncated` 拒绝出计划；`/tmp`、`/var`、`/etc` 按 realpath 识别为保护根；`Season 00` 不再并入第一季。
  - 库根扁平季目录改用 `title_candidates` 作为剧名；show/season 子目录单元补齐 `season` 上下文；show 与 season 同时需要改名时统一 `unplanned/needs_directory_mode`；show 目录含 `poster.jpg` 时不再被误判为不可信容器。
  - 新增 `test_regressions.py` 回归测试；Python 测试从 43 增至 60。

## [2026-11-12] - 独立复验修复（第二轮）

- **修改类型**: Fixed
- **影响范围**: `scan.py`、`plan.py`、`apply.py`、`rollback.py`、`paths.py`、`test_regressions.py`
- **变更原因**: 第一轮修复后的三路独立复验仍为 BLOCK。确认：同剧多个扁平季目录共享 show 根被 precheck 误判重复目标；多松散电影在 `--match=on` 下仍使用 off 结果；`Subs/`/`Extras/` 电影目录被误判 library；扁平季目录 poster 导致整单元 ambiguous；非连续多集文件会连带丢弃同目录合法单元并触发 TMDB；generic 容器下 `S1` 被当作剧名；多季侧车字幕归错季；reconcile 越界 unlink；rollback 自身日志未对账；movie_collection 目标嵌套；剧名未剥离清晰度/方括号；隐藏项未跳过。
- **具体内容**:
  - precheck 的 unit 级目标唯一性只约束 movie；TV 单元允许共享 show 根，op 级 move 目标仍全局唯一。
  - 多松散电影/混合松散根改为按安全文件逐个 `--match=<用户值>` 检测；目录含非连续多集文件时绝不把整目录送 TMDB。
  - MediaDetect 退出码 4（`--match=on` 基础设施失败）仍读取完整本地 JSON，按 `no_tmdb` 降级，不丢弃文件列表。
  - `Subs/`/`Extras/` 等电影级子目录不再触发 library 判定；`_auto_dir` 只在存在非电影级子目录时拆分。
  - 扁平季/散落剧集只用 `media_type=tv_episode` 文件派生剧名与来源，poster/NFO/readme 留在原处，不再触发 `ambiguous_loose_shows`。
  - 非连续多集文件只标记自身 unplanned，同目录安全文件继续生成单元；所有 auto 检测前先排除 unsafe 文件。
  - generic 容器下的季子目录先做可信容器校验，失败 `ambiguous_season_parent`。
  - 侧车字幕按所属视频继承 season/episode/range；多季扁平目录不再把 S00 字幕放入 Season 01。
  - `reconcile` 接收 root，在任何 unlink/补写 done 前校验 from/to；rollback 启动时对 `rollback.log.jsonl` 做非严格对账，link+unlink 中断后二次 rollback 幂等。
  - apply 使用非严格 reconcile：未决 intent 只阻断对应选中单元，`--retry-failed` 可继续执行无关单元；rollback 引入 `rolling_back` 状态。
  - mkdir 对账按 `pre_exists` 记录 `created=true`，满足 Spec 4.8 验收表。
  - movie 文件单元目标父目录改用 `unit.root`，合集子目录中的电影不再嵌套。
  - 剧名清洗剥离清晰度/来源/发布组/方括号与年份；容器名与唯一候选剧名不一致时改用 `title_candidates[0]` 并记录 `container_name_ignored`；`1923` 这类纯年份标题不再重复追加年份。
  - 扫描与季目录枚举跳过隐藏项；辅助/系统直接文件记录 `skipped/auxiliary`，不再进入 unplanned。
  - 保护根补充 `/System`、`/Library`、`/Applications`、`/usr`、`/bin`、`/sbin`、`/opt`、`/dev`、`/proc`；rollback 同样拒绝保护根。
  - rollback `--select` 的 created/allowed 集合只从选中单元派生；共享父目录仍含未选单元内容时在预检阶段整体拒绝、零改动，全量 `rollback all` 可完整恢复。
  - Python 测试从 60 增至 70，新增合集目标、剧名清洗、隐藏项、侧车季号、共享 show、rollback 日志对账、无关 unit retry、越界 unlink、mkdir created、`--match=on` 等回归。

## [2026-11-12] - 独立验收修复（第三轮）

- **修改类型**: Fixed
- **影响范围**: `scan.py`、`plan.py`、`apply.py`、`rollback.py`、`test_regressions.py`、本 changelog
- **变更原因**: 第三轮三路验收仍为 BLOCK，指出 reconcile 可删除唯一副本、rollback 日志未校验、共享父目录部分回滚部分执行、非通用名混合库根 `E_STATE_DIR_INSIDE_UNIT`、`Extras/` 视频生成嵌套目标、计划后新增同组电影视频未拦截、无季子目录剧名不一致被 unplanned。
- **具体内容**:
  - reconcile 仅在 `from`/`to` 为不同路径且目标 inode 与 intent 一致时才按 link+unlink 完成移动；同一路径或身份不明一律冲突，绝不 unlink。precheck 对任何已存在的 move 目标返回 `E_TARGET_EXISTS`。
  - rollback.log 逐条校验 `session_id`/`session_token`/`plan_id`/`state_dir`；外来或复制日志返回 `E_SESSION_STATE_MISSING`。
  - `rollback --select` 的 removable 集合只来自选中单元；共享 created 父目录仍含未选内容时在预检阶段整体拒绝，零改动。
  - apply 在加锁与 reconcile 之前检查保护根。
  - 非通用名混合库根的散落剧集不再把扫描根本身设为 `source_root`，避免 session 状态目录落在 unit source 内。
  - `Extras/`/`Featurettes/`/`Trailers/` 等电影级子目录下的视频不再单独成 movie unit；单电影目录正面校验与 movie 分组均排除这些子树，目录整体改名不会把 featurette 当第二部电影。
  - 计划后新增同组电影视频（如 `Inception.2010.2160p.mkv`）按 title/original_title/源文件名归一化匹配，返回 `E_SOURCE_STATE_MISMATCH`。
  - 无季子目录的非通用 show 目录在唯一候选剧名一致时使用 `title_candidates[0]`，记录 `container_name_ignored`，不再直接 unplanned。
  - precheck 增加跨单元 source/target 祖先-后代检查：目录 move 目标下再有其他单元的 mkdir/move 时返回 `E_TARGET_IN_SOURCE`，零改动；仅共享 mkdir 重叠允许。
  - multipart 过滤前移到任何 TMDB 调用与目录单元判定之前；目录级电影单元、`--mode single`、散落文件与子目录 movie 均先标记 `unsupported_multipart`。
  - Python 测试从 70 增至 80。

## [2026-11-12] - SMB check-then-rename 降级需求（In Review）

- **修改类型**: Changed
- **影响范围**: §1.3；§2.1（新增 G7）；§4.2 apply/rollback 选项；§4.7.1；§4.7.2；新增 §4.7.4；§4.8；§4.11；§6.1；附录 A/B；`tasks.md`（T9）；`docs/specs/README.md`
- **变更原因**: macOS 媒体库常放在 SMB 共享上；smbfs 上 `renamex_np(RENAME_EXCL)` 返回 ENOTSUP/EINVAL，`os.link` 不可用，导致 `probe_no_replace` 在预检阶段整体拒绝，一个文件都无法移动。用户要求提供显式 opt-in 的非原子降级路径，默认行为不变。
- **具体内容**:
  - 新增 G7 与 T9：能力分级探测 `renameat2`/`renamex_np` → `link+unlink`（仅文件）→ check-then-rename。
  - `apply`/`rollback` 新增 `--no-replace strict|check`，默认 `strict`；`MEDIA_TITLE_ALLOW_CHECK_RENAME=1` 等价于 `check`，CLI 优先；不得按文件系统类型自动开启。
  - `check` 模式：rename 前 `lexists(dst)`，存在即 `E_TARGET_EXISTS`；移动后文件校验 `size`/`mtime_ns`，目录校验 `mtime_ns` + 可移植子树指纹（不含 `dev/ino`）；失败保留现场并记录 `E_NON_ATOMIC_MOVE_FAILED`。
  - intent/done 日志新增 `move_method`/`atomic`/`validation`；apply/rollback 结果与人类输出新增 `warning: non_atomic_move`。
  - rollback 对含 `check_then_rename` 的日志必须显式 opt-in，否则 `E_NO_REPLACE_UNSUPPORTED`、零改动；反向移动沿用可移植指纹，二次回滚幂等。
  - `SKILL.md` 安全条款、4.11、附录 B 明确写出检查与 rename 之间的竞态风险；默认 strict 行为保持不变。
  - 测试新增 mock：`renamex_np`/`renameat2` 返回 ENOTSUP/EINVAL、`os.link` 抛 EPERM；默认拒绝、显式开启成功、目标存在不覆盖、size/mtime/指纹失败、rollback opt-in。
  - 状态按 CLAUDE.md 回退为 `In Review`，等待用户批准后再实现；回退期间不改生产代码。

## [2026-11-12] - 批准 G7/T9

- **修改类型**: Approved
- **影响范围**: SPEC-003 spec/tasks 状态；`docs/specs/README.md`
- **变更原因**: 用户明确批准 SMB check-then-rename 降级需求。
- **具体内容**:
  - SPEC-003 与 `tasks.md` 恢复为 `Approved`；新增 G7/T9 进入实现。
  - 实现 T9：能力分级探测、`--no-replace strict|check`、`MEDIA_TITLE_ALLOW_CHECK_RENAME=1`、check-then-rename、日志/告警、rollback 可移植指纹与 mock 测试。

## [2026-11-12] - T9 实现完成

- **修改类型**: Implemented
- **影响范围**: `skills/media-title/scripts/media_title_lib/{fsops,paths,apply,rollback}.py`、`scripts/media_title.py`、`SKILL.md`、`tests/test_fsops.py`、`tests/test_regressions.py`
- **变更原因**: 完成 G7/T9，使 SMB/NFS 用户可显式选择非原子 check-then-rename，默认 strict 行为不变。
- **具体内容**:
  - `fsops.safe_move` 返回 `method`/`atomic`/`validation`；能力探测返回 `native`/`link_unlink`/`check_then_rename`。
  - `check` 模式：`lexists` 检查后普通 `rename`；文件校验 `size`/`mtime_ns`，目录校验顶层 `mtime_ns` + 可移植子树指纹（不含 `dev/ino`）；失败尝试恢复源并报 `E_NON_ATOMIC_MOVE_FAILED`。
  - apply/rollback 新增 `--no-replace strict|check` 与 `MEDIA_TITLE_ALLOW_CHECK_RENAME=1`，CLI 优先；结果与人类输出含 `non_atomic_move` warning。
  - apply.log/rollback.log 的 move intent/done 记录 `move_method`/`atomic`/`validation`；rollback 对 check 日志未 opt-in 时零改动拒绝。
  - `SKILL.md` 安全条款与调用示例更新，明确禁止智能体自行启用。
  - Python 测试从 80 增至 89，覆盖 ENOTSUP/EPERM mock、默认拒绝、显式成功、不覆盖、目录 check、探测、校验失败恢复、rollback opt-in 与 CLI/env 优先级。

## [2026-11-12] - 分卷误判修复与 Part N 策略（In Review）

- **修改类型**: Changed
- **影响范围**: §2.1 G2；§4.4.2（分卷 token 表与新增 4.4.2.1）；§4.9；§6.1；附录 A/B；`tasks.md`（T10）；`docs/specs/README.md`
- **变更原因**: `MULTIPART_RES[4]` 将普通标题中的冠词/介词 `A`/`B` 当作字母分卷；`MULTIPART_RES[1]` 将发行组 `PTH` 拆成 `pt`+`h`；`後編` 等续集标题被误判。另有 `Part N` 既可能是真拆盘，也可能是独立电影，需要产品决策。
- **具体内容**:
  - 字母后缀只匹配文件名主干（去掉扩展名和发布标签后）末尾的 `A`/`B`；`A.City.of.Sadness`、`B.for.Busy`、`Story.of.a.Murderer` 不再命中。
  - `part/pt` 后必须跟分隔符或数字；`PTH`/`PTer` 不再命中；`Part.1`/`Part1`/`pt2` 保持命中。
  - `前編/後編` 不加入硬分卷词，`3月のライオン.後編` 按普通电影处理。
  - 新增 4.4.2.1：`Part N`（数字）作为候选，不立即 unplanned；必须使用真实 TMDB best（非 local），且 `title`/`original_title` 归一化后包含对应 `part N`，才按独立电影处理；否则保持 `unplanned/unsupported_multipart`。
  - 单文件、目录、movie 分组使用同一判定；`--match=off`、`disabled`、`unavailable`、`error` 或本地 best 时 Part N 仍 unplanned。
  - 硬分卷（CD/Disc/Disk、1of2、上下/前后、Part.A/B、主干末尾 A/B）保持拒绝；Part N 例外不影响同一 TMDB id/目标冲突的计划级 unplanned。
  - 状态按 CLAUDE.md 回退为 `In Review`，等待用户批准 T10 后再改生产代码。

## [2026-11-12] - 批准 T10

- **修改类型**: Approved
- **影响范围**: SPEC-003 spec/tasks 状态；`docs/specs/README.md`
- **变更原因**: 用户批准分卷误判修复与 Part N TMDB 判定策略。
- **具体内容**:
  - SPEC-003 与 `tasks.md` 恢复为 `Approved`；T10 进入实现。
  - 实现 A/B 主干末尾匹配、`Part/Pt` 分隔符约束、`PTH`/`後編` 假阳性修复，以及 Part N 的真实 TMDB 标题证明与统一扫描判定。

## [2026-11-12] - T10 实现完成

- **修改类型**: Implemented
- **影响范围**: `skills/media-title/scripts/media_title_lib/{paths,scan}.py`、`tests/test_paths.py`、`tests/test_regressions.py`
- **变更原因**: 完成分卷误判修复与 Part N 独立电影判定。
- **具体内容**:
  - `MULTIPART_RES` 拆分为硬分卷规则与 `MULTIPART_PART_RE`；A/B 只在去掉扩展名/发布标签后的主干末尾命中。
  - `Part/Pt` 后必须有分隔符或数字，`PTH`/`PTer` 不再命中；`Part.1`/`Part1`/`pt2` 仍识别为候选。
  - `前編/後編` 不加入硬分卷；`3月のライオン.後編` 走普通电影路径。
  - 新增 `part_movie_number`/`part_title_matches`：Part N 必须有真实非 local TMDB best，且 title/original_title 包含对应 `part N`。
  - 单文件、目录单元、movie 分组统一使用同一判定；`--match=off`/local best 下 Part N 仍 `unsupported_multipart`。
  - 硬分卷（CD/Disc/Disk、1of2、上下/前后、Part.A/B、主干末尾 A/B）保持拒绝。
  - Python 测试从 89 增至 92；真实离线扫描 9 个误报文件名得到 9 个 unit，0 个 `unsupported_multipart`。

## [2026-11-12] - 匹配 warning 透传与 SMB 指引（In Review）

- **修改类型**: Changed
- **影响范围**: §2.1（新增 G9）；§4.3.6；§4.7.2；`tasks.md`（T12）；`docs/specs/README.md`
- **变更原因**: 负样本报告指出高置信度误匹配没有任何 warning 可见；SMB 用户在 `E_NO_REPLACE_UNSUPPORTED` 时缺少明确的 `--no-replace=check` 指引。
- **具体内容**:
  - scan/plan 必须透传 MediaDetect 的 `warnings[]`，尤其是 `match.year_conflict`、`match.ambiguous_title`，按 `(code, detail, file)` 去重并在人类输出显示。
  - `E_NO_REPLACE_UNSUPPORTED` message 增加 SMB/NFS 指引：用户确认后可在 apply 与 rollback 同时使用 `--no-replace=check` 或 `MEDIA_TITLE_ALLOW_CHECK_RENAME=1`；不得自动启用。
  - 不新增平台探测或网络请求。
  - 状态按 CLAUDE.md 回退为 `In Review`，等待用户批准 T12 后再改生产代码。

## [2026-11-12] - T12/T13 评审修订

- **修改类型**: Changed
- **影响范围**: §2.1 G9/G10；§4.3.6；§4.7.2；§4.7.4；`tasks.md` T12/T13
- **变更原因**: 三路评审与 NG 报告确认：A2 是 plan 层把文件级 low 提升为 high；短别名 warning 不够；低分单元仍 planned；SMB check 模式因 mtime 改写全部失败。T12 只做提示/SMB 指引不足以修复。
- **具体内容**:
  - G9 扩展为端到端门控：scan 保存 status/margin/score/title_hit；plan 取较低 status，绝不按 score 提升；low/unmatched/score<0.6/title_hit=false → `unplanned/low_confidence`；disabled/unavailable 本地命名例外；medium+title_hit=true 可 planned 但显示 warning。
  - warning 统一为 `{code,detail,file}` 对象；plan 汇总并 human 输出；本轮只透传 `match.year_conflict`。
  - `E_NO_REPLACE_UNSUPPORTED` 提示保留；SMB 实际可用性由 G10/T13 修复。
  - 新增 G10/T13：check-then-rename 先按 size/内容指纹（不含 mtime）校验；utime 恢复 mtime；失败但内容一致 → `size_content` + `mtime_rewritten`，rollback 同策略。
  - 收缩范围：超集/续集/短别名、B1/B2、u68/R3-u44 等残余风险写入已知限制。
  - 状态保持 `In Review`，等待用户批准后再实现。

## [2026-11-12] - T12/T13 实现完成

- **修改类型**: Implemented
- **影响范围**: `skills/media-title/scripts/media_title_lib/{scan,plan,fsops,apply,rollback}.py`、`media_title.py`、tests
- **变更原因**: 落地端到端置信度门控与 SMB mtime 兼容。
- **具体内容**:
  - scan/plan 继承文件级 match status/margin/score/title_hit；low/unmatched/score<0.6/title_hit=false → `unplanned/low_confidence`；disabled/unavailable 例外；medium+title_hit=true 可 planned。
  - `match.year_conflict` 以 `{code,detail,file}` 进入 scan/plan/human；现有字符串 warning 统一为对象。
  - `E_NO_REPLACE_UNSUPPORTED` 消息包含 `--no-replace=check`/环境变量提示。
  - check-then-rename 先按 size/内容指纹（不含 mtime）校验；utime 恢复 mtime；失败 `size_content` + `mtime_rewritten`；rollback 同策略并恢复 from_state mtime。
  - Python 测试 101 项通过；Go 测试全绿。

## [2026-11-12] - scan 跳过已整理条目（In Review）

- **修改类型**: Changed
- **影响范围**: §2.1（新增 G8）；§4.2 通用选项；§4.3.5.1；§5.1/§5.2；§6.1；`tasks.md`（T11）；`docs/specs/README.md`
- **变更原因**: 媒体库根扫描会对所有条目调用 MediaDetect（含 TMDB），名称已带 `{tt...}`/`{tmdb...}` 的已整理条目白跑检测，105 个已整理目录 + 21 个待处理文件耗时超过 8 分钟。
- **具体内容**:
  - scan 遍历在进入目录/文件、调用 MediaDetect 前，用共享正则 `\{(?:tt\d+|tmdb\d+)\}`（大小写不敏感）识别已整理条目；命中写 `skipped/already_organized`，不产生 unit/unplanned，不递归子项。
  - 默认开启；新增 `--include-organized` 强制重新检测，恢复旧行为。目录、文件、输入根本身均适用。
  - 只看名称，不校验内容或 TMDB ID；其他花括号内容不命中。plan 阶段的已整理判断保留为第二道防线，两处共享正则/辅助函数。
  - `skipped[]` 只列顶层命中路径，不展开 season/sidecar；扫描仍按原 root 创建 session，媒体文件零改动。
  - 验收：MediaDetect 调用次数不随已整理目录数量增长；`--include-organized` 后行为与旧版一致；recording FakeRunner 断言 0 次调用。
  - 状态按 CLAUDE.md 回退为 `In Review`，等待用户批准 T11 后再改生产代码。

## [2026-11-12] - 批准 T11

- **修改类型**: Approved
- **影响范围**: SPEC-003 spec/tasks 状态；`docs/specs/README.md`
- **变更原因**: 用户批准 scan 阶段跳过已整理条目。
- **具体内容**:
  - SPEC-003 与 `tasks.md` 恢复为 `Approved`；T11 进入实现。
  - 实现共享已整理正则、scan 提前短路、`--include-organized`、`skipped/already_organized` 与 recording FakeRunner 测试。

## [2026-11-12] - T11 实现完成

- **修改类型**: Implemented
- **影响范围**: `skills/media-title/scripts/media_title_lib/{paths,plan,scan}.py`、`scripts/media_title.py`、`tests/test_scan.py`
- **变更原因**: 完成 scan 阶段已整理条目短路，避免无效 MediaDetect/TMDB 调用。
- **具体内容**:
  - `paths.py` 新增共享 `ORGANIZED_ID_RE`/`is_organized_name`；plan 的 `_already_organized_movie` 改为复用。
  - scan 对输入路径本身、库根直接子项、目录与文件统一提前短路；命中写 `skipped/already_organized`，不调用 MediaDetect、不递归、不产生 unit/unplanned。
  - `--include-organized` 关闭短路并恢复检测；`scan` 选项与 JSON `options` 记录该值。
  - 过滤 MediaDetect 返回的文件列表，避免已整理子目录内的文件在后续 movie 分组中重新生成 unit。
  - 人类输出逐条打印 `skipped[]`。
  - Python 测试从 92 增至 96；真实 CLI：10 个已整理目录 + 1 个待处理文件仅 1 次根检测、0 次 tagged 路径调用、10 条 skipped、1 个 unit。

## [2026-11-14] - 提交前验收修复

- **修改类型**: Fixed
- **影响范围**: `skills/media-title/scripts/media_title_lib/{scan,paths,fsops}.py`, tests
- **变更原因**: 提交前独立验收发现 T10/T11/T13 的回归缺口。
- **具体内容**:
  - `--mode single` 扫描目录时，已整理文件（含 `--match=off`）不再生成 unit 或 move，写 `skipped/already_organized`；直接文件输入也会识别已整理祖先。
  - 分卷 A/B 支持 `Movie-A`/`Movie-B` 连字符形式；补 `1-2`/`2-2` 分数式硬分卷，`2020-2021` 不误判。
  - `E_NO_REPLACE_UNSUPPORTED` 同时提示 `--no-replace=check` 与 `MEDIA_TITLE_ALLOW_CHECK_RENAME=1`。
