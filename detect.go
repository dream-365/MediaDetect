package mediadetect

import (
	"context"
	"errors"
	"io"
	"os"
	pathpkg "path"
	"path/filepath"
	"strings"

	"golang.org/x/text/unicode/norm"

	"github.com/dream-365/MediaDetect/collect"
	"github.com/dream-365/MediaDetect/probe"
)

// detectSkipNames are always skipped by the CLI. Callers that use collect
// directly can pass their own narrower SkipNames list.
var detectSkipNames = []string{
	".mstruct",
	"@eaDir",
	"#recycle",
	"$RECYCLE.BIN",
	"System Volume Information",
	".Trashes",
	".Spotlight-V100",
	".fseventsd",
}

// Detect inspects exactly one file or directory. It never writes to the input
// tree and never creates persistent state.
func Detect(ctx context.Context, inputPath string, opts Options) (Result, error) {
	if err := ctx.Err(); err != nil {
		return Result{}, newError(ErrCanceled, "detection canceled")
	}
	if strings.TrimSpace(inputPath) == "" {
		return Result{}, newError(ErrInputRequired, "a path is required")
	}
	if strings.ContainsRune(inputPath, 0) {
		return Result{}, newError(ErrInputInvalid, "path cannot be resolved")
	}
	absPath, err := filepath.Abs(inputPath)
	if err != nil {
		return Result{}, newError(ErrInputInvalid, "path cannot be resolved")
	}
	absFS := filepath.Clean(absPath)
	absDisplay := norm.NFC.String(absFS)

	info, err := os.Lstat(absFS)
	if err != nil {
		if os.IsNotExist(err) {
			return Result{}, newError(ErrPathNotFound, "path not found")
		}
		return Result{}, newError(ErrPathUnreadable, "path is not readable")
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return Result{}, newError(ErrInputSymlink, "input path is a symbolic link")
	}
	kind := "file"
	if info.IsDir() {
		kind = "directory"
	} else if !info.Mode().IsRegular() {
		return Result{}, newError(ErrPathUnreadable, "input is not a regular file or directory")
	}
	if err := precheckReadable(absFS, kind); err != nil {
		return Result{}, newError(ErrPathUnreadable, "path is not readable")
	}

	probeMode, probeErr := normalizeProbeMode(opts.ProbeMode)
	if probeErr != nil {
		return Result{}, probeErr
	}
	matchMode, matchErr := normalizeMatchMode(opts.MatchMode)
	if matchErr != nil {
		return Result{}, matchErr
	}

	warnings := newWarningSet()
	prober := func(ctx context.Context, path string) (probe.Info, error) {
		if probeMode == ProbeOff {
			return probe.Info{}, collect.ErrProbeSkipped
		}
		if opts.Prober != nil {
			return opts.Prober.Probe(ctx, path)
		}
		return probe.Probe(ctx, path)
	}

	collected, _, counts, cerr := collect.Collect(ctx, absFS, collect.Options{
		MaxDepth:   opts.MaxDepth,
		MaxFiles:   opts.MaxFiles,
		SkipHidden: !opts.IncludeHidden,
		SkipNames:  detectSkipNames,
		Prober:     prober,
	})
	if cerr != nil {
		return Result{}, mapCollectError(ctx, cerr)
	}
	if counts.Truncated {
		warnings.add("scan.truncated", "max-files reached", nil)
	}
	if counts.SkippedHidden > 0 {
		warnings.add("scan.skipped_hidden", "hidden entries were skipped", nil)
	}
	if counts.SkippedSymlinks > 0 {
		warnings.add("scan.skipped_symlink", "symbolic links were skipped", nil)
	}
	if counts.Unreadable > 0 {
		warnings.add("scan.unreadable", "unreadable entries were skipped", nil)
	}

	results := buildFileResults(collected, warnings)
	groups, byIndex := buildMovieGroups(results)
	plan := planMatch(matchMode, opts.TMDB.APIKey, len(groups) > 0)
	if opts.LLMFallback && opts.Resolver == nil {
		warnings.add("match.llm_key_missing", "DEEPSEEK_API_KEY is not set; continuing without LLM expansion", nil)
	}

	var groupResults []groupResult
	usedTMDB := false
	if plan.run {
		var matchRunErr *Error
		groupResults, usedTMDB, matchRunErr = runMovieMatching(ctx, opts, matchMode, results, collected, groups, candidateLimit(opts), warnings)
		if matchRunErr != nil {
			return Result{}, matchRunErr
		}
	}
	applyFileMatches(results, byIndex, groupResults, plan)

	distinct := computeDistinct(groups, groupResults, plan.run)
	unmatchedGroups := computeUnmatchedGroups(groups, groupResults, plan)
	mixed := hasType(results, "movie") && hasType(results, "tv_episode")
	topMatch := assembleTopMatch(matchMode, results, groups, groupResults, plan, mixed, distinct, warnings)

	mediaType, confidence := aggregateType(results, distinct, absDisplay)
	title, year := topTitleYear(results, mediaType)
	if kind == "file" && len(results) == 1 {
		// A single file has no directory to aggregate: its own type is the
		// answer. Directory aggregation would turn one episode into tv_series.
		mediaType = results[0].MediaType
		confidence = results[0].Confidence
		title, year = fileTitleYear(results[0])
	}
	summary := buildSummary(results, counts, distinct, unmatchedGroups, mediaType, absDisplay)

	var attribution *string
	if usedTMDB {
		v := TMDBAttribution
		attribution = &v
	}
	if err := ctx.Err(); err != nil {
		return Result{}, newError(ErrCanceled, "detection canceled")
	}

	return Result{
		SchemaVersion: SchemaVersion,
		OK:            true,
		Input:         &Input{Path: absDisplay, Kind: kind},
		MediaType:     mediaType,
		Confidence:    confidence,
		Title:         title,
		Year:          year,
		Summary:       summary,
		Files:         results,
		Match:         topMatch,
		Detection: Detection{
			ProbeMode: string(probeMode),
			MatchMode: string(matchMode),
			Warnings:  warnings.list(),
			Truncated: counts.Truncated,
		},
		Attribution: attribution,
	}, nil
}

func normalizeProbeMode(mode ProbeMode) (ProbeMode, *Error) {
	switch mode {
	case "", ProbeAuto:
		return ProbeAuto, nil
	case ProbeOff:
		return ProbeOff, nil
	default:
		return "", newError(ErrFlagInvalid, "probe mode must be auto or off")
	}
}

func normalizeMatchMode(mode MatchMode) (MatchMode, *Error) {
	switch mode {
	case "", MatchAuto:
		return MatchAuto, nil
	case MatchOn:
		return MatchOn, nil
	case MatchOff:
		return MatchOff, nil
	default:
		return "", newError(ErrFlagInvalid, "match mode must be auto, on or off")
	}
}

func candidateLimit(opts Options) int {
	if opts.TMDB.CandidateLimit <= 0 {
		return 5
	}
	if opts.TMDB.CandidateLimit > 20 {
		return 20
	}
	return opts.TMDB.CandidateLimit
}

func precheckReadable(path, kind string) error {
	if kind == "directory" {
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		_, readErr := f.Readdirnames(1)
		f.Close()
		if readErr != nil && !errors.Is(readErr, io.EOF) {
			return readErr
		}
		return nil
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	return f.Close()
}

func mapCollectError(ctx context.Context, err error) *Error {
	if ctx.Err() != nil || errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return newError(ErrCanceled, "detection canceled")
	}
	switch {
	case errors.Is(err, collect.ErrRootNotExist):
		return newError(ErrPathNotFound, "path not found")
	case errors.Is(err, collect.ErrRootSymlink):
		return newError(ErrInputSymlink, "input path is a symbolic link")
	case errors.Is(err, collect.ErrRootUnreadable):
		return newError(ErrPathUnreadable, "path is not readable")
	default:
		return newError(ErrPathUnreadable, "failed to read input")
	}
}

func buildFileResults(collected []collect.CollectedFile, warnings *warningSet) []FileResult {
	out := make([]FileResult, 0, len(collected))
	for _, cf := range collected {
		ft := mapFile(cf.Hints)
		season, episode := parseSeasonEpisode(cf.Hints.SeasonEpisode)
		var duration *int
		if cf.ProbeStatus == "ok" && cf.DurationSec > 0 {
			duration = ptrInt(cf.DurationSec)
		}
		var groupKey *string
		if ft.mediaType == "movie" && cf.GroupKey != "" {
			v := cf.GroupKey
			groupKey = &v
		}
		var seasonEpisode *string
		if cf.Hints.SeasonEpisode != "" {
			v := cf.Hints.SeasonEpisode
			seasonEpisode = &v
		}
		var auxiliaryKind *string
		if ft.auxKind != "" {
			v := ft.auxKind
			auxiliaryKind = &v
		}
		out = append(out, FileResult{
			Path:            cf.RelPath,
			Name:            pathpkg.Base(cf.RelPath),
			Ext:             cf.Hints.Ext,
			Role:            cf.Hints.RoleHint,
			MediaType:       ft.mediaType,
			Confidence:      ft.confidence,
			TitleCandidates: displayTitles(cf.Hints),
			YearCandidates:  sortedYears(cf.Hints.YearCandidates),
			Edition:         ptrString(cf.Hints.Edition),
			Resolution:      ptrString(cf.Hints.Resolution),
			Source:          ptrString(cf.Hints.Source),
			Codec:           ptrString(cf.Hints.Codec),
			ReleaseGroup:    ptrString(cf.Hints.Group),
			SeasonEpisode:   seasonEpisode,
			Season:          season,
			Episode:         episode,
			AuxiliaryKind:   auxiliaryKind,
			GroupKey:        groupKey,
			ProbeStatus:     cf.ProbeStatus,
			DurationSec:     duration,
		})
		if cf.ProbeStatus == "failed" {
			file := cf.RelPath
			if cf.ProbeUnavailable {
				warnings.add("probe.unavailable", cf.ProbeError, &file)
			} else {
				warnings.add("probe.failed", cf.ProbeError, &file)
			}
		}
	}
	return out
}

func applyFileMatches(results []FileResult, byIndex []*movieGroup, groupResults []groupResult, plan matchPlan) {
	byGroup := map[*movieGroup]groupResult{}
	union := map[int]groupResult{}
	for _, gr := range groupResults {
		byGroup[gr.group] = gr
		if gr.matched && gr.match.Best != nil {
			id := gr.match.Best.TMDBID
			if prev, ok := union[id]; !ok || gr.score > prev.score {
				union[id] = gr
			}
		}
	}
	for i := range results {
		file := results[i].Path
		if results[i].MediaType != "movie" {
			results[i].Match = notApplicableMatch(&file)
			continue
		}
		if !plan.run {
			results[i].Match = matchForPlan(plan, &file)
			continue
		}
		group := byIndex[i]
		gr, ok := byGroup[group]
		if !ok {
			results[i].Match = unavailableMatch(&file)
			continue
		}
		if gr.matched && gr.match.Best != nil {
			// Union by TMDB id: every file whose group resolved to the same
			// movie shares the highest-scoring group's match payload.
			if u, ok := union[gr.match.Best.TMDBID]; ok {
				gr = u
			}
		}
		m := gr.match
		m.File = &file
		results[i].Match = m
	}
}
