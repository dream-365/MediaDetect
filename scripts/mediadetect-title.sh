#!/usr/bin/env bash
# 调用 mediadetect 匹配一个电影文件或电影目录，匹配成功时输出：
#   title original_title (year) {imdb_id}
# original_title 缺失（null/空）或与 title 相同时省略该段，输出 title (year) {imdb_id}。
# imdb_id 缺失时改用 TMDB id，形如 {tmdb387830}。
# 目录里有多个电影时，每个匹配成功的电影输出一行。
# 若输入是目录且目录名已含 {...} 形式（如 "片名 (1995) {tt0113243}"），
# 视为已重命名过，直接跳过而不调用 mediadetect（退出码 0）。
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
#   MD_RENAME          ask | off（默认 ask）。只推出一部电影时：
#                      推荐名称 = 脚本输出的那一行 "title original_title (year) {imdb_id}"；
#                      输入是目录 -> 目录名不同则重命名；
#                      输入是电影文件 -> 把文件移入推荐名称目录，
#                      status 为 high 时自动执行，其余状态询问 Y/n（回车默认确认）；
#                      目录不存在时新建，已存在则直接移入。
#                      提示走 /dev/tty，确认后才动文件系统。非交互场景请设为 off
#                      status 为 high 时绿色、unmatched 时红色高亮（NO_COLOR 可关闭）
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
MD_RENAME="${MD_RENAME:-ask}"

case "$MD_INCLUDE_UNMATCHED" in
  0 | 1) ;;
  *)
    echo "错误: MD_INCLUDE_UNMATCHED 只能是 0 或 1" >&2
    exit 1
    ;;
esac
case "$MD_RENAME" in
  ask | off) ;;
  *)
    echo "错误: MD_RENAME 只能是 ask 或 off" >&2
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
  MD_RENAME             ask | off（默认 ask）；目录重命名 / 电影文件建档，
                        status 为 high 时自动执行，其余需确认 Y/n
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

# 目录名已带 {...}（重命名过的痕迹）时跳过，避免重复检测。
dir_base=${path%/}
dir_base=${dir_base##*/}
if [ -d "$path" ] && [[ "$dir_base" =~ \{[^{}]+\} ]]; then
  echo "跳过: 目录名已含 {...} 标识，视为已重命名: ${dir_base}" >&2
  exit 0
fi

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
  def also_title($b):
    ($b.title | tostring) as $t
    | (($b.original_title // "") | tostring) as $o
    | if $o != "" and $o != $t then " \($o)" else "" end;
  def id_tag($b):
    (($b.imdb_id // "") | tostring) as $i
    | if $i != "" then $i
      elif (($b.tmdb_id // "") | tostring) != "" then "tmdb\($b.tmdb_id)"
      else "N/A" end;
  def fmt($b):
    ($b.title | tostring)
    + also_title($b)
    + " (\($b.year)) {\(id_tag($b))}";
  def accepted: . == "high" or . == "medium" or . == "low";
  def usable: ($weak == 1) or (.status? | accepted);

  [ (.match? | select(usable) | .best),
    (.files[]? | .match? | select(usable) | .best) ]
  | map(select(. != null))
  | unique_by(.tmdb_id)
  | .[]
  | fmt(.)
')

# 只推出一部电影时，按推荐名称整理输入：
#   推荐名称就是脚本输出的那一行：title original_title (year) {imdb_id}
#   目录 -> 目录名与推荐名称不同就重命名；电影文件 -> 新建同名目录并移入。
# 必须交互确认 y；非 TTY 或 MD_RENAME=off 时什么都不做。
# 重命名/移动失败只告警，不影响已经拿到的匹配结果和退出码。
# 读取确认：回车默认 yes；读不到输入（EOF/异常）按 no 处理，避免误动文件。
confirm() {
  local answer=
  if ! { read -r answer </dev/tty; } 2>/dev/null; then
    return 1
  fi
  case "$answer" in
    "" | y | Y | yes | YES | Yes) return 0 ;;
    *) return 1 ;;
  esac
}

maybe_organize() {
  [ "$MD_RENAME" = "ask" ] || return 0
  { : </dev/tty; } 2>/dev/null || return 0

  local pick suggestion pick_status pick_score media_type current parent parent_base target created
  pick=$(printf '%s' "$json" | jq -r --argjson weak "$MD_INCLUDE_UNMATCHED" '
    def accepted: . == "high" or . == "medium" or . == "low";
    def usable: ($weak == 1) or (.status? | accepted);
    def also_title($b):
      ($b.title | tostring) as $t
      | (($b.original_title // "") | tostring) as $o
      | if $o != "" and $o != $t then " \($o)" else "" end;
    def id_tag($b):
      (($b.imdb_id // "") | tostring) as $i
      | if $i != "" then $i
        elif (($b.tmdb_id // "") | tostring) != "" then "tmdb\($b.tmdb_id)"
        else "N/A" end;
    def name($b):
      ($b.title | tostring)
      + also_title($b)
      + " (\($b.year)) {\(id_tag($b))}";

    [ (.match? | select(usable) | {status: .status, best: .best}),
      (.files[]? | .match? | select(usable) | {status: .status, best: .best}) ]
    | map(select(.best != null))
    | unique_by(.best.tmdb_id)
    | if length == 1 and ((.[0].best.title // "") | tostring) != "" then
        .[0] as $p
        | $p.best as $b
        | [ (name($b)
             | gsub("/"; "-")
             | gsub(":"; " -")
             | gsub("[[:cntrl:]]"; " ")
             | gsub("^[[:space:]]+|[[:space:]]+$"; "")),
            ($p.status // "unknown"),
            (((($b.score // 0) * 100 | round) / 100) | tostring) ]
        | @tsv
      else empty end
  ') || return 0

  [ -n "$pick" ] || return 0
  IFS=$'\t' read -r suggestion pick_status pick_score <<<"$pick"
  [ -n "$suggestion" ] || return 0

  # high 绿色、unmatched 红色高亮；NO_COLOR 或 stderr 非终端时保持纯文本。
  local status_color= status_reset=
  if [ -z "${NO_COLOR:-}" ] && [ -t 2 ]; then
    case "$pick_status" in
      high) status_color=$'\033[1;32m' ;;
      unmatched) status_color=$'\033[1;31m' ;;
    esac
    status_reset=$'\033[0m'
  fi
  local status_display=$pick_status
  if [ -n "$status_color" ]; then
    status_display="${status_color}${pick_status}${status_reset}"
  fi

  media_type=$(printf '%s' "$json" | jq -r '.media_type // empty')
  current=${path%/}
  current=${current##*/}
  case "$current" in
    "" | "." | "..") return 0 ;;
  esac

  parent=${path%/}
  case "$parent" in
    */*) parent=${parent%/*} ;;
    *) parent=. ;;
  esac
  [ -n "$parent" ] || parent=/
  if [ "$parent" = "/" ]; then
    target="/${suggestion}"
  else
    target="${parent}/${suggestion}"
  fi

  if [ -d "$path" ]; then
    [ "$current" = "$suggestion" ] && return 0
    if [ -e "$target" ] || [ -L "$target" ]; then
      echo "提示: 同名目录已存在，跳过重命名: ${target}" >&2
      return 0
    fi
    printf '目录名与推荐标题不一致：\n  当前: %s\n  推荐: %s（status: %s, score: %s）\n' \
      "$current" "$suggestion" "$status_display" "$pick_score" >&2
    if [ "$pick_status" = "high" ]; then
      echo "status: high，自动确认重命名" >&2
    else
      printf '是否重命名为推荐名称？[Y/n] ' >&2
      if ! confirm; then
        echo "已保留原目录名" >&2
        return 0
      fi
    fi
    if mv -- "$path" "$target"; then
      echo "已重命名: ${current} -> ${suggestion}" >&2
      path=$target
    else
      echo "错误: 重命名失败: ${path}" >&2
    fi
    return 0
  fi

  # 文件输入：只处理被识别为电影的视频文件。
  [ -f "$path" ] || return 0
  [ "$media_type" = "movie" ] || return 0

  # 已经在推荐名称的目录里，就不再套一层。
  parent_base=${parent%/}
  parent_base=${parent_base##*/}
  [ "$parent_base" = "$suggestion" ] && return 0

  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ ! -d "$target" ]; then
      echo "提示: 同名文件已存在，跳过建档: ${target}" >&2
      return 0
    fi
    if [ -e "${target}/${current}" ]; then
      echo "提示: 目标目录中已存在同名文件，跳过移动: ${target}/${current}" >&2
      return 0
    fi
  fi

  if [ -d "$target" ]; then
    printf '建议把该视频移入已存在的目录：\n  文件: %s\n  目录: %s（status: %s, score: %s）\n' \
      "$current" "$suggestion" "$status_display" "$pick_score" >&2
  else
    printf '建议为该视频新建目录并移入：\n  文件: %s\n  目录: %s（status: %s, score: %s）\n' \
      "$current" "$suggestion" "$status_display" "$pick_score" >&2
  fi
  if [ "$pick_status" = "high" ]; then
    echo "status: high，自动确认执行" >&2
  else
    printf '是否执行？[Y/n] ' >&2
    if ! confirm; then
      echo "已保留原文件位置" >&2
      return 0
    fi
  fi

  created=0
  if [ ! -d "$target" ]; then
    if ! mkdir -- "$target"; then
      echo "错误: 无法创建目录: ${target}" >&2
      return 0
    fi
    created=1
  fi
  if mv -- "$path" "${target}/"; then
    if [ "$created" = 1 ]; then
      echo "已新建目录并移动: ${target}/${current}" >&2
    else
      echo "已移入已有目录: ${target}/${current}" >&2
    fi
    path="${target}/${current}"
  else
    echo "错误: 移动失败: ${path}" >&2
  fi
}

if [ -n "$out" ]; then
  printf '%s\n' "$out"
  maybe_organize
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
