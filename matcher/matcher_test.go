package matcher

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/dream-365/MediaDetect/parser"
	"github.com/dream-365/MediaDetect/tmdb"
)

func clientFor(t *testing.T, body string) *tmdb.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, body)
	}))
	t.Cleanup(srv.Close)
	return tmdb.New("key", srv.URL, "zh-CN")
}

func TestUnicodeFractionTitleNormalization(t *testing.T) {
	score, titleScore, _, _, _ := calculate(
		"示例片1/2:示例副标题",
		tmdb.Movie{Title: "示例片½ 示例副标题", ReleaseDate: "1991-11-02"},
		1991, 0,
	)
	if titleScore < 0.60 || score < 0.60 {
		t.Fatalf("titleScore=%v score=%v, want fraction normalization to keep the candidate above 0.60", titleScore, score)
	}
}

func TestExactTitleAndYearIsHigh(t *testing.T) {
	c := clientFor(t, `{"results":[{"id":1,"title":"示例电影","original_title":"Blood Diamond","release_date":"2006-12-08"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"Blood Diamond"}, YearCandidates: []int{2006}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high (%+v)", res.Confidence, res.Candidates)
	}
}

func TestWrongYearWithoutRuntimeIsLow(t *testing.T) {
	c := clientFor(t, `{"results":[{"id":1,"title":"示例电影","original_title":"Blood Diamond","release_date":"2006-12-08"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"Blood Diamond"}, YearCandidates: []int{2020}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "low" {
		t.Fatalf("confidence = %s, want low", res.Confidence)
	}
	if len(res.Warnings) == 0 || res.Warnings[0].Code != "match.year_conflict" {
		t.Fatalf("warnings = %+v, want match.year_conflict", res.Warnings)
	}
}

func TestWrongYearWithRuntimeMatchIsHigh(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/search/movie" {
			fmt.Fprint(w, `{"results":[{"id":1,"title":"示例电影","original_title":"Blood Diamond","release_date":"2006-12-08"}]}`)
			return
		}
		fmt.Fprint(w, `{"id":1,"title":"示例电影","release_date":"2006-12-08","runtime":120}`)
	}))
	defer srv.Close()
	m := &Matcher{Client: tmdb.New("key", srv.URL, "zh-CN")}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"Blood Diamond"}, YearCandidates: []int{2020}}, 7200, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high", res.Confidence)
	}
	if len(res.Warnings) == 0 || res.Warnings[0].Code != "match.year_conflict" {
		t.Fatalf("warnings = %+v, want match.year_conflict", res.Warnings)
	}
}

func TestAmbiguousCandidatesAreLow(t *testing.T) {
	c := clientFor(t, `{"results":[
		{"id":1,"title":"同名电影","release_date":"2000-01-01"},
		{"id":2,"title":"同名电影2","release_date":"2000-01-01"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"同名电影"}, YearCandidates: []int{2000}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "low" {
		t.Fatalf("confidence = %s, want low", res.Confidence)
	}
}

func TestProbeFailureDowngrades(t *testing.T) {
	c := clientFor(t, `{"results":[{"id":1,"title":"示例电影","original_title":"Blood Diamond","release_date":"2006-12-08"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"Blood Diamond"}, YearCandidates: []int{2006}}, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "medium" {
		t.Fatalf("confidence = %s, want medium after downgrade", res.Confidence)
	}
}

func TestAliasRescue(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/search/movie":
			fmt.Fprint(w, `{"results":[{"id":9,"title":"示例片C别名","original_title":"Bullet Train","release_date":"2022-08-03"}]}`)
		case r.URL.Path == "/movie/9/alternative_titles":
			fmt.Fprint(w, `{"titles":[{"title":"示例片C"}]}`)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	m := &Matcher{Client: tmdb.New("key", srv.URL, "zh-CN")}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"示例片C"}, YearCandidates: []int{2022}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high", res.Confidence)
	}
	if best, _ := res.Best(); best.MatchedBy != "alt_title" {
		t.Fatalf("matched_by = %s, want alt_title", best.MatchedBy)
	}
}

func TestDuplicateEntryDoesNotSplitMargin(t *testing.T) {
	c := clientFor(t, `{"results":[
		{"id":1,"title":"示例片B","original_title":"Burning","release_date":"2018-05-17"},
		{"id":2,"title":"示例片B","original_title":"Burning","release_date":"2018-12-01"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"示例片B"}, YearCandidates: []int{2018}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high despite the duplicate entry", res.Confidence)
	}
}

type fakeResolver struct {
	queries []string
	err     error
}

func (f fakeResolver) Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error) {
	return f.queries, f.err
}

func TestLLMResolverProposesQuery(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/search/movie" {
			http.NotFound(w, r)
			return
		}
		if r.URL.Query().Get("query") == "Thirteen Lives" {
			fmt.Fprint(w, `{"results":[{"id":1,"title":"十三条命","original_title":"Thirteen Lives","release_date":"2022-07-18"}]}`)
			return
		}
		fmt.Fprint(w, `{"results":[]}`)
	}))
	defer srv.Close()

	m := &Matcher{
		Client:   tmdb.New("key", srv.URL, "zh-CN"),
		Resolver: fakeResolver{queries: []string{"Thirteen Lives"}},
	}
	res, err := m.Match(context.Background(), parser.Hints{
		Filename: "示例片14.2022.mkv", TitleCandidates: []string{"示例片14"}, YearCandidates: []int{2022},
	}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high", res.Confidence)
	}
	if best, _ := res.Best(); best.Query != "Thirteen Lives" {
		t.Fatalf("query = %q", best.Query)
	}
}

func TestTraditionalExpansion(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/search/movie":
			// Only the traditional variant of the parsed title finds the entry.
			if r.URL.Query().Get("query") == "示例電影2" {
				fmt.Fprint(w, `{"results":[{"id":2,"title":"示例电影","original_title":"示例電影","release_date":"2003-01-16"}]}`)
				return
			}
			fmt.Fprint(w, `{"results":[]}`)
		case "/movie/2/alternative_titles":
			fmt.Fprint(w, `{"titles":[{"title":"示例電影2"}]}`)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	m := &Matcher{Client: tmdb.New("key", srv.URL, "zh-CN")}
	res, err := m.Match(context.Background(), parser.Hints{
		Filename: "示例电影2.2003.mkv", TitleCandidates: []string{"示例电影2"}, YearCandidates: []int{2003},
	}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "high" {
		t.Fatalf("confidence = %s, want high", res.Confidence)
	}
}

func TestNoResultsIsUnmatched(t *testing.T) {
	c := clientFor(t, `{"results":[]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"不存在"}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "unmatched" {
		t.Fatalf("confidence = %s, want unmatched", res.Confidence)
	}
}

func TestSoftYearConflictKeepsMedium(t *testing.T) {
	c := clientFor(t, `{"results":[{"id":1,"title":"示例电影","original_title":"Ant-Man and the Wasp","release_date":"2018-07-06"}]}`)
	m := &Matcher{Client: c}
	res, err := m.Match(context.Background(), parser.Hints{TitleCandidates: []string{"Ant-Man and the Wasp"}, YearCandidates: []int{2022}}, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if res.Confidence != "medium" {
		t.Fatalf("confidence = %s, want medium", res.Confidence)
	}
	if len(res.Warnings) != 0 {
		t.Fatalf("warnings = %+v, want none for delta<=5", res.Warnings)
	}
}
