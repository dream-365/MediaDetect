---
type: changelog
status: Published
owner: alang
depends_on: []
updated_at: 2026-11-11
---

# Changelog: SPEC-001 MediaDetect 媒体检测库与 CLI

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
