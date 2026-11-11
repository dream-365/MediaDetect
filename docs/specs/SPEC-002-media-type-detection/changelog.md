---
type: changelog
status: Draft
owner: alang
depends_on: []
updated_at: 2026-11-11
---

# Changelog: SPEC-002 MediaDetect 媒体检测独立模块与 CLI

## [2026-11-11] - 初始起草

- **修改类型**: Added
- **影响范围**: 全文
- **变更原因**: 维护者要求把媒体类型判断从 mstruct 扫描链路中分离出来，形成可独立使用的检测 CLI，同时保留被系统集成的模块边界
- **具体内容**: 定义文件/目录输入、单对象 JSON 契约、电影/剧集/季/系列/合集/混合/非影视/附属/未知类型词表；确定“文件名与结构优先，证据不足时自动 ffprobe 探测”的策略；补充性能、只读、确定性、无网络、回滚和替代方案（该初始草案已被 2026-11-11 的后续条目取代）

## [2026-11-11] - 范围修正为抽取现有检测链路

- **修改类型**: Changed
- **影响范围**: 标题、1.1–1.4、2.1 G1–G5、2.2 NG1–NG10、3.1–3.4、4.1–4.6、5.1–5.5、6.1–6.4、7.1–7.5、附录 A
- **变更原因**: 维护者澄清工具是“把之前已经做的工作独立出来，不要重新做”“完全无状态”，并且探测需要拿到现有链路可返回的 IMDb 数据；早期草案重新设计了本地类型规则，属于重复造轮子
- **具体内容**: 方案改为复用 `internal/parser`、`internal/probe`、`internal/matcher`、`internal/tmdb`、`internal/llm`；从 `internal/scanner.Scan` 抽出只读收集逻辑；工具不建索引、不写 SQLite/缓存/临时文件；电影复用现有 matcher 并补齐 `imdb_id`，剧集只做本地 type 映射且 `match.status=not_applicable`；明确 IMDb 数据边界为 TMDB 条目字段 + `imdb_id`，全量 IMDb 数据集和 TMDB 剧集匹配 Deferred；新增 `--match=auto|on|off`、降级与 key 脱敏契约；删除自建类型规则和离线探测器方案

## [2026-11-11] - 尝试只抽取 probe 探测块（已被下一版取代）

- **修改类型**: Changed
- **影响范围**: 1.1–1.4、2.1 G2/G6、2.2 NG11、3.1–3.4、4.2、4.4.1、4.5.4、5.1、5.5、6.2、6.3、7.5、附录 A
- **变更原因**: 维护者要求“把这个 probe 块做成独立的模块”；当时理解为只抽 ffprobe/exiftool 封装
- **具体内容**: 规划独立 `probe/` Go module、`internal/probe` 薄包装和 `internal/collect`；该版只把底层探测独立，未满足“detect 整体独立”的目标，已被下一版取代

## [2026-11-11] - detect 独立成 module，工具更名为 MediaDetect

- **修改类型**: Changed
- **影响范围**: 标题、1.1–1.4、2.1 G1–G6、2.2 NG1–NG12、3.1–3.4、4.1–4.6、5.1–5.5、6.1–6.4、7.1–7.6、附录 A；SPEC 目录名
- **变更原因**: 维护者澄清独立对象是 detect 功能，不是只抽 ffprobe 探测块；同时 `mprobe` 与 `ffprobe` 名称相近，最终确定工具名为 **MediaDetect**
- **具体内容**: 新建独立 Go module `github.com/dream-365/mediadetect`（目录 `mediadetect/`），把 `parser`、`probe`、`tmdb`、`matcher`、`llm` 的实现和测试整体迁入，并从 `scanner.Scan` 抽出 `collect`；根包 `mediadetect` 提供 `Detect`，`cmd/mediadetect` 提供无状态 CLI；根 `go.mod` 增加 `require` + `replace github.com/dream-365/mediadetect => ./mediadetect`；mstruct 的 `internal/parser`、`internal/probe`、`internal/tmdb`、`internal/matcher`、`internal/llm` 改为薄包装，`internal/scanner` 使用模块 `collect`，store/query/auditor/media/workspace 留在 mstruct；工具/包/CLI 命名为 `mediadetect`，产品名为 `MediaDetect`；Spec 目录改为 `SPEC-002-media-type-detection`；新增模块独立性与 mstruct 集成的验收目标

## [2026-11-11] - 按架构/对抗性评审修订契约与验收

- **修改类型**: Changed
- **影响范围**: 1.3–1.4、2.1 G3–G6、2.2 NG3/NG13、3.2–3.4、4.2–4.6、5.1–5.2、5.4、6.1–6.4、7.6–7.7、附录 A–B
- **变更原因**: 独立架构评审与对抗性评审发现 G4 95% 在引用数据上不可达、`collect` 契约缺失、`MaxDepth`/`MaxFiles` 零值二义、`match.status` 无优先级、输入符号链接/不可读根未处理、parser 映射与声明不一致等问题
- **具体内容**: G4 的 high+medium 从 95% 调整为 90%（文件级 225 文件，保留 92.0% 校准基线说明）；接受 parser 四项最小修正（辅助类型优先、`sample`/`oad` 词边界、`ova` 误报、`1x01`/`S01.E01`）；补齐 `collect` 契约（`CollectedFile`/`Seen`/`Counts`/`Prober`/root 不可读）；`MaxDepth`/`MaxFiles` 改为 `*int`；重写目录聚合与 match 状态优先级；输入改用 `lstat`、拒绝输入符号链接、增加根可读性预检；类型别名/测试/testdata 迁移；TMDB 重试与 probe 预算对齐；匹配后按 `movie_id` union；全路径脱敏；错误 JSON 与数组 null 规则；LLM 缺 key 降级为 warning；增加 `--tmdb-base-url`、`--help` 例外、flags 混排；补充 G6 可执行基线、附录 B 已知限制

## [2026-11-11] - 批准并实施

- **修改类型**: Added
- **影响范围**: frontmatter 状态；`tasks.md`；`mediadetect/` 独立 module；root `internal/*` 薄包装；`internal/scanner`；CLI
- **变更原因**: 影库维护者批准修订后的 Spec，进入实施阶段
- **具体内容**: 状态 `In Review` → `Approved`；新增 `tasks.md`；建立独立模块 `github.com/dream-365/mediadetect`（parser/probe/tmdb/matcher/llm/collect/根包/`cmd/mediadetect`）；root `internal/*` 改为 `=` 类型别名；`internal/scanner` 改用 `mediadetect/collect`；parser 四项修正在 SPEC-001 changelog 单独记录

## [2026-11-11] - 对抗性评审修复

- **修改类型**: Fixed
- **影响范围**: `mediadetect/collect`、`mediadetect/probe`、`mediadetect/parser`、`mediadetect/mapping`、`mediadetect/aggregate`、`mediadetect/match`、`mediadetect/detect`、`mediadetect/tmdb`、`mediadetect/cmd/mediadetect`、`internal/scanner`、`internal/store`、`internal/tmdb`、测试与质量报告
- **变更原因**: 三路独立只读评审发现 1 条 P1、3 条 P2 和若干 P3 契约偏差
- **具体内容**: root 级 WalkDir 错误返回失败而不是空目录；scanner 在存在不可读项时跳过 MarkMissing；store 对未变化但已标 missing 的文件恢复 active；展示层剥离 `S01.E01`/`1x01`/CJK 集号；`tv_season` 用目录季号补齐 `summary.seasons`；probe 使用 WalkDir 原始路径以兼容 NFD；`probe.unavailable` 仅在两个工具都不可执行时产生；`--verbose` 输出 best；`evidence` 分数三位小数；仅在真正发起 TMDB 请求时输出 attribution；`--pretty` 作用于错误与 version；收紧 `1x01` 误报；NUL 路径返回 `ERR_INPUT_INVALID`；探测后检查取消；mstruct 的 TMDB wrapper 保持 20s 单请求超时；README 说明外部 `go install` 限制。Spec 正文与状态不变。

## [2026-11-11] - 回退 In Review 处理评审遗留项

- **修改类型**: Changed
- **影响范围**: frontmatter 状态；2.1 G3；3.2；4.3.2；4.5.1.1；4.5.2；附录 B
- **变更原因**: 对抗性评审遗留三项：全角斜杠标题搜索失败、union 到同一 TMDB ID 的顶层状态与 spec 措辞冲突、顶层 `error` 的省略/null 规则自相矛盾；维护者确认处理方向
- **具体内容**: 状态 `Approved` → `In Review`；新增 parser 第五项最小修正：`clean` 保留 `/`，`示例片1／2` 的标题候选变为 `示例片1/2`；matcher 的 `normalizeTitle` 先做 NFKC，把 TMDB 的 `½` 与文件名的 `1/2` 统一后再评分；G3 与 4.5.1.1 的修正清单从四项扩为五项；4.5.2 规则 6 明确“union 后 `distinct_movies>1` 才 `multiple`”；4.3.2 序列化规则明确顶层 `error` 仅 `ok=false` 时出现；附录 B 记录导演剪辑版年份差异与低 margin 两项既有 matcher 行为

## [2026-11-11] - 评审遗留项修订确认

- **修改类型**: Changed
- **影响范围**: frontmatter 状态
- **变更原因**: 维护者确认按“修复 parser 全角斜杠、保留 matcher 既有行为、按代码语义修订 spec”处理
- **具体内容**: 状态 `In Review` → `Approved`；随后实施 parser 第五项修正、matcher 的 Unicode 分数归一化，并更新校准报告与测试

## [2026-11-11] - 拆仓为独立公开项目

- **修改类型**: Changed
- **影响范围**: frontmatter 状态；1.3；2.1 G2/G6；2.2 NG12；3.1–3.2；3.4；4.2 模块边界；4.4.1；4.4.4；5.5；6.1–6.5；7.2；附录 A
- **变更原因**: 维护者要求把 MediaDetect 迁移为独立公开新项目；仓库名与 Go module path 使用 `MediaDetect`，CLI 命令保持小写 `mediadetect`，License 使用 MIT；并要求 SPEC 与质量报告随项目配套迁移
- **具体内容**: 新建公开仓库 `github.com/dream-365/MediaDetect`，module path 与仓库路径一致（含大写），`mediadetect/` 代码整体平移；mstruct 根 `go.mod` 去掉 `v0.0.0` + `replace`，改为 `require github.com/dream-365/MediaDetect v0.1.0`；`internal/*` 与 `internal/scanner` 的 import 同步改写；SPEC-002 的 `spec.md`/`tasks.md`/`changelog.md` 与 `docs/quality/SPEC-002/` 迁入新仓库同名目录并成为唯一事实源，mstruct 仅保留指针；新增 6.5 拆仓发布方案、跨仓 `go.work` 联调、tag 顺序、回滚与 SPEC 迁移验收；状态 `Approved` → `In Review`

## [2026-11-11] - 按三路独立评审修订拆仓方案

- **修改类型**: Changed
- **影响范围**: frontmatter `depends_on`；关联资源；3.1–3.2；4.2；4.4.4；5.5；6.1–6.5；7.2；tasks.md（T1–T11）；docs/specs/README.md；根 README 的 SPEC 状态
- **变更原因**: 架构评审、对抗性发布评审与 SPEC 一致性评审发现：真实影库语料与绝对路径会随公开仓库/module zip 永久泄露；`v0.1.0` 在 mstruct 联调前发布且 tag 未禁止移动；T1–T10 与 T11 顺序矛盾；T11 验收缺 LICENSE/CI/README/go.sum/脱敏/删除门禁；GOPROXY 转义示例错误；`go.work` 会掩盖真实依赖；G6 与已接受的 scanner 行为变更冲突
- **具体内容**: 新增公开内容脱敏与历史审计闸门（真实片名、绝对路径、逐文件 TMDB/IMDb 映射不得进入公开仓库；不使用含敏感历史的首个 commit）；发布顺序改为“候选 SHA → mstruct 联调 → CI 全绿 → 打 v0.1.0 → 切换依赖”，已推送 tag 永不移动；T1–T10 恢复为嵌套 module 历史任务，T11 统一拆仓并补齐交付物与 `GOWORK=off` 验收；转义修正为 `!media!detect`；G6 补充不可读项跳过 `MarkMissing` 与 missing→active 两项已接受行为变更；SPEC 去除对 mstruct 私有文档的依赖；6.4 回滚区分拆仓前后；指针改为 4 列表格；状态保持 `In Review`

## [2026-11-11] - 批准拆仓方案并进入实施

- **修改类型**: Changed
- **影响范围**: frontmatter 状态；T11 实施
- **变更原因**: 维护者明确批准修订后的拆仓方案，并要求提交文档、开始实施
- **具体内容**: 状态 `In Review` → `Approved`；按 6.5 执行顺序启动 T11：脱敏 fixture 与 quality 报告、建立 private 仓库 `dream-365/MediaDetect`、改写 module path 与内部 import、补齐 README/LICENSE/CI/.gitignore、预发布联调通过后再打 `v0.1.0`

## [2026-11-11] - 从 MStruct 迁入独立仓库

- **修改类型**: Added
- **影响范围**: 代码（parser/probe/tmdb/matcher/llm/collect/根包/cmd/mediadetect）；go.mod/go.sum；README/LICENSE/CI/.gitignore；SPEC-002 三件套；docs/quality/SPEC-002/ 脱敏版
- **变更原因**: 按 6.5 把 MediaDetect 拆为独立公开仓库 `github.com/dream-365/MediaDetect`，并配套迁移 SPEC 与质量产物
- **具体内容**: module path 与全部内部 import 改为 `github.com/dream-365/MediaDetect`；`parser/testdata/filenames.txt` 替换为 231 条合成/匿名 fixture；真实片名、绝对路径和逐文件 TMDB/IMDb 映射从公开文档移除，原始报告保留在 MStruct 私有仓库；`MSTRUCT_CALIBRATE` 改为 `MEDIADETECT_CALIBRATE`；新增 MIT LICENSE、macOS + Linux CI 与 .gitignore；本目录成为 SPEC-002 的唯一事实源，mstruct 仅保留指针
