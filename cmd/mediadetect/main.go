// Command mediadetect inspects one file or directory and prints one JSON
// object. It never creates an index, cache or temporary file.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/signal"
	"runtime/debug"
	"strconv"
	"strings"
	"syscall"

	"github.com/dream-365/MediaDetect"
	"github.com/dream-365/MediaDetect/llm"
)

// defaultVersion is used for local builds where no release version is
// recorded. version is overridable at build time with
// -ldflags "-X main.version=x.y.z".
const defaultVersion = "0.1.1"

var version string

// buildVersion prefers an explicit -ldflags value, then the module version
// recorded by go install/build, then defaultVersion.
func buildVersion() string {
	if version != "" {
		return version
	}
	if info, ok := debug.ReadBuildInfo(); ok {
		if v := info.Main.Version; v != "" && v != "(devel)" && !strings.HasSuffix(v, "+dirty") {
			return strings.TrimPrefix(v, "v")
		}
	}
	return defaultVersion
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

type config struct {
	path          string
	probe         mediadetect.ProbeMode
	match         mediadetect.MatchMode
	candidates    int
	maxQueries    int
	llmFallback   bool
	tmdbBaseURL   string
	maxDepth      *int
	maxFiles      *int
	includeHidden bool
	pretty        bool
	verbose       bool
	version       bool
	help          bool
}

func defaultConfig() config {
	return config{
		probe:      mediadetect.ProbeAuto,
		match:      mediadetect.MatchAuto,
		candidates: 5,
		maxQueries: 3,
	}
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) (exit int) {
	defer func() {
		if recovered := recover(); recovered != nil {
			writeError(stdout, stderr, mediadetect.ErrInternal, "internal error", 3, false)
			exit = 3
		}
	}()

	cfg, positional, parseErr := parseArgs(args)
	if parseErr != nil {
		return writeError(stdout, stderr, parseErr.code, parseErr.message, 1, false)
	}
	if cfg.help {
		fmt.Fprint(stdout, helpText)
		return 0
	}
	if cfg.version {
		writeJSON(stdout, map[string]string{
			"name":           "mediadetect",
			"display_name":   "MediaDetect",
			"version":        buildVersion(),
			"schema_version": mediadetect.SchemaVersion,
		}, cfg.pretty)
		return 0
	}

	path, inputErr := resolveInput(positional, stdin)
	if inputErr != nil {
		return writeError(stdout, stderr, inputErr.code, inputErr.message, 1, cfg.pretty)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	opts := mediadetect.Options{
		ProbeMode:     cfg.probe,
		MatchMode:     cfg.match,
		MaxDepth:      cfg.maxDepth,
		MaxFiles:      cfg.maxFiles,
		IncludeHidden: cfg.includeHidden,
		LLMFallback:   cfg.llmFallback,
		TMDB: mediadetect.TMDBOptions{
			APIKey:         strings.TrimSpace(os.Getenv("TMDB_API_KEY")),
			BaseURL:        cfg.tmdbBaseURL,
			MaxQueries:     cfg.maxQueries,
			CandidateLimit: cfg.candidates,
		},
	}
	if cfg.llmFallback {
		// FromEnv only reads DEEPSEEK_*; a missing key degrades to a warning
		// inside Detect rather than aborting the local detection.
		if resolver, err := llm.FromEnv(); err == nil {
			opts.Resolver = resolver
		}
	}

	result, err := mediadetect.Detect(ctx, path, opts)
	if err != nil {
		code := mediadetect.ErrInternal
		message := err.Error()
		exit := 3
		if e, ok := err.(*mediadetect.Error); ok {
			code = e.Code
			message = e.Message
			exit = exitCodeFor(code)
		}
		return writeError(stdout, stderr, code, message, exit, cfg.pretty)
	}
	if ctx.Err() != nil {
		return writeError(stdout, stderr, mediadetect.ErrCanceled, "detection canceled", 130, cfg.pretty)
	}
	if cfg.verbose {
		writeVerbose(stderr, result)
	}
	if err := writeJSON(stdout, result, cfg.pretty); err != nil {
		return writeError(stdout, stderr, mediadetect.ErrInternal, "json encoding failed", 3, cfg.pretty)
	}

	if result.Match.Status == "error" && result.Match.Error != nil {
		return 4
	}
	return 0
}

type cliError struct {
	code    string
	message string
}

func parseArgs(args []string) (config, []string, *cliError) {
	cfg := defaultConfig()
	var positional []string
	endFlags := false
	for i := 0; i < len(args); i++ {
		arg := args[i]
		if endFlags {
			positional = append(positional, arg)
			continue
		}
		if arg == "--" {
			endFlags = true
			continue
		}
		if arg == "-h" || arg == "--help" {
			cfg.help = true
			continue
		}
		if arg == "--version" {
			cfg.version = true
			continue
		}
		if arg == "-" || !strings.HasPrefix(arg, "-") {
			positional = append(positional, arg)
			continue
		}

		name, inline, hasInline := splitFlag(arg)
		value := func() (string, bool) {
			if hasInline {
				return inline, true
			}
			if i+1 < len(args) {
				i++
				return args[i], true
			}
			return "", false
		}
		switch name {
		case "--probe":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--probe requires a value")
			}
			switch mediadetect.ProbeMode(v) {
			case mediadetect.ProbeAuto, mediadetect.ProbeOff:
				cfg.probe = mediadetect.ProbeMode(v)
			default:
				return cfg, nil, flagError("--probe must be auto or off")
			}
		case "--match":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--match requires a value")
			}
			switch mediadetect.MatchMode(v) {
			case mediadetect.MatchAuto, mediadetect.MatchOn, mediadetect.MatchOff:
				cfg.match = mediadetect.MatchMode(v)
			default:
				return cfg, nil, flagError("--match must be auto, on or off")
			}
		case "--candidates":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--candidates requires a value")
			}
			n, err := strconv.Atoi(v)
			if err != nil || n < 1 || n > 20 {
				return cfg, nil, flagError("--candidates must be between 1 and 20")
			}
			cfg.candidates = n
		case "--max-queries":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--max-queries requires a value")
			}
			n, err := strconv.Atoi(v)
			if err != nil || n < 1 || n > 3 {
				return cfg, nil, flagError("--max-queries must be between 1 and 3")
			}
			cfg.maxQueries = n
		case "--max-depth":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--max-depth requires a value")
			}
			n, err := strconv.Atoi(v)
			if err != nil || n < 0 || n > 64 {
				return cfg, nil, flagError("--max-depth must be between 0 and 64")
			}
			cfg.maxDepth = &n
		case "--max-files":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--max-files requires a value")
			}
			n, err := strconv.Atoi(v)
			if err != nil || n < 1 || n > 100000 {
				return cfg, nil, flagError("--max-files must be between 1 and 100000")
			}
			cfg.maxFiles = &n
		case "--tmdb-base-url":
			v, ok := value()
			if !ok {
				return cfg, nil, flagError("--tmdb-base-url requires a value")
			}
			cfg.tmdbBaseURL = v
		case "--pretty":
			b, err := boolValue(inline, hasInline)
			if err != nil {
				return cfg, nil, flagError("--pretty must be true or false")
			}
			cfg.pretty = b
		case "--verbose":
			b, err := boolValue(inline, hasInline)
			if err != nil {
				return cfg, nil, flagError("--verbose must be true or false")
			}
			cfg.verbose = b
		case "--llm-fallback":
			b, err := boolValue(inline, hasInline)
			if err != nil {
				return cfg, nil, flagError("--llm-fallback must be true or false")
			}
			cfg.llmFallback = b
		case "--include-hidden":
			b, err := boolValue(inline, hasInline)
			if err != nil {
				return cfg, nil, flagError("--include-hidden must be true or false")
			}
			cfg.includeHidden = b
		default:
			return cfg, nil, flagError("unknown flag " + name)
		}
	}
	return cfg, positional, nil
}

func splitFlag(arg string) (name, value string, hasValue bool) {
	if i := strings.IndexByte(arg, '='); i >= 0 {
		return arg[:i], arg[i+1:], true
	}
	return arg, "", false
}

func boolValue(inline string, hasInline bool) (bool, error) {
	if !hasInline {
		return true, nil
	}
	return strconv.ParseBool(inline)
}

func flagError(message string) *cliError {
	return &cliError{code: mediadetect.ErrFlagInvalid, message: message}
}

func resolveInput(positional []string, stdin io.Reader) (string, *cliError) {
	if len(positional) > 1 {
		return "", &cliError{code: mediadetect.ErrInputMultiple, message: "exactly one path is allowed"}
	}
	if len(positional) == 1 && positional[0] != "-" {
		if strings.TrimSpace(positional[0]) == "" {
			return "", &cliError{code: mediadetect.ErrInputRequired, message: "a path is required"}
		}
		return positional[0], nil
	}
	if len(positional) == 1 || !isTTY(stdin) {
		path, err := readStdinPath(stdin)
		if err != nil {
			return "", err
		}
		return path, nil
	}
	return "", &cliError{code: mediadetect.ErrInputRequired, message: "a path is required"}
}

func readStdinPath(stdin io.Reader) (string, *cliError) {
	data, err := io.ReadAll(io.LimitReader(stdin, 1<<20))
	if err != nil {
		return "", &cliError{code: mediadetect.ErrInputInvalid, message: "cannot read stdin"}
	}
	if strings.ContainsRune(string(data), '\x00') {
		return "", &cliError{code: mediadetect.ErrInputInvalid, message: "stdin contains a NUL byte"}
	}
	var lines []string
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			lines = append(lines, line)
		}
	}
	switch len(lines) {
	case 0:
		return "", &cliError{code: mediadetect.ErrInputRequired, message: "stdin is empty"}
	case 1:
		return lines[0], nil
	default:
		return "", &cliError{code: mediadetect.ErrInputMultiple, message: "stdin must contain exactly one path"}
	}
}

func isTTY(r io.Reader) bool {
	f, ok := r.(*os.File)
	if !ok {
		return false
	}
	info, err := f.Stat()
	if err != nil {
		return false
	}
	return info.Mode()&os.ModeCharDevice != 0
}

func writeError(stdout, stderr io.Writer, code, message string, exit int, pretty bool) int {
	payload := map[string]any{
		"schema_version": mediadetect.SchemaVersion,
		"ok":             false,
		"input":          nil,
		"error": map[string]string{
			"code":    code,
			"message": message,
		},
	}
	writeJSON(stdout, payload, pretty)
	if stderr != nil {
		fmt.Fprintf(stderr, "%s: %s\n", code, message)
	}
	return exit
}

func writeJSON(w io.Writer, value any, pretty bool) error {
	var (
		data []byte
		err  error
	)
	if pretty {
		data, err = json.MarshalIndent(value, "", "  ")
	} else {
		data, err = json.Marshal(value)
	}
	if err != nil {
		return err
	}
	data = append(data, '\n')
	_, err = w.Write(data)
	return err
}

func exitCodeFor(code string) int {
	switch code {
	case mediadetect.ErrCanceled:
		return 130
	case mediadetect.ErrPathNotFound, mediadetect.ErrPathUnreadable, mediadetect.ErrInputSymlink:
		return 2
	case mediadetect.ErrInternal:
		return 3
	default:
		return 1
	}
}

func writeVerbose(w io.Writer, result mediadetect.Result) {
	kind := ""
	if result.Input != nil {
		kind = result.Input.Kind
	}
	fmt.Fprintf(w, "path=%s kind=%s media_type=%s confidence=%s files=%d match=%s%s\n",
		pathOf(result), kind, result.MediaType, result.Confidence, result.Summary.TotalFiles, result.Match.Status, bestVerbose(result.Match.Best))
	for _, file := range result.Files {
		fmt.Fprintf(w, "  %s type=%s probe=%s match=%s%s\n",
			file.Path, file.MediaType, file.ProbeStatus, file.Match.Status, bestVerbose(file.Match.Best))
	}
}

func bestVerbose(best *mediadetect.Candidate) string {
	if best == nil {
		return ""
	}
	imdb := "-"
	if best.IMDbID != nil {
		imdb = *best.IMDbID
	}
	return fmt.Sprintf(" best=%d %q imdb=%s score=%.3f", best.TMDBID, best.Title, imdb, best.Score)
}

func pathOf(result mediadetect.Result) string {
	if result.Input == nil {
		return ""
	}
	return result.Input.Path
}

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
