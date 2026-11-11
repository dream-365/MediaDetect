---
type: tasks
status: In Progress
owner: alang
depends_on: []
spec: ./spec.md
spec_sha256: "016c1705a3619c4b8a2a14e4635b8d0214f22411555cb698f44bc889da48c2e2"
updated_at: 2026-11-11
---

# MediaDetect Go 包边界与工程结构 执行拆解

| ID | 任务 | 覆盖 | 依赖 | 写入 | 完成标准 | 验证 |
|---|---|---|---|---|---|---|
| T1 | 将 `collect`、`llm` 移入 `internal/` 并更新导入 | G1 | — | `internal/collect/`, `internal/llm/`, `collect/`, `llm/`, `aggregate.go`, `detect.go`, `match.go`, `cmd/mediadetect/main.go` | 排除 `/internal/` 后恰好 6 个包；`internal/` 下恰好 2 个包；四个领域包不导入 `/internal/`；模块外临时 module 导入 `internal/collect` 或 `internal/llm` 编译失败 | `go test ./...` |
| T2 | 根包自行定义 `MediaInfo`、`QueryResolver`、`ErrProbeUnavailable` | G2 | T1 | `result.go`, `options.go`, `errors.go`, `detect.go`, `detect_test.go` | `result.go` 不导入 `probe`/`matcher`；`Prober` 返回根包 `MediaInfo`；`MediaInfo` 与 `probe.Info` 无损互转；`errors.Is(ErrProbeUnavailable, probe.ErrUnavailable)` 成立 | `go test .` |
| T3 | 按职责拆分 `cmd/mediadetect` | G3 | T1, T2 | `cmd/mediadetect/` | `main.go` 只保留 `main` 与 `run`；`main.go` ≤120 行，`config.go` ≤120 行，`args.go`/`output.go` ≤200 行，`input.go` ≤100 行，`help.go` ≤80 行；`config.toOptions()` 负责环境变量与 resolver 注入 | `go test ./cmd/mediadetect` |
| T4 | 同步 README、公开包列表、版本口径与 Spec 索引 | G4 | T3 | `README.md`, `docs/specs/README.md`, `cmd/mediadetect/config.go` | README 公开包列表为根包、`parser`、`probe`、`tmdb`、`matcher`；README 当前版本、安装 tag、`defaultVersion`、目标 tag 均为 `0.2.0`；Spec 索引收录 SPEC-002 | `go test ./cmd/mediadetect -run TestCLIVersionAndHelp` |
| T5 | 加入 CI 边界断言并完成发布验证 | G5 | T1, T2, T3, T4 | `.github/workflows/ci.yml` | CI 的 `boundary` 步骤覆盖包数量、领域包 import、`result.go` import 和外部 `internal` 导入断言；`gofmt`、`tidy`、`vet`、`test`、`build` 全绿；`v0.2.0` tag 与 `--version` 一致 | `go test ./...` |
