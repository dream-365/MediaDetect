package mediadetect

import (
	"context"
	"crypto/sha256"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"syscall"
	"testing"

	"github.com/dream-365/MediaTitle/probe"
)

func TestDetectNoKeyAutoDegrades(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	result := detectOK(t, root, Options{ProbeMode: ProbeOff, MatchMode: MatchAuto})
	if result.Match.Status != "disabled" || result.Match.Reason == nil || *result.Match.Reason != "no_tmdb_key" {
		t.Fatalf("top match = %+v", result.Match)
	}
	if result.Files[0].Match.Status != "disabled" {
		t.Fatalf("file match = %+v", result.Files[0].Match)
	}
	if result.Attribution != nil {
		t.Fatalf("attribution = %v, want nil", *result.Attribution)
	}
	if !hasWarning(result, "match.no_key") {
		t.Fatalf("warnings = %+v", result.Detection.Warnings)
	}
}

func TestDetectNoKeyOnReturnsMatchError(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	result := detectOK(t, root, Options{ProbeMode: ProbeOff, MatchMode: MatchOn})
	if result.Match.Status != "error" || result.Match.Error == nil || result.Match.Error.Code != ErrTMDBKeyMissing {
		t.Fatalf("top match = %+v", result.Match)
	}
	if result.Files[0].Match.Status != "error" {
		t.Fatalf("file match = %+v", result.Files[0].Match)
	}
}

func TestDetectTVWithoutKeyDoesNotFail(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Show.S01E01.mkv")
	result := detectOK(t, root, Options{ProbeMode: ProbeOff, MatchMode: MatchOn})
	if result.MediaType != "tv_series" && result.MediaType != "tv_season" {
		t.Fatalf("media_type = %s", result.MediaType)
	}
	if result.Match.Status != "not_applicable" || result.Match.Error != nil {
		t.Fatalf("match = %+v", result.Match)
	}
	if !hasWarning(result, "match.tv_not_supported") {
		t.Fatalf("warnings = %+v", result.Detection.Warnings)
	}
}

func TestDetectCanceled(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := Detect(ctx, root, offlineOptions())
	if err == nil {
		t.Fatal("expected an error")
	}
	e, ok := err.(*Error)
	if !ok || e.Code != ErrCanceled {
		t.Fatalf("err = %v", err)
	}
}

func TestDetectAuxiliaryAndNonFeatureWithoutKey(t *testing.T) {
	auxRoot := t.TempDir()
	writeFile(t, auxRoot, "poster.jpg")
	aux := detectOK(t, auxRoot, Options{ProbeMode: ProbeOff, MatchMode: MatchOn})
	if aux.MediaType != "auxiliary" {
		t.Fatalf("aux media_type = %s", aux.MediaType)
	}
	if aux.Match.Status != "not_applicable" || aux.Match.Error != nil {
		t.Fatalf("aux match = %+v", aux.Match)
	}

	nfRoot := t.TempDir()
	writeFile(t, nfRoot, "Show.S01E01.sample.mkv")
	nf := detectOK(t, nfRoot, Options{ProbeMode: ProbeOff, MatchMode: MatchOn})
	if nf.MediaType != "non_feature" {
		t.Fatalf("nf media_type = %s", nf.MediaType)
	}
	if nf.Match.Status != "not_applicable" || nf.Match.Error != nil {
		t.Fatalf("nf match = %+v", nf.Match)
	}
}

func TestDetectMatchOffMakesNoRequests(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.1080p.mkv")
	var calls int
	opts := Options{
		ProbeMode: ProbeOff,
		MatchMode: MatchOff,
		TMDB: TMDBOptions{
			APIKey: "key",
			HTTPClient: &http.Client{Transport: countTransport(func(*http.Request) {
				calls++
			})},
		},
	}
	_ = detectOK(t, root, opts)
	if calls != 0 {
		t.Fatalf("HTTP calls = %d, want 0", calls)
	}
}

func TestDetectTVMakesNoRequests(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Show.S01E01.mkv")
	var calls int
	opts := Options{
		ProbeMode: ProbeOff,
		MatchMode: MatchAuto,
		TMDB: TMDBOptions{
			APIKey: "key",
			HTTPClient: &http.Client{Transport: countTransport(func(*http.Request) {
				calls++
			})},
		},
	}
	_ = detectOK(t, root, opts)
	if calls != 0 {
		t.Fatalf("HTTP calls = %d, want 0", calls)
	}
}

func TestDetectZeroWrite(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")
	writeFile(t, root, "Show.S01E01.mkv")
	writeFile(t, root, "poster.jpg")
	before := snapshotTree(t, root)
	_ = detectOK(t, root, offlineOptions())
	after := snapshotTree(t, root)
	if !reflect.DeepEqual(before, after) {
		t.Fatalf("input tree changed:\nbefore=%v\nafter=%v", before, after)
	}
}

func TestDetectInputErrors(t *testing.T) {
	if code := detectErrorCode(t, "", offlineOptions()); code != ErrInputRequired {
		t.Fatalf("empty path code = %s", code)
	}
	if code := detectErrorCode(t, filepath.Join(t.TempDir(), "missing"), offlineOptions()); code != ErrPathNotFound {
		t.Fatalf("not found code = %s", code)
	}

	root := t.TempDir()
	target := writeFile(t, root, "target.mkv")
	link := filepath.Join(t.TempDir(), "link.mkv")
	if err := os.Symlink(target, link); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	if code := detectErrorCode(t, link, offlineOptions()); code != ErrInputSymlink {
		t.Fatalf("symlink code = %s", code)
	}

	if os.Geteuid() != 0 {
		unreadable := t.TempDir()
		writeFile(t, unreadable, "a.mkv")
		if err := os.Chmod(unreadable, 0o000); err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = os.Chmod(unreadable, 0o755) })
		if code := detectErrorCode(t, unreadable, offlineOptions()); code != ErrPathUnreadable {
			t.Fatalf("unreadable code = %s", code)
		}
	}
}

func TestDetectHiddenAndTruncated(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "a.mkv")
	writeFile(t, root, "b.mkv")
	writeFile(t, root, ".hidden.mkv")
	limit := 1
	result := detectOK(t, root, Options{ProbeMode: ProbeOff, MatchMode: MatchOff, MaxFiles: &limit})
	if !result.Detection.Truncated || !hasWarning(result, "scan.truncated") {
		t.Fatalf("truncated=%v warnings=%+v", result.Detection.Truncated, result.Detection.Warnings)
	}
	if result.Summary.SkippedHidden != 1 {
		t.Fatalf("skipped_hidden = %d", result.Summary.SkippedHidden)
	}

	root2 := t.TempDir()
	writeFile(t, root2, "a.mkv")
	writeFile(t, root2, ".hidden.mkv")
	hidden := detectOK(t, root2, offlineOptions())
	if hidden.Summary.TotalFiles != 1 {
		t.Fatalf("default hidden total = %d", hidden.Summary.TotalFiles)
	}
	included := detectOK(t, root2, Options{ProbeMode: ProbeOff, MatchMode: MatchOff, IncludeHidden: true})
	if included.Summary.TotalFiles != 2 {
		t.Fatalf("include-hidden total = %d", included.Summary.TotalFiles)
	}
}

func TestDetectProbeModes(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Inception.2010.mkv")

	off := detectOK(t, root, Options{MatchMode: MatchOff, ProbeMode: ProbeOff})
	if off.Files[0].ProbeStatus != "skipped" || off.Files[0].DurationSec != nil {
		t.Fatalf("off file = %+v", off.Files[0])
	}

	failing := Options{
		MatchMode: MatchOff,
		Prober: proberFunc(func(context.Context, string) (MediaInfo, error) {
			return MediaInfo{}, errors.New("boom")
		}),
	}
	failed := detectOK(t, root, failing)
	if failed.Files[0].ProbeStatus != "failed" || !hasWarning(failed, "probe.failed") {
		t.Fatalf("failed file = %+v warnings=%+v", failed.Files[0], failed.Detection.Warnings)
	}

	unavailable := Options{
		MatchMode: MatchOff,
		Prober: proberFunc(func(context.Context, string) (MediaInfo, error) {
			return MediaInfo{}, errors.Join(probe.ErrUnavailable, errors.New(`exec: "ffprobe": executable file not found in $PATH`))
		}),
	}
	missing := detectOK(t, root, unavailable)
	if !hasWarning(missing, "probe.unavailable") {
		t.Fatalf("warnings = %+v", missing.Detection.Warnings)
	}
}

type proberFunc func(context.Context, string) (MediaInfo, error)

func (f proberFunc) Probe(ctx context.Context, path string) (MediaInfo, error) {
	return f(ctx, path)
}

type countTransport func(*http.Request)

func (f countTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	f(req)
	return nil, errors.New("no network in this test")
}

func TestDetectNULPathIsInvalid(t *testing.T) {
	_, err := Detect(context.Background(), "a\x00b", Options{})
	e, ok := err.(*Error)
	if !ok || e.Code != ErrInputInvalid {
		t.Fatalf("err = %v, want %s", err, ErrInputInvalid)
	}
}

func TestDetectLLMKeyWarningWithoutGroups(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "Show.S01E01.mkv")
	result := detectOK(t, root, Options{
		ProbeMode:   ProbeOff,
		MatchMode:   MatchOff,
		LLMFallback: true,
	})
	if !hasWarning(result, "match.llm_key_missing") {
		t.Fatalf("warnings = %+v", result.Detection.Warnings)
	}
}

func TestDetectAttributionRequiresRequest(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "!!!.mkv")
	result := detectOK(t, root, Options{
		ProbeMode: ProbeOff,
		MatchMode: MatchAuto,
		TMDB: TMDBOptions{
			APIKey:  "key",
			BaseURL: "http://127.0.0.1:1",
		},
	})
	if result.Attribution != nil {
		t.Fatalf("attribution = %q without a TMDB request", *result.Attribution)
	}
}

func hasWarning(result Result, code string) bool {
	for _, warning := range result.Detection.Warnings {
		if warning.Code == code {
			return true
		}
	}
	return false
}

type fileSnapshot struct {
	Size  int64
	Mtime int64
	Inode uint64
	Mode  os.FileMode
	Hash  [sha256.Size]byte
}

func snapshotTree(t *testing.T, root string) map[string]fileSnapshot {
	t.Helper()
	out := map[string]fileSnapshot{}
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		snap := fileSnapshot{Size: info.Size(), Mtime: info.ModTime().UnixNano(), Mode: info.Mode()}
		if info.Mode().IsRegular() {
			data, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			snap.Hash = sha256.Sum256(data)
		}
		if st, ok := info.Sys().(*syscall.Stat_t); ok {
			snap.Inode = uint64(st.Ino)
		}
		out[rel] = snap
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}
