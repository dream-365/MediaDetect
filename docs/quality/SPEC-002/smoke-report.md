# SPEC-002 MediaDetect 上线冒烟记录

- 日期：2026-11-11
- Spec：`docs/specs/SPEC-002-media-type-detection/spec.md`（Approved）
- 二进制：`bin/mediadetect`（`go build -o bin/mediadetect ./cmd/mediadetect`）
- 环境：macOS，Go 1.27.1；真实 SMB 根在本次冒烟时未挂载，涉及真实 TMDB 的项用 mock 服务或既有基线

## 结果

| # | 检查 | 命令/证据 | 结果 |
| --- | --- | --- | --- |
| 1 | test/vet | `go test ./...`；`go vet ./...` | 通过 |
| 2 | CLI 构建 | `go build -o bin/mediadetect ./cmd/mediadetect` | 通过 |
| 3 | 模块独立性 | `go list -deps ./cmd/mediadetect \| grep -c github.com/dream-365/MStruct/` = 0；`go.mod` 不含 MStruct | 通过 |
| 4 | 电影文件 | `./bin/mediadetect --match=off --probe=off <movie>` → `media_type=movie`、`match.status=disabled`、`ok=true` | 通过 |
| 5 | 剧集文件 | `./bin/mediadetect --match=off --probe=off Show.2019.S01E01.1080p.mkv` → `media_type=tv_episode`、`season_episode=S01E01`、`match.status=not_applicable` | 通过 |
| 6 | 剧集目录 | `./bin/mediadetect --match=off --probe=off <show-dir>` → `media_type=tv_series`（或 `tv_season`，取决于目录名） | 通过 |
| 7 | stdin 与直接路径一致 | `printf '%s\n' <movie> \| ./bin/mediadetect ... -` 与直接传路径的 stdout `cmp` 一致 | 通过 |
| 8 | 无 key + auto | `TMDB_API_KEY= ./bin/mediadetect --match=auto <movie>` → `match.status=disabled`、`reason=no_tmdb_key`，退出 0 | 通过（单元测试 `TestCLINoKeyModes`） |
| 9 | 无 key + on | `TMDB_API_KEY= ./bin/mediadetect --match=on <movie>` → `match.status=error`、`ERR_TMDB_KEY_MISSING`，退出 4 | 通过（`TestCLINoKeyModes`） |
| 10 | mock TMDB | `--tmdb-base-url <httptest>` → `match.best.imdb_id` 非空且 `tmdb_id` 与 mock 一致 | 通过（`TestCLIMockTMDB`、`TestDetectMockMatchAndIMDb`） |
| 11 | 确定性 + 零写入 | 同一命令连续运行两次 stdout sha256 一致；`TestDetectZeroWrite`、`TestCLIZeroWrite` 快照内容/mtime/inode | 通过 |
| 12 | 零 HTTP | `TestDetectMatchOffMakesNoRequests`、`TestDetectTVMakesNoRequests` 计数 transport = 0 | 通过 |
| 13 | mstruct 回归 | root `go test ./...`；`internal/scanner` 通过；`cmd/mstruct` 冒烟断言 `files=3 added=3 changed=0 missing=0 probe_failed=1` 与 SQLite 行 | 通过（`TestScanSmoke`） |
| 14 | parser before/after | `TestParserFixes`：`Show.S01E01.srt` → `auxiliary/subtitle`；`Inception.2010.sample.mkv`、`Show.S01E01.sample.mkv`、`某动画.OAD.01.mkv` → `non_feature`；`Nova.2020.mkv` → `movie`；`Show.1x01.mkv` → `tv_episode` | 通过 |
| 15 | 输入边界 | 输入符号链接 → `ERR_INPUT_SYMLINK`/退出 2；`chmod 000` 根 → `ERR_PATH_UNREADABLE`/退出 2 | 通过（手工冒烟 + `TestDetectInputErrors`） |

## 手工冒烟命令

```bash
cd <MediaDetect-repo>
mkdir -p bin
go build -o bin/mediadetect ./cmd/mediadetect

TMP=$(mktemp -d)
mkdir -p "$TMP/movie" "$TMP/show"
touch "$TMP/movie/Inception.2010.1080p.mkv"
touch "$TMP/show/Show.2019.S01E01.1080p.mkv"

./bin/mediadetect --match=off --probe=off "$TMP/movie/Inception.2010.1080p.mkv"
./bin/mediadetect --match=off --probe=off "$TMP/show/Show.2019.S01E01.1080p.mkv"
./bin/mediadetect --match=off --probe=off "$TMP/show"
printf '%s\n' "$TMP/show/Show.2019.S01E01.1080p.mkv" | ./bin/mediadetect --match=off --probe=off -
```

## 未完成/待补

- 真实 100+ 目录样本的类型准确率：SMB 根未挂载，见 `calibration-report.md` 第 1 节。
- 真实 225 文件 `high imdb_id` 非空率：待根恢复后补测。
- `--match=auto` 真实 TMDB 的 P95 延迟：本次未在真实网络上测量；单组 60s deadline 与重试预算已由代码和 mock 测试覆盖。

## 回滚

1. 删除 `bin/mediadetect` 或恢复上一版二进制 / 上一个 tag。
2. 下游（如 MStruct）回退到上一个 `require` 版本；已推送 tag 不移动、不删除。
3. 运行 `go test ./...` 与 `go vet ./...` 确认通过。
4. 无数据回滚：mediadetect 不写索引、不做持久化。
5. parser 四项修正可单独回退，不影响模块边界。
