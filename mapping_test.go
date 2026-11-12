package mediadetect

import (
	"reflect"
	"testing"

	"github.com/dream-365/MediaDetect/parser"
)

func TestMapFile(t *testing.T) {
	cases := []struct {
		name  string
		hints parser.Hints
		want  fileType
	}{
		{
			name:  "feature with title",
			hints: parser.Hints{RoleHint: parser.RoleFeature, TitleCandidates: []string{"Inception"}},
			want:  fileType{mediaType: "movie", confidence: "high"},
		},
		{
			name:  "feature without evidence",
			hints: parser.Hints{RoleHint: parser.RoleFeature},
			want:  fileType{mediaType: "movie", confidence: "medium"},
		},
		{
			name:  "sample wins over episode marker",
			hints: parser.Hints{RoleHint: parser.RoleNonFeature, NonFeatureReason: "sample", SeasonEpisode: "S01E01"},
			want:  fileType{mediaType: "non_feature", confidence: "high"},
		},
		{
			name:  "episode marker maps to tv_episode",
			hints: parser.Hints{RoleHint: parser.RoleNonFeature, SeasonEpisode: "S01E01"},
			want:  fileType{mediaType: "tv_episode", confidence: "high"},
		},
		{
			name:  "cjk episode marker maps to tv_episode",
			hints: parser.Hints{RoleHint: parser.RoleNonFeature, SeasonEpisode: "第2集"},
			want:  fileType{mediaType: "tv_episode", confidence: "high"},
		},
		{
			name:  "non-feature without marker",
			hints: parser.Hints{RoleHint: parser.RoleNonFeature},
			want:  fileType{mediaType: "non_feature", confidence: "high"},
		},
		{
			name:  "subtitle",
			hints: parser.Hints{RoleHint: parser.RoleSubtitle},
			want:  fileType{mediaType: "auxiliary", confidence: "high", auxKind: "subtitle"},
		},
		{
			name:  "artwork",
			hints: parser.Hints{RoleHint: parser.RoleArtwork},
			want:  fileType{mediaType: "auxiliary", confidence: "high", auxKind: "artwork"},
		},
		{
			name:  "nfo",
			hints: parser.Hints{RoleHint: parser.RoleNFO},
			want:  fileType{mediaType: "auxiliary", confidence: "high", auxKind: "nfo"},
		},
		{
			name:  "other",
			hints: parser.Hints{RoleHint: parser.RoleOther},
			want:  fileType{mediaType: "other", confidence: "high"},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := mapFile(tc.hints); got != tc.want {
				t.Fatalf("mapFile = %+v, want %+v", got, tc.want)
			}
		})
	}
}

func TestSeasonDisplay(t *testing.T) {
	h := parser.Hints{
		TitleCandidates: []string{"Show S01E01-E03", "Show"},
		SeasonEpisode:   "S01E01-E03",
	}
	if got := displayTitles(h); !reflect.DeepEqual(got, []string{"Show"}) {
		t.Fatalf("titles = %v", got)
	}
	season, episode := parseSeasonEpisode("S01E01-E03")
	if season == nil || episode == nil || *season != 1 || *episode != 1 {
		t.Fatalf("season=%v episode=%v", season, episode)
	}
	season, episode = parseSeasonEpisode("第2集")
	if season != nil || episode == nil || *episode != 2 {
		t.Fatalf("cjk season=%v episode=%v", season, episode)
	}
}

func TestDisplayTitlesMultiEpisode(t *testing.T) {
	cases := []struct {
		title  string
		season string
	}{
		{"Show S01E01E02", "S01E01-E02"},
		{"Show S01E01E02E03", "S01E01-E03"},
		{"Show S01E01-E02", "S01E01-E02"},
	}
	for _, tc := range cases {
		got := displayTitles(parser.Hints{
			TitleCandidates: []string{tc.title},
			SeasonEpisode:   tc.season,
		})
		if len(got) != 1 || got[0] != "Show" {
			t.Errorf("%q = %v, want [Show]", tc.title, got)
		}
	}
}

func TestDetectMultiEpisodeTitleClean(t *testing.T) {
	root := t.TempDir()
	path := writeFile(t, root, "Show.S01E01E02.mkv")
	result := detectOK(t, path, offlineOptions())
	if result.MediaType != "tv_episode" {
		t.Fatalf("media_type = %q", result.MediaType)
	}
	if len(result.Files) != 1 {
		t.Fatalf("files = %d", len(result.Files))
	}
	file := result.Files[0]
	if file.SeasonEpisode == nil || *file.SeasonEpisode != "S01E01-E02" {
		t.Fatalf("season_episode = %v", file.SeasonEpisode)
	}
	if len(file.TitleCandidates) != 1 || file.TitleCandidates[0] != "Show" {
		t.Fatalf("title_candidates = %v", file.TitleCandidates)
	}
}

func TestDisplayTitlesStripEpisodeForms(t *testing.T) {
	cases := []struct {
		title  string
		season string
		want   string
	}{
		{"Show S01 E01", "S01E01", "Show"},
		{"Show 1x01", "S01E01", "Show"},
		{"Show 第 2 集", "第2集", "Show"},
		{"Show S01E01-E03", "S01E01-E03", "Show"},
	}
	for _, tc := range cases {
		got := displayTitles(parser.Hints{
			TitleCandidates: []string{tc.title},
			SeasonEpisode:   tc.season,
		})
		if len(got) != 1 || got[0] != tc.want {
			t.Errorf("%q = %v, want [%q]", tc.title, got, tc.want)
		}
	}
}

func TestAggregateRows(t *testing.T) {
	tests := []struct {
		name     string
		files    []string
		dirName  string
		wantType string
	}{
		{name: "empty", files: nil, wantType: "other"},
		{name: "auxiliary", files: []string{"Show.S01E01.srt"}, wantType: "auxiliary"},
		{name: "other", files: []string{"readme.txt"}, wantType: "other"},
		{name: "mixed", files: []string{"Inception.2010.mkv", "Show.S01E01.mkv"}, wantType: "mixed"},
		{name: "one movie", files: []string{"Inception.2010.mkv", "Inception.2010.1080p.mkv"}, wantType: "movie"},
		{name: "collection", files: []string{"Inception.2010.mkv", "Interstellar.2014.mkv"}, wantType: "movie_collection"},
		{name: "season", files: []string{"Show.S01E01.mkv", "Show.S01E02.mkv"}, dirName: "Season 1", wantType: "tv_season"},
		{name: "series", files: []string{"Show.S01E01.mkv", "Show.S01E02.mkv"}, wantType: "tv_series"},
		{name: "non-feature", files: []string{"sample.mkv"}, wantType: "non_feature"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			target := root
			if tc.dirName != "" {
				target = root + "/" + tc.dirName
			}
			for _, name := range tc.files {
				writeFile(t, target, name)
			}
			result := detectOK(t, target, offlineOptions())
			if result.MediaType != tc.wantType {
				t.Fatalf("media_type = %q, want %q", result.MediaType, tc.wantType)
			}
		})
	}
}

func TestSeasonDirectoryFillsSummary(t *testing.T) {
	cases := []struct {
		dir  string
		want int
	}{
		{"S02", 2},
		{"Season 2", 2},
		{"第 2 季", 2},
	}
	for _, tc := range cases {
		t.Run(tc.dir, func(t *testing.T) {
			root := t.TempDir()
			target := root + "/" + tc.dir
			writeFile(t, target, "Show.第01集.mkv")
			writeFile(t, target, "Show.第02集.mkv")
			result := detectOK(t, target, offlineOptions())
			if result.MediaType != "tv_season" {
				t.Fatalf("media_type = %q", result.MediaType)
			}
			if len(result.Summary.Seasons) != 1 || result.Summary.Seasons[0] != tc.want {
				t.Fatalf("seasons = %v, want [%d]", result.Summary.Seasons, tc.want)
			}
		})
	}
}

func TestSummaryIdentity(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Show.S01E01.mkv")
	writeFile(t, root, "poster.jpg")
	writeFile(t, root, "readme.txt")
	result := detectOK(t, root, offlineOptions())
	sum := result.Summary
	if sum.TotalFiles != sum.MovieFiles+sum.EpisodeFiles+sum.NonFeatureFiles+sum.AuxiliaryFiles+sum.OtherFiles {
		t.Fatalf("summary identity broken: %+v", sum)
	}
	if sum.TotalFiles != len(result.Files) {
		t.Fatalf("total_files = %d, files = %d", sum.TotalFiles, len(result.Files))
	}
}
