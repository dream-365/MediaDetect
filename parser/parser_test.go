package parser

import (
	"bufio"
	"os"
	"path"
	"strings"
	"testing"
)

func TestParseCaseTable(t *testing.T) {
	cases := []struct {
		file      string
		role      string
		wantTitle string
		wantYear  int
	}{
		{"Example.Film-2003_HD国语中字V2.mp4", RoleFeature, "Example Film", 2003},
		{"Blood.Diamond.2020.1080p.BluRay.x264.mkv", RoleFeature, "Blood Diamond", 2020},
		{"示例房间.3.Iron.2004.1080p.mkv", RoleFeature, "示例房间", 2004},
		{"2012.2009.1080p.BluRay.mkv", RoleFeature, "2012", 2009},
		{"Example.Plate.17.mkv", RoleFeature, "Example Plate 17", 0},
		{"示例侦探2.Detective.Chinatown.2.2018.mkv", RoleFeature, "示例侦探2", 2018},
		{"示例夏天（1996）.mkv", RoleFeature, "示例夏天", 1996},
		{"示例权臣.The.Treacherous.2015.1920x804p.x264.mkv", RoleFeature, "示例权臣", 2015},
		{"Keynote.mkv", RoleNonFeature, "", 0},
		{"某剧.S01E02.1080p.mkv", RoleNonFeature, "", 0},
		{"示例纪录片.01.BD720P.国语中字.mkv", RoleFeature, "示例纪录片", 0},
		{"Example.I⧸O.'26.Keynote.mp4", RoleNonFeature, "", 0},
		{"sub.1234567890.srt", RoleSubtitle, "sub", 0},
		{"poster.jpg", RoleArtwork, "", 0},
	}
	for _, tc := range cases {
		h := Parse(tc.file)
		if h.RoleHint != tc.role {
			t.Errorf("%s: role = %s, want %s", tc.file, h.RoleHint, tc.role)
		}
		if tc.wantTitle != "" && !contains(h.TitleCandidates, tc.wantTitle) {
			t.Errorf("%s: candidates %v do not contain %q", tc.file, h.TitleCandidates, tc.wantTitle)
		}
		if tc.wantYear != 0 && !containsInt(h.YearCandidates, tc.wantYear) {
			t.Errorf("%s: years %v do not contain %d", tc.file, h.YearCandidates, tc.wantYear)
		}
		if len(h.TitleCandidates) > 3 {
			t.Errorf("%s: %d candidates, want at most 3", tc.file, len(h.TitleCandidates))
		}
	}
}

func TestParseResolutionAndEdition(t *testing.T) {
	h := Parse("Film.2019.2160p.BluRay.HEVC.导演剪辑版.mkv")
	if h.Resolution != "2160p" {
		t.Errorf("resolution = %q", h.Resolution)
	}
	if h.Source != "bluray" {
		t.Errorf("source = %q", h.Source)
	}
	if h.Codec != "hevc" {
		t.Errorf("codec = %q", h.Codec)
	}
	if h.Edition == "" {
		t.Errorf("edition not detected")
	}
}

func TestParseSampleCorpus(t *testing.T) {
	f, err := os.Open("testdata/filenames.txt")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	var total, videos, subtitles, noTitle, nonFeature int
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		total++
		h := Parse(line)
		switch h.RoleHint {
		case RoleSubtitle:
			subtitles++
			continue
		case RoleArtwork, RoleNFO, RoleOther:
			continue
		}
		videos++
		if h.RoleHint == RoleNonFeature {
			nonFeature++
		}
		if len(h.TitleCandidates) == 0 && path.Ext(line) != "" {
			noTitle++
			t.Logf("no title candidate: %s", line)
		}
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}
	t.Logf("total=%d videos=%d subtitles=%d non_feature=%d no_title=%d", total, videos, subtitles, nonFeature, noTitle)
	if total != 231 {
		t.Errorf("total = %d, want 231", total)
	}
	if videos != 228 {
		t.Errorf("videos = %d, want 228", videos)
	}
	if subtitles != 3 {
		t.Errorf("subtitles = %d, want 3", subtitles)
	}
	if nonFeature < 3 {
		t.Errorf("non_feature = %d, want at least 3", nonFeature)
	}
	if noTitle > 3 {
		t.Errorf("files without a title candidate = %d, want at most 3", noTitle)
	}
}

func contains(ss []string, want string) bool {
	for _, s := range ss {
		if s == want {
			return true
		}
	}
	return false
}

func containsInt(ns []int, want int) bool {
	for _, n := range ns {
		if n == want {
			return true
		}
	}
	return false
}
