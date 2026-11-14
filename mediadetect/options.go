package mediadetect

import (
	"context"
	"net/http"
)

// ProbeMode controls ffprobe/exiftool usage.
type ProbeMode string

const (
	ProbeAuto ProbeMode = "auto"
	ProbeOff  ProbeMode = "off"
)

// MatchMode controls TMDB matching.
type MatchMode string

const (
	MatchAuto MatchMode = "auto"
	MatchOn   MatchMode = "on"
	MatchOff  MatchMode = "off"
)

// TMDBOptions configures the TMDB adapter.
type TMDBOptions struct {
	APIKey         string
	BaseURL        string
	Language       string
	MaxQueries     int
	CandidateLimit int
	HTTPClient     *http.Client
	CacheLimit     int
}

// Prober reads technical metadata. Probe=off injects a collector sentinel
// internally; external callers normally leave this nil.
type Prober interface {
	Probe(ctx context.Context, path string) (MediaInfo, error)
}

// MediaInfo is the technical subset collected for each file. Its fields must
// stay in sync with probe.Info; the root package converts at the boundary.
type MediaInfo struct {
	DurationSec int
	Resolution  string
	Codec       string
}

// QueryResolver is the optional LLM query expander.
type QueryResolver interface {
	Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error)
}

// Options controls one Detect call. The zero value means auto/auto with the
// documented defaults.
type Options struct {
	ProbeMode     ProbeMode
	MatchMode     MatchMode
	TMDB          TMDBOptions
	LLMFallback   bool
	Resolver      QueryResolver
	MaxDepth      *int
	MaxFiles      *int
	IncludeHidden bool
	Prober        Prober
}
