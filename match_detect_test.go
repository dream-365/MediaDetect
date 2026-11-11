package mediadetect

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func tmdbServer(t *testing.T, search func(query string) []map[string]any, details map[int]map[string]any) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/search/movie":
			json.NewEncoder(w).Encode(map[string]any{"results": search(r.URL.Query().Get("query"))})
		case strings.HasSuffix(r.URL.Path, "/alternative_titles"):
			json.NewEncoder(w).Encode(map[string]any{"titles": []string{}})
		default:
			for id, body := range details {
				if r.URL.Path == "/movie/"+itoa(id) {
					json.NewEncoder(w).Encode(body)
					return
				}
			}
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(srv.Close)
	return srv
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}

func inceptionSearch(query string) []map[string]any {
	return []map[string]any{{
		"id": 27205, "title": "Inception", "original_title": "Inception",
		"release_date": "2010-07-15", "popularity": 80.5,
	}}
}

func inceptionDetails() map[int]map[string]any {
	return map[int]map[string]any{
		27205: {
			"id": 27205, "title": "Inception", "original_title": "Inception",
			"release_date": "2010-07-15", "runtime": 148, "imdb_id": "tt1375666",
		},
	}
}

func mockOptions(baseURL string, mode MatchMode) Options {
	return Options{
		ProbeMode: ProbeOff,
		MatchMode: mode,
		TMDB: TMDBOptions{
			APIKey:  "key",
			BaseURL: baseURL,
		},
	}
}

func TestDetectMockMatchAndIMDb(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	srv := tmdbServer(t, inceptionSearch, inceptionDetails())
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))

	if result.Match.Status != "high" {
		t.Fatalf("status = %q", result.Match.Status)
	}
	if result.Match.Best == nil || result.Match.Best.TMDBID != 27205 {
		t.Fatalf("best = %+v", result.Match.Best)
	}
	if result.Match.Best.IMDbID == nil || *result.Match.Best.IMDbID != "tt1375666" {
		t.Fatalf("imdb = %v", result.Match.Best.IMDbID)
	}
	if result.Files[0].Match.Status != "high" || result.Files[0].Match.Best == nil {
		t.Fatalf("file match = %+v", result.Files[0].Match)
	}
	if result.Attribution == nil || *result.Attribution != TMDBAttribution {
		t.Fatalf("attribution = %v", result.Attribution)
	}
	if result.Summary.DistinctMovies != 1 {
		t.Fatalf("distinct = %d", result.Summary.DistinctMovies)
	}
}

func TestDetectCandidatesOnlyBestHasIMDb(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	search := func(string) []map[string]any {
		return []map[string]any{
			{"id": 27205, "title": "Inception", "original_title": "Inception", "release_date": "2010-07-15"},
			{"id": 999, "title": "Inception Legacy", "original_title": "Inception Legacy", "release_date": "2010-01-01"},
		}
	}
	details := map[int]map[string]any{
		27205: {"id": 27205, "title": "Inception", "release_date": "2010-07-15", "runtime": 148, "imdb_id": "tt1375666"},
		999:   {"id": 999, "title": "Inception Legacy", "release_date": "2010-01-01", "runtime": 90, "imdb_id": "tt0000999"},
	}
	srv := tmdbServer(t, search, details)
	opts := mockOptions(srv.URL, MatchAuto)
	opts.TMDB.CandidateLimit = 1
	result := detectOK(t, root, opts)

	if len(result.Match.Candidates) != 1 {
		t.Fatalf("candidates = %+v", result.Match.Candidates)
	}
	if result.Match.Candidates[0].IMDbID != nil {
		t.Fatalf("alternative candidate must not carry imdb_id: %v", *result.Match.Candidates[0].IMDbID)
	}
}

func TestDetectEvidenceRoundsScores(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Alpha.Beta.2010.mkv")
	search := func(string) []map[string]any {
		return []map[string]any{{
			"id": 42, "title": "Beta Gamma", "release_date": "2010-07-15",
		}}
	}
	details := map[int]map[string]any{
		42: {"id": 42, "title": "Beta Gamma", "release_date": "2010-07-15", "runtime": 5400},
	}
	srv := tmdbServer(t, search, details)
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	best := result.Match.Best
	if best == nil {
		t.Fatal("expected best candidate")
	}
	if best.Evidence.Score != round3(best.Score) || best.Evidence.TitleScore != round3(best.TitleScore) {
		t.Fatalf("evidence score=%v/%v, candidate score=%v/%v",
			best.Evidence.Score, best.Evidence.TitleScore, best.Score, best.TitleScore)
	}
}

func TestDetectUnmatchedHasNullBestAndMargin(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	srv := tmdbServer(t, func(string) []map[string]any { return nil }, nil)
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	if result.Match.Status != "unmatched" {
		t.Fatalf("status = %q", result.Match.Status)
	}
	if result.Match.Best != nil || result.Match.Margin != nil {
		t.Fatalf("best=%v margin=%v", result.Match.Best, result.Match.Margin)
	}
	if result.Match.Candidates == nil || len(result.Match.Candidates) != 0 {
		t.Fatalf("candidates = %#v", result.Match.Candidates)
	}
}

func TestDetectUnionByMovieID(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "盗梦空间.2010.mkv")
	search := func(query string) []map[string]any {
		return []map[string]any{{"id": 1, "title": query, "original_title": query, "release_date": "2010-01-01"}}
	}
	details := map[int]map[string]any{
		1: {"id": 1, "title": "Inception", "release_date": "2010-01-01", "runtime": 148, "imdb_id": "tt0000001"},
	}
	srv := tmdbServer(t, search, details)
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))

	if result.MediaType != "movie" {
		t.Fatalf("media_type = %s, want movie after union", result.MediaType)
	}
	if result.Summary.DistinctMovies != 1 {
		t.Fatalf("distinct = %d", result.Summary.DistinctMovies)
	}
	for _, file := range result.Files {
		if file.Match.Best == nil || file.Match.Best.TMDBID != 1 {
			t.Fatalf("file %s match = %+v", file.Path, file.Match)
		}
	}
}

func TestDetectMultipleMovies(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Interstellar.2014.mkv")
	search := func(query string) []map[string]any {
		if strings.Contains(query, "Interstellar") {
			return []map[string]any{{"id": 157336, "title": "Interstellar", "release_date": "2014-11-07"}}
		}
		return []map[string]any{{"id": 27205, "title": "Inception", "release_date": "2010-07-15"}}
	}
	details := map[int]map[string]any{
		27205:  {"id": 27205, "title": "Inception", "release_date": "2010-07-15", "runtime": 148, "imdb_id": "tt1375666"},
		157336: {"id": 157336, "title": "Interstellar", "release_date": "2014-11-07", "runtime": 169, "imdb_id": "tt0816692"},
	}
	srv := tmdbServer(t, search, details)
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))

	if result.MediaType != "movie_collection" {
		t.Fatalf("media_type = %s", result.MediaType)
	}
	if result.Match.Status != "multiple" || result.Match.Reason == nil || *result.Match.Reason != "multiple_movies" {
		t.Fatalf("match = %+v", result.Match)
	}
	if result.Match.Best != nil {
		t.Fatalf("top-level multiple must not carry best")
	}
	if result.Summary.DistinctMovies != 2 {
		t.Fatalf("distinct = %d", result.Summary.DistinctMovies)
	}
}

func TestDetectMixedTypes(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Show.S01E01.mkv")
	srv := tmdbServer(t, inceptionSearch, inceptionDetails())
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))

	if result.MediaType != "mixed" {
		t.Fatalf("media_type = %s", result.MediaType)
	}
	if result.Match.Status != "multiple" || result.Match.Reason == nil || *result.Match.Reason != "mixed_types" {
		t.Fatalf("match = %+v", result.Match)
	}
	for _, file := range result.Files {
		if file.MediaType == "tv_episode" && file.Match.Status != "not_applicable" {
			t.Fatalf("tv file match = %+v", file.Match)
		}
	}
}

func TestDetectMixedOnlySearchesMovieTitles(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Show.S01E01.mkv")
	var queries []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/search/movie":
			queries = append(queries, r.URL.Query().Get("query"))
			json.NewEncoder(w).Encode(map[string]any{"results": []map[string]any{{
				"id": 27205, "title": "Inception", "release_date": "2010-07-15",
			}}})
		case r.URL.Path == "/movie/27205":
			json.NewEncoder(w).Encode(map[string]any{
				"id": 27205, "title": "Inception", "release_date": "2010-07-15", "runtime": 148, "imdb_id": "tt1375666",
			})
		case strings.HasSuffix(r.URL.Path, "/alternative_titles"):
			json.NewEncoder(w).Encode(map[string]any{"titles": []string{}})
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	_ = detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	for _, query := range queries {
		if strings.Contains(query, "Show") {
			t.Fatalf("episode title was sent to /search/movie: %v", queries)
		}
	}
}

func TestDetectFullWidthSlashQueryKeepsSlash(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "剧场版.示例片1／2：示例副标题！.1991.日语中字.mkv")
	var queries []string
	search := func(query string) []map[string]any {
		queries = append(queries, query)
		if strings.Contains(query, "示例片1/2:示例副标题") {
			return []map[string]any{{
				"id": 990001, "title": "示例片½ 示例副标题",
				"release_date": "1991-11-02",
			}}
		}
		return nil
	}
	details := map[int]map[string]any{
		990001: {
			"id": 990001, "title": "示例片½ 示例副标题",
			"release_date": "1991-11-02", "runtime": 135, "imdb_id": "tt0000001",
		},
	}
	srv := tmdbServer(t, search, details)
	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	if len(queries) == 0 {
		t.Fatal("no TMDB queries were sent")
	}
	if !strings.Contains(strings.Join(queries, "|"), "示例片1/2") {
		t.Fatalf("queries = %v, want slash preserved", queries)
	}
	if result.Match.Best == nil || result.Match.Best.TMDBID != 990001 {
		t.Fatalf("match = %+v, want short query to find the mock entry", result.Match)
	}
}

func TestDetectMultipleGroupsUnavailableUsesPartialMatch(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Interstellar.2014.mkv")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusBadRequest)
	}))
	defer srv.Close()

	result := detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	if result.Match.Status != "multiple" || result.Match.Reason == nil || *result.Match.Reason != "partial_match" {
		t.Fatalf("match = %+v", result.Match)
	}
	if !hasWarning(result, "match.unavailable") {
		t.Fatalf("warnings = %+v", result.Detection.Warnings)
	}
}

func TestDetectAutoUnavailableAndOnError(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusBadRequest)
	}))
	defer srv.Close()

	auto := detectOK(t, root, mockOptions(srv.URL, MatchAuto))
	if auto.Match.Status != "unavailable" || auto.Match.Reason == nil || *auto.Match.Reason != "tmdb_unavailable" {
		t.Fatalf("auto match = %+v", auto.Match)
	}
	if auto.Match.Error != nil {
		t.Fatalf("auto match must not carry an error object: %+v", auto.Match.Error)
	}
	if !hasWarning(auto, "match.unavailable") {
		t.Fatalf("warnings = %+v", auto.Detection.Warnings)
	}

	on := detectOK(t, root, mockOptions(srv.URL, MatchOn))
	if on.Match.Status != "error" || on.Match.Error == nil || on.Match.Error.Code != ErrTMDBUnavailable {
		t.Fatalf("on match = %+v", on.Match)
	}
}
