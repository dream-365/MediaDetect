package collect

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"

	"golang.org/x/text/unicode/norm"

	"github.com/dream-365/MediaTitle/parser"
	"github.com/dream-365/MediaTitle/probe"
)

func write(t *testing.T, root, name string) string {
	t.Helper()
	p := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func stubProber(duration int) func(context.Context, string) (probe.Info, error) {
	return func(context.Context, string) (probe.Info, error) {
		return probe.Info{DurationSec: duration}, nil
	}
}

func TestCollectDirectory(t *testing.T) {
	root := t.TempDir()
	write(t, root, "Inception.2010.1080p.mkv")
	write(t, root, "Show.S01E01.mkv")
	write(t, root, "poster.jpg")
	write(t, root, ".hidden.mkv")
	write(t, root, ".mstruct/index.sqlite")

	files, seen, counts, err := Collect(context.Background(), root, Options{
		SkipHidden: true,
		SkipNames:  []string{".mstruct"},
		Prober:     stubProber(8880),
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 3 {
		t.Fatalf("files = %d, want 3: %+v", len(files), files)
	}
	if counts.FilesSeen != 3 || counts.SkippedHidden != 2 {
		t.Fatalf("counts = %+v", counts)
	}
	if !seen["Inception.2010.1080p.mkv"] || !seen["Show.S01E01.mkv"] {
		t.Fatalf("seen = %+v", seen)
	}
	byPath := map[string]CollectedFile{}
	for _, f := range files {
		byPath[f.RelPath] = f
	}
	movie := byPath["Inception.2010.1080p.mkv"]
	if movie.ProbeStatus != "ok" || movie.DurationSec != 8880 || movie.GroupKey == "" {
		t.Fatalf("movie = %+v", movie)
	}
	if movie.Hints.RoleHint != parser.RoleFeature {
		t.Fatalf("movie role = %s", movie.Hints.RoleHint)
	}
	episode := byPath["Show.S01E01.mkv"]
	if episode.ProbeStatus != "skipped" || episode.GroupKey != "" {
		t.Fatalf("episode = %+v", episode)
	}
	if byPath["poster.jpg"].Hints.RoleHint != parser.RoleArtwork {
		t.Fatalf("poster role = %s", byPath["poster.jpg"].Hints.RoleHint)
	}
}

func TestCollectFileRoot(t *testing.T) {
	root := t.TempDir()
	p := write(t, root, "Inception.2010.1080p.mkv")
	files, seen, counts, err := Collect(context.Background(), p, Options{Prober: stubProber(8880)})
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 1 || files[0].RelPath != "Inception.2010.1080p.mkv" {
		t.Fatalf("files = %+v", files)
	}
	if !seen["Inception.2010.1080p.mkv"] || counts.FilesSeen != 1 {
		t.Fatalf("seen=%+v counts=%+v", seen, counts)
	}
}

func TestCollectMaxFilesTruncated(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a.mkv")
	write(t, root, "b.mkv")
	write(t, root, "c.mkv")
	limit := 2
	files, _, counts, err := Collect(context.Background(), root, Options{MaxFiles: &limit, Prober: stubProber(1)})
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 2 || !counts.Truncated {
		t.Fatalf("files=%d truncated=%v", len(files), counts.Truncated)
	}
}

func TestCollectMaxDepth(t *testing.T) {
	root := t.TempDir()
	write(t, root, "root.mkv")
	write(t, root, "one/one.mkv")
	write(t, root, "one/two/two.mkv")
	limit := 1
	files, _, _, err := Collect(context.Background(), root, Options{MaxDepth: &limit, Prober: stubProber(1)})
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 2 {
		t.Fatalf("files = %+v, want root.mkv and one/one.mkv", files)
	}
}

func TestCollectSkipsSymlinks(t *testing.T) {
	root := t.TempDir()
	target := write(t, root, "target.mkv")
	link := filepath.Join(root, "link.mkv")
	if err := os.Symlink(target, link); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	_, seen, counts, err := Collect(context.Background(), root, Options{Prober: stubProber(1)})
	if err != nil {
		t.Fatal(err)
	}
	if counts.SkippedSymlinks != 1 {
		t.Fatalf("skipped symlinks = %d", counts.SkippedSymlinks)
	}
	if seen["link.mkv"] {
		t.Fatal("symlink must not enter seen")
	}
}

func TestCollectRejectsSymlinkRoot(t *testing.T) {
	root := t.TempDir()
	target := write(t, root, "target.mkv")
	link := filepath.Join(t.TempDir(), "link.mkv")
	if err := os.Symlink(target, link); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	if _, _, _, err := Collect(context.Background(), link, Options{}); !errors.Is(err, ErrRootSymlink) {
		t.Fatalf("err = %v, want ErrRootSymlink", err)
	}
}

func TestCollectRejectsUnreadableRoot(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root can read a 000 directory")
	}
	root := t.TempDir()
	write(t, root, "a.mkv")
	if err := os.Chmod(root, 0o000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(root, 0o755) })
	if _, _, _, err := Collect(context.Background(), root, Options{}); !errors.Is(err, ErrRootUnreadable) {
		t.Fatalf("err = %v, want ErrRootUnreadable", err)
	}
}

func TestCollectProbeSkipped(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a.mkv")
	prober := func(context.Context, string) (probe.Info, error) {
		return probe.Info{}, ErrProbeSkipped
	}
	files, _, counts, err := Collect(context.Background(), root, Options{Prober: prober})
	if err != nil {
		t.Fatal(err)
	}
	if files[0].ProbeStatus != "skipped" || counts.ProbeFailed != 0 {
		t.Fatalf("file=%+v counts=%+v", files[0], counts)
	}
}

func TestCollectContextCanceled(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a.mkv")
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, _, _, err := Collect(ctx, root, Options{Prober: stubProber(1)}); !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want context.Canceled", err)
	}
}

func TestCollectRootWalkFailure(t *testing.T) {
	root := t.TempDir()
	old := walkDir
	walkDir = func(root string, fn fs.WalkDirFunc) error {
		return fn(root, nil, errors.New("boom"))
	}
	defer func() { walkDir = old }()

	if _, _, _, err := Collect(context.Background(), root, Options{Prober: stubProber(1)}); err == nil || err.Error() != "boom" {
		t.Fatalf("err = %v, want root walk error", err)
	}
}

func TestCollectCancelAfterProbe(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a.mkv")
	ctx, cancel := context.WithCancel(context.Background())
	prober := func(context.Context, string) (probe.Info, error) {
		cancel()
		return probe.Info{DurationSec: 1}, nil
	}
	if _, _, _, err := Collect(ctx, root, Options{Prober: prober}); !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v, want context.Canceled", err)
	}
}

func TestCollectProbesRawNFDPath(t *testing.T) {
	root := t.TempDir()
	raw := "Café.2010.mkv"
	if err := os.WriteFile(filepath.Join(root, raw), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	var probed string
	prober := func(_ context.Context, path string) (probe.Info, error) {
		probed = path
		return probe.Info{DurationSec: 1}, nil
	}
	files, _, _, err := Collect(context.Background(), root, Options{Prober: prober})
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(root, raw); probed != want {
		t.Fatalf("probe path = %q, want raw %q", probed, want)
	}
	if len(files) != 1 || files[0].RelPath != norm.NFC.String(raw) {
		t.Fatalf("rel path = %+v, want NFC", files)
	}
}

func TestCollectProbeUnavailable(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a.mkv")
	prober := func(context.Context, string) (probe.Info, error) {
		return probe.Info{}, probe.ErrUnavailable
	}
	files, _, counts, err := Collect(context.Background(), root, Options{Prober: prober})
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != 1 || !files[0].ProbeUnavailable || counts.ProbeFailed != 1 {
		t.Fatalf("files=%+v counts=%+v", files, counts)
	}
}
