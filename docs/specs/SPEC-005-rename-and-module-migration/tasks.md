---
type: tasks
status: Done
owner: alang
depends_on: []
spec: ./spec.md
spec_sha256: "52102467741899a206470fe04ac55166956cdbdfd52b680a2212d3f92694b716"
updated_at: 2026-11-14
---

# MediaTitle 仓库更名与模块路径迁移 执行拆解

| ID | 任务 | 覆盖 | 依赖 | 写入 | 完成标准 | 验证 |
|---|---|---|---|---|---|---|
| T1 | 统一 module path 与全部 Go import | G1 | — | go.mod, go.sum, doc.go, aggregate.go, detect.go, errors.go, mapping.go, match.go, options.go, policy.go, result.go, warnings.go, helpers_test.go, detect_test.go, mapping_test.go, match_detect_test.go, options_test.go, parser/, probe/, tmdb/, matcher/, internal/, cmd/ | `go list ./...` 的 8 个包全部以 `github.com/dream-365/MediaTitle` 开头；`go build ./...` 与 `go test ./...` 通过 | `go test ./...` |
| T2 | 迁移 CI 断言与构建输出 | G1 | T1 | .github/workflows/ci.yml | 私有依赖白名单、`result.go` 边界、临时消费者模块、版本断言均使用新路径；`go build` 使用 `-o`；包含 `check-ignore --no-index` 断言 | `go build -o /tmp/mediadetect ./cmd/mediadetect` |
| T3 | 根包下沉并修正忽略规则 | G2 | T1 | mediadetect/, .gitignore, scripts/, cmd/ | 根目录无 `*.go`；`mediadetect/` 含 15 个原包文件；`scripts/mediadetect-title.sh` 删除；`git check-ignore -q --no-index mediadetect/doc.go` 为非 0 | `test -z "$(find . -maxdepth 1 -name '*.go')"` |
| T4 | 收敛产品入口与仓库元数据 | G3 | T1, T3 | README.md, skills/media-title/SKILL.md | README 首屏以 `media-title` 技能为入口，CLI 标为实现细节；`SKILL.md` 含前置条件；仓库描述与 README 标题对齐 MediaTitle；历史文档之外无旧路径 | `test -z "$(grep -rn "dream-365/MediaDetect" --exclude-dir=.git --exclude-dir=docs .)"` |
| T5 | 版本升至 0.3.0 并准备发布资产 | G4 | T2, T4 | cmd/mediadetect/config.go, cmd/mediadetect/main_test.go, .github/workflows/ci.yml | `--version` 输出 `"version":"0.3.0"` 与 `"schema_version":"1"`；4 个平台二进制、技能包与 `checksums.txt` 可在临时目录生成 | `sh -c 'go run ./cmd/mediadetect --version > /tmp/version.json && grep -q "0.3.0" /tmp/version.json'` |
| T6 | 契约回归与发布后安装验证 | G5 | T1, T3, T4, T5 | — | Go 测试与技能测试通过；全新缓存下新路径 v0.3.0 与旧路径 v0.2.2 均可安装；旧 `@latest` 的预期错误记入 changelog | `python3 -m unittest discover -s skills/media-title/tests` |
