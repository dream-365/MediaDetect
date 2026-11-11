package mediadetect

import (
	"regexp"
	"sort"
	"strings"

	"github.com/dream-365/MediaDetect/parser"
)

type fileType struct {
	mediaType  string
	confidence string
	auxKind    string
}

// mapFile implements the SPEC-001 4.5.1 table. It adds no new classification
// rules: every decision comes from the parser's role and episode hints.
func mapFile(h parser.Hints) fileType {
	switch h.RoleHint {
	case parser.RoleFeature:
		if len(h.TitleCandidates) > 0 || len(h.YearCandidates) > 0 {
			return fileType{mediaType: "movie", confidence: "high"}
		}
		return fileType{mediaType: "movie", confidence: "medium"}
	case parser.RoleNonFeature:
		if h.NonFeatureReason != "" {
			return fileType{mediaType: "non_feature", confidence: "high"}
		}
		if h.SeasonEpisode != "" {
			return fileType{mediaType: "tv_episode", confidence: "high"}
		}
		return fileType{mediaType: "non_feature", confidence: "high"}
	case parser.RoleSubtitle:
		return fileType{mediaType: "auxiliary", confidence: "high", auxKind: "subtitle"}
	case parser.RoleArtwork:
		return fileType{mediaType: "auxiliary", confidence: "high", auxKind: "artwork"}
	case parser.RoleNFO:
		return fileType{mediaType: "auxiliary", confidence: "high", auxKind: "nfo"}
	default:
		return fileType{mediaType: "other", confidence: "high"}
	}
}

// displayTitles strips the episode marker from parser title candidates for
// presentation. The parser's own TitleCandidates are not modified.
func displayTitles(h parser.Hints) []string {
	out := []string{}
	seen := map[string]bool{}
	for _, title := range h.TitleCandidates {
		title = stripEpisode(title, h.SeasonEpisode)
		title = strings.TrimSpace(strings.Trim(title, " ._-"))
		if title == "" || seen[title] {
			continue
		}
		seen[title] = true
		out = append(out, title)
	}
	return out
}

var (
	rangeSuffixRE     = regexp.MustCompile(`(?i)[-~]e?\d{1,3}$`)
	displayEpisodeRE  = regexp.MustCompile(`(?i)(?:^|[\s._-])s\d{1,2}\s*[._-]?\s*e\d{1,3}(?:\s*[-~]\s*e?\d{1,3})?`)
	displayXEpisodeRE = regexp.MustCompile(`(?i)\b\d{1,2}x\d{1,3}\b`)
	displayCJKEpRE    = regexp.MustCompile(`第\s*\d+\s*[集话話]`)
)

func stripEpisode(title, seasonEpisode string) string {
	stripped := title
	if seasonEpisode != "" {
		quoted := regexp.QuoteMeta(seasonEpisode)
		re := regexp.MustCompile(`(?i)` + quoted + `(?:[-~]e\d{1,3})?`)
		stripped = re.ReplaceAllString(stripped, " ")
		if stripped == title {
			// The title may contain only the first segment of a range.
			base := rangeSuffixRE.ReplaceAllString(seasonEpisode, "")
			if base != "" {
				re = regexp.MustCompile(`(?i)` + regexp.QuoteMeta(base) + `(?:[-~]e?\d{1,3})?`)
				stripped = re.ReplaceAllString(stripped, " ")
			}
		}
	}
	// clean() normalizes separators, so the parser's canonical "S01E01" may
	// appear as "S01 E01" or retain the original "1x01" spelling.
	stripped = displayEpisodeRE.ReplaceAllString(stripped, " ")
	stripped = displayXEpisodeRE.ReplaceAllString(stripped, " ")
	stripped = displayCJKEpRE.ReplaceAllString(stripped, " ")
	return strings.Join(strings.Fields(stripped), " ")
}

var (
	seasonEpisodeRE = regexp.MustCompile(`(?i)^S(\d{1,2})E(\d{1,3})`)
	cjkEpisodeRE    = regexp.MustCompile(`第\s*(\d+)\s*[集话話]`)
)

// parseSeasonEpisode extracts the display-level season and episode. Ranges
// use their first segment; CJK "第 N 集" has no season.
func parseSeasonEpisode(seasonEpisode string) (season, episode *int) {
	if seasonEpisode == "" {
		return nil, nil
	}
	if m := seasonEpisodeRE.FindStringSubmatch(seasonEpisode); m != nil {
		s := atoi(m[1])
		e := atoi(m[2])
		return &s, &e
	}
	if m := cjkEpisodeRE.FindStringSubmatch(seasonEpisode); m != nil {
		e := atoi(m[1])
		return nil, &e
	}
	return nil, nil
}

func atoi(s string) int {
	n := 0
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return n
		}
		n = n*10 + int(s[i]-'0')
	}
	return n
}

func sortedYears(years []int) []int {
	out := append([]int{}, years...)
	sort.Ints(out)
	return out
}

func ptrString(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func ptrInt(n int) *int {
	return &n
}

func ptrFloat(f float64) *float64 {
	return &f
}
