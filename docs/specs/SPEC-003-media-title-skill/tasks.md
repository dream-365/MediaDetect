---
type: tasks
status: Approved
owner: alang
depends_on: []
spec: ./spec.md
spec_sha256: "475b1c6eb8e2413998439868b88c2186f8813e58476d5278ced11d0a8d8c310c"
updated_at: 2026-11-12
---

# media-title 智能体技能 执行拆解

| ID | 任务 | 覆盖 | 依赖 | 写入 | 完成标准 | 验证 |
|---|---|---|---|---|---|---|
| T1 | 技能包骨架、session 模型、路径工具与计划 schema | G1, G4, G5 | — | `skills/media-title/SKILL.md`, `scripts/media_title.py`, `scripts/media_title_lib/{session,paths}.py`, `references/`, `assets/plan.schema.json`, `tests/test_session.py`, `tests/test_paths.py` | frontmatter 含 `name: media-title`；session ID 校验；一 session 一 plan；`<root>/.media-title/sessions/<id>/` 布局；`session_token`/`state_dir`/`applied-plan.json`；复制/移动 session 目录拒绝；原子写 JSON；`unplanned[]`/`skipped[]` schema；`os.scandir` 原始路径映射与 NFC 防御；保护根/越界/名称清洗/`samefile` | `python3 -m unittest discover -s skills/media-title/tests -p 'test_session.py'`；`... -p 'test_paths.py'` |
| T2 | 实现 `scan`：模式/根判定、单元提取、unplanned 兜底 | G2, G3, G5 | T1 | `scripts/media_title_lib/scan.py`, `tests/test_scan.py`, `tests/fixtures/` | 4.3.1 规则顺序正确：单电影目录正面校验（通用容器/未知条目/目录名不匹配负例）、季目录整名匹配、扁平季目录、季目录内单集文件 `needs_directory_mode`、单剧/多剧库根、散落电影+剧集 mixed、通用下载目录、同名不同年份、多剧混放、多分部变体；`--max-depth 0`；`scan.truncated` 即停止；`E_SCHEMA_UNSUPPORTED`/不可执行 md-bin/版本 JSON 不可解析；非连续多集（所有 media_type）/多分部/歧义剧名 `unplanned`；`unplanned[]` 逐条输出；扫描不写媒体文件 | `... -p 'test_scan.py'` |
| T3 | 实现 `plan`：命名、可信剧容器、sources[]、计划哈希 | G2, G3, G4 | T2 | `scripts/media_title_lib/plan.py`, `scripts/media_title_lib/naming.py`, `tests/test_plan.py`, `references/naming.md` | 电影名称格式；缺失字段省略；`sources[]` 覆盖所有 move（含祖先目录）；共享 mkdir；剧集结构、可信剧容器（名称一致性优先）、散落剧集 `(title, year)` 分组、CJK、季号未知、侧车、父目录同名跳过；操作排序/重叠检查；`plan_id` 内容哈希；`session_token`/`state_dir`；`unplanned[]` 契约与 reason_code；单元全有或全无；`applied-plan.json`；目录子树指纹；重复计划为空 | `... -p 'test_plan.py'`；黄金计划断言 |
| T4 | 实现 `fsops` 与原子预检：no-replace 探测、mkdir、remove_empty_dir | G4, G5 | T3 | `scripts/media_title_lib/fsops.py`, `tests/test_fsops.py` | 按 `st_dev` 和文件/目录分别在实际目标父目录做能力探测；Linux `renameat2(RENAME_NOREPLACE)`、macOS `renamex_np(RENAME_EXCL)`、文件 `link+unlink` 回退；目录无回退拒绝；TOCTOU 目标出现冲突；`link` 后 unlink 失败回滚 dst，崩溃对账按“完成移动”处理；`mkdir pre_exists/created` + ino；`remove_empty_dir` 非空跳过、ENOENT 幂等；跨设备/大小写/NFC 冲突拦截 | `... -p 'test_fsops.py'` |
| T5 | 实现 `apply`：expect-plan-id、强制选择、intent/done、共享 mkdir、锁 | G4 | T4 | `scripts/media_title_lib/apply.py`, `tests/test_apply.py` | `--expect-plan-id`/`--select`/`--yes` 必填；只接受 unit ID/`all`；`--retry-failed`；一次预检全部选中单元；共享 mkdir 去重；`state.json` 写 `applying/applied/failed`；intent 先写、done 后写；mkdir/remove 对账；done 后 state 前崩溃提升并继续剩余 unit；plan 后新增侧车 `E_SOURCE_STATE_MISMATCH`；按 dev/类型探测；`flock` 防同 session 并发 | `... -p 'test_apply.py'` |
| T6 | 实现 `rollback`：日志派生、intent 对账、目录指纹、幂等 | G4 | T5 | `scripts/media_title_lib/rollback.py`, `tests/test_rollback.py` | 与 apply 共用锁；默认从日志派生 unit；intent/done 对账；逆序恢复；整体预检（状态/逆向目标/token/plan）；目录递归 `to_subtree_hash` 冲突；`applied-plan.json` 回退；`E_SESSION_STATE_MISSING`/`E_NOTHING_TO_ROLLBACK`；rollback 自身 intent/done；`mkdir created=false` 不删除；空目录重建；二次回滚成功且不移动 | `... -p 'test_rollback.py'` |
| T7 | MediaDetect G6：连续多集 parser + displayTitles 清理 + v0.2.1 | G6 | Spec 批准 + SPEC-001/SPEC-002 回退流程 | `parser/parser.go`, `parser/*_test.go`, `mapping.go`, `detect_test.go`/`match_detect_test.go`, `cmd/mediadetect/config.go`, `cmd/mediadetect/main_test.go`, `README.md`, `docs/specs/SPEC-001-media-type-detection/spec.md`, `docs/specs/SPEC-001-media-type-detection/changelog.md`, `docs/specs/SPEC-002-package-boundary/spec.md`, `docs/specs/SPEC-002-package-boundary/changelog.md` | `S01E01E02`/`S01E01E02E03` 为 `tv_episode` 且 `season_episode` 为范围；集号必须数值连续，`S01E01E03`/`S01E01E02E04` 不匹配；2 段/3 段 `title_candidates` 均为 `["Show"]`，不含 `E02E03`；`S01E01-E02` 不变；`defaultVersion`/README/SPEC-001/SPEC-002/`main_test.go` 均为 `0.2.1`；现有 Go 测试全绿 | `go test ./...`；`--version` 断言 `0.2.1`；CLI 冒烟 |
| T8 | 集成测试、安全走查、CI 与文档收尾 | G1, G5 | T1–T7 | `skills/media-title/tests/`, `references/mediadetect-json.md`, `.github/workflows/ci.yml`, `docs/specs/README.md`, `README.md`（技能入口说明） | 真实 mediadetect 完成 scan→plan→apply→rollback；伪造 mediadetect 覆盖 TMDB 分支；空格/引号/中文/NFD 路径；媒体树元数据指纹排除 `.media-title`；unplanned/skipped 逐条报告；plan 替换/删除、session 复制/移动拒绝；目录回滚新增嵌套文件冲突；G6 2/3 段 display 断言与 0.2.1 版本；CI Ubuntu/macOS 全绿；Go boundary 计数不变 | `go test ./...`；`python3 -m unittest discover -s skills/media-title/tests -v`；CI |

## 依赖关系

```text
T1 -> T2 -> T3 -> T4 -> T5 -> T6
T2, T3 --------> T8
T7 (CLI) ------> T8
T4, T5, T6 ----> T8
```

## 说明

* 任务按“先只读、后写入”的顺序推进：T2/T3 完成前没有任何写媒体文件代码；T4–T6 的写操作只处理临时测试目录。
* **所有无法唯一判定的情况必须 `unplanned`**：通用下载目录散落剧集、多剧混放、多分部/多版本、非连续多集、季号未知且无上下文、歧义根模式。不得为了“多整理一点”而猜测。
* T7 是本 Spec 明确授权的唯一 CLI 行为变更。按 CLAUDE.md，开始 T7 前先把 SPEC-001 与 SPEC-002 回退为 `In Review`、更新各自 `updated_at`、在其 `changelog.md` 追加记录；SPEC-003 批准后才改代码，完成后再把两份 Spec 恢复为 `Approved`。SPEC-002 的 G4/G5 版本口径与 `cmd/mediadetect/main_test.go` 必须同步为 `0.2.1`，否则 `go test ./...` 不会全绿。
* 任何超出 G6 的 CLI 变更都必须先修订 Spec 并重新批准；不得顺手修改。
* T8 的 `README.md` 变更只增加技能入口说明与已知限制同步，不改 MediaDetect 的其他行为文档。
