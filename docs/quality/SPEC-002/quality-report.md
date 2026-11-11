# Spec Quality Report

- Target: `docs/specs/SPEC-002-package-boundary/spec.md`
- Rubric: 1.1.0 (`1e6c4740ed85512b1657e6798e481c893fe015f4ce2a140665ff6ecb2ef7b29e`)
- Target SHA-256: `016c1705a3619c4b8a2a14e4635b8d0214f22411555cb698f44bc889da48c2e2`
- Reviewer session: `spec002-review-20261111-r3`

**Headline score (core): 100.0**  |  Diagnostic score (all): 100.0

> The auditor verifies evidence presence, section placement, and score arithmetic. It does not judge whether evidence is sufficient or true.

> Normalization covers full-width ASCII, NBSP, and ideographic space; it is not full Unicode NFKC.

| Dimension | Headline | Diagnostic | Weight |
|---|---:|---:|---:|
| 背景落地 | 100.0 | 100.0 | 2 |
| 痛点证据 | 100.0 | 100.0 | 3 |
| 目标可验收 | 100.0 | 100.0 | 3 |
| 非目标边界 | 100.0 | 100.0 | 2 |
| 架构自洽 | 100.0 | 100.0 | 2 |
| 详细设计完整 | 100.0 | 100.0 | 2 |
| NFR 可度量 | 100.0 | 100.0 | 2 |
| 上线可回滚 | 100.0 | 100.0 | 2 |
| 替代方案诚实 | 100.0 | 100.0 | 2 |
| 跨章自洽 | 100.0 | 100.0 | 2 |
| 证据卫生 | 100.0 | 100.0 | 3 |

## 背景落地 (background)

- **bg.current_state** [core, level 2] — 1.1 是否写清了模块职责、核心流程与当前技术栈？
  - evidence `1.1 系统现状`: "MediaDetect 是一个无状态、只读的媒体类型检测库与 CLI，当前 module path 为 'github.com/dream-365/MediaDetect'。仓库由四层组成："
  - normalized: "MediaDetect 是一个无状态、只读的媒体类型检测库与 CLI,当前 module path 为 'github.com/dream-365/MediaDetect'。仓库由四层组成:"
  - evidence `1.1 系统现状`: "当前包依赖无环：根包依赖 'collect'、'parser'、'probe'、'tmdb'、'matcher'；'collect' 依赖 'parser'、'probe'；'matcher' 依赖 'parser'、'tmdb'；'llm' 和 'cmd/mediadetect' 只依赖标准库与根包/对方。'go list ./...' 当前列出 8 个包，仓库中没有 'internal/' 目录。"
  - normalized: "当前包依赖无环:根包依赖 'collect'、'parser'、'probe'、'tmdb'、'matcher';'collect' 依赖 'parser'、'probe';'matcher' 依赖 'parser'、'tmdb';'llm' 和 'cmd/mediadetect' 只依赖标准库与根包/对方。'go list ./...' 当前列出 8 个包,仓库中没有 'internal/' 目录。"
  - rationale: 1.1 写出四层模块职责、根包内部编排顺序与包依赖图，并交代 Go module 与 CLI 技术栈，足以理解现状。
- **bg.failure_chain** [core, level 2] — 1.2 是否有从触发到后果的分步失败链？
  - evidence `1.2 核心技术痛点`: "**公开面链路**：下游按 README 引入 'collect' 或 'llm' → 维护者调整遍历器签名或 LLM 客户端 → 该调整从内部重构变成破坏性变更 → 为了兼容被迫保留旧形状，结构债务固化。"
  - normalized: "**公开面链路**:下游按 README 引入 'collect' 或 'llm' → 维护者调整遍历器签名或 LLM 客户端 → 该调整从内部重构变成破坏性变更 → 为了兼容被迫保留旧形状,结构债务固化。"
  - evidence `1.2 核心技术痛点`: "**CLI 链路**：新增一个输出字段 → 修改 'main.go' 中的输出/错误/verbose 多个函数 → 测试仍集中在一个 330 行的 'main_test.go' 中 → 后续改动继续叠加，评审范围扩大。"
  - normalized: "**CLI 链路**:新增一个输出字段 → 修改 'main.go' 中的输出/错误/verbose 多个函数 → 测试仍集中在一个 330 行的 'main_test.go' 中 → 后续改动继续叠加,评审范围扩大。"
  - rationale: 1.2 为 CLI、公开面和契约三条链路给出从触发动作到后果的箭头式分步失败链。
- **bg.trigger** [core, level 2] — 1.3 是否解释了为什么现在做？
  - evidence `1.3 重构/设计动机`: "当前版本为 'v0.1.1'，按 SPEC-001 6.5 的约定，v0.x 的 minor 版本允许破坏性 Go API 变更。现在整理的边际成本最低："
  - normalized: "当前版本为 'v0.1.1',按 SPEC-001 6.5 的约定,v0.x 的 minor 版本允许破坏性 Go API 变更。现在整理的边际成本最低:"
  - evidence `1.3 重构/设计动机`: "在 v1.0 之前建立公开/内部边界，后续 'parser'、'probe'、'tmdb'、'matcher' 的演进可以在明确契约下进行。"
  - normalized: "在 v1.0 之前建立公开/内部边界,后续 'parser'、'probe'、'tmdb'、'matcher' 的演进可以在明确契约下进行。"
  - rationale: 1.3 说明 v0.x 允许破坏性变更、下游尚未规模化，因而现在整理的边际成本最低，回答了为什么现在做。
- **bg.non_goals** [core, level 2] — 1.4 是否写了不做的后果与本次非目标？
  - evidence `1.4 非目标`: "**不做本次整理的后果**：CLI 入口继续增长；'collect' / 'llm' 继续与扩展 API 平级，下游可能按 README 形成事实依赖；根包公共契约继续被 'probe' / 'matcher' 的类型变化穿透；文档版本口径继续分叉。等到 v1.0 或出现外部下游后再做，同样的调整会从 v0.x minor 变更升级为受兼容窗口约束的破坏性变更。"
  - normalized: "**不做本次整理的后果**:CLI 入口继续增长;'collect' / 'llm' 继续与扩展 API 平级,下游可能按 README 形成事实依赖;根包公共契约继续被 'probe' / 'matcher' 的类型变化穿透;文档版本口径继续分叉。等到 v1.0 或出现外部下游后再做,同样的调整会从 v0.x minor 变更升级为受兼容窗口约束的破坏性变更。"
  - evidence `1.4 非目标`: "本次整理的正式非目标见 2.2。以下约束在本次范围内不可突破："
  - normalized: "本次整理的正式非目标见 2.2。以下约束在本次范围内不可突破:"
  - rationale: 1.4 写出不整理的后果，并以 2.2 的正式非目标和本节约束界定本次范围。

## 痛点证据 (pain_evidence)

- **bg.pain_evidence** [core, level 2] — 1.2 是否有至少一条可核实的证据（事故、度量或引述）？
  - evidence `1.2 核心技术痛点`: "1. **CLI 入口文件承担了过多职责。** 'cmd/mediadetect/main.go' 为 484 行、17 个函数，同时包含 'main/run'、参数解析、stdin 读取、TTY 判断、JSON 输出、错误输出、退出码映射、verbose 输出和 help 文本。改动输出格式或退出码时，评审者必须在一个文件内跨 400 多行定位；新增 flag 会继续推高该文件。"
  - normalized: "1. **CLI 入口文件承担了过多职责。** 'cmd/mediadetect/main.go' 为 484 行、17 个函数,同时包含 'main/run'、参数解析、stdin 读取、TTY 判断、JSON 输出、错误输出、退出码映射、verbose 输出和 help 文本。改动输出格式或退出码时,评审者必须在一个文件内跨 400 多行定位;新增 flag 会继续推高该文件。"
  - evidence `1.2 核心技术痛点`: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用；但 'llm' 只在 'cmd/mediadetect' 中被引用，'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包，它们就从实现细节变成事实上的公共 API，后续任何内部调整都要考虑兼容或提版本。"
  - normalized: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用;但 'llm' 只在 'cmd/mediadetect' 中被引用,'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包,它们就从实现细节变成事实上的公共 API,后续任何内部调整都要考虑兼容或提版本。"
  - rationale: 痛点用可复核的文件行数、函数数与 README 具体行号作证据，并分别对应 1.2 的 CLI 与公开面失败链。

## 目标可验收 (goal_verifiability)

- **goal.verifiable** [core, level 2] — 2.1 每个 Goal 是否都有验收方式？
  - evidence `2.1 目标`: "验收：排除 '/internal/' 后 'go list ./...' 恰好给出根包、'cmd/mediadetect' 和四个领域包；'parser'、'probe'、'tmdb'、'matcher' 的依赖列表中不出现 '/internal/'；外部临时模块导入 '.../internal/collect' 或 '.../internal/llm' 编译失败，临时模块必须先 'require' 本模块并用 'replace' 指向本地仓库，断言错误信息包含 'internal' 拒绝文本，避免因模块缺失而假阳性；该断言进入 CI。"
  - normalized: "验收:排除 '/internal/' 后 'go list ./...' 恰好给出根包、'cmd/mediadetect' 和四个领域包;'parser'、'probe'、'tmdb'、'matcher' 的依赖列表中不出现 '/internal/';外部临时模块导入 '.../internal/collect' 或 '.../internal/llm' 编译失败,临时模块必须先 'require' 本模块并用 'replace' 指向本地仓库,断言错误信息包含 'internal' 拒绝文本,避免因模块缺失而假阳性;该断言进入 CI。"
  - evidence `2.1 目标`: "验收：'go doc github.com/dream-365/MediaDetect' 中两个类型显示为本地定义；'result.go' 的 import 不含 'probe'、'matcher'；'detect_test.go' 的 'proberFunc' 返回类型改为 'MediaInfo' 后，现有检测与匹配测试全部通过；新增字段转换测试断言 'MediaInfo' 与 'probe.Info' 无损互转；新增 'errors.Is' 测试断言 'ErrProbeUnavailable' 与 'probe.ErrUnavailable' 等价。"
  - normalized: "验收:'go doc github.com/dream-365/MediaDetect' 中两个类型显示为本地定义;'result.go' 的 import 不含 'probe'、'matcher';'detect_test.go' 的 'proberFunc' 返回类型改为 'MediaInfo' 后,现有检测与匹配测试全部通过;新增字段转换测试断言 'MediaInfo' 与 'probe.Info' 无损互转;新增 'errors.Is' 测试断言 'ErrProbeUnavailable' 与 'probe.ErrUnavailable' 等价。"
  - evidence `2.1 目标`: "验收：'main.go' ≤120 行；新增 CLI 文件各自 ≤200 行；'go test ./cmd/mediadetect' 的现有用例全部通过；CLI stdout/stderr/退出码不变。"
  - normalized: "验收:'main.go' ≤120 行;新增 CLI 文件各自 ≤200 行;'go test ./cmd/mediadetect' 的现有用例全部通过;CLI stdout/stderr/退出码不变。"
  - evidence `2.1 目标`: "验收：README 中公开包列表与 G1 的 'go list' 结果一致；README 当前版本、README 安装 tag、'defaultVersion'、目标 tag 四者一致指向 '0.2.0'，并以 git tag 作为发布 SSOT；SPEC-001 的 §2.1 G2、§3.2、§4.4.1、§4.4.1.1 带指向 SPEC-002 的替代说明；SPEC-001 中 'v0.1.0' 的目标版本、'--version' 示例和 'tasks.md' 标题作为历史基线保留，不作为当前版本验收项。"
  - normalized: "验收:README 中公开包列表与 G1 的 'go list' 结果一致;README 当前版本、README 安装 tag、'defaultVersion'、目标 tag 四者一致指向 '0.2.0',并以 git tag 作为发布 SSOT;SPEC-001 的 §2.1 G2、§3.2、§4.4.1、§4.4.1.1 带指向 SPEC-002 的替代说明;SPEC-001 中 'v0.1.0' 的目标版本、'--version' 示例和 'tasks.md' 标题作为历史基线保留,不作为当前版本验收项。"
  - evidence `2.1 目标`: "验收：'gofmt -l .' 为空；'go mod tidy -diff' 无差异；'go vet ./...'、'go test ./...'、'go build ./cmd/mediadetect' 全部通过；同一输入在整理前后的 JSON 输出逐字节一致，唯一允许的差异是 '--version' 从 '0.1.1' 变为 '0.2.0'。"
  - normalized: "验收:'gofmt -l .' 为空;'go mod tidy -diff' 无差异;'go vet ./...'、'go test ./...'、'go build ./cmd/mediadetect' 全部通过;同一输入在整理前后的 JSON 输出逐字节一致,唯一允许的差异是 '--version' 从 '0.1.1' 变为 '0.2.0'。"
  - rationale: G1–G5 每条都以可执行的命令、测试或文档检查给出验收方式。
- **goal.quantified** [core, level 2] — 2.1 是否至少有一个 Goal 有数字/单位/明确阈值？
  - evidence `2.1 目标`: "验收：'main.go' ≤120 行；新增 CLI 文件各自 ≤200 行；'go test ./cmd/mediadetect' 的现有用例全部通过；CLI stdout/stderr/退出码不变。"
  - normalized: "验收:'main.go' ≤120 行;新增 CLI 文件各自 ≤200 行;'go test ./cmd/mediadetect' 的现有用例全部通过;CLI stdout/stderr/退出码不变。"
  - rationale: G3 给出 'main.go' ≤120 行、新增文件 ≤200 行的明确阈值与单位。
- **goal.count** [extended, level 2] — 2.1 Goals 是否控制在 3–6 个？
  - evidence `2.1 目标`: "**G1 - 架构/代码：收敛公开边界**"
  - normalized: "**G1 - 架构/代码:收敛公开边界**"
  - evidence `2.1 目标`: "**G2 - 架构/代码：公共契约与实现解耦**"
  - normalized: "**G2 - 架构/代码:公共契约与实现解耦**"
  - evidence `2.1 目标`: "**G3 - 可维护性：CLI 按职责拆分**"
  - normalized: "**G3 - 可维护性:CLI 按职责拆分**"
  - evidence `2.1 目标`: "**G4 - 工程效率：文档与版本口径一致**"
  - normalized: "**G4 - 工程效率:文档与版本口径一致**"
  - evidence `2.1 目标`: "**G5 - 可靠性：构建与行为基线不变**"
  - normalized: "**G5 - 可靠性:构建与行为基线不变**"
  - rationale: 共 5 个 Goal，落在 3–6 范围内，且每个都带架构/代码、可维护性、工程效率或可靠性分类。

## 非目标边界 (non_goal_boundary)

- **nongoal.labeled** [core, level 2] — 2.2 每条 Non-Goal 是否标了本次不做或 Deferred to Phase 2？
  - evidence `2.2 非目标`: "* **NG1 - 检测规则与匹配算法**：不新增媒体类型规则、不调整 matcher 评分、不改变 TMDB 查询策略（本次不做）。"
  - normalized: "* **NG1 - 检测规则与匹配算法**:不新增媒体类型规则、不调整 matcher 评分、不改变 TMDB 查询策略(本次不做)。"
  - evidence `2.2 非目标`: "* **NG2 - JSON 契约与错误码**：不增删 JSON 字段、不修改 'schema_version'、不重排退出码（本次不做）。"
  - normalized: "* **NG2 - JSON 契约与错误码**:不增删 JSON 字段、不修改 'schema_version'、不重排退出码(本次不做)。"
  - evidence `2.2 非目标`: "* **NG3 - 模块重命名**：不改 module path、仓库名或大小写；不把 'MediaDetect' 改为全小写路径（本次不做）。"
  - normalized: "* **NG3 - 模块重命名**:不改 module path、仓库名或大小写;不把 'MediaDetect' 改为全小写路径(本次不做)。"
  - evidence `2.2 非目标`: "* **NG4 - 引入 'pkg/' 目录**：不把公开包移动到 'pkg/' 下（本次不做；理由见 7.3）。"
  - normalized: "* **NG4 - 引入 'pkg/' 目录**:不把公开包移动到 'pkg/' 下(本次不做;理由见 7.3)。"
  - evidence `2.2 非目标`: "* **NG5 - 功能扩展**：剧集 TMDB 匹配、批量/NDJSON、持久缓存、Windows 支持均不在本次范围（Deferred to Phase 2）。"
  - normalized: "* **NG5 - 功能扩展**:剧集 TMDB 匹配、批量/NDJSON、持久缓存、Windows 支持均不在本次范围(Deferred to Phase 2)。"
  - evidence `2.2 非目标`: "* **NG6 - 发布渠道与 CI 平台扩展**：不新增 Homebrew/Docker/包管理器发布，不增加新的 CI 平台（本次不做）。"
  - normalized: "* **NG6 - 发布渠道与 CI 平台扩展**:不新增 Homebrew/Docker/包管理器发布,不增加新的 CI 平台(本次不做)。"
  - rationale: NG1–NG6 每条都显式标注「本次不做」或「Deferred to Phase 2」。
- **nongoal.not_dumping_ground** [extended, level 2] — 2.2 非目标是否能追溯到痛点或边界？
  - evidence `2.2 非目标`: "非目标与边界的对应关系：NG1、NG2 对应 1.2 的行为契约风险（结构整理不能顺手改规则）；NG3、NG4 对应 3.4 的选型边界（module path 与顶层公开包是刻意保留的）；NG5 对应 SPEC-001 附录 A 的延后项；NG6 对应本次只做源码结构、不扩大发布面。"
  - normalized: "非目标与边界的对应关系:NG1、NG2 对应 1.2 的行为契约风险(结构整理不能顺手改规则);NG3、NG4 对应 3.4 的选型边界(module path 与顶层公开包是刻意保留的);NG5 对应 SPEC-001 附录 A 的延后项;NG6 对应本次只做源码结构、不扩大发布面。"
  - rationale: 该段逐条把 NG1–NG6 追溯到痛点、选型边界或 SPEC-001 延后项，非目标不是无关联的垃圾桶。

## 架构自洽 (architecture)

- **arch.solution_shape** [core, level 2] — 第 3 章是否有本次变更的拓扑或等价的模块/数据流描述？
  - evidence `3. 架构设计与核心方案`: "本次变更落在包布局、公开边界、根包公共契约和 CLI 文件划分四处；检测数据流、JSON 输出和外部依赖保持不变。"
  - normalized: "本次变更落在包布局、公开边界、根包公共契约和 CLI 文件划分四处;检测数据流、JSON 输出和外部依赖保持不变。"
  - evidence `3. 架构设计与核心方案`: "    ROOT --> COLLECT     ROOT --> PARSER     ROOT --> PROBE     ROOT --> TMDB     ROOT --> MATCHER     COLLECT --> PARSER     COLLECT --> PROBE     MATCHER --> PARSER     MATCHER --> TMDB     CMD --> ROOT     CMD --> LLM"
  - normalized: "ROOT --> COLLECT ROOT --> PARSER ROOT --> PROBE ROOT --> TMDB ROOT --> MATCHER COLLECT --> PARSER COLLECT --> PROBE MATCHER --> PARSER MATCHER --> TMDB CMD --> ROOT CMD --> LLM"
  - rationale: 第 3 章用 mermaid 拓扑图和一句变更范围描述给出本次变更的模块关系与边界。
- **arch.topology** [extended, level 2] — 3.1 拓扑图是否让每个模块有一句职责？
  - evidence `3.1 总体架构`: "    ROOT --> COLLECT     ROOT --> PARSER     ROOT --> PROBE     ROOT --> TMDB     ROOT --> MATCHER     COLLECT --> PARSER     COLLECT --> PROBE     MATCHER --> PARSER     MATCHER --> TMDB     CMD --> ROOT     CMD --> LLM"
  - normalized: "ROOT --> COLLECT ROOT --> PARSER ROOT --> PROBE ROOT --> TMDB ROOT --> MATCHER COLLECT --> PARSER COLLECT --> PROBE MATCHER --> PARSER MATCHER --> TMDB CMD --> ROOT CMD --> LLM"
  - evidence `3.2 核心模块职责`: "\| '.../parser' \| 公开 \| 文件名解析为标题、年份、角色、季集和发布线索 \| 不变 \| \| '.../probe' \| 公开 \| ffprobe / exiftool 技术元数据探测 \| 不变 \| \| '.../tmdb' \| 公开 \| TMDB 搜索、详情、缓存、限流与脱敏 \| 不变 \|"
  - normalized: "\| '.../parser' \| 公开 \| 文件名解析为标题、年份、角色、季集和发布线索 \| 不变 \| \| '.../probe' \| 公开 \| ffprobe / exiftool 技术元数据探测 \| 不变 \| \| '.../tmdb' \| 公开 \| TMDB 搜索、详情、缓存、限流与脱敏 \| 不变 \|"
  - rationale: 3.1 的 mermaid 图给出模块连接，3.2 的表格为每个模块补一句职责。
- **arch.change_set** [extended, level 2] — 第 3 章是否写清新增/改造/保持不变？
  - evidence `3. 架构设计与核心方案`: "\| 'github.com/dream-365/MediaDetect' \| 公开 \| 'Detect'、'Options'、'Result'、错误与 JSON 契约；编排本地检测和匹配 \| 公共契约与实现分文件；去掉对 'probe'/'matcher' 的类型别名 \| \| '.../parser' \| 公开 \| 文件名解析为标题、年份、角色、季集和发布线索 \| 不变 \| \| '.../probe' \| 公开 \| ffprobe / exiftool 技术元数据探测 \| 不变 \| \| '.../tmdb' \| 公开 \| TMDB 搜索、详情、缓存、限流与脱敏 \| 不变 \| \| '.../matcher' \| 公开 \| 候选评分、置信度与领先分差 \| 不变 \| \| '.../internal/collect' \| 内部 \| 只读遍历、解析、探测、分组键计算 \| 从顶层 'collect' 移入 'internal/'；符号名保持 \| \| '.../internal/llm' \| 内部 \| DeepSeek 查询扩展，仅供 CLI 使用 \| 从顶层 'llm' 移入 'internal/'；符号名保持 \| \| '.../cmd/mediadetect' \| 可执行 \| 参数、stdin、环境变量、JSON 输出和退出码 \| 按职责拆分为多个文件 \|"
  - normalized: "\| 'github.com/dream-365/MediaDetect' \| 公开 \| 'Detect'、'Options'、'Result'、错误与 JSON 契约;编排本地检测和匹配 \| 公共契约与实现分文件;去掉对 'probe'/'matcher' 的类型别名 \| \| '.../parser' \| 公开 \| 文件名解析为标题、年份、角色、季集和发布线索 \| 不变 \| \| '.../probe' \| 公开 \| ffprobe / exiftool 技术元数据探测 \| 不变 \| \| '.../tmdb' \| 公开 \| TMDB 搜索、详情、缓存、限流与脱敏 \| 不变 \| \| '.../matcher' \| 公开 \| 候选评分、置信度与领先分差 \| 不变 \| \| '.../internal/collect' \| 内部 \| 只读遍历、解析、探测、分组键计算 \| 从顶层 'collect' 移入 'internal/';符号名保持 \| \| '.../internal/llm' \| 内部 \| DeepSeek 查询扩展,仅供 CLI 使用 \| 从顶层 'llm' 移入 'internal/';符号名保持 \| \| '.../cmd/mediadetect' \| 可执行 \| 参数、stdin、环境变量、JSON 输出和退出码 \| 按职责拆分为多个文件 \|"
  - rationale: 3.2 的「本次变化」列明确区分保持不变、移入 internal 和按职责拆分三类变更。
- **arch.rationale** [extended, level 2] — 关键选型是否有理由，详细对比指向第 7 章？
  - evidence `3.4 关键选型与约束`: "* **不使用 'pkg/' 目录**：顶层公开包是 Go module 的惯用形态；'pkg/' 只增加路径层级，不提供语言级可见性约束，反而让导入路径变长。详细对比见 7.3。"
  - normalized: "* **不使用 'pkg/' 目录**:顶层公开包是 Go module 的惯用形态;'pkg/' 只增加路径层级,不提供语言级可见性约束,反而让导入路径变长。详细对比见 7.3。"
  - evidence `3.4 关键选型与约束`: "* **CLI 按“配置/参数/输入/输出/help”拆分**：每个文件只对应一个变更理由，保持 'package main' 不变，避免为了测试而引入不必要的子包。备选方案见第 7 章。"
  - normalized: "* **CLI 按“配置/参数/输入/输出/help”拆分**:每个文件只对应一个变更理由,保持 'package main' 不变,避免为了测试而引入不必要的子包。备选方案见第 7 章。"
  - rationale: 关键选型均给出理由，并把详细对比指向 7.3 和第 7 章。
- **arch.references_source** [extended, level 2] — 第 3 章是否引用 depends_on 架构文档，而不是自行展开其全局结构？
  - evidence `3. 架构设计与核心方案`: "仓库当前没有 'docs/architecture/' 下的受管架构文档；SPEC-001 §3.2 是现状模块划分与职责的 SSOT，本 Spec 只描述其增量变更，不复制完整全局拓扑。"
  - normalized: "仓库当前没有 'docs/architecture/' 下的受管架构文档;SPEC-001 §3.2 是现状模块划分与职责的 SSOT,本 Spec 只描述其增量变更,不复制完整全局拓扑。"
  - rationale: 第 3 章明确把 depends_on 的 SPEC-001 §3.2 作为现状架构 SSOT 引用，并声明只描述增量、不复制全局拓扑。

## 详细设计完整 (detailed_design)

- **design.contract** [core, level 2] — 第 4 章是否至少有一份数据模型或接口契约？
  - evidence `4. 详细设计`: "\| 'MediaInfo' \| 'DurationSec' \| 'int' \| 否 \| 探测失败或未探测时为 0；字段与 'probe.Info.DurationSec' 一致 \|"
  - normalized: "\| 'MediaInfo' \| 'DurationSec' \| 'int' \| 否 \| 探测失败或未探测时为 0;字段与 'probe.Info.DurationSec' 一致 \|"
  - evidence `4. 详细设计`: "\| 'mediadetect.Detect' \| 'Detect(ctx context.Context, path string, opts Options) (Result, error)' \| 公开 \| 唯一检测入口；行为不变 \|"
  - normalized: "\| 'mediadetect.Detect' \| 'Detect(ctx context.Context, path string, opts Options) (Result, error)' \| 公开 \| 唯一检测入口;行为不变 \|"
  - rationale: 第 4 章至少包含 4.3 的字段表与 4.4 的接口签名表两份契约。
- **design.data_model** [extended, level 2] — 4.3 数据模型是否有字段类型、必填与校验？
  - evidence `4.3 数据模型与契约`: "\| 类型 \| 字段/方法 \| 类型 \| 必填 \| 校验与说明 \| \| --- \| --- \| --- \| --- \| --- \| \| 'MediaInfo' \| 'DurationSec' \| 'int' \| 否 \| 探测失败或未探测时为 0；字段与 'probe.Info.DurationSec' 一致 \| \| 'MediaInfo' \| 'Resolution' \| 'string' \| 否 \| 允许为空；字段与 'probe.Info.Resolution' 一致 \|"
  - normalized: "\| 类型 \| 字段/方法 \| 类型 \| 必填 \| 校验与说明 \| \| --- \| --- \| --- \| --- \| --- \| \| 'MediaInfo' \| 'DurationSec' \| 'int' \| 否 \| 探测失败或未探测时为 0;字段与 'probe.Info.DurationSec' 一致 \| \| 'MediaInfo' \| 'Resolution' \| 'string' \| 否 \| 允许为空;字段与 'probe.Info.Resolution' 一致 \|"
  - rationale: 4.3 的表格为每个字段给出类型、必填性与校验/说明。
- **design.interface** [extended, level 2] — 4.4 接口是否有请求/响应/状态码或方法签名？
  - evidence `4.4 接口与协议`: "\| 'mediadetect.Detect' \| 'Detect(ctx context.Context, path string, opts Options) (Result, error)' \| 公开 \| 唯一检测入口；行为不变 \| \| 'mediadetect.Prober' \| 'Probe(ctx context.Context, path string) (MediaInfo, error)' \| 公开 \| 外部注入探测实现；nil 时用 'probe.Probe' \| \| 'mediadetect.QueryResolver' \| 'Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error)' \| 公开 \| 可选查询扩展；与 matcher 接口结构兼容 \|"
  - normalized: "\| 'mediadetect.Detect' \| 'Detect(ctx context.Context, path string, opts Options) (Result, error)' \| 公开 \| 唯一检测入口;行为不变 \| \| 'mediadetect.Prober' \| 'Probe(ctx context.Context, path string) (MediaInfo, error)' \| 公开 \| 外部注入探测实现;nil 时用 'probe.Probe' \| \| 'mediadetect.QueryResolver' \| 'Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error)' \| 公开 \| 可选查询扩展;与 matcher 接口结构兼容 \|"
  - rationale: 4.4 用方法签名、可见性和说明列出公开接口契约。
- **design.sequence** [extended, level 2] — 4.5 复杂流程是否有时序图或等价分步说明？
  - evidence `4.5 核心流程与时序`: "1. CLI 解析 flag 与唯一输入路径，读取环境变量，构造 'Options'。 2. 根包 'Detect' 做 'lstat'、符号链接和可读性检查；失败返回 '*Error'，CLI 输出错误 JSON 和对应退出码。 3. 根包调用 'internal/collect' 完成只读遍历与探测；外部 'Prober' 的 'MediaInfo' 在此转换为 'probe.Info'。 4. 根包用 'parser.Hints' 映射类型、按 'GroupKey' 聚合；仅电影组调用 'matcher' 和 'tmdb'。 5. 根包组装 'Result'；CLI 序列化到内存后一次性写 stdout，并按 'match.status' 映射退出码。"
  - normalized: "1. CLI 解析 flag 与唯一输入路径,读取环境变量,构造 'Options'。 2. 根包 'Detect' 做 'lstat'、符号链接和可读性检查;失败返回 '*Error',CLI 输出错误 JSON 和对应退出码。 3. 根包调用 'internal/collect' 完成只读遍历与探测;外部 'Prober' 的 'MediaInfo' 在此转换为 'probe.Info'。 4. 根包用 'parser.Hints' 映射类型、按 'GroupKey' 聚合;仅电影组调用 'matcher' 和 'tmdb'。 5. 根包组装 'Result';CLI 序列化到内存后一次性写 stdout,并按 'match.status' 映射退出码。"
  - evidence `4.5 核心流程与时序`: "* 路径不存在、输入符号链接、根不可读：根包返回结构化错误，CLI 退出 2。"
  - normalized: "* 路径不存在、输入符号链接、根不可读:根包返回结构化错误,CLI 退出 2。"
  - rationale: 4.5 用编号步骤描述正常路径，并单列异常路径，等价于时序说明。
- **design.errors** [extended, level 2] — 4.6 每个错误码是否有触发场景与处理策略？
  - evidence `4.6 异常处理与错误码`: "\| 场景 \| 触发条件 \| 表现 \| 处理策略 \| \| --- \| --- \| --- \| --- \| \| 下游导入内部包 \| 模块外 'import .../internal/collect' 或 '.../internal/llm' \| Go 编译失败 \| 按 4.7 迁移到根包 'Detect' 或 CLI '--llm-fallback' \| \| 公共领域包反向依赖 \| 'parser'/'probe'/'tmdb'/'matcher' 导入 'internal/' \| 'go list' 依赖断言失败 \| 调整依赖方向；领域包只依赖标准库、第三方库和彼此 \|"
  - normalized: "\| 场景 \| 触发条件 \| 表现 \| 处理策略 \| \| --- \| --- \| --- \| --- \| \| 下游导入内部包 \| 模块外 'import .../internal/collect' 或 '.../internal/llm' \| Go 编译失败 \| 按 4.7 迁移到根包 'Detect' 或 CLI '--llm-fallback' \| \| 公共领域包反向依赖 \| 'parser'/'probe'/'tmdb'/'matcher' 导入 'internal/' \| 'go list' 依赖断言失败 \| 调整依赖方向;领域包只依赖标准库、第三方库和彼此 \|"
  - rationale: 本次不新增 'ERR_*'；4.6 为每个结构性异常给出触发条件、表现和处理策略，现有错误码沿用 SPEC-001，属不适用场景。

## NFR 可度量 (nfr)

- **nfr.measurable** [core, level 2] — 第 5 章每条 NFR 是否有数字、单位或验收方式？
  - evidence `5. 非功能性需求`: "* **CLI 文件预算**：'main.go' ≤120 行；'config.go' ≤120 行；'args.go' 和 'output.go' ≤200 行；'input.go' ≤100 行；'help.go' ≤80 行。验收用 'wc -l'。"
  - normalized: "* **CLI 文件预算**:'main.go' ≤120 行;'config.go' ≤120 行;'args.go' 和 'output.go' ≤200 行;'input.go' ≤100 行;'help.go' ≤80 行。验收用 'wc -l'。"
  - evidence `5. 非功能性需求`: "* **检测结果不变**：同一输入在整理前后，'Result' 的字段值和 JSON 序列化逐字节一致；'schema_version' 保持 '"1"'。"
  - normalized: "* **检测结果不变**:同一输入在整理前后,'Result' 的字段值和 JSON 序列化逐字节一致;'schema_version' 保持 '"1"'。"
  - evidence `5. 非功能性需求`: "* **性能与资源**：本次不新增运行时逻辑、依赖或后台任务，检测路径的 CPU、内存和 I/O 行为不变。验收：现有测试通过；不引入基准测试回归。"
  - normalized: "* **性能与资源**:本次不新增运行时逻辑、依赖或后台任务,检测路径的 CPU、内存和 I/O 行为不变。验收:现有测试通过;不引入基准测试回归。"
  - rationale: 第 5 章各节均给出数字阈值、命令或测试/检查方式；5.5 的性能项也明确以现有测试和基准回归为验收。
- **nfr.coverage** [core, level 2] — 第 5 章是否覆盖性能、可靠性、可观测性、安全，或说明不适用？
  - evidence `5. 非功能性需求`: "* **凭据不变**：'TMDB_API_KEY'、'DEEPSEEK_API_KEY' 仍只从环境变量读取，不进入 JSON、stderr、错误信息或日志；现有脱敏测试通过。"
  - normalized: "* **凭据不变**:'TMDB_API_KEY'、'DEEPSEEK_API_KEY' 仍只从环境变量读取,不进入 JSON、stderr、错误信息或日志;现有脱敏测试通过。"
  - evidence `5. 非功能性需求`: "* **性能与资源**：本次不新增运行时逻辑、依赖或后台任务，检测路径的 CPU、内存和 I/O 行为不变。验收：现有测试通过；不引入基准测试回归。 * **可靠性**：无状态、只读、零写入、零 HTTP 的既有保证不变；降级与错误语义沿用 SPEC-001。 * **可观测性**：本仓库不提供常驻服务或指标端点，可观测性体现为 CLI stderr、warning 和退出码；本次不改变这些输出，因此不新增指标。"
  - normalized: "* **性能与资源**:本次不新增运行时逻辑、依赖或后台任务,检测路径的 CPU、内存和 I/O 行为不变。验收:现有测试通过;不引入基准测试回归。 * **可靠性**:无状态、只读、零写入、零 HTTP 的既有保证不变;降级与错误语义沿用 SPEC-001。 * **可观测性**:本仓库不提供常驻服务或指标端点,可观测性体现为 CLI stderr、warning 和退出码;本次不改变这些输出,因此不新增指标。"
  - rationale: 5.4 覆盖安全，5.5 明确覆盖性能、可靠性与可观测性，四类均有交代。
- **nfr.honesty** [core, level 2] — 未实测的指标是否标了 [estimated] 或 未实现？
  - evidence `5. 非功能性需求`: "* **性能与资源**：本次不新增运行时逻辑、依赖或后台任务，检测路径的 CPU、内存和 I/O 行为不变。验收：现有测试通过；不引入基准测试回归。"
  - normalized: "* **性能与资源**:本次不新增运行时逻辑、依赖或后台任务,检测路径的 CPU、内存和 I/O 行为不变。验收:现有测试通过;不引入基准测试回归。"
  - rationale: 本文是待实现的设计稿，未声称任何实测数值或已达成指标，因此不存在需要标 [estimated] 或「未实现」的项；本章的定量内容是验收目标而非实测结果。

## 上线可回滚 (rollout)

- **rollout.release** [core, level 2] — 6.1 是否有发布策略与灰度节奏？
  - evidence `6.1 发布与灰度`: "本次没有运行时服务，因此不使用流量灰度；用“分阶段提交 + 每阶段 CI 观察期”代替。每个阶段必须 CI 全绿后才能进入下一阶段，观察指标为 'go test ./...'、'go vet ./...'、'go build ./cmd/mediadetect' 和公开包清单。按 v0.x 语义发布 'v0.2.0' minor 版本，步骤分三段："
  - normalized: "本次没有运行时服务,因此不使用流量灰度;用“分阶段提交 + 每阶段 CI 观察期”代替。每个阶段必须 CI 全绿后才能进入下一阶段,观察指标为 'go test ./...'、'go vet ./...'、'go build ./cmd/mediadetect' 和公开包清单。按 v0.x 语义发布 'v0.2.0' minor 版本,步骤分三段:"
  - evidence `6.1 发布与灰度`: "不设灰度：这是源码级结构变更，没有运行时服务；下游通过版本号选择升级。"
  - normalized: "不设灰度:这是源码级结构变更,没有运行时服务;下游通过版本号选择升级。"
  - rationale: 6.1 明确无流量灰度，改用分阶段提交与每阶段 CI 观察期，并给出观察指标和三段发布步骤。
- **rollout.migration** [core, level 2] — 6.2 是否有迁移/兼容方案，或说明无需迁移？
  - evidence `6.2 数据迁移与兼容性`: "* 无数据库、无索引、无持久化数据，不需要数据迁移。"
  - normalized: "* 无数据库、无索引、无持久化数据,不需要数据迁移。"
  - evidence `6.2 数据迁移与兼容性`: "* Go API 迁移按 4.7 执行；'Options'、'Result'、JSON 契约保持兼容。"
  - normalized: "* Go API 迁移按 4.7 执行;'Options'、'Result'、JSON 契约保持兼容。"
  - evidence `6.2 数据迁移与兼容性`: "* 旧版本下游可继续使用 'v0.1.1'；升级到 'v0.2.0' 时需要处理 'collect' / 'llm' 导入，以及 'MediaInfo' / 'QueryResolver' / 'Prober' 的类型身份变化。"
  - normalized: "* 旧版本下游可继续使用 'v0.1.1';升级到 'v0.2.0' 时需要处理 'collect' / 'llm' 导入,以及 'MediaInfo' / 'QueryResolver' / 'Prober' 的类型身份变化。"
  - rationale: 6.2 明确说明无需数据迁移，并给出 Go API 的兼容与升级路径。
- **rollout.smoke** [core, level 2] — 6.3 是否有冒烟清单与观察指标？
  - evidence `6.3 上线验证与冒烟`: "gofmt -l . go mod tidy -diff go vet ./... go test ./... go build -o /tmp/mediadetect ./cmd/mediadetect go list ./... \| grep -v '/internal/'"
  - normalized: "gofmt -l . go mod tidy -diff go vet ./... go test ./... go build -o /tmp/mediadetect ./cmd/mediadetect go list ./... \| grep -v '/internal/'"
  - evidence `6.3 上线验证与冒烟`: "* 排除 '/internal/' 后 'go list ./...' 恰好 6 个包；'go list ./... \| grep '/internal/'' 恰好输出 'internal/collect' 和 'internal/llm' 两个包。"
  - normalized: "* 排除 '/internal/' 后 'go list ./...' 恰好 6 个包;'go list ./... \| grep '/internal/'' 恰好输出 'internal/collect' 和 'internal/llm' 两个包。"
  - rationale: 6.3 给出可执行命令与逐项观察断言，冒烟清单和指标齐全。
- **rollout.rollback_trigger** [core, level 2] — 6.4 回滚触发条件是否是可观测数字？
  - evidence `6.4 回滚与熔断`: "* **回滚触发条件**（均为可观测计数或 diff）：   * 'go test ./...' 的失败用例数 > 0，且无法用导入路径机械修复解决；   * CLI fixture 的 stdout diff 行数 > 0（'--version' 输出除外）；   * 排除 '/internal/' 后的包数 ≠ 6，或 'internal/' 下的包数 ≠ 2；   * 'parser'、'probe'、'tmdb'、'matcher' 的 import 列表中出现 '/internal/' 的次数 > 0；   * 'cmd/mediadetect/main.go' 行数 > 120；"
  - normalized: "* **回滚触发条件**(均为可观测计数或 diff): * 'go test ./...' 的失败用例数 > 0,且无法用导入路径机械修复解决; * CLI fixture 的 stdout diff 行数 > 0('--version' 输出除外); * 排除 '/internal/' 后的包数 ≠ 6,或 'internal/' 下的包数 ≠ 2; * 'parser'、'probe'、'tmdb'、'matcher' 的 import 列表中出现 '/internal/' 的次数 > 0; * 'cmd/mediadetect/main.go' 行数 > 120;"
  - rationale: 回滚触发条件全部是可观测计数或 diff 阈值（失败用例数、diff 行数、包数、import 次数、行数）。
- **rollout.rollback_steps** [core, level 2] — 6.4 回滚步骤是否可执行？
  - evidence `6.4 回滚与熔断`: "* **回滚步骤**：在 tag 推送前，直接回退实现段提交并恢复文档状态；不涉及数据或运行时。若 'v0.2.0' 已推送且发现阻断问题，按 SPEC-001 6.5 发布 'v0.2.1' 修复，必要时 'retract' 'v0.2.0'，不移动既有 tag。"
  - normalized: "* **回滚步骤**:在 tag 推送前,直接回退实现段提交并恢复文档状态;不涉及数据或运行时。若 'v0.2.0' 已推送且发现阻断问题,按 SPEC-001 6.5 发布 'v0.2.1' 修复,必要时 'retract' 'v0.2.0',不移动既有 tag。"
  - rationale: 回滚步骤区分 tag 推送前后，分别给出回退提交/恢复文档和发布 patch/retract 的可执行动作。

## 替代方案诚实 (alternatives)

- **alts.status_quo** [core, level 2] — 第 7 章是否有 Status Quo 及其成本/风险？
  - evidence `7. 替代方案与权衡`: "* **思路**：不调整包布局，只在 README 补充说明。 * **优点**：零改动、零兼容风险；现有测试和下游完全不受影响。 * **成本与风险**：CLI 继续增长；'collect'/'llm' 继续与扩展 API 平级；根包继续别名子包类型；v1.0 后任何结构整理都会变成破坏性变更并需要更长的兼容窗口。 * **触发阈值**：当出现第一个外部下游依赖 'collect'/'llm'，或 'main.go' 超过 600 行，或 v1.0 发布临近时，现状成本超过一次 v0.x 整理的成本。"
  - normalized: "* **思路**:不调整包布局,只在 README 补充说明。 * **优点**:零改动、零兼容风险;现有测试和下游完全不受影响。 * **成本与风险**:CLI 继续增长;'collect'/'llm' 继续与扩展 API 平级;根包继续别名子包类型;v1.0 后任何结构整理都会变成破坏性变更并需要更长的兼容窗口。 * **触发阈值**:当出现第一个外部下游依赖 'collect'/'llm',或 'main.go' 超过 600 行,或 v1.0 发布临近时,现状成本超过一次 v0.x 整理的成本。"
  - rationale: 7.1 给出 Status Quo 的思路、优点、成本风险与触发阈值。
- **alts.rejected** [core, level 2] — 第 7 章是否至少有一个被否决方案，且淘汰原因对应当前约束？
  - evidence `7. 替代方案与权衡`: "* **淘汰原因**：SPEC-001 §1.2 明确把解析器、匹配器和探测层作为库 API 暴露；全部 internal 会删除下游复用能力，属于产品能力回退，而不是结构整理。"
  - normalized: "* **淘汰原因**:SPEC-001 §1.2 明确把解析器、匹配器和探测层作为库 API 暴露;全部 internal 会删除下游复用能力,属于产品能力回退,而不是结构整理。"
  - evidence `7. 替代方案与权衡`: "* **淘汰原因**：'llm' 只服务 CLI，'collect' 只服务根包，二者没有独立版本契约；继续公开会让下游形成事实依赖，后续内部调整仍需兼容。公开面应与实际支持面一致。"
  - normalized: "* **淘汰原因**:'llm' 只服务 CLI,'collect' 只服务根包,二者没有独立版本契约;继续公开会让下游形成事实依赖,后续内部调整仍需兼容。公开面应与实际支持面一致。"
  - rationale: 7.2 和 7.4 至少两个被否决方案，淘汰原因分别对应保留库复用能力和公开面收敛的约束。
- **alts.matrix** [core, level 2] — 第 7 章是否有与约束对应的权衡矩阵？
  - evidence `7. 替代方案与权衡`: "\| 维度 \| Status Quo \| 全部 internal \| 'pkg/' 层 \| 保持 collect/llm 公开 \| 引擎整体 internal \| 本次选型 \| \| --- \| --- \| --- \| --- \| --- \| --- \| --- \| \| 公共面收敛 \| 否 \| 最强 \| 强 \| 否 \| 强 \| **强** \| \| 保留库复用 \| 是 \| 否 \| 是 \| 是 \| 是 \| **是** \| \| 兼容风险 \| 无 \| 高 \| 中 \| 低 \| 高 \| **中（v0.x 可控）** \|"
  - normalized: "\| 维度 \| Status Quo \| 全部 internal \| 'pkg/' 层 \| 保持 collect/llm 公开 \| 引擎整体 internal \| 本次选型 \| \| --- \| --- \| --- \| --- \| --- \| --- \| --- \| \| 公共面收敛 \| 否 \| 最强 \| 强 \| 否 \| 强 \| **强** \| \| 保留库复用 \| 是 \| 否 \| 是 \| 是 \| 是 \| **是** \| \| 兼容风险 \| 无 \| 高 \| 中 \| 低 \| 高 \| **中(v0.x 可控)** \|"
  - rationale: 7.6 的权衡矩阵以公共面收敛、库复用、兼容风险等与约束直接对应的维度对比五个方案。
- **alts.consistency** [core, level 2] — 第 7 章结论是否与 Goals、架构选型一致？
  - evidence `7. 替代方案与权衡`: "结论：本次选型与 G1–G5 一致；它收敛公开面但保留 SPEC-001 承诺的扩展能力，且不引入类型循环或额外目录层级。"
  - normalized: "结论:本次选型与 G1–G5 一致;它收敛公开面但保留 SPEC-001 承诺的扩展能力,且不引入类型循环或额外目录层级。"
  - rationale: 结论显式对齐 G1–G5 与第 3 章的选型理由，未与 Goals 或架构矛盾。

## 跨章自洽 (cross_consistency)

- **x.goals_trace** [core, level 2] — 后续章节是否逐条回应 Goals？
  - evidence `全文`: "Goal 与章节的对应关系：G1 由 4.1 和 4.6 的导入边界覆盖；G2 由 4.2、4.3、4.4 覆盖；G3 由 4.8 覆盖；G4 由 4.9 覆盖；G5 由 5.2、5.3 和 6.3 覆盖。"
  - normalized: "Goal 与章节的对应关系:G1 由 4.1 和 4.6 的导入边界覆盖;G2 由 4.2、4.3、4.4 覆盖;G3 由 4.8 覆盖;G4 由 4.9 覆盖;G5 由 5.2、5.3 和 6.3 覆盖。"
  - rationale: 4.6 末尾逐条给出 G1–G5 到后续章节的映射，每个 Goal 都能找到对应设计。
- **x.nfr_arch** [core, level 2] — NFR 与架构、选型是否一致？
  - evidence `全文`: "* **包数量**：排除 '/internal/' 后共 6 个包（根包、'cmd/mediadetect' 和四个领域包），其中可被下游导入的库包为 5 个；'internal/' 下为 2 个包。"
  - normalized: "* **包数量**:排除 '/internal/' 后共 6 个包(根包、'cmd/mediadetect' 和四个领域包),其中可被下游导入的库包为 5 个;'internal/' 下为 2 个包。"
  - evidence `全文`: "* **CLI 文件预算**：'main.go' ≤120 行；'config.go' ≤120 行；'args.go' 和 'output.go' ≤200 行；'input.go' ≤100 行；'help.go' ≤80 行。验收用 'wc -l'。"
  - normalized: "* **CLI 文件预算**:'main.go' ≤120 行;'config.go' ≤120 行;'args.go' 和 'output.go' ≤200 行;'input.go' ≤100 行;'help.go' ≤80 行。验收用 'wc -l'。"
  - rationale: 5.2 的 6+2 包数量与 G1/3.2 的布局一致，5.3 的文件预算与 4.8 的拆分表一致，NFR 与架构选型无矛盾。
- **x.rollback_release** [core, level 2] — 回滚与发布策略是否一致？
  - evidence `全文`: "3. **发布段**：CI 全绿后打 'v0.2.0' tag；tag 推送后按 SPEC-001 6.5 不移动、不删除。"
  - normalized: "3. **发布段**:CI 全绿后打 'v0.2.0' tag;tag 推送后按 SPEC-001 6.5 不移动、不删除。"
  - evidence `全文`: "* **回滚步骤**：在 tag 推送前，直接回退实现段提交并恢复文档状态；不涉及数据或运行时。若 'v0.2.0' 已推送且发现阻断问题，按 SPEC-001 6.5 发布 'v0.2.1' 修复，必要时 'retract' 'v0.2.0'，不移动既有 tag。"
  - normalized: "* **回滚步骤**:在 tag 推送前,直接回退实现段提交并恢复文档状态;不涉及数据或运行时。若 'v0.2.0' 已推送且发现阻断问题,按 SPEC-001 6.5 发布 'v0.2.1' 修复,必要时 'retract' 'v0.2.0',不移动既有 tag。"
  - rationale: 6.1 的 tag 不可变发布节奏与 6.4 的 tag 前后回滚策略一致。

## 证据卫生 (evidence_hygiene)

- **x.no_placeholders** [core, level 2] — 是否没有把 无 / ... / 待补充 / TBD 当作实质回答？
  - evidence `全文`: "* 无数据库、无索引、无持久化数据，不需要数据迁移。"
  - normalized: "* 无数据库、无索引、无持久化数据,不需要数据迁移。"
  - rationale: 全文没有 TBD/待补充/TODO 等占位；「无」在此是明确的迁移结论，'...' 仅作为路径或结构体字面量简写，不构成实质回答的占位。
- **x.no_code** [core, level 2] — 是否没有堆砌实现代码、测试日志或偶发报错？
  - evidence `全文`: "gofmt -l . go mod tidy -diff go vet ./... go test ./... go build -o /tmp/mediadetect ./cmd/mediadetect go list ./... \| grep -v '/internal/'"
  - normalized: "gofmt -l . go mod tidy -diff go vet ./... go test ./... go build -o /tmp/mediadetect ./cmd/mediadetect go list ./... \| grep -v '/internal/'"
  - rationale: 全文代码块只有目录树、mermaid 拓扑/流程和 shell 命令，没有实现代码、测试日志或偶发报错堆砌。
- **x.numbers_sourced** [core, level 2] — 关键数字是否有出处，或标了 [estimated]？
  - evidence `全文`: "1. **CLI 入口文件承担了过多职责。** 'cmd/mediadetect/main.go' 为 484 行、17 个函数，同时包含 'main/run'、参数解析、stdin 读取、TTY 判断、JSON 输出、错误输出、退出码映射、verbose 输出和 help 文本。改动输出格式或退出码时，评审者必须在一个文件内跨 400 多行定位；新增 flag 会继续推高该文件。"
  - normalized: "1. **CLI 入口文件承担了过多职责。** 'cmd/mediadetect/main.go' 为 484 行、17 个函数,同时包含 'main/run'、参数解析、stdin 读取、TTY 判断、JSON 输出、错误输出、退出码映射、verbose 输出和 help 文本。改动输出格式或退出码时,评审者必须在一个文件内跨 400 多行定位;新增 flag 会继续推高该文件。"
  - evidence `全文`: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用；但 'llm' 只在 'cmd/mediadetect' 中被引用，'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包，它们就从实现细节变成事实上的公共 API，后续任何内部调整都要考虑兼容或提版本。"
  - normalized: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用;但 'llm' 只在 'cmd/mediadetect' 中被引用,'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包,它们就从实现细节变成事实上的公共 API,后续任何内部调整都要考虑兼容或提版本。"
  - rationale: 结构盘点的关键数字绑定到具体文件、行号或 README 行，可在仓库内复核；NFR 数字是验收阈值而非实测结果，无需 [estimated]。
- **x.no_fabricated_refs** [core, level 2] — 是否没有捏造 SPEC 引用、depends_on 目标或 M<N>？
  - evidence `全文`: "仓库当前没有 'docs/architecture/' 下的受管架构文档；SPEC-001 §3.2 是现状模块划分与职责的 SSOT，本 Spec 只描述其增量变更，不复制完整全局拓扑。"
  - normalized: "仓库当前没有 'docs/architecture/' 下的受管架构文档;SPEC-001 §3.2 是现状模块划分与职责的 SSOT,本 Spec 只描述其增量变更,不复制完整全局拓扑。"
  - evidence `全文`: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用；但 'llm' 只在 'cmd/mediadetect' 中被引用，'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包，它们就从实现细节变成事实上的公共 API，后续任何内部调整都要考虑兼容或提版本。"
  - normalized: "2. **公开面与实际支持面不一致。** README 第 274 行明确把 'parser'、'probe'、'tmdb'、'matcher'、'llm'、'collect' 六个包都列为可直接使用;但 'llm' 只在 'cmd/mediadetect' 中被引用,'collect' 只在根包中被引用。下游一旦按照 README 依赖这两个包,它们就从实现细节变成事实上的公共 API,后续任何内部调整都要考虑兼容或提版本。"
  - rationale: 引用集中在 SPEC-001 的既有章节（6.5、§3.2、§4.4.1 等）和 README 行号，均可在上下文中对上；全文没有 M<N> 形式的里程碑引用。

## Audit failures

None.
