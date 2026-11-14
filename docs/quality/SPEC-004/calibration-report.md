# SPEC-004 匹配安全子集校准报告

日期：2026-11-14

适用版本：MediaDetect `0.2.2`；media-title `0.1.1`。

## 范围

本轮只验证安全关键子集：

- 硬年份冲突 `|year_delta| > 5` 且 runtime 不成立 → confidence 最高 low；runtime 成立保留原 confidence + warning。
- media-title plan 继承文件级 `match.status`/`margin`/`score`/`title_hit`；low/unmatched/score<0.6/title_hit=false → `unplanned/low_confidence`；disabled/unavailable 例外。
- SMB check-then-rename 的 size/内容指纹与 mtime 恢复。

不包含：超集/续集/短别名规则、B1 跨语言召回、B2 TV、短片/赛事/语言过滤。

## 样本

| 样本 | 期望 | 结果 |
| --- | --- | --- |
| A1 `Give.Me.Five.2022` vs 1984 | MediaDetect low + plan unplanned | matcher 单测 delta>5；`fixtures/a1-scan.json` 离线 plan 回归 |
| A2 `诗人.BARDO...2022` 文件级 low | plan 不再 high | `fixtures/a2-scan.json` 离线 plan 回归 |
| D `蚁人2.2022` vs 2018（delta=4） | 保持 medium | matcher 软年份单测 |
| D `分贝`/`原样复制`/`喜欢妳是妳`/`秒速5厘米` | 不因新门控降级 | 本轮仅用代理单测（delta≤5 与 medium+title_hit=true），未回放真实样本 |
| SMB rename 改写 mtime | apply/rollback 成功 + `mtime_rewritten` | fsops/apply/rollback mock |
| 内容/尺寸不一致 | `E_NON_ATOMIC_MOVE_FAILED` | fsops 校验失败单测 |

## 已知限制

- `Her Story→Herstory`、`Eye for an Eye→Eye for an Eye 2` 等 delta≤1、title_hit=true 的错误不在本轮规则内。
- 超集/子串、续集编号、TV、跨语言召回仍可能误配。
- 低分门控降低召回；部分正确低分样本会进入 `unplanned/low_confidence`。
- 历史 225 真实基线未重放；本报告不宣称外部基线比例。

## 验证命令

```bash
go test ./...
go vet ./...
gofmt -l .
go mod tidy -diff
MD_BIN=/tmp/md-accept python3 -m unittest discover -s skills/media-title/tests
```

当前结果：Go 测试全绿；Python 108 项通过。
