package mediadetect

import (
	"context"
	"strings"
	"time"

	"github.com/dream-365/MediaTitle/internal/collect"
	"github.com/dream-365/MediaTitle/matcher"
	"github.com/dream-365/MediaTitle/tmdb"
)

type movieGroup struct {
	key     string
	indices []int
	rep     int
}

type groupResult struct {
	group   *movieGroup
	match   Match
	failed  bool
	matched bool
	score   float64
}

func buildMovieGroups(files []FileResult) ([]*movieGroup, []*movieGroup) {
	groups := []*movieGroup{}
	byKey := map[string]*movieGroup{}
	byIndex := make([]*movieGroup, len(files))
	for i := range files {
		if files[i].MediaType != "movie" {
			continue
		}
		key := ""
		if files[i].GroupKey != nil {
			key = *files[i].GroupKey
		}
		if key == "" {
			key = "__file__:" + files[i].Path
		}
		g, ok := byKey[key]
		if !ok {
			g = &movieGroup{key: key, rep: i}
			byKey[key] = g
			groups = append(groups, g)
		}
		g.indices = append(g.indices, i)
		byIndex[i] = g
	}
	return groups, byIndex
}

type recordingResolver struct {
	inner  matcher.QueryResolver
	failed bool
}

func (r *recordingResolver) Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error) {
	queries, err := r.inner.Queries(ctx, filename, titles, year, runtimeSec)
	if err != nil {
		r.failed = true
	}
	return queries, err
}

func runMovieMatching(
	ctx context.Context,
	opts Options,
	mode MatchMode,
	files []FileResult,
	collected []collect.CollectedFile,
	groups []*movieGroup,
	candidateLimit int,
	warnings *warningSet,
) ([]groupResult, bool, *Error) {
	client := tmdb.NewWithOptions(tmdb.Options{
		APIKey:     opts.TMDB.APIKey,
		BaseURL:    opts.TMDB.BaseURL,
		Language:   opts.TMDB.Language,
		HTTPClient: opts.TMDB.HTTPClient,
		CacheLimit: opts.TMDB.CacheLimit,
	})
	maxQueries := opts.TMDB.MaxQueries
	if maxQueries <= 0 {
		maxQueries = 3
	}
	var resolver matcher.QueryResolver
	if opts.LLMFallback {
		resolver = opts.Resolver
	}
	var recorder *recordingResolver
	if resolver != nil {
		recorder = &recordingResolver{inner: resolver}
		resolver = recorder
	}
	mt := &matcher.Matcher{Client: client, MaxQueries: maxQueries, Resolver: resolver}

	byRel := map[string]collect.CollectedFile{}
	for _, cf := range collected {
		byRel[cf.RelPath] = cf
	}

	results := make([]groupResult, 0, len(groups))
	for _, group := range groups {
		if err := ctx.Err(); err != nil {
			return nil, false, newError(ErrCanceled, "detection canceled")
		}
		repIndex := group.rep
		repFile := files[repIndex].Path
		cf := byRel[repFile]
		groupCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
		res, err := mt.Match(groupCtx, cf.Hints, cf.DurationSec, cf.ProbeStatus == "failed")
		if err != nil {
			cancel()
			if ctx.Err() != nil {
				return nil, false, newError(ErrCanceled, "detection canceled")
			}
			var m Match
			if mode == MatchOn {
				m = matchError(repFile, "tmdb_unavailable", ErrTMDBUnavailable, "TMDB request failed")
			} else {
				m = unavailableMatch(&repFile)
			}
			results = append(results, groupResult{group: group, match: m, failed: true})
			continue
		}
		m := buildMatch(groupCtx, res, repFile, client, candidateLimit, warnings)
		cancel()
		results = append(results, groupResult{
			group:   group,
			match:   m,
			matched: m.Best != nil,
			score:   matchScore(m),
		})
	}
	if recorder != nil && recorder.failed {
		warnings.add("match.llm_unavailable", "LLM query expansion failed; continuing with deterministic queries", nil)
	}
	return results, client.Requests() > 0, nil
}

func buildMatch(ctx context.Context, res matcher.Result, file string, client *tmdb.Client, candidateLimit int, warnings *warningSet) Match {
	status := res.Confidence
	if status == "" {
		status = "unmatched"
	}
	m := Match{
		Status:     status,
		File:       &file,
		Candidates: []Candidate{},
	}
	for _, warning := range res.Warnings {
		warnings.add(warning.Code, warning.Detail, &file)
	}
	if len(res.Candidates) == 0 {
		return m
	}
	margin := res.Margin
	m.Margin = &margin

	best := res.Candidates[0]
	imdb := best.Movie.IMDbID
	if imdb == "" {
		if details, err := client.Details(ctx, best.Movie.ID); err == nil {
			best = applyDetails(best, details)
			imdb = details.IMDbID
		}
	}
	if imdb == "" {
		warnings.add("match.imdb_id_unavailable", "TMDB details did not return an IMDb id", &file)
	}
	bestCandidate := candidateFrom(best, imdbPtr(imdb))
	m.Best = &bestCandidate
	for i := 1; i < len(res.Candidates) && len(m.Candidates) < candidateLimit; i++ {
		m.Candidates = append(m.Candidates, candidateFrom(res.Candidates[i], nil))
	}
	return m
}

func applyDetails(scored matcher.Scored, details tmdb.Movie) matcher.Scored {
	if details.IMDbID != "" {
		scored.Movie.IMDbID = details.IMDbID
	}
	if details.Runtime > 0 {
		scored.Movie.Runtime = details.Runtime
	}
	if scored.Movie.Title == "" {
		scored.Movie.Title = details.Title
	}
	if scored.Movie.OriginalTitle == "" {
		scored.Movie.OriginalTitle = details.OriginalTitle
	}
	if scored.Movie.ReleaseDate == "" {
		scored.Movie.ReleaseDate = details.ReleaseDate
	}
	if scored.Movie.Popularity == 0 {
		scored.Movie.Popularity = details.Popularity
	}
	return scored
}

func candidateFrom(scored matcher.Scored, imdb *string) Candidate {
	return Candidate{
		Source:          "tmdb",
		TMDBID:          scored.Movie.ID,
		IMDbID:          imdb,
		Title:           scored.Movie.Title,
		OriginalTitle:   scored.Movie.OriginalTitle,
		ReleaseDate:     scored.Movie.ReleaseDate,
		Year:            scored.Movie.Year(),
		RuntimeSec:      scored.Movie.Runtime,
		Popularity:      scored.Movie.Popularity,
		Score:           scored.Score,
		TitleScore:      scored.TitleScore,
		YearDelta:       scored.YearDelta,
		RuntimeDeltaSec: scored.RuntimeDelta,
		MatchedBy:       scored.MatchedBy,
		TitleHit:        scored.TitleHit,
		Expanded:        scored.Expanded,
		Query:           scored.Query,
		Evidence: Evidence{
			Query:           scored.Query,
			TMDBID:          scored.Movie.ID,
			TMDBTitle:       scored.Movie.Title,
			TMDBYear:        scored.Movie.Year(),
			TitleScore:      round3(scored.TitleScore),
			Score:           round3(scored.Score),
			MatchedBy:       scored.MatchedBy,
			YearDelta:       scored.YearDelta,
			RuntimeDeltaSec: scored.RuntimeDelta,
		},
	}
}

func round3(f float64) float64 {
	return float64(int(f*1000+0.5)) / 1000
}

func imdbPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func matchScore(m Match) float64 {
	if m.Best == nil {
		return 0
	}
	return m.Best.Score
}

func assembleTopMatch(
	mode MatchMode,
	results []FileResult,
	groups []*movieGroup,
	groupResults []groupResult,
	plan matchPlan,
	mixed bool,
	distinct int,
	warnings *warningSet,
) Match {
	if len(groups) == 0 {
		file := firstPathOfType(results, "tv_episode")
		if file == nil {
			file = firstAnyPath(results)
		}
		if hasType(results, "tv_episode") {
			warnings.add("match.tv_not_supported", "TMDB TV matching is not part of this version", nil)
		}
		return notApplicableMatch(file)
	}
	if !plan.run {
		file := firstPathOfType(results, "movie")
		switch plan.reason {
		case "match_disabled":
			warnings.add("match.disabled", "TMDB matching disabled by --match=off", nil)
		case "no_tmdb_key":
			warnings.add("match.no_key", "TMDB_API_KEY is not set", nil)
		}
		return matchForPlan(plan, file)
	}

	failed, succeeded := false, false
	for _, gr := range groupResults {
		if gr.failed {
			failed = true
		} else {
			succeeded = true
		}
	}
	rep := representativeMatchFile(groupResults, results)
	if failed {
		if mode == MatchOn {
			if succeeded {
				warnings.add("match.partial", "some movie groups failed", nil)
			}
			return Match{
				Status:     "error",
				Reason:     ptrString("tmdb_unavailable"),
				File:       rep,
				Candidates: []Candidate{},
				Error:      &ErrorObject{Code: ErrTMDBUnavailable, Message: "TMDB request failed"},
			}
		}
		warnings.add("match.unavailable", "TMDB is unavailable", nil)
		if len(groups) > 1 {
			reason := "partial_match"
			if succeeded {
				warnings.add("match.partial", "some movie groups failed", nil)
			}
			return Match{Status: "multiple", Reason: &reason, File: rep, Candidates: []Candidate{}}
		}
		return unavailableMatch(rep)
	}

	if (len(groups) > 1 && distinct > 1) || mixed {
		reason := "multiple_movies"
		if mixed {
			reason = "mixed_types"
		}
		return Match{Status: "multiple", Reason: &reason, File: rep, Candidates: []Candidate{}}
	}

	best := groupResults[0]
	for _, gr := range groupResults {
		if gr.score > best.score {
			best = gr
		}
	}
	return best.match
}

func representativeMatchFile(groupResults []groupResult, results []FileResult) *string {
	var path *string
	best := 0.0
	for _, gr := range groupResults {
		index := gr.group.rep
		if index < 0 || index >= len(results) {
			continue
		}
		if path == nil || gr.score > best {
			p := results[index].Path
			path = &p
			best = gr.score
		}
	}
	if path == nil {
		return firstPathOfType(results, "movie")
	}
	return path
}

func computeDistinct(groups []*movieGroup, groupResults []groupResult, ran bool) int {
	byGroup := map[*movieGroup]groupResult{}
	for _, gr := range groupResults {
		byGroup[gr.group] = gr
	}
	ids := map[int]bool{}
	emptyKeyFiles := 0
	unmatchedGroups := 0
	for _, group := range groups {
		if strings.HasPrefix(group.key, "__file__:") {
			emptyKeyFiles++
			continue
		}
		gr, ok := byGroup[group]
		if ran && ok && gr.matched && gr.match.Best != nil {
			ids[gr.match.Best.TMDBID] = true
		} else {
			unmatchedGroups++
		}
	}
	return emptyKeyFiles + len(ids) + unmatchedGroups
}

// computeUnmatchedGroups counts movie groups whose final status is unmatched
// or error. A plan-level error (for example --match=on without a key) applies
// to every movie group.
func computeUnmatchedGroups(groups []*movieGroup, groupResults []groupResult, plan matchPlan) int {
	if !plan.run {
		if plan.status == "error" {
			return len(groups)
		}
		return 0
	}
	byGroup := map[*movieGroup]groupResult{}
	for _, gr := range groupResults {
		byGroup[gr.group] = gr
	}
	count := 0
	for _, group := range groups {
		gr, ok := byGroup[group]
		if !ok {
			continue
		}
		if gr.match.Status == "unmatched" || gr.match.Status == "error" {
			count++
		}
	}
	return count
}

func firstPathOfType(results []FileResult, mediaType string) *string {
	for i := range results {
		if results[i].MediaType == mediaType {
			p := results[i].Path
			return &p
		}
	}
	return nil
}

func firstAnyPath(results []FileResult) *string {
	if len(results) == 0 {
		return nil
	}
	p := results[0].Path
	return &p
}

func hasType(results []FileResult, mediaType string) bool {
	return firstPathOfType(results, mediaType) != nil
}
