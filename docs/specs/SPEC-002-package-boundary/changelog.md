---
type: changelog
status: Published
owner: alang
depends_on: []
updated_at: 2026-11-11
---

# Changelog: SPEC-002 MediaDetect Go 包边界与工程结构

## [2026-11-11] - 初始草案

- **修改类型**: Added
- **影响范围**: 全 Spec；SPEC-001 §3.2、§4.4.1.1；仓库包布局；CLI 文件划分；README 与版本口径
- **变更原因**: 公开面与实际支持面不一致，`collect` / `llm` 被 README 当作公开包但只服务内部与 CLI；根包公共 API 直接别名 `probe` / `matcher` 类型；CLI 入口 484 行；文档版本口径不一致
- **具体内容**:
  - 新建 SPEC-002，定义公开包为根包、`parser`、`probe`、`tmdb`、`matcher`；`collect`、`llm` 移入 `internal/`
  - 根包在 `options.go` 自行定义 `MediaInfo` 与 `QueryResolver`，移除对 `probe` / `matcher` 的类型别名
  - CLI 按 `main` / `config` / `args` / `input` / `output` / `help` 拆分
  - 明确 v0.2.0 发布、下游迁移、冒烟命令与回滚触发条件
  - 规划 SPEC-001 受影响条款的回退、替代说明与恢复流程

## [2026-11-11] - 独立评审修订

- **修改类型**: Changed
- **影响范围**: §1.2 痛点 4；§2.1 G1/G2/G4；§3.3/§3.4；§4.2/§4.3/§4.4/§4.6/§4.7/§4.8/§4.9；§5.2/§5.3；§6.1/§6.2/§6.3；§7.2
- **变更原因**: 独立对抗性评审发现两个阻断项和五个重要问题：SPEC-001 的 §4.4.1 公共 API 与 §2.1 G2 未纳入替代范围；`MediaInfo` 去别名会破坏 `Prober` 实现和 `detect_test.go`，但迁移矩阵与测试计划遗漏；`probe.ErrUnavailable` 仍穿透公共契约；版本口径整改范围与 CI 边界断言不足；`config → Options` 映射和外部 `internal` 导入测试描述不准确。
- **具体内容**:
  - 在 SPEC-001 替代范围中加入 §2.1 G2、§4.4.1 和 §4.4.1.1，并给出可执行的替代文本、历史 changelog 注记和 `tasks.md` 哈希重算步骤
  - 在 §4.2/§4.7 增加 `Prober` 破坏性变更、下游迁移和 `detect_test.go` 修改说明
  - 新增根包 `ErrProbeUnavailable`，与 `probe.ErrUnavailable` 同值，外部 `Prober` 无需导入 `probe`
  - 将版本痛点改为“版本口径分散”，明确以 git tag 为发布 SSOT，并保留 SPEC-001 的 v0.1.0 历史基线
  - 把包数量、领域包 import、`result.go` import 和外部 `internal` 导入断言写入 CI 与冒烟步骤
  - 增加 `config.toOptions()`，修正“新增 flag 只改 args/config”的可维护性承诺
  - 修正外部 `internal` 导入测试的假阳性风险，增加 `require`/`replace` 与错误文本断言
  - 修正 SPEC-001 §7.6 的引用，只保留 §1.2

## [2026-11-11] - 复核修订

- **修改类型**: Changed
- **影响范围**: §1.2 痛点 4；§2.1 G4；§4.2；§4.8；§4.9；§6.3
- **变更原因**: 技术复核确认外部 `internal` 导入测试仍写错：`go list .../internal/collect` 直接列出内部包不会触发导入者可见性检查，断言不会失败。另修正 `Prober` 签名措辞、`Options` 兼容性表述、版本口径与 CI 断言细节。
- **具体内容**:
  - 外部 `internal` 导入测试改为在临时 module 中创建真正 import 内部包的 `main.go`，执行 `GOFLAGS=-mod=mod go build ./...`，断言 stderr 包含 `use of internal package ... not allowed`
  - 明确 `boundary` CI 步骤在实现段随包移动加入，避免文档段因 8 ≠ 6 提前变红
  - 明确 `config.toOptions()` 负责读取 `TMDB_API_KEY` 和注入 `llm.FromEnv()` resolver
  - 将 `Prober` 的“签名不变”改为“方法名与参数不变，返回类型身份变化”
  - 将 `Options` 的“源码兼容”改为字段名与语义兼容，并指向 `Prober`/`Resolver` 的破坏性行
  - 版本验收改为 README 当前版本、README 安装 tag、`defaultVersion`、目标 tag 四者一致，以 git tag 为发布 SSOT
  - 补充 `ErrProbeUnavailable` 的 godoc 会显示 `probe.ErrUnavailable` 的权衡说明

## [2026-11-11] - 用户批准

- **修改类型**: Changed
- **影响范围**: frontmatter 状态；SPEC-001 替代说明；`tasks.md`
- **变更原因**: 用户明确批准 SPEC-002，进入实现前文档段。
- **具体内容**:
  - SPEC-002 状态由 `In Review` 改为 `Approved`
  - 按 §4.9/§6.1 完成 SPEC-001 的状态回退、changelog 记录、替代说明和 `tasks.md` 哈希重算，并恢复为 `Approved`
  - 新增 SPEC-002 `tasks.md`，按依赖关系拆解实现与发布步骤
