package main

import (
	"strconv"
	"strings"

	"github.com/dream-365/MediaTitle"
)

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
