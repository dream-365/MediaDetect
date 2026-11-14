// Package matcher scores TMDB candidates against parsed file hints.
package matcher

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"

	"github.com/siongui/gojianfan"

	"github.com/dream-365/MediaTitle/parser"
	"github.com/dream-365/MediaTitle/tmdb"
)

// Scored is one evaluated candidate.
type Scored struct {
	Movie        tmdb.Movie
	Query        string
	Score        float64
	TitleScore   float64
	YearDelta    *int
	RuntimeDelta *int
	MatchedBy    string // title | alt_title
	TitleHit     bool
	Expanded     bool // discovered through traditional/compact/LLM query expansion
}

func (m *Matcher) queryAll(ctx context.Context, queries []string, seen map[int]Scored, year, runtimeSec int, expanded bool) error {
	for _, query := range queries {
		if strings.TrimSpace(query) == "" {
			continue
		}
		results, err := m.Client.Search(ctx, query, 0)
		if err != nil {
			return err
		}
		for _, movie := range results {
			s := scoreOne(query, movie, year, runtimeSec)
			s.Expanded = expanded
			if prev, ok := seen[movie.ID]; !ok || s.Score > prev.Score {
				seen[movie.ID] = s
			}
		}
		if best, second, ok := topTwo(seen); ok && meetsHigh(best, second, -1) {
			return nil
		}
	}
	return nil
}

func isHigh(seen map[int]Scored) bool {
	best, second, ok := topTwo(seen)
	return ok && meetsHigh(best, second, -1)
}

// expandQueries produces traditional, simplified and compact variants of the
// parsed titles. These catch names that differ only by script or spacing.
func expandQueries(titles []string, limit int) []string {
	seen := map[string]bool{}
	var out []string
	add := func(q string) {
		q = strings.TrimSpace(q)
		if q == "" || seen[q] || len(out) >= limit {
			return
		}
		seen[q] = true
		out = append(out, q)
	}
	for _, t := range titles {
		if len(out) >= limit {
			break
		}
		add(gojianfan.S2T(t))
		add(gojianfan.T2S(t))
		add(compact(t))
	}
	return out
}

// Result is the outcome for one file.
type MatchWarning struct {
	Code   string
	Detail string
}

type Result struct {
	Candidates []Scored // sorted by score, best first
	Confidence string   // high | medium | low | unmatched
	Margin     float64
	Warnings   []MatchWarning
}

// Best returns the highest-scored candidate.
func (r Result) Best() (Scored, bool) {
	if len(r.Candidates) == 0 {
		return Scored{}, false
	}
	return r.Candidates[0], true
}

// QueryResolver turns a filename into additional search queries. It is
// optional; without one the matcher only uses deterministic expansion.
type QueryResolver interface {
	Queries(ctx context.Context, filename string, titles []string, year, runtimeSec int) ([]string, error)
}

// Matcher evaluates parsed hints against TMDB.
type Matcher struct {
	Client     *tmdb.Client
	MaxQueries int
	Resolver   QueryResolver
}

// Match scores up to three title candidates and applies the confidence rules
// from SPEC-001 3.4. runtimeSec is the probed file duration (0 when unknown);
// probeFailed downgrades the final tier by one step.
func (m *Matcher) Match(ctx context.Context, hints parser.Hints, runtimeSec int, probeFailed bool) (Result, error) {
	maxQueries := m.MaxQueries
	if maxQueries <= 0 {
		maxQueries = 3
	}
	year := primaryYear(hints.YearCandidates)
	seen := map[int]Scored{}

	queries := hints.TitleCandidates
	if len(queries) > maxQueries {
		queries = queries[:maxQueries]
	}
	if err := m.queryAll(ctx, queries, seen, year, runtimeSec, false); err != nil {
		return Result{}, err
	}

	// Deterministic expansion: traditional/simplified and compact variants.
	if !isHigh(seen) {
		expanded := expandQueries(hints.TitleCandidates, 3)
		if err := m.queryAll(ctx, expanded, seen, year, runtimeSec, true); err != nil {
			return Result{}, err
		}
	}

	// LLM fallback: let a model propose original-language titles.
	if !isHigh(seen) && m.Resolver != nil {
		llmQueries, err := m.Resolver.Queries(ctx, hints.Filename, hints.TitleCandidates, year, runtimeSec)
		if err == nil {
			if err := m.queryAll(ctx, llmQueries, seen, year, runtimeSec, true); err != nil {
				return Result{}, err
			}
		}
	}

	out := Result{}
	for _, s := range seen {
		out.Candidates = append(out.Candidates, s)
	}
	sort.Slice(out.Candidates, func(i, j int) bool { return out.Candidates[i].Score > out.Candidates[j].Score })
	if len(out.Candidates) == 0 {
		out.Confidence = "unmatched"
		return out, nil
	}
	m.aliasRescue(ctx, &out, year, runtimeSec)

	best := &out.Candidates[0]
	// Runtime only exists on the details endpoint; fetch it when the year
	// condition fails and a file duration is available.
	if runtimeSec > 0 && !yearCondition(best.YearDelta) {
		if d, err := m.Client.Details(ctx, best.Movie.ID); err == nil && d.Runtime > 0 {
			best.Movie.Runtime = d.Runtime
			best.Score, best.TitleScore, best.RuntimeDelta, best.MatchedBy, best.TitleHit =
				recalculate(*best, year, runtimeSec)
			sort.Slice(out.Candidates, func(i, j int) bool { return out.Candidates[i].Score > out.Candidates[j].Score })
			best = &out.Candidates[0]
		}
	}

	second := effectiveSecond(out.Candidates)
	margin := func() float64 {
		if second == nil {
			return 1
		}
		return out.Candidates[0].Score - second.Score
	}
	// Close calls are usually near-name entries or TMDB duplicates. Spend a
	// few details calls to separate them by real runtime before downgrading.
	if runtimeSec > 0 && second != nil && margin() < 0.10 {
		m.disambiguateByRuntime(ctx, &out, year, runtimeSec)
		best = &out.Candidates[0]
		second = effectiveSecond(out.Candidates)
	}
	out.Margin = margin()

	switch {
	case meetsHigh(*best, second, runtimeSec):
		out.Confidence = "high"
	case out.Margin < 0.10 && second != nil && best.Score >= 0.60:
		out.Confidence = "low"
	case best.Score >= 0.60:
		out.Confidence = "medium"
	default:
		out.Confidence = "unmatched"
	}

	if probeFailed {
		out.Confidence = downgrade(out.Confidence)
	}
	applyYearCap(&out, hints)
	return out, nil
}

// aliasRescue tries TMDB alternative titles for the top candidates that did
// not match by primary title. Chinese and regional titles are frequently
// absent from `title`/`original_title` but present in the alias list.
func (m *Matcher) aliasRescue(ctx context.Context, res *Result, year, runtimeSec int) {
	// Candidates found through expanded queries are checked first: their
	// query language may differ from the TMDB title even though they are right.
	var order []*Scored
	for i := range res.Candidates {
		c := &res.Candidates[i]
		if c.Expanded && !c.TitleHit {
			order = append(order, c)
		}
	}
	for i := 0; i < len(res.Candidates) && i < 5; i++ {
		c := &res.Candidates[i]
		if c.Expanded || c.TitleHit || c.Query == "" {
			continue
		}
		order = append(order, c)
	}

	changed := false
	calls := 0
	for _, c := range order {
		if calls >= 3 {
			break
		}
		if c.TitleHit || c.Query == "" {
			continue
		}
		calls++
		aliases, err := m.Client.Aliases(ctx, c.Movie.ID)
		if err != nil {
			continue
		}
		if !aliasHit(c.Query, aliases) {
			continue
		}
		c.TitleScore = 1.0
		c.TitleHit = true
		c.MatchedBy = "alt_title"
		c.Score = 0.7 + 0.3*maxFloat(yearScore(c.YearDelta), runtimeScore(c.RuntimeDelta))
		changed = true
	}
	if changed {
		sort.Slice(res.Candidates, func(i, j int) bool { return res.Candidates[i].Score > res.Candidates[j].Score })
	}
}

// disambiguateByRuntime fetches runtime for the top candidates and rescores
// them, so that near-name entries lose the runtime condition.
func (m *Matcher) disambiguateByRuntime(ctx context.Context, res *Result, year, runtimeSec int) {
	limit := 3
	if len(res.Candidates) < limit {
		limit = len(res.Candidates)
	}
	changed := false
	for i := 0; i < limit; i++ {
		c := &res.Candidates[i]
		if c.Movie.Runtime > 0 {
			continue
		}
		d, err := m.Client.Details(ctx, c.Movie.ID)
		if err != nil || d.Runtime <= 0 {
			continue
		}
		c.Movie.Runtime = d.Runtime
		c.Score, c.TitleScore, c.RuntimeDelta, c.MatchedBy, c.TitleHit =
			calculate(c.Query, c.Movie, year, runtimeSec)
		changed = true
	}
	if changed {
		sort.Slice(res.Candidates, func(i, j int) bool { return res.Candidates[i].Score > res.Candidates[j].Score })
	}
}

func aliasHit(query string, aliases []string) bool {
	q := compact(normalizeTitle(query))
	if q == "" {
		return false
	}
	for _, a := range aliases {
		if compact(normalizeTitle(a)) == q {
			return true
		}
	}
	return false
}

// effectiveSecond returns the best candidate that is not a metadata duplicate
// of the winner. TMDB often holds the same film twice with a one-year release
// difference; those should not be treated as a competing interpretation.
func effectiveSecond(cands []Scored) *Scored {
	if len(cands) < 2 {
		return nil
	}
	best := cands[0]
	for i := 1; i < len(cands); i++ {
		if sameEntry(best, cands[i]) {
			continue
		}
		return &cands[i]
	}
	return nil
}

func sameEntry(a, b Scored) bool {
	same := compact(normalizeTitle(a.Movie.Title)) == compact(normalizeTitle(b.Movie.Title)) &&
		compact(normalizeTitle(a.Movie.Title)) != ""
	if !same {
		oa := compact(normalizeTitle(a.Movie.OriginalTitle))
		ob := compact(normalizeTitle(b.Movie.OriginalTitle))
		same = oa != "" && oa == ob
	}
	if !same {
		return false
	}
	return abs(a.Movie.Year()-b.Movie.Year()) <= 1
}

func meetsHigh(best Scored, second *Scored, runtimeSec int) bool {
	if !best.TitleHit || best.TitleScore < 0.88 {
		return false
	}
	if !yearCondition(best.YearDelta) && !runtimeCondition(best.RuntimeDelta) {
		return false
	}
	if second != nil && best.Score-second.Score < 0.10 {
		return false
	}
	return true
}

func yearCondition(delta *int) bool {
	return delta != nil && abs(*delta) <= 1
}

func runtimeCondition(delta *int) bool {
	return delta != nil && abs(*delta) <= 180
}

func downgrade(c string) string {
	switch c {
	case "high":
		return "medium"
	case "medium":
		return "low"
	default:
		return c
	}
}

func applyYearCap(out *Result, hints parser.Hints) {
	if len(out.Candidates) == 0 {
		return
	}
	best := out.Candidates[0]
	fileYear := primaryYear(hints.YearCandidates)
	tmdbYear := best.Movie.Year()
	if fileYear == 0 || tmdbYear == 0 {
		return
	}
	delta := tmdbYear - fileYear
	if abs(delta) <= 5 {
		return
	}
	runtimeOK := best.RuntimeDelta != nil && abs(*best.RuntimeDelta) <= 180
	out.Warnings = append(out.Warnings, MatchWarning{
		Code: "match.year_conflict",
		Detail: fmt.Sprintf("year_delta=%d file_year=%d tmdb_year=%d runtime_ok=%t",
			delta, fileYear, tmdbYear, runtimeOK),
	})
	if !runtimeOK && out.Confidence != "unmatched" {
		out.Confidence = "low"
	}
}

func primaryYear(years []int) int {
	if len(years) == 0 {
		return 0
	}
	// The release year is the last 4-digit group in the sample corpus
	// ("2001.A.Space.Odyssey.1968", "2012.2009").
	return years[len(years)-1]
}

func scoreOne(query string, movie tmdb.Movie, year, runtimeSec int) Scored {
	s := Scored{Movie: movie, Query: query}
	s.Score, s.TitleScore, s.RuntimeDelta, s.MatchedBy, s.TitleHit = calculate(query, movie, year, runtimeSec)
	if year > 0 && movie.Year() > 0 {
		d := movie.Year() - year
		s.YearDelta = &d
	}
	return s
}

func recalculate(s Scored, year, runtimeSec int) (float64, float64, *int, string, bool) {
	score, titleScore, runtimeDelta, matchedBy, hit := calculate(s.Query, s.Movie, year, runtimeSec)
	return score, titleScore, runtimeDelta, matchedBy, hit
}

func calculate(query string, movie tmdb.Movie, year, runtimeSec int) (score, titleScore float64, runtimeDelta *int, matchedBy string, hit bool) {
	titleScore, matchedBy, hit = titleMatch(query, movie)
	var yDelta *int
	if year > 0 && movie.Year() > 0 {
		d := movie.Year() - year
		yDelta = &d
	}
	if runtimeSec > 0 && movie.Runtime > 0 {
		d := runtimeSec - movie.Runtime
		runtimeDelta = &d
	}
	score = 0.7*titleScore + 0.3*maxFloat(yearScore(yDelta), runtimeScore(runtimeDelta))
	return score, titleScore, runtimeDelta, matchedBy, hit
}

func titleMatch(query string, movie tmdb.Movie) (float64, string, bool) {
	nq := normalizeTitle(query)
	if nq == "" {
		return 0, "", false
	}
	best := 0.0
	matchedBy := ""
	hit := false
	for _, pair := range []struct {
		field string
		value string
	}{{"title", movie.Title}, {"alt_title", movie.OriginalTitle}} {
		nt := normalizeTitle(pair.value)
		if nt == "" {
			continue
		}
		// Spacing between Chinese characters and digits is a formatting
		// difference, not a different title ("示例侦探2" vs "示例侦探 2").
		cq, ct := compact(nq), compact(nt)
		var s float64
		switch {
		case cq != "" && cq == ct:
			s = 1.0
			hit = true
		case cq != "" && ct != "" && (strings.Contains(ct, cq) || strings.Contains(cq, ct)):
			ratio := containment(cq, ct)
			if ratio >= 0.75 {
				s = 0.92
			} else {
				s = 0.6
			}
		case len(cq) >= 5 && len(ct) >= 5 && levenshteinAtMostOne(cq, ct):
			s = 0.88
		default:
			if j := jaccard(nq, nt); j > 0 {
				s = minFloat(0.87, 0.5+0.4*j)
			} else {
				s = 0.2
			}
		}
		if s > best {
			best = s
			matchedBy = pair.field
		}
	}
	return best, matchedBy, hit
}

func yearScore(delta *int) float64 {
	if delta == nil {
		return 0
	}
	switch d := abs(*delta); {
	case d == 0:
		return 1.0
	case d == 1:
		return 0.9
	default:
		return 0.2
	}
}

func runtimeScore(delta *int) float64 {
	if delta == nil {
		return 0
	}
	switch d := abs(*delta); {
	case d <= 60:
		return 1.0
	case d <= 180:
		return 0.9
	case d <= 300:
		return 0.5
	default:
		return 0
	}
}

func normalizeTitle(s string) string {
	// NFKC expands compatibility characters such as "½" to "1⁄2" so
	// fractions compare equal to their "1/2" filename spelling.
	s = norm.NFKC.String(s)
	var b strings.Builder
	prevSpace := true
	for _, r := range strings.ToLower(s) {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			b.WriteRune(r)
			prevSpace = false
		} else if !prevSpace {
			b.WriteRune(' ')
			prevSpace = true
		}
	}
	return strings.TrimSpace(b.String())
}

func compact(s string) string {
	return strings.ReplaceAll(s, " ", "")
}

func jaccard(a, b string) float64 {
	as := strings.Fields(a)
	bs := strings.Fields(b)
	if len(as) == 0 || len(bs) == 0 {
		return 0
	}
	set := map[string]bool{}
	for _, t := range as {
		set[t] = true
	}
	inter := 0
	for _, t := range bs {
		if set[t] {
			inter++
		}
	}
	union := len(as) + len(bs) - inter
	return float64(inter) / float64(union)
}

func levenshteinAtMostOne(a, b string) bool {
	ar, br := []rune(a), []rune(b)
	if abs(len(ar)-len(br)) > 1 {
		return false
	}
	i, j, edits := 0, 0, 0
	for i < len(ar) && j < len(br) {
		if ar[i] == br[j] {
			i++
			j++
			continue
		}
		edits++
		if edits > 1 {
			return false
		}
		switch {
		case len(ar) > len(br):
			i++
		case len(br) > len(ar):
			j++
		default:
			i++
			j++
		}
	}
	return true
}

func topTwo(m map[int]Scored) (Scored, *Scored, bool) {
	var all []Scored
	for _, s := range m {
		all = append(all, s)
	}
	if len(all) == 0 {
		return Scored{}, nil, false
	}
	sort.Slice(all, func(i, j int) bool { return all[i].Score > all[j].Score })
	if len(all) == 1 {
		return all[0], nil, true
	}
	return all[0], &all[1], true
}

// Evidence renders the scored candidate for match_candidate.evidence_json.
func (s Scored) Evidence() string {
	ev := map[string]any{
		"query":       s.Query,
		"tmdb_id":     s.Movie.ID,
		"tmdb_title":  s.Movie.Title,
		"tmdb_year":   s.Movie.Year(),
		"title_score": round(s.TitleScore),
		"score":       round(s.Score),
		"matched_by":  s.MatchedBy,
	}
	if s.YearDelta != nil {
		ev["year_delta"] = *s.YearDelta
	}
	if s.RuntimeDelta != nil {
		ev["runtime_delta_sec"] = *s.RuntimeDelta
	}
	b, _ := json.Marshal(ev)
	return string(b)
}

func round(f float64) float64 {
	return float64(int(f*1000+0.5)) / 1000
}

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}

func minFloat(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}

// containment is |A∩B| / min(|A|,|B|) over character-bigram sets.
func containment(a, b string) float64 {
	as, bs := bigrams(a), bigrams(b)
	if len(as) == 0 || len(bs) == 0 {
		return 0
	}
	inter := 0
	for g := range as {
		if bs[g] {
			inter++
		}
	}
	return float64(inter) / float64(minInt(len(as), len(bs)))
}

func bigrams(s string) map[string]bool {
	r := []rune(compact(s))
	out := map[string]bool{}
	if len(r) < 2 {
		if len(r) == 1 {
			out[string(r)] = true
		}
		return out
	}
	for i := 0; i+1 < len(r); i++ {
		out[string(r[i:i+2])] = true
	}
	return out
}
