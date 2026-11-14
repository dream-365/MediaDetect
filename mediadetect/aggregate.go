package mediadetect

import (
	"path/filepath"
	"regexp"
	"sort"

	"github.com/dream-365/MediaTitle/internal/collect"
)

var (
	seasonDirRE    = regexp.MustCompile(`(?i)^(?:season|s)\s*[._-]?(\d{1,2})$`)
	cjkSeasonDirRE = regexp.MustCompile(`第\s*(\d+)\s*季`)
)

func aggregateType(results []FileResult, distinct int, inputPath string) (mediaType, confidence string) {
	if len(results) == 0 {
		return "other", "high"
	}
	movies, episodes, nonFeatures, auxiliaries := 0, 0, 0, 0
	for _, file := range results {
		switch file.MediaType {
		case "movie":
			movies++
		case "tv_episode":
			episodes++
		case "non_feature":
			nonFeatures++
		case "auxiliary":
			auxiliaries++
		}
	}
	switch {
	case movies > 0 && episodes > 0:
		return "mixed", "high"
	case movies > 0:
		if distinct <= 1 {
			return "movie", maxMovieConfidence(results)
		}
		return "movie_collection", "high"
	case episodes > 0:
		seasons := episodeSeasons(results)
		if hasSeasonMarker(inputPath) && len(seasons) <= 1 {
			return "tv_season", "high"
		}
		return "tv_series", "high"
	case nonFeatures > 0:
		return "non_feature", "high"
	case auxiliaries > 0:
		return "auxiliary", "high"
	default:
		return "other", "high"
	}
}

func maxMovieConfidence(results []FileResult) string {
	best := ""
	for _, file := range results {
		if file.MediaType != "movie" {
			continue
		}
		switch file.Confidence {
		case "high":
			return "high"
		case "medium":
			best = "medium"
		case "low":
			if best == "" {
				best = "low"
			}
		}
	}
	if best == "" {
		return "high"
	}
	return best
}

func hasSeasonMarker(inputPath string) bool {
	_, ok := seasonFromDir(inputPath)
	return ok
}

// seasonFromDir extracts the season number from a directory basename such as
// "S02", "Season 2" or "第 2 季".
func seasonFromDir(inputPath string) (int, bool) {
	base := filepath.Base(inputPath)
	for _, re := range []*regexp.Regexp{seasonDirRE, cjkSeasonDirRE} {
		if m := re.FindStringSubmatch(base); m != nil {
			return atoi(m[1]), true
		}
	}
	return 0, false
}

func episodeSeasons(results []FileResult) []int {
	set := map[int]bool{}
	for _, file := range results {
		if file.MediaType == "tv_episode" && file.Season != nil {
			set[*file.Season] = true
		}
	}
	return sortedSet(set)
}

func sortedSet(set map[int]bool) []int {
	out := make([]int, 0, len(set))
	for v := range set {
		out = append(out, v)
	}
	sort.Ints(out)
	return out
}

func topTitleYear(results []FileResult, mediaType string) (*string, *int) {
	index := representativeIndex(results, mediaType)
	if index < 0 {
		return nil, nil
	}
	var title *string
	if len(results[index].TitleCandidates) > 0 {
		v := results[index].TitleCandidates[0]
		title = &v
	}
	var year *int
	if len(results[index].YearCandidates) > 0 {
		v := results[index].YearCandidates[0]
		year = &v
	}
	return title, year
}

func fileTitleYear(file FileResult) (*string, *int) {
	var title *string
	if len(file.TitleCandidates) > 0 {
		v := file.TitleCandidates[0]
		title = &v
	}
	var year *int
	if len(file.YearCandidates) > 0 {
		v := file.YearCandidates[0]
		year = &v
	}
	return title, year
}

func representativeIndex(results []FileResult, mediaType string) int {
	switch mediaType {
	case "movie", "movie_collection":
		return firstIndex(results, "movie")
	case "tv_season", "tv_series":
		return firstIndex(results, "tv_episode")
	case "mixed":
		// First video in path order, whether movie or episode.
		for i := range results {
			if results[i].MediaType == "movie" || results[i].MediaType == "tv_episode" {
				return i
			}
		}
		return -1
	case "non_feature":
		return firstIndex(results, "non_feature")
	case "auxiliary":
		return firstIndex(results, "auxiliary")
	default:
		return -1
	}
}

func firstIndex(results []FileResult, mediaType string) int {
	for i := range results {
		if results[i].MediaType == mediaType {
			return i
		}
	}
	return -1
}

func buildSummary(results []FileResult, counts collect.Counts, distinct, unmatchedGroups int, topMediaType, inputPath string) Summary {
	seasons := episodeSeasons(results)
	if topMediaType == "tv_season" && len(seasons) == 0 {
		if season, ok := seasonFromDir(inputPath); ok {
			seasons = []int{season}
		}
	}
	summary := Summary{
		TotalFiles:           len(results),
		DistinctMovies:       distinct,
		Seasons:              seasons,
		SkippedHidden:        counts.SkippedHidden,
		SkippedSymlinks:      counts.SkippedSymlinks,
		Unreadable:           counts.Unreadable,
		UnmatchedMovieGroups: unmatchedGroups,
	}
	for _, file := range results {
		switch file.MediaType {
		case "movie":
			summary.MovieFiles++
		case "tv_episode":
			summary.EpisodeFiles++
		case "non_feature":
			summary.NonFeatureFiles++
		case "auxiliary":
			summary.AuxiliaryFiles++
		default:
			summary.OtherFiles++
		}
	}
	return summary
}
