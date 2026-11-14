package matcher

import (
	"bufio"
	"context"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/dream-365/MediaTitle/parser"
	"github.com/dream-365/MediaTitle/tmdb"
)

// TestTMDBTitleYearCalibration runs the Phase 0 corpus against the live TMDB
// API. It is filename-level: no media files are probed, so runtime fallback is
// unavailable. Enable with MEDIADETECT_CALIBRATE=1 and TMDB_API_KEY set.
func TestTMDBTitleYearCalibration(t *testing.T) {
	if os.Getenv("MEDIADETECT_CALIBRATE") != "1" {
		t.Skip("set MEDIADETECT_CALIBRATE=1 to run the live calibration")
	}
	key := os.Getenv("TMDB_API_KEY")
	if key == "" {
		t.Skip("TMDB_API_KEY is not set")
	}
	f, err := os.Open("../parser/testdata/filenames.txt")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()

	client := tmdb.New(key, "", "zh-CN")
	m := &Matcher{Client: client, MaxQueries: 3}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()

	conf := map[string]int{}
	var total, unparsable, yearOK, yearMissing, yearWrong int
	var unmatched []string
	start := time.Now()

	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		h := parser.Parse(line)
		if h.RoleHint != parser.RoleFeature {
			continue
		}
		total++
		if len(h.TitleCandidates) == 0 {
			unparsable++
			unmatched = append(unmatched, "[no-title] "+line)
			continue
		}
		res, err := m.Match(ctx, h, 0, false)
		if err != nil {
			t.Fatalf("%s: %v", line, err)
		}
		conf[res.Confidence]++
		best, ok := res.Best()
		if !ok {
			unmatched = append(unmatched, "[no-candidate] "+line)
			continue
		}
		switch {
		case best.YearDelta == nil:
			yearMissing++
		case abs(*best.YearDelta) <= 1:
			yearOK++
		default:
			yearWrong++
		}
		if res.Confidence != "high" && len(unmatched) < 60 {
			unmatched = append(unmatched, "["+res.Confidence+"] "+line+" -> "+best.Movie.Title)
		}
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}

	sort.Strings(unmatched)
	t.Logf("feature_files=%d unparsable=%d", total, unparsable)
	t.Logf("confidence: high=%d medium=%d low=%d unmatched=%d",
		conf["high"], conf["medium"], conf["low"], conf["unmatched"])
	t.Logf("best-candidate year: exact_or_±1=%d missing=%d wrong=%d", yearOK, yearMissing, yearWrong)
	if total > 0 {
		t.Logf("high rate = %.1f%%", 100*float64(conf["high"])/float64(total))
	}
	t.Logf("elapsed=%s", time.Since(start).Round(time.Second))
	for _, u := range unmatched {
		t.Logf("  %s", u)
	}
}
