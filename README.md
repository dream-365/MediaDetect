# MediaTitle

MediaTitle 是一个媒体库整理产品：由 `media-title` Agent Skill 交付，底层使用无状态、只读的 `mediadetect` 检测引擎。输入文件或目录，引擎输出 JSON，说明它是电影、剧集、季、系列、合集、非正片、附属文件还是其他类型；开启 TMDB 匹配时，还会返回最佳条目和 `imdb_id`。

它不创建索引、不写 SQLite、不写缓存或临时文件，也不会修改输入目录中的任何文件。

- 当前版本：`0.3.0`
- JSON Schema 版本：`"1"`
- 最低 Go 版本：`1.27.1`
- License：[MIT](LICENSE)

## 产品入口：media-title Skill

MediaTitle 的产品形态是 `skills/media-title/` 技能。它扫描本地媒体库、生成整理计划，用户逐项确认后才执行，并保留可回滚的 intent/done 日志。

前置条件：

- Python 3.9+
- `mediadetect` 在 `PATH` 中，或通过 `--md-bin` / `MD_BIN` 指定（安装见下一节）
- 可选：`TMDB_API_KEY` 用于 TMDB 匹配

```bash
python3 skills/media-title/scripts/media_title.py scan "/path/to/library" --json
python3 skills/media-title/scripts/media_title.py plan --scan "<state_dir>/scan.json" --json
python3 skills/media-title/scripts/media_title.py apply \
  --plan "<state_dir>/plan.json" --expect-plan-id "<plan_id>" --select all --yes
```

完整工作流与安全约束见 [skills/media-title/SKILL.md](skills/media-title/SKILL.md)。

## 安装检测引擎 mediadetect

`mediadetect` 是 MediaTitle 的实现细节：技能通过子进程调用它，通常不需要最终用户直接操作。本仓库同时把它作为公开库与 CLI 发布。

```bash
go install github.com/dream-365/MediaTitle/cmd/mediadetect@v0.3.0
```

`go install` 会把二进制装到 `$(go env GOPATH)/bin/mediadetect`，不需要手写模块代理转义。module path 大小写敏感，代理转义形式为 `!media!title`。

从源码构建：

```bash
git clone https://github.com/dream-365/MediaTitle.git
cd MediaTitle
go build -o bin/mediadetect ./cmd/mediadetect
```

## 作为库使用

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	mediadetect "github.com/dream-365/MediaTitle/mediadetect"
)

func main() {
	res, err := mediadetect.Detect(context.Background(), "/path/to/movie.mkv", mediadetect.Options{
		TMDB: mediadetect.TMDBOptions{
			APIKey: os.Getenv("TMDB_API_KEY"), // 留空则自动降级
		},
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(res)
}
```

`Options` 的零值等同于 CLI 的 `--probe=auto --match=auto`。库调用不会读取环境变量，TMDB key、语言和 HTTP client 都通过 `TMDBOptions` 显式传入。

## 项目结构

```text
.
├── cmd/mediadetect/     # CLI：main、config、args、input、output、help
├── internal/
│   ├── collect/         # 只读遍历与探测（不对外）
│   └── llm/             # LLM 查询扩展（不对外）
├── parser/              # 公开：文件名解析
├── probe/               # 公开：ffprobe/exiftool 封装
├── tmdb/                # 公开：TMDB 客户端
├── matcher/             # 公开：匹配评分
├── doc.go               # 根包文档
├── options.go           # 公开配置与契约类型
├── result.go            # JSON 结果类型
├── errors.go            # 错误码与错误类型
├── detect.go            # Detect 入口与输入检查
├── aggregate.go         # 目录级聚合
├── mapping.go           # 本地类型映射
├── match.go             # 匹配编排
├── policy.go            # 匹配状态决策
├── warnings.go          # warning 去重与排序
├── *_test.go            # 根包测试
├── skills/media-title/  # 通用 Agent Skill：scan → plan → apply → rollback
└── docs/                # Spec 与质量报告
```

公开边界：根包 `mediadetect`、`parser`、`probe`、`tmdb`、`matcher` 可被下游导入；`internal/collect`、`internal/llm` 受 Go `internal` 规则约束，只能由本模块使用。

## 快速开始

```bash
# 检测单个文件
mediadetect "/path/to/Movie/Inception.2010.1080p.mkv"

# 检测一个目录
mediadetect "/path/to/TV/Show/Season 1"

# 从 stdin 读取一个路径
printf '%s\n' "/path/to/Movie/Inception.2010.mkv" | mediadetect -

# 完全离线：不探测、不访问 TMDB
mediadetect --match=off --probe=off "/path/to/Movie/Inception.2010.mkv"

# 人类可读的 JSON
mediadetect --pretty --verbose "/path/to/Movie/Inception.2010.mkv"
```

## 输入规则

- 只接受一个路径：文件或目录。
- 输入路径本身不能是符号链接；目录内部的符号链接会被跳过并计入 `summary.skipped_symlinks`。
- 目录默认最多遍历 8 层、最多收集 5000 个文件；隐藏项默认跳过，系统目录（如 `.mstruct`、`@eaDir`、`#recycle`）始终跳过。
- stdin 只接受一个非空路径；多行、空输入或 NUL 字节会返回用法错误。
- 路径不存在、根不可读或输入是符号链接时返回 `ok:false` 的错误对象，退出码 2。

## 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--probe auto\|off` | `auto` | `auto` 用 ffprobe/exiftool 读取时长、分辨率、编码；`off` 只按文件名检测 |
| `--match auto\|on\|off` | `auto` | 电影 TMDB 匹配；`off` 完全不发 HTTP 请求 |
| `--candidates 1-20` | `5` | 返回的备选候选数量，不含 `best` |
| `--max-queries 1-3` | `3` | 每个电影组的标题检索数 |
| `--llm-fallback` | 关闭 | 允许用 DeepSeek 生成额外查询词；缺 key 只降级为 warning |
| `--tmdb-base-url <url>` | 官方 API | 测试/本地 mock 用，不要用于生产 |
| `--max-depth 0-64` | `8` | 目录深度；`0` 表示不限制 |
| `--max-files 1-100000` | `5000` | 收集文件上限 |
| `--include-hidden` | 关闭 | 处理点号开头的文件/目录；系统目录仍跳过 |
| `--pretty` | 关闭 | 缩进输出 JSON |
| `--verbose` | 关闭 | 把摘要和 best 条目写到 stderr |
| `--version` | — | 输出 JSON 版本信息 |
| `-h` / `--help` | — | 输出文本帮助（唯一不是 JSON 的 stdout 模式） |

参数可以放在路径前后，也可以使用 `--` 终止参数解析。

## 输出结构

成功时 stdout 恰好一个 JSON 对象。核心字段：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 固定 `"1"` |
| `ok` | 本地检测完成时为 `true`；路径/输入错误时为 `false` |
| `input` | `{path, kind}`，`kind` 为 `file` 或 `directory` |
| `media_type` | 顶层媒体类型 |
| `confidence` | 顶层本地类型置信度：`high` / `medium` / `low` |
| `title` / `year` | 代表文件的标题和年份候选；无法确定时为 `null` |
| `summary` | 文件计数、季号、跳过/不可读计数、`distinct_movies` 等 |
| `files` | 文件级结果，按相对路径排序；文件输入时是单元素数组 |
| `match` | 顶层匹配摘要 |
| `detection` | `probe_mode`、`match_mode`、`warnings`、`truncated` |
| `attribution` | 实际调用过 TMDB 时为署名文本，否则 `null` |
| `error` | 仅 `ok:false` 时出现，`{code, message}` |

错误对象示例：

```json
{
  "schema_version": "1",
  "ok": false,
  "input": null,
  "error": {
    "code": "ERR_PATH_NOT_FOUND",
    "message": "path not found"
  }
}
```

### 文件级结果

`files[]` 的常用字段：

- `path` / `name` / `ext`：相对路径、文件名、扩展名。
- `role`：parser 角色，如 `feature`、`non_feature`、`subtitle`、`artwork`、`nfo`、`other`。
- `media_type` / `confidence`：文件级类型和置信度。
- `title_candidates` / `year_candidates`：文件名解析出的候选标题和年份。
- `season_episode` / `season` / `episode`：季集标记；中文“第 N 集”没有季号。
- `resolution` / `source` / `codec` / `release_group`：可选的命名线索。
- `group_key`：电影分组键；非电影为 `null`。
- `probe_status`：`ok`、`failed` 或 `skipped`。
- `duration_sec`：探测到的时长；未探测或失败时为 `null`。
- `match`：该文件自己的匹配结果。

### `match` 状态

| 状态 | 含义 |
| --- | --- |
| `high` / `medium` / `low` | 匹配成功，置信度不同 |
| `unmatched` | 没有达到接受阈值；可能有弱候选，也可能 `best=null` |
| `not_applicable` | 非电影，不参与 TMDB 电影匹配 |
| `disabled` | 未开启匹配，或 `auto` 模式没有 `TMDB_API_KEY` |
| `unavailable` | `auto` 模式下 TMDB 不可达；本地结果仍返回，退出 0 |
| `error` | `on` 模式下 TMDB 或 key 失败；退出 4 |
| `multiple` | 多电影组或 mixed 输入的顶层摘要；`best=null` |

`match.best` 是最佳候选，字段包括 `tmdb_id`、`imdb_id`、`title`、`original_title`、`release_date`、`year`、`runtime_sec`、`score`、`query`、`matched_by` 和 `evidence`。`match.candidates` 是不含 best 的备选候选，`imdb_id` 为 `null`。

## 媒体类型

| 类型 | 典型输入 |
| --- | --- |
| `movie` | 单个电影文件，或目录中只有一部电影 |
| `movie_collection` | 目录中有多部不同电影 |
| `tv_episode` | 单个剧集文件 |
| `tv_season` | 季目录，目录名含 `S01` / `Season 1` / `第 1 季` |
| `tv_series` | 只有剧集文件，但没有可识别的季目录 |
| `mixed` | 同时含电影和剧集 |
| `non_feature` | sample、OAD、OVA、花絮等非正片 |
| `auxiliary` | 字幕、封面、NFO 等附属文件 |
| `other` | 无法归类的其他文件，或空目录 |

## 环境变量

CLI 会读取以下环境变量；库调用通过 `Options` 显式传入。

| 变量 | 作用 |
| --- | --- |
| `TMDB_API_KEY` | `--match=auto/on` 时使用；缺失时 auto 降级为 disabled，on 返回 `ERR_TMDB_KEY_MISSING` |
| `DEEPSEEK_API_KEY` | `--llm-fallback` 时用于查询扩展；缺失只产生 `match.llm_key_missing` warning |
| `HTTPS_PROXY` / `HTTP_PROXY` | Go HTTP 客户端会自动使用；访问 TMDB 需要代理时设置 |
| `PATH` | 需要能找到 `ffprobe` 和 `exiftool`；缺失时探测降级 |

## 退出码

| 退出码 | 场景 |
| ---: | --- |
| 0 | 成功；包括 `unmatched`、`disabled`、`unavailable` |
| 1 | 参数错误、stdin 用法错误、无输入 |
| 2 | 路径不存在、输入符号链接、根不可读 |
| 3 | 内部错误、panic、JSON 编码失败 |
| 4 | `--match=on` 且 TMDB 匹配失败 |
| 130 | Ctrl-C / SIGTERM |

## 常见用法

### 只取关键字段

```bash
mediadetect --match=off --probe=off "/path/to/Movie/Inception.2010.mkv" \
| jq '{media_type, confidence, title, year, files: [.files[] | {path, media_type, probe_status}]}'
```

### 输出 `title original_title (year)`

```bash
mediadetect "/path/to/Movie/Inception.2010.mkv" 2>/dev/null \
| jq -r '.match.best as $b
         | if $b == null then "unmatched"
           else "\($b.title) \($b.original_title) (\($b.year // "-"))"
           end'
```

### 批量检测目录中的视频

```bash
root="/path/to/Movie"
find "$root" -maxdepth 1 -type f \( -name '*.mkv' -o -name '*.mp4' -o -name '*.m4v' \) \
| while IFS= read -r f; do
    printf '%s\t' "$(basename "$f")"
    mediadetect --match=off --probe=off "$f" 2>/dev/null \
    | jq -r '[.media_type, .confidence] | @tsv'
  done
```

### 查看警告和探测失败

```bash
mediadetect --pretty "/path/to/Movie/Inception.2010.mkv" \
| jq '{warnings: .detection.warnings, files: [.files[] | {path, probe_status, duration_sec}]}'
```

## media-title Agent Skill

`skills/media-title/` 是一个通用 Agent Skill，用 MediaDetect 的只读 JSON 输出生成电影/剧集整理计划。它先扫描、再出计划，用户逐项确认后才执行，并保留可回滚的 intent/done 日志。

```bash
python3 skills/media-title/scripts/media_title.py scan "/path/to/library" --json
python3 skills/media-title/scripts/media_title.py plan --scan "<state_dir>/scan.json" --json
python3 skills/media-title/scripts/media_title.py apply \
  --plan "<state_dir>/plan.json" --expect-plan-id "<plan_id>" --select all --yes
python3 skills/media-title/scripts/media_title.py rollback \
  --plan "<state_dir>/plan.json" --expect-plan-id "<plan_id>" --select all --yes
```

技能本身只依赖 Python 3.9+ 标准库；MediaDetect 通过 `--md-bin` 或 `MD_BIN` 指定。详细工作流见 `skills/media-title/SKILL.md`，命名规则见 `skills/media-title/references/naming.md`。

`scan` 默认跳过名称已含 `{tt...}`/`{tmdb...}` 的已整理目录和文件，写入 `skipped/already_organized`，不调用 MediaDetect。需要强制重扫这些条目时加 `--include-organized`。

TMDB 匹配为 low/unmatched、score 低于 0.6 或 `title_hit=false` 的单元默认进入 `unplanned/low_confidence`，不会生成可执行计划；`--match=off` 等本地降级命名不受影响。`medium` 且 `title_hit=true` 可进入计划，但会带 `medium_confidence` warning，提示执行前核对。

SMB/NFS 文件系统可能既不支持原子 no-replace，也不支持硬链接。默认 `strict` 模式会以 `E_NO_REPLACE_UNSUPPORTED` 拒绝执行，媒体文件零改动。只有用户明确接受非原子移动的竞态风险时，才可以在 `apply` 和 `rollback` 上同时加 `--no-replace=check`（或设置 `MEDIA_TITLE_ALLOW_CHECK_RENAME=1`）；该模式会校验 size/内容指纹，结果输出 `non_atomic_move` 警告，日志记录 `move_method`/`atomic`/`validation`。

## 无状态与只读

- 不写输入目录，不创建索引、SQLite、缓存或临时文件。
- 不跟随输入根符号链接；目录内符号链接跳过并计数。
- `--match=off` 零 HTTP；`--probe=off` 不启动 ffprobe/exiftool。
- TMDB/LLM 密钥、URL query 和响应 body 不会出现在正常 JSON 或 stderr 中。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| `ERR_PATH_NOT_FOUND`，退出 2 | 检查路径；SMB 未挂载时先恢复挂载 |
| `ERR_INPUT_SYMLINK`，退出 2 | 传真实路径，不要传符号链接 |
| `probe.failed` | 文件损坏或工具不支持；本地类型仍按文件名给出 |
| `probe.unavailable` | `ffprobe` 和 `exiftool` 都不可执行；安装工具或使用 `--probe=off` |
| `match.unavailable`，退出 0 | `auto` 模式网络/TMDB 不可达；检查代理或稍后重试 |
| `ERR_TMDB_KEY_MISSING`，退出 4 | 设置 `TMDB_API_KEY`，或改用 `--match=auto/off` |
| `match.llm_key_missing` | 缺少 `DEEPSEEK_API_KEY`；仅影响 LLM 查询扩展 |

## 已知限制

- 裸数字集号（如 `Example.Documentary.01.mkv`）仍可能被判为电影。
- `S01E01E02`、`S01E01E02E03` 这类连续多集写法自 v0.2.1 起识别为 `tv_episode` 并输出范围；非连续写法（如 `S01E01E03`）仍不识别。
- `Show S01`、`Show.Season.1` 这类目录名当前按 `tv_series` 处理；只识别 `S01`、`Season 1`、`第 N 季`。
- 无季集上下文的 `NxM` 数字 token 仍可能有歧义。
- 中英文双命名且未匹配成功时，`distinct_movies` 可能多算。
- 自 v0.2.2 起，文件名年份与 TMDB 年份相差超过 5 年且 runtime 证据不成立时，`confidence` 最高 `low`，并输出 `match.year_conflict`；runtime 证据成立时保留原 confidence，但仍输出 warning。
- 导演剪辑版/重映条目的年份差异、正确 best 但 margin 过低的候选，按既有 matcher 规则处理，详见 [SPEC-001 附录 B](docs/specs/SPEC-001-media-type-detection/spec.md#附录-b已知限制)。
- TMDB 剧集匹配尚未实现；剧集只做本地识别。

## 下游集成

任何 Go 项目都可以通过 `require github.com/dream-365/MediaTitle vX.Y.Z` 使用本模块。v0.3.0 起根包位于 `github.com/dream-365/MediaTitle/mediadetect`，公开包还包括 `parser`、`probe`、`tmdb` 和 `matcher`；`collect`、`llm` 自 v0.2.0 起位于 `internal/`，只能由本模块与 CLI 使用。本仓库不包含任何下游项目的包装代码。

旧 module path 的已发布 pin 版本（含 v0.2.2）仍可安装。旧路径的 `@latest` 行为取决于解析模式：`GOPROXY=direct` 下会解析到 v0.3.0 并报路径不一致，部分代理仍解析到 v0.2.2；需要旧版本时请固定 `@v0.2.2`。

## License 与 TMDB

本项目使用 [MIT License](LICENSE)。

本产品使用 TMDB API，但未获得 TMDB 的认可或认证。TMDB 数据的使用受 [TMDB Terms of Use](https://www.themoviedb.org/documentation/api/terms-of-use) 约束；分发或展示 TMDB 数据时需遵守其署名要求。MediaDetect 只在用户开启 TMDB 匹配且实际发起请求时输出 attribution。
