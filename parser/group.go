package parser

import (
	"path/filepath"
	"strconv"
	"strings"
	"unicode"
)

// GroupKey builds the stable pre-match movie key from the highest-confidence
// title candidate, or from the file basename when no title could be parsed.
// The key is not used as identity after a successful match: groups that map to
// the same movie_id are unioned and the key is rewritten to the movie_id.
func GroupKey(filename string, h Hints) string {
	title := ""
	if len(h.TitleCandidates) > 0 {
		title = h.TitleCandidates[0]
	}
	if title == "" {
		base := filepath.Base(filename)
		title = strings.TrimSuffix(base, filepath.Ext(base))
	}
	title = normalizeKey(title)
	if title == "" {
		return ""
	}
	year := ""
	if len(h.YearCandidates) > 0 {
		year = strconv.Itoa(h.YearCandidates[0])
	}
	return title + "|" + year
}

func normalizeKey(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	var b strings.Builder
	for _, r := range s {
		if unicode.IsSpace(r) || unicode.IsPunct(r) || unicode.IsSymbol(r) {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}
