package mediadetect

import (
	"context"
	"net/http"

	"github.com/dream-365/MediaDetect/matcher"
	"github.com/dream-365/MediaDetect/probe"
)

// SchemaVersion is the JSON contract version. Additive changes keep "1";
// removing or renaming fields requires a major bump.
const SchemaVersion = "1"

// TMDBAttribution is emitted whenever TMDB was queried.
const TMDBAttribution = "This product uses the TMDB API but is not endorsed or certified by TMDB."

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

// MediaInfo is the technical subset collected for each file.
type MediaInfo = probe.Info

// QueryResolver is the optional LLM query expander.
type QueryResolver = matcher.QueryResolver

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

// Result is the single JSON object returned by Detect.
type Result struct {
	SchemaVersion string       `json:"schema_version"`
	OK            bool         `json:"ok"`
	Input         *Input       `json:"input"`
	MediaType     string       `json:"media_type,omitempty"`
	Confidence    string       `json:"confidence,omitempty"`
	Title         *string      `json:"title"`
	Year          *int         `json:"year"`
	Summary       Summary      `json:"summary"`
	Files         []FileResult `json:"files"`
	Match         Match        `json:"match"`
	Detection     Detection    `json:"detection"`
	Attribution   *string      `json:"attribution"`
	Error         *ErrorObject `json:"error,omitempty"`
}

// Input identifies the single path that was inspected.
type Input struct {
	Path string `json:"path"`
	Kind string `json:"kind"`
}

// Summary aggregates file-level results.
type Summary struct {
	TotalFiles           int   `json:"total_files"`
	MovieFiles           int   `json:"movie_files"`
	EpisodeFiles         int   `json:"episode_files"`
	NonFeatureFiles      int   `json:"non_feature_files"`
	AuxiliaryFiles       int   `json:"auxiliary_files"`
	OtherFiles           int   `json:"other_files"`
	DistinctMovies       int   `json:"distinct_movies"`
	Seasons              []int `json:"seasons"`
	SkippedHidden        int   `json:"skipped_hidden"`
	SkippedSymlinks      int   `json:"skipped_symlinks"`
	Unreadable           int   `json:"unreadable"`
	UnmatchedMovieGroups int   `json:"unmatched_movie_groups"`
}

// FileResult is one file-level detection.
type FileResult struct {
	Path            string   `json:"path"`
	Name            string   `json:"name"`
	Ext             string   `json:"ext"`
	Role            string   `json:"role"`
	MediaType       string   `json:"media_type"`
	Confidence      string   `json:"confidence"`
	TitleCandidates []string `json:"title_candidates"`
	YearCandidates  []int    `json:"year_candidates"`
	Edition         *string  `json:"edition"`
	Resolution      *string  `json:"resolution"`
	Source          *string  `json:"source"`
	Codec           *string  `json:"codec"`
	ReleaseGroup    *string  `json:"release_group"`
	SeasonEpisode   *string  `json:"season_episode"`
	Season          *int     `json:"season"`
	Episode         *int     `json:"episode"`
	AuxiliaryKind   *string  `json:"auxiliary_kind"`
	GroupKey        *string  `json:"group_key"`
	ProbeStatus     string   `json:"probe_status"`
	DurationSec     *int     `json:"duration_sec"`
	Match           Match    `json:"match"`
}

// Match is the matching summary for a file or for the whole input.
type Match struct {
	Status     string       `json:"status"`
	Reason     *string      `json:"reason"`
	File       *string      `json:"file"`
	Margin     *float64     `json:"margin"`
	Best       *Candidate   `json:"best"`
	Candidates []Candidate  `json:"candidates"`
	Error      *ErrorObject `json:"error"`
}

// Candidate is one scored TMDB candidate.
type Candidate struct {
	Source          string   `json:"source"`
	TMDBID          int      `json:"tmdb_id"`
	IMDbID          *string  `json:"imdb_id"`
	Title           string   `json:"title"`
	OriginalTitle   string   `json:"original_title"`
	ReleaseDate     string   `json:"release_date"`
	Year            int      `json:"year"`
	RuntimeSec      int      `json:"runtime_sec"`
	Popularity      float64  `json:"popularity"`
	Score           float64  `json:"score"`
	TitleScore      float64  `json:"title_score"`
	YearDelta       *int     `json:"year_delta"`
	RuntimeDeltaSec *int     `json:"runtime_delta_sec"`
	MatchedBy       string   `json:"matched_by"`
	TitleHit        bool     `json:"title_hit"`
	Expanded        bool     `json:"expanded"`
	Query           string   `json:"query"`
	Evidence        Evidence `json:"evidence"`
}

// Evidence mirrors matcher.Scored.Evidence in structured form.
type Evidence struct {
	Query           string  `json:"query"`
	TMDBID          int     `json:"tmdb_id"`
	TMDBTitle       string  `json:"tmdb_title"`
	TMDBYear        int     `json:"tmdb_year"`
	TitleScore      float64 `json:"title_score"`
	Score           float64 `json:"score"`
	MatchedBy       string  `json:"matched_by"`
	YearDelta       *int    `json:"year_delta"`
	RuntimeDeltaSec *int    `json:"runtime_delta_sec"`
}

// Detection captures the requested modes and diagnostics.
type Detection struct {
	ProbeMode string    `json:"probe_mode"`
	MatchMode string    `json:"match_mode"`
	Warnings  []Warning `json:"warnings"`
	Truncated bool      `json:"truncated"`
}

// Warning is a stable code plus a human-readable detail.
type Warning struct {
	Code   string  `json:"code"`
	Detail string  `json:"detail"`
	File   *string `json:"file"`
}

// ErrorObject is the JSON error shape used by the top-level error and
// match.error.
type ErrorObject struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}
