package main

const helpText = `MediaDetect - read-only media type detection

usage:
  mediadetect [flags] <path>
  mediadetect [flags] -
  mediadetect --version
  mediadetect -h|--help

flags:
  --probe auto|off          probe feature files with ffprobe/exiftool (default auto)
  --match auto|on|off       TMDB movie matching (default auto; off makes no HTTP requests)
  --candidates 1-20         alternative candidates to return (default 5)
  --max-queries 1-3         title queries per movie group (default 3)
  --llm-fallback            ask DeepSeek for extra queries; missing key only warns
  --tmdb-base-url <url>     use a mock/local TMDB endpoint (testing only)
  --max-depth 0-64          directory depth; 0 means unlimited (default 8)
  --max-files 1-100000      collected file cap (default 5000)
  --include-hidden          process dot-prefixed entries (system dirs still skipped)
  --pretty                  indent the JSON output
  --verbose                 print a human-readable summary to stderr
  --version                 print version JSON
  -h, --help                print this help

stdin:
  With no path and a non-TTY stdin, one path is read from stdin.
  "mediadetect -" always reads stdin. Multiple non-empty lines are an error.

exit codes:
  0 success (including unmatched/disabled/unavailable)   1 usage error
  2 path missing/symlink/unreadable                      3 internal error
  4 --match=on infrastructure failure                   130 canceled
`
