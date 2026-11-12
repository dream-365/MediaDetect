package parser

import (
	"strings"
	"testing"
)

// TestParserFixes covers the parser behavior changes in SPEC-001 4.5.1.1.
// Every case is a before/after fixture used by the parser contract.
func TestFullWidthSlashKeptInTitle(t *testing.T) {
	h := Parse("剧场版.示例片1／2：示例副标题！.1991.日语中字.mkv")
	joined := strings.Join(h.TitleCandidates, " | ")
	if !strings.Contains(joined, "示例片1/2") {
		t.Fatalf("title candidates = %q, want slash preserved", joined)
	}
	if strings.Contains(joined, "示例片1 2") {
		t.Fatalf("title candidates = %q, slash was flattened", joined)
	}
	if !strings.Contains(joined, "示例片1/2:示例副标题") {
		t.Fatalf("title candidates = %q, missing short search variant", joined)
	}
}

func TestEpisodeXFalsePositives(t *testing.T) {
	movies := []string{
		"4x4.2019.mkv",
		"10x10.2018.mkv",
		"Movie.4x4.mkv",
		"Movie.10x10.mkv",
		"Movie.2019.16x9.mkv",
		"Movie.16x9.mkv",
	}
	for _, file := range movies {
		h := Parse(file)
		if h.RoleHint != RoleFeature || h.SeasonEpisode != "" {
			t.Errorf("%s = role %q season %q, want feature with no episode", file, h.RoleHint, h.SeasonEpisode)
		}
	}
	episodes := map[string]string{
		"1x01.mkv":           "S01E01",
		"Show.1x01.mkv":      "S01E01",
		"Show.2x05.mkv":      "S02E05",
		"Show.2019.1x01.mkv": "S01E01",
	}
	for file, want := range episodes {
		if h := Parse(file); h.SeasonEpisode != want {
			t.Errorf("%s = %q, want %q", file, h.SeasonEpisode, want)
		}
	}
}

func TestMultiEpisodeRanges(t *testing.T) {
	cases := []struct {
		file   string
		role   string
		season string
	}{
		{"Show.S01E01E02.mkv", RoleNonFeature, "S01E01-E02"},
		{"Show.S01E01E02E03.mkv", RoleNonFeature, "S01E01-E03"},
		{"Show.S01E01-E02.mkv", RoleNonFeature, "S01E01-E02"},
		{"Show.S01E01-E03.mkv", RoleNonFeature, "S01E01-E03"},
		{"Show.S01E01E03.mkv", RoleFeature, ""},
		{"Show.S01E01E02E04.mkv", RoleFeature, ""},
		{"Show.S01E01E02-E04.mkv", RoleFeature, ""},
	}
	for _, tc := range cases {
		t.Run(tc.file, func(t *testing.T) {
			h := Parse(tc.file)
			if h.RoleHint != tc.role {
				t.Fatalf("role = %q, want %q", h.RoleHint, tc.role)
			}
			if h.SeasonEpisode != tc.season {
				t.Fatalf("season_episode = %q, want %q", h.SeasonEpisode, tc.season)
			}
		})
	}
}

func TestParserFixes(t *testing.T) {
	cases := []struct {
		name   string
		file   string
		role   string
		reason string
		season string
	}{
		{
			name: "subtitle keeps auxiliary role despite SxxExx",
			file: "Show.S01E01.srt", role: RoleSubtitle, season: "S01E01",
		},
		{
			name: "artwork keeps auxiliary role despite SxxExx",
			file: "Show.S01E01.jpg", role: RoleArtwork, season: "S01E01",
		},
		{
			name: "sample movie is non-feature",
			file: "Inception.2010.sample.mkv", role: RoleNonFeature, reason: "sample",
		},
		{
			name: "sample episode stays non-feature",
			file: "Show.S01E01.sample.mkv", role: RoleNonFeature, reason: "sample", season: "S01E01",
		},
		{
			name: "OAD is non-feature",
			file: "某动画.OAD.01.mkv", role: RoleNonFeature, reason: "oad",
		},
		{
			name: "Nova is not an OVA",
			file: "Nova.2020.mkv", role: RoleFeature,
		},
		{
			name: "Road is not an OAD",
			file: "Road.2019.mkv", role: RoleFeature,
		},
		{
			name: "Sampler is not a sample",
			file: "Sampler.2019.mkv", role: RoleFeature,
		},
		{
			name: "1x01 is normalized",
			file: "Show.1x01.mkv", role: RoleNonFeature, season: "S01E01",
		},
		{
			name: "S01.E01 is normalized",
			file: "Show.S01.E01.mkv", role: RoleNonFeature, season: "S01E01",
		},
		{
			name: "S01E01-E03 keeps the full range",
			file: "Show.S01E01-E03.mkv", role: RoleNonFeature, season: "S01E01-E03",
		},
		{
			name: "CJK episode marker",
			file: "某剧.第2集.mkv", role: RoleNonFeature, season: "第2集",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := Parse(tc.file)
			if h.RoleHint != tc.role {
				t.Fatalf("role = %q, want %q", h.RoleHint, tc.role)
			}
			if h.NonFeatureReason != tc.reason {
				t.Fatalf("non-feature reason = %q, want %q", h.NonFeatureReason, tc.reason)
			}
			if tc.season != "" && h.SeasonEpisode != tc.season {
				t.Fatalf("season_episode = %q, want %q", h.SeasonEpisode, tc.season)
			}
		})
	}
}
