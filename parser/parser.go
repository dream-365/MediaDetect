// Package parser turns a media file name into matching hints.
package parser

import (
	"fmt"
	"path"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
	"golang.org/x/text/width"
)

// Role values returned in Hints.RoleHint.
const (
	RoleFeature    = "feature"
	RoleSubtitle   = "subtitle"
	RoleArtwork    = "artwork"
	RoleNFO        = "nfo"
	RoleNonFeature = "non_feature"
	RoleOther      = "other"
)

// Hints is the ParsedHints contract from SPEC-001 4.4.
type Hints struct {
	Filename        string
	TitleCandidates []string
	YearCandidates  []int
	RoleHint        string
	Edition         string
	Resolution      string
	Source          string
	Codec           string
	Group           string
	SeasonEpisode   string
	// NonFeatureReason records which token classified a video as non-feature
	// (for example "sample", "oad" or "trailer"). It lets callers distinguish
	// a sample/OAD that also carries an SxxExx marker from a real episode.
	NonFeatureReason string
	Ext              string
}

var (
	videoExts = map[string]bool{
		".mkv": true, ".mp4": true, ".m4v": true, ".avi": true, ".mov": true,
		".ts": true, ".wmv": true, ".flv": true, ".webm": true, ".mpg": true, ".mpeg": true,
	}
	subtitleExts = map[string]bool{".srt": true, ".ass": true, ".ssa": true, ".sub": true, ".idx": true}
	artworkExts  = map[string]bool{".jpg": true, ".jpeg": true, ".png": true, ".webp": true}
	nfoExts      = map[string]bool{".nfo": true}

	yearRE         = regexp.MustCompile(`(^|[^0-9])((?:18|19|20)\d{2})([^0-9]|$)`)
	episodeRE      = regexp.MustCompile(`(?i)(?:^|[^a-z0-9])s(\d{1,2})[._-]?e(\d{1,3})(?:[-~]e(\d{1,3}))?(?:[^a-z0-9]|$)`)
	multiEpisodeRE = regexp.MustCompile(`(?i)(?:^|[^a-z0-9])s(\d{1,2})[._-]?e(\d{1,3})((?:[._~-]?e\d{1,3})+)(?:[^a-z0-9]|$)`)
	tailEpisodeRE  = regexp.MustCompile(`(?i)([._~-]?)e(\d{1,3})`)
	episodeXRE     = regexp.MustCompile(`(?i)(?:^|[^a-z0-9])(\d{1,2})x(\d{1,3})(?:[^a-z0-9]|$)`)
	cjkEpisodeRE   = regexp.MustCompile(`第\s*\d+\s*[集话話]`)
	resolutionRE   = regexp.MustCompile(`(?i)(?:^|[^a-z0-9])(2160p|1080p|720p|540p|480p|4k|8k)(?:[^a-z0-9]|$)`)
	dimensionRE    = regexp.MustCompile(`(?i)\b\d{3,4}[x×]\d{3,4}p?\b`)
	groupRE        = regexp.MustCompile(`-([A-Za-z0-9]{2,})$`)
	ratingRE       = regexp.MustCompile(`豆瓣\s*\d+(?:\.\d+)?`)
	longDigitsRE   = regexp.MustCompile(`\d{8,}`)
)

var sourceTokens = []string{
	"bluray", "blu-ray", "bdrip", "brrip", "web-dl", "webdl", "webrip", "hdtv",
	"dvdrip", "dvd", "remux", "hdrip", "hd4k", "hdtc", "tc",
}

var codecTokens = []string{"x265", "x264", "h265", "h264", "hevc", "avc", "av1", "vp9"}

var editionTokens = []string{
	"导演剪辑版", "导演剪辑", "加长版", "未删减", "未删减版", "完整版", "修复版",
	"director's cut", "directors cut", "extended", "unrated", "theatrical",
}

var nonFeatureTokens = []string{
	"keynote", "发布会", "游戏实况", "gameplay", "ova", "oad", "sample",
	"旅行特辑", "花絮", "幕后", "预告片", "trailer", "特典", "映像特典",
}

var languageTokens = []string{
	"国语", "粤语", "韩语", "日语", "英语", "法语", "德语", "西班牙语", "马来语",
	"波兰语", "荷兰语", "双语", "三语", "国英", "国粤", "国韩", "中字",
	"中英双字", "中文字幕", "特效中英字幕", "内封中字", "无删减版", "缺字幕",
}

// Parse extracts hints from a path relative to a media root.
func Parse(relativePath string) Hints {
	relativePath = norm.NFC.String(relativePath)
	base := path.Base(relativePath)
	ext := strings.ToLower(path.Ext(base))
	h := Hints{Ext: ext}

	switch {
	case videoExts[ext]:
		h.RoleHint = RoleFeature
	case subtitleExts[ext]:
		h.RoleHint = RoleSubtitle
	case artworkExts[ext]:
		h.RoleHint = RoleArtwork
	case nfoExts[ext]:
		h.RoleHint = RoleNFO
	default:
		h.RoleHint = RoleOther
		return h
	}

	h.Filename = base
	stem := strings.TrimSuffix(base, path.Ext(base))
	stem = norm.NFKC.String(stem)
	stem = width.Fold.String(stem)

	if h.RoleHint == RoleSubtitle {
		// Long numeric suffixes on subtitles are hashes, not titles.
		stem = longDigitsRE.ReplaceAllString(stem, " ")
	}

	h.Resolution = findTokenGroup(stem, resolutionRE)
	if h.Resolution == "" {
		if m := dimensionRE.FindString(stem); m != "" {
			h.Resolution = strings.ToLower(strings.ReplaceAll(m, "×", "x"))
		}
	}
	h.Source = findAny(stem, sourceTokens)
	h.Codec = findAny(stem, codecTokens)
	h.Edition = findAny(stem, editionTokens)
	if m := groupRE.FindStringSubmatch(stem); m != nil {
		h.Group = m[1]
	}

	multiSeasonEpisode, multiMatched := parseMultiEpisode(stem)
	if multiMatched {
		// An invalid repeated-E form (for example S01E01E03) must suppress the
		// ordinary S01E01 match; otherwise it would still be classified as TV.
		h.SeasonEpisode = multiSeasonEpisode
	} else if m := episodeRE.FindStringSubmatch(stem); m != nil {
		h.SeasonEpisode = "S" + m[1] + "E" + m[2]
		if m[3] != "" {
			h.SeasonEpisode += "-E" + m[3]
		}
	} else if season, episode, ok := parseEpisodeX(stem); ok {
		h.SeasonEpisode = fmt.Sprintf("S%02dE%02d", season, episode)
	} else if cjkEpisodeRE.MatchString(stem) {
		h.SeasonEpisode = cjkEpisodeRE.FindString(stem)
	}

	// Auxiliary roles (subtitle/artwork/nfo) always win: an SxxExx marker or a
	// "sample" token on a .srt/.jpg must not turn the file into a non-feature
	// video.
	if h.RoleHint == RoleFeature {
		if reason := findNonFeatureReason(strings.ToLower(stem)); reason != "" {
			h.RoleHint = RoleNonFeature
			h.NonFeatureReason = reason
		}
		if h.SeasonEpisode != "" {
			// v1 indexes movies only; episodes are classified out of the G1 denominator.
			h.RoleHint = RoleNonFeature
		}
	}

	titlePart, years := splitTitle(stem)
	h.YearCandidates = years
	h.TitleCandidates = candidates(titlePart)
	return h
}

// parseMultiEpisode recognizes repeated E segments. The first return value is
// the canonical range; matched reports whether a repeated-E form was present,
// even when it is rejected as non-contiguous. A rejected form returns an empty
// range so the caller suppresses the ordinary SxxExx match.
func parseMultiEpisode(stem string) (string, bool) {
	m := multiEpisodeRE.FindStringSubmatch(stem)
	if m == nil {
		return "", false
	}
	season, err := strconv.Atoi(m[1])
	if err != nil {
		return "", true
	}
	first, err := strconv.Atoi(m[2])
	if err != nil {
		return "", true
	}
	tail := m[3]
	parts := tailEpisodeRE.FindAllStringSubmatch(tail, -1)
	if len(parts) == 0 {
		return "", true
	}
	numbers := make([]int, 0, len(parts)+1)
	numbers = append(numbers, first)
	hasRangeSuffix := false
	for index, part := range parts {
		separator := part[1]
		number, err := strconv.Atoi(part[2])
		if err != nil {
			return "", true
		}
		if separator == "-" || separator == "~" {
			// Only the classic "S01E01-E03" form is an explicit range. A dash
			// after multiple E segments is ambiguous and must stay unplanned.
			if index != 0 || len(parts) != 1 {
				return "", true
			}
			hasRangeSuffix = true
		}
		numbers = append(numbers, number)
	}
	if !hasRangeSuffix {
		for index := 1; index < len(numbers); index++ {
			if numbers[index] != numbers[index-1]+1 {
				return "", true
			}
		}
	}
	last := numbers[len(numbers)-1]
	return fmt.Sprintf("S%02dE%02d-E%02d", season, first, last), true
}

// parseEpisodeX accepts "1x01" only when it looks like an episode marker.
// Bare patterns such as "4x4", "10x10" and aspect ratios like "16x9" are
// common movie-title/resolution tokens and must not become TV episodes.
func parseEpisodeX(stem string) (season, episode int, ok bool) {
	m := episodeXRE.FindStringSubmatchIndex(stem)
	if m == nil {
		return 0, 0, false
	}
	season, _ = strconv.Atoi(stem[m[2]:m[3]])
	episode, _ = strconv.Atoi(stem[m[4]:m[5]])
	if aspectRatioPair(season, episode) {
		return 0, 0, false
	}
	before := strings.TrimRight(stem[:m[0]], " ._-")
	if before == "" && !strings.HasPrefix(stem[m[4]:m[5]], "0") {
		return 0, 0, false
	}
	return season, episode, true
}

func aspectRatioPair(w, h int) bool {
	switch w*100 + h {
	case 4*100 + 3, 4*100 + 4, 10*100 + 10, 16*100 + 9, 16*100 + 10, 21*100 + 9:
		return true
	}
	return false
}

// splitTitle cuts the stem at the first plausible year and returns the title
// portion plus every year candidate. Numbers inside titles are preserved.
func splitTitle(stem string) (string, []int) {
	work := resolutionRE.ReplaceAllString(stem, " ")
	work = dimensionRE.ReplaceAllString(work, " ")
	pos := findYears(work)
	if len(pos) == 0 {
		return work, nil
	}
	years := make([]int, 0, len(pos))
	for _, p := range pos {
		years = append(years, p.year)
	}
	if pos[0].start == 0 {
		if len(pos) > 1 {
			// A title that itself starts with a year, e.g. "2012 (2009)".
			return work[:pos[1].start], years
		}
		// "1993-豆瓣9.1-完美的世界": the year is a prefix, not the title.
		return work[pos[0].end:], years
	}
	return work[:pos[0].start], years
}

type yearPos struct {
	start, end, year int
}

// findYears scans for standalone four-digit years. A regex with a leading
// delimiter would consume the separator shared by "2012.2009", so this walks
// the string instead.
func findYears(s string) []yearPos {
	var out []yearPos
	for i := 0; i+4 <= len(s); {
		if isDigit(s[i]) && isDigit(s[i+1]) && isDigit(s[i+2]) && isDigit(s[i+3]) &&
			(i == 0 || !isDigit(s[i-1])) && (i+4 == len(s) || !isDigit(s[i+4])) {
			if y, err := strconv.Atoi(s[i : i+4]); err == nil && y >= 1888 && y <= 2100 {
				out = append(out, yearPos{i, i + 4, y})
				i += 4
				continue
			}
		}
		i++
	}
	return out
}

func isDigit(b byte) bool { return b >= '0' && b <= '9' }

// candidates produces at most three de-duplicated title variants.
func candidates(titlePart string) []string {
	s := clean(titlePart)
	if s == "" {
		return nil
	}
	var out []string
	add := func(v string) {
		v = clean(v)
		if v == "" {
			return
		}
		for _, x := range out {
			if x == v {
				return
			}
		}
		out = append(out, v)
	}

	add(s)
	cjk, latin := splitScripts(s)
	if cjk != "" && latin != "" {
		add(trimTrailingDigits(cjk))
		add(latin)
		add(cjk)
	}
	// Long theatrical titles often append a subtitle after "!". A shorter
	// search variant improves TMDB recall without changing the display title.
	if short := searchShortTitle(s); short != s {
		add(short)
	}
	// Punctuation variants are aliases, not replacements.
	alt := clean(strings.NewReplacer("·", " ", "《", " ", "》", " ", "#", " ", "｜", " ", "⧸", " ").Replace(s))
	if alt != s {
		add(alt)
	}
	if len(out) > 3 {
		out = out[:3]
	}
	return out
}

func searchShortTitle(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "剧场版 ") {
		s = strings.TrimSpace(strings.TrimPrefix(s, "剧场版 "))
	}
	if i := strings.IndexAny(s, "!！"); i > 0 {
		s = strings.TrimSpace(s[:i])
	}
	return s
}

func clean(s string) string {
	s = width.Fold.String(norm.NFKC.String(s))
	// Drop technical and language tokens.
	lower := strings.ToLower(s)
	for _, tok := range append(append([]string{}, sourceTokens...), append(codecTokens, languageTokens...)...) {
		if strings.Contains(lower, tok) {
			s = replaceFold(s, tok, " ")
			lower = strings.ToLower(s)
		}
	}
	for _, tok := range editionTokens {
		s = replaceFold(s, tok, " ")
	}
	// Ratings are noise, not part of a title.
	s = ratingRE.ReplaceAllString(s, " ")
	// Scene names use dots as separators; hyphens stay inside titles.
	// Keep slashes: they carry meaning in titles such as "示例片1/2" and are
	// valid in TMDB queries. Dots, underscores, pipes and backslashes are
	// scene separators.
	s = strings.NewReplacer(".", " ", "_", " ", "|", " ", "\\", " ").Replace(s)
	s = strings.NewReplacer("(", " ", ")", " ", "（", " ", "）", " ", "[", " ", "]", " ", "【", " ", "】", " ").Replace(s)
	s = strings.Trim(s, " -—:：,，;；!！?？")
	s = strings.Join(strings.Fields(s), " ")
	s = strings.TrimSpace(groupRE.ReplaceAllString(s, ""))
	return s
}

func splitScripts(s string) (cjk, latin string) {
	firstLatin := -1
	for i, r := range s {
		if r < unicode.MaxASCII && unicode.IsLetter(r) {
			firstLatin = i
			break
		}
	}
	if firstLatin < 0 {
		return s, ""
	}
	cjkPart := strings.TrimSpace(s[:firstLatin])
	latinPart := strings.TrimSpace(s[firstLatin:])
	if cjkPart == "" || latinPart == "" {
		return "", ""
	}
	return cjkPart, latinPart
}

// trimTrailingDigits drops a stray number that belongs to the Latin part
// ("示例房间 3 Iron" -> "示例房间") but keeps sequel numbers glued to the Chinese
// title ("示例侦探2" stays "示例侦探2").
func trimTrailingDigits(s string) string {
	s = strings.TrimSpace(s)
	i := len(s)
	for i > 0 {
		r := rune(s[i-1])
		if unicode.IsDigit(r) {
			i--
			continue
		}
		break
	}
	if i == len(s) || i == 0 {
		return s
	}
	if unicode.IsSpace(rune(s[i-1])) {
		return strings.TrimSpace(s[:i])
	}
	return s
}

func findAny(s string, toks []string) string {
	lower := strings.ToLower(s)
	for _, t := range toks {
		if strings.Contains(lower, t) {
			return t
		}
	}
	return ""
}

func findTokenGroup(s string, re *regexp.Regexp) string {
	if m := re.FindStringSubmatch(s); m != nil {
		return strings.ToLower(m[1])
	}
	return ""
}

func replaceFold(s, old, new string) string {
	re := regexp.MustCompile(`(?i)` + regexp.QuoteMeta(old))
	return re.ReplaceAllString(s, new)
}

// SortCandidatesByLength is used only by tests to compare sets deterministically.
func SortCandidatesByLength(ss []string) []string {
	out := append([]string{}, ss...)
	sort.Slice(out, func(i, j int) bool { return len(out[i]) > len(out[j]) })
	return out
}

// findNonFeatureReason returns the first non-feature token in a lowercased
// stem. ASCII tokens are matched on word boundaries so that "oad" does not
// hit "Road" and "ova" does not hit "Nova"; CJK tokens keep substring
// matching because they have no word separator.
func findNonFeatureReason(s string) string {
	for _, tok := range nonFeatureTokens {
		if isASCII(tok) {
			if containsToken(s, tok) {
				return tok
			}
			continue
		}
		if strings.Contains(s, tok) {
			return tok
		}
	}
	return ""
}

func isASCII(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			return false
		}
	}
	return true
}

func containsToken(s, tok string) bool {
	for i := 0; ; {
		j := strings.Index(s[i:], tok)
		if j < 0 {
			return false
		}
		j += i
		before := j == 0 || !isASCIIAlnum(s[j-1])
		after := j+len(tok) == len(s) || !isASCIIAlnum(s[j+len(tok)])
		if before && after {
			return true
		}
		i = j + 1
	}
}

func isASCIIAlnum(b byte) bool {
	return b >= 'a' && b <= 'z' || b >= '0' && b <= '9'
}
