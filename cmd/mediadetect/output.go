package main

import (
	"encoding/json"
	"fmt"
	"io"

	"github.com/dream-365/MediaTitle"
)

func writeVersion(w io.Writer, pretty bool) {
	writeJSON(w, map[string]string{
		"name":           "mediadetect",
		"display_name":   "MediaDetect",
		"version":        buildVersion(),
		"schema_version": mediadetect.SchemaVersion,
	}, pretty)
}

func writeError(stdout, stderr io.Writer, code, message string, exit int, pretty bool) int {
	payload := map[string]any{
		"schema_version": mediadetect.SchemaVersion,
		"ok":             false,
		"input":          nil,
		"error": map[string]string{
			"code":    code,
			"message": message,
		},
	}
	writeJSON(stdout, payload, pretty)
	if stderr != nil {
		fmt.Fprintf(stderr, "%s: %s\n", code, message)
	}
	return exit
}

func writeJSON(w io.Writer, value any, pretty bool) error {
	var (
		data []byte
		err  error
	)
	if pretty {
		data, err = json.MarshalIndent(value, "", "  ")
	} else {
		data, err = json.Marshal(value)
	}
	if err != nil {
		return err
	}
	data = append(data, '\n')
	_, err = w.Write(data)
	return err
}

func exitCodeFor(code string) int {
	switch code {
	case mediadetect.ErrCanceled:
		return 130
	case mediadetect.ErrPathNotFound, mediadetect.ErrPathUnreadable, mediadetect.ErrInputSymlink:
		return 2
	case mediadetect.ErrInternal:
		return 3
	default:
		return 1
	}
}

func writeVerbose(w io.Writer, result mediadetect.Result) {
	kind := ""
	if result.Input != nil {
		kind = result.Input.Kind
	}
	fmt.Fprintf(w, "path=%s kind=%s media_type=%s confidence=%s files=%d match=%s%s\n",
		pathOf(result), kind, result.MediaType, result.Confidence, result.Summary.TotalFiles, result.Match.Status, bestVerbose(result.Match.Best))
	for _, file := range result.Files {
		fmt.Fprintf(w, "  %s type=%s probe=%s match=%s%s\n",
			file.Path, file.MediaType, file.ProbeStatus, file.Match.Status, bestVerbose(file.Match.Best))
	}
}

func bestVerbose(best *mediadetect.Candidate) string {
	if best == nil {
		return ""
	}
	imdb := "-"
	if best.IMDbID != nil {
		imdb = *best.IMDbID
	}
	return fmt.Sprintf(" best=%d %q imdb=%s score=%.3f", best.TMDBID, best.Title, imdb, best.Score)
}

func pathOf(result mediadetect.Result) string {
	if result.Input == nil {
		return ""
	}
	return result.Input.Path
}
