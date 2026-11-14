// Package collect walks a file or directory and returns read-only file facts.
// It has no knowledge of any index: callers decide what to persist.
package collect

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"golang.org/x/text/unicode/norm"

	"github.com/dream-365/MediaTitle/parser"
	"github.com/dream-365/MediaTitle/probe"
)

// Sentinel errors let callers map the failure to their own error codes.
var (
	ErrRootNotExist   = errors.New("collect: root does not exist")
	ErrRootSymlink    = errors.New("collect: root is a symbolic link")
	ErrRootUnreadable = errors.New("collect: root is unreadable")
	// ErrProbeSkipped is returned by a Prober to request probe_status=skipped
	// without counting a probe failure. Detect uses it for --probe=off.
	ErrProbeSkipped = errors.New("collect: probing disabled")
)

// walkDir is injectable so tests can exercise root-level walk failures.
var walkDir = filepath.WalkDir

// CollectedFile is one read-only file fact. RelPath is NFC-normalized and
// uses POSIX separators, matching store keys.
type CollectedFile struct {
	RelPath          string
	SizeBytes        int64
	Mtime            time.Time
	Hints            parser.Hints
	ProbeStatus      string // ok | failed | skipped
	ProbeUnavailable bool   // both ffprobe and exiftool were not executable
	DurationSec      int
	GroupKey         string // non-empty only for feature files
	ProbeError       string // diagnostics only; never persisted as a contract
}

// Counts separates the reasons an entry did not produce a CollectedFile.
type Counts struct {
	FilesSeen       int
	ProbeFailed     int
	Unreadable      int
	SkippedHidden   int
	SkippedSymlinks int
	Truncated       bool
}

// Options controls traversal. MaxDepth/MaxFiles use nil for the default and
// a pointer to zero for "unlimited".
type Options struct {
	MaxDepth   *int
	MaxFiles   *int
	SkipHidden bool
	SkipNames  []string
	Prober     func(ctx context.Context, path string) (probe.Info, error)
}

// Collect walks root. root may be a regular file or a directory. It returns
// the files that were successfully recorded, the relative-path set for
// MarkMissing, and traversal counts. A missing, symlinked or unreadable root
// returns an error rather than an empty success.
func Collect(ctx context.Context, root string, opts Options) ([]CollectedFile, map[string]bool, Counts, error) {
	files := []CollectedFile{}
	seen := map[string]bool{}
	counts := Counts{}

	info, err := os.Lstat(root)
	if err != nil {
		if os.IsNotExist(err) {
			return files, seen, counts, ErrRootNotExist
		}
		return files, seen, counts, ErrRootUnreadable
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return files, seen, counts, ErrRootSymlink
	}

	prober := opts.Prober
	if prober == nil {
		prober = probe.Probe
	}

	if !info.IsDir() {
		if !info.Mode().IsRegular() {
			return files, seen, counts, ErrRootUnreadable
		}
		f, err := os.Open(root)
		if err != nil {
			return files, seen, counts, ErrRootUnreadable
		}
		f.Close()
		base := filepath.Base(root)
		rel := norm.NFC.String(filepath.ToSlash(base))
		cf, err := collectFile(ctx, root, rel, info, prober)
		if err != nil {
			return files, seen, counts, err
		}
		files = append(files, cf)
		seen[rel] = true
		counts.FilesSeen = 1
		if cf.ProbeStatus == "failed" {
			counts.ProbeFailed = 1
		}
		if err := ctx.Err(); err != nil {
			return files, seen, counts, err
		}
		return files, seen, counts, nil
	}

	// An unreadable root is not an empty library. On SMB a disconnected share
	// must fail loudly instead of producing an empty successful scan.
	df, err := os.Open(root)
	if err != nil {
		return files, seen, counts, ErrRootUnreadable
	}
	_, readErr := df.Readdirnames(1)
	df.Close()
	if readErr != nil && !errors.Is(readErr, io.EOF) {
		return files, seen, counts, ErrRootUnreadable
	}

	maxDepth := 8
	if opts.MaxDepth != nil {
		maxDepth = *opts.MaxDepth
	}
	maxFiles := 5000
	if opts.MaxFiles != nil {
		maxFiles = *opts.MaxFiles
	}
	skipNames := opts.SkipNames
	if len(skipNames) == 0 {
		skipNames = []string{".mstruct"}
	}

	walkErr := walkDir(root, func(p string, d fs.DirEntry, walkErr error) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		if walkErr != nil {
			if p == root {
				// A root that disappears or becomes unreadable between the
				// precheck and WalkDir must not look like an empty library.
				return walkErr
			}
			counts.Unreadable++
			return nil
		}
		if p == root {
			return nil
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			counts.Unreadable++
			return nil
		}
		rel = norm.NFC.String(filepath.ToSlash(rel))
		name := d.Name()

		if d.IsDir() {
			if skipName(name, skipNames) {
				counts.SkippedHidden++
				return fs.SkipDir
			}
			if opts.SkipHidden && strings.HasPrefix(name, ".") {
				counts.SkippedHidden++
				return fs.SkipDir
			}
			if maxDepth > 0 && strings.Count(rel, "/") >= maxDepth {
				return fs.SkipDir
			}
			return nil
		}
		if d.Type()&fs.ModeSymlink != 0 {
			counts.SkippedSymlinks++
			return nil
		}
		if skipName(name, skipNames) || (opts.SkipHidden && strings.HasPrefix(name, ".")) {
			counts.SkippedHidden++
			return nil
		}
		if maxFiles > 0 && len(files) >= maxFiles {
			counts.Truncated = true
			return fs.SkipAll
		}
		fi, err := d.Info()
		if err != nil {
			counts.Unreadable++
			return nil
		}
		// Probe the raw WalkDir path. rel is NFC for output/store keys, but
		// rebuilding the path from it would fail on normalization-sensitive
		// filesystems (ext4/SMB) that store NFD names.
		cf, err := collectFile(ctx, p, rel, fi, prober)
		if err != nil {
			return err
		}
		files = append(files, cf)
		seen[rel] = true
		counts.FilesSeen++
		if cf.ProbeStatus == "failed" {
			counts.ProbeFailed++
		}
		return nil
	})
	if walkErr != nil {
		return files, seen, counts, walkErr
	}
	if err := ctx.Err(); err != nil {
		return files, seen, counts, err
	}
	sort.Slice(files, func(i, j int) bool { return files[i].RelPath < files[j].RelPath })
	return files, seen, counts, nil
}

func collectFile(ctx context.Context, fullPath, rel string, info fs.FileInfo, prober func(context.Context, string) (probe.Info, error)) (CollectedFile, error) {
	if err := ctx.Err(); err != nil {
		return CollectedFile{}, err
	}
	hints := parser.Parse(rel)
	cf := CollectedFile{
		RelPath:     rel,
		SizeBytes:   info.Size(),
		Mtime:       info.ModTime(),
		Hints:       hints,
		ProbeStatus: "skipped",
	}
	if hints.RoleHint == parser.RoleFeature {
		cf.GroupKey = parser.GroupKey(rel, hints)
		probed, err := prober(ctx, fullPath)
		switch {
		case err == nil:
			cf.ProbeStatus = "ok"
			cf.DurationSec = probed.DurationSec
		case errors.Is(err, ErrProbeSkipped):
			// Explicitly disabled; not a failure.
		case errors.Is(err, probe.ErrUnavailable):
			cf.ProbeStatus = "failed"
			cf.ProbeUnavailable = true
			cf.ProbeError = err.Error()
		default:
			cf.ProbeStatus = "failed"
			cf.ProbeError = err.Error()
		}
	}
	if err := ctx.Err(); err != nil {
		return CollectedFile{}, err
	}
	return cf, nil
}

func skipName(name string, names []string) bool {
	for _, n := range names {
		if strings.EqualFold(name, n) {
			return true
		}
	}
	return false
}
