package main

import (
	"os"
	"regexp"
	"runtime/debug"
	"strings"

	"github.com/dream-365/MediaDetect"
	"github.com/dream-365/MediaDetect/internal/llm"
)

// defaultVersion is used for local builds where no release version is
// recorded. version is overridable at build time with
// -ldflags "-X main.version=x.y.z".
const defaultVersion = "0.2.1"

var version string

var releaseVersionRE = regexp.MustCompile(`^\d+\.\d+\.\d+$`)

// normalizeBuildVersion accepts only a released semver. Local `go build`
// inside a git checkout reports a VCS pseudo-version such as
// "0.0.0-20261112063404-8f87066b4abc"; that must not override the default.
func normalizeBuildVersion(value string) string {
	value = strings.TrimPrefix(value, "v")
	if releaseVersionRE.MatchString(value) {
		return value
	}
	return defaultVersion
}

// buildVersion prefers an explicit -ldflags value, then the released module
// version recorded by go install, then defaultVersion.
func buildVersion() string {
	if version != "" {
		return version
	}
	if info, ok := debug.ReadBuildInfo(); ok {
		return normalizeBuildVersion(info.Main.Version)
	}
	return defaultVersion
}

type config struct {
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

// toOptions maps parsed flags and environment variables onto the public
// library options. It is the only place the CLI assembles mediadetect.Options.
func (c config) toOptions() mediadetect.Options {
	opts := mediadetect.Options{
		ProbeMode:     c.probe,
		MatchMode:     c.match,
		MaxDepth:      c.maxDepth,
		MaxFiles:      c.maxFiles,
		IncludeHidden: c.includeHidden,
		LLMFallback:   c.llmFallback,
		TMDB: mediadetect.TMDBOptions{
			APIKey:         strings.TrimSpace(os.Getenv("TMDB_API_KEY")),
			BaseURL:        c.tmdbBaseURL,
			MaxQueries:     c.maxQueries,
			CandidateLimit: c.candidates,
		},
	}
	if c.llmFallback {
		// FromEnv only reads DEEPSEEK_*; a missing key degrades to a warning
		// inside Detect rather than aborting the local detection.
		if resolver, err := llm.FromEnv(); err == nil {
			opts.Resolver = resolver
		}
	}
	return opts
}
