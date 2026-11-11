#!/usr/bin/env bash
# 调用 mediadetect 匹配一个电影文件或电影目录，匹配成功时输出：
#   title original_title (year) {imdb_id}
# 目录里有多个电影时，每个匹配成功的电影输出一行。
#
# 用法：
#   ./scripts/mediadetect-title.sh "/Volumes/.../大话西游之大圣娶亲 (1995)"
#   MD_MATCH=auto MD_PROBE=off ./scripts/mediadetect-title.sh "<路径>" --candidates 3
#
# 环境变量：
#   MD_BIN       mediadetect 可执行文件（默认 mediadetect）
#   MD_MATCH          on | auto | off（默认 on）
#   MD_PROBE          auto | off（默认 auto）
#   MD_INCLUDE_UNMATCHED  默认 1：只要 best 非 null 就输出（best-effort）。
#                         设为 0 时只输出 match.status 为 high/medium/low 的结果
#   TMDB_API_KEY      TMDB 密钥；MD_MATCH=on 时缺失会直接报错
#
# 默认 best-effort：unmatched 但有 best 候选时也会输出。
#
# 退出码：0 匹配成功；1 未匹配；其余透传 mediadetect（2 路径错误、4 TMDB 失败等）。

set -euo pipefail

MD_BIN="${MD_BIN:-mediadetect}"
MD_MATCH="${MD_MATCH:-on}"
MD_PROBE="${MD_PROBE:-auto}"
MD_INCLUDE_UNMATCHED="${MD_INCLUDE_UNMATCHED:-1}"

case "$MD_INCLUDE_UNMATCHED" in
  0 | 1) ;;
  *)
    echo "错误: MD_INCLUDE_UNMATCHED 只能是 0 或 1" >&2
    exit 1
    ;;
esac

usage() {
  cat >&2 <<'EOF'
用法: mediadetect-title.sh <路径> [mediadetect 额外参数...]

环境变量:
  MD_BIN       mediadetect 可执行文件（默认 mediadetect）
  MD_MATCH              on | auto | off（默认 on）
  MD_PROBE              auto | off（默认 auto）
  MD_INCLUDE_UNMATCHED  默认 1（best-effort）；设为 0 只输出 high/medium/low
  TMDB_API_KEY          MD_MATCH=on 时必填
EOF
}

if [ $# -lt 1 ]; then
  usage
  exit 1
fi
case "$1" in
  -h | --help)
    usage
    exit 0
    ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  echo "错误: 需要 jq（brew install jq）" >&2
  exit 127
fi
if ! command -v "$MD_BIN" >/dev/null 2>&1; then
  echo "错误: 找不到 ${MD_BIN}，请先安装：go install github.com/dream-365/MediaDetect/cmd/mediadetect@latest" >&2
  exit 127
fi

path=$1
shift

rc=0
json=$("$MD_BIN" --match="$MD_MATCH" --probe="$MD_PROBE" "$@" -- "$path") || rc=$?
if [ "$rc" -ne 0 ]; then
  code=$rc
  msg=$(printf '%s' "$json" | jq -r '
    (.error? // .match.error?)
    | select(. != null)
    | "\(.code): \(.message)"
  ' 2>/dev/null || true)
  echo "mediadetect 失败（退出码 ${code}）${msg:+: $msg}" >&2
  exit "$code"
fi

if [ -z "$json" ]; then
  echo "错误: mediadetect 未输出任何 JSON" >&2
  exit 3
fi
if ! printf '%s' "$json" | jq -e 'type == "object"' >/dev/null 2>&1; then
  echo "错误: mediadetect 输出无法解析为 JSON 对象" >&2
  exit 3
fi

# 顶层 best 与 files[].match.best 可能重复，按 tmdb_id 去重。
# 默认 best-effort；MD_INCLUDE_UNMATCHED=0 时仅接受 high/medium/low。
out=$(printf '%s' "$json" | jq -r --argjson weak "$MD_INCLUDE_UNMATCHED" '
  def fmt($b):
    "\($b.title) \($b.original_title) (\($b.year)) {\($b.imdb_id // "N/A")}";
  def accepted: . == "high" or . == "medium" or . == "low";
  def usable: ($weak == 1) or (.status? | accepted);

  [ (.match? | select(usable) | .best),
    (.files[]? | .match? | select(usable) | .best) ]
  | map(select(. != null))
  | unique_by(.tmdb_id)
  | .[]
  | fmt(.)
')

if [ -n "$out" ]; then
  printf '%s\n' "$out"
  exit 0
fi

status=$(printf '%s' "$json" | jq -r '.match.status // "unknown"')
reason=$(printf '%s' "$json" | jq -r '.match.reason // empty')
echo "未匹配（status: ${status}${reason:+, reason: ${reason}}）" >&2

weak_score=$(printf '%s' "$json" | jq -r '.match.best.score // empty')
if [ -n "$weak_score" ]; then
  echo "提示: best 候选未达接受阈值（score ${weak_score}），当前因 MD_INCLUDE_UNMATCHED=0 未输出" >&2
fi
exit 1
