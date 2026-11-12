---
type: changelog
status: Published
owner: alang
depends_on: []
updated_at: 2026-11-12
---

# Changelog: SPEC-001 MediaDetect 媒体检测库与 CLI

## [2026-11-12] - SPEC-003 G6 连续多集解析

- **修改类型**: Changed
- **影响范围**: §2.1 G2；§4.5.1.1；附录 B；`tasks.md` 的 `spec_sha256`
- **变更原因**: SPEC-003 G6 需要修复 `S01E01E02`/`S01E01E02E03` 多集解析，并同步 `title_candidates` 清理与 `v0.2.1` 版本口径。按 CLAUDE.md，先把本 Spec 状态回退为 `In Review`、更新 `updated_at`、记录变更；回退期间不修改生产代码。
- **具体内容**:
  - 连续多集按**集号数值连续**识别，输出 `S01E01-E02`/`S01E01-E03`，按 `tv_episode` 分类
  - 非连续 `S01E01E03`/`S01E01E02E04` 仍不匹配，保持 movie，由技能层标记 `unsupported_multi_episode`
  - `mapping.go` 的 `displayTitles`/`stripEpisode` 同步剥离 2 段/3 段连续 E 段，`title_candidates` 不含 `E02E03`
  - 版本口径改为 `v0.2.1`；完成实现与验证后恢复 `Approved`

## [2026-11-11] - 修正交叉引用

- **修改类型**: Fixed
- **影响范围**: §4.4.1；`tasks.md` 的 `spec_sha256`
- **变更原因**: §4.4.1 引用了不存在的 SPEC-002 §4.4.1；按 CLAUDE.md 先将本 Spec 状态回退为 `In Review`，修正后恢复 `Approved`。
- **具体内容**:
  - 将“SPEC-002 §4.4.1”改为“SPEC-002 §4.2/§4.3”，与同节开头的替代说明一致
  - 重算 `tasks.md` 的 `spec_sha256`，使其与修订后的 `spec.md` 一致

## [2026-11-11] - SPEC-002 包边界替代

- **修改类型**: Changed
- **影响范围**: §2.1 G2；§3.2；§4.4.1；§4.4.1.1；`tasks.md` 的 `spec_sha256`
- **变更原因**: SPEC-002 将 `collect`、`llm` 移入 `internal/`，并让根包自行定义公共类型。按 CLAUDE.md，先把本 Spec 状态回退为 `In Review`，更新 `updated_at`，记录变更并写入替代说明，再恢复 `Approved`；回退期间不修改生产代码。
- **具体内容**:
  - §2.1 G2 的包清单改为 `internal/llm`、`internal/collect`，其余验收不变
  - §3.2 的模块布局与 `collect` 位置改由 SPEC-002 §4.1 定义；`llm`、`collect` 标注为内部包
  - §4.4.1 的 `Resolver` 类型改为根包 `QueryResolver`；`Prober` 返回根包 `MediaInfo`；删除 `type MediaInfo = probe.Info` 与类型别名表述，改为根包定义并在边界显式转换；新增 `ErrProbeUnavailable` 错误契约
  - §4.4.1.1 标注 `collect` 不再是公开包，公开契约由 SPEC-002 §4.7 的迁移说明替代
  - 重算 `tasks.md` 的 `spec_sha256`，使其与修订后的 `spec.md` 一致
  - 历史注记：v0.1.1 条目中的“`SPEC-002` → `SPEC-001`”是编号整理前的旧编号，指当前 SPEC-001；当前仓库的 SPEC-002 是包边界 Spec，与那次改名无关

## [2026-11-11] - v0.1.1 文档整理与版本注入

- **修改类型**: Changed / Fixed
- **影响范围**: SPEC 编号与目录；`spec.md`/`tasks.md`/`changelog.md`；质量报告；README；`cmd/mediadetect`
- **变更原因**: 独立仓库的 spec 应从 `SPEC-001` 开始；公开文档不应包含上游项目的内部路径与历史迁移上下文；`--version` 不应硬编码
- **具体内容**:
  - `SPEC-002` → `SPEC-001`，目录同步改名
  - `spec.md` 改写为产品方案（背景、目标、架构、发布、替代方案），删除上游项目的内部实现与迁移过程
  - `tasks.md` 收敛为 v0.1.0/v0.1.1 交付清单
  - 质量报告去除上游项目名称、内部路径与历史任务编号；删除内部评审记录
  - README 只保留下游集成说明
  - `--version` 优先使用 `debug.ReadBuildInfo()`，并支持 `-ldflags "-X main.version=x.y.z"`，不再硬编码

## [2026-11-11] - v0.1.0 首次发布

- **修改类型**: Added
- **影响范围**: 全仓
- **变更原因**: 把已验证的媒体检测能力发布为独立、无状态、可版本化的 Go module 与 CLI
- **具体内容**: 首次发布 parser/probe/tmdb/matcher/llm/collect/根包与 `cmd/mediadetect`；单 JSON 输出；电影 TMDB 匹配与 `imdb_id`；剧集本地识别；无 key/无网络降级；MIT License；macOS + Linux CI；合成/匿名测试语料；SPEC-001 与质量报告
