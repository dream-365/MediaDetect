// Package probe reads technical metadata with ffprobe, falling back to
// exiftool. It never writes media.
package probe

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// ErrUnavailable means neither ffprobe nor exiftool could be executed. A
// tool that runs but fails is a probe failure, not an unavailable one.
var ErrUnavailable = errors.New("probe tools unavailable")

// Info is the technical subset mstruct stores on a version.
type Info struct {
	DurationSec int
	Resolution  string
	Codec       string
}

type ffprobeOutput struct {
	Streams []struct {
		CodecName string `json:"codec_name"`
		Width     int    `json:"width"`
		Height    int    `json:"height"`
	} `json:"streams"`
	Format struct {
		Duration string `json:"duration"`
	} `json:"format"`
}

type exiftoolOutput struct {
	Duration    json.RawMessage
	ImageWidth  int
	ImageHeight int
	VideoCodec  string
}

// Probe reads duration, resolution and codec. ffprobe is preferred; when it is
// unavailable (missing shared libraries, or the file is not supported) the
// exiftool fallback keeps the runtime signal available. Both tools share one
// 10-second budget so a pathological file cannot cost 20 seconds.
func Probe(ctx context.Context, path string) (Info, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	info, ffErr := probeFFprobe(ctx, path)
	if ffErr == nil {
		return info, nil
	}
	info, exErr := probeExiftool(ctx, path)
	if exErr == nil {
		return info, nil
	}
	if errors.Is(ffErr, exec.ErrNotFound) && errors.Is(exErr, exec.ErrNotFound) {
		return Info{}, fmt.Errorf("%w: ffprobe: %v; exiftool: %v", ErrUnavailable, ffErr, exErr)
	}
	return Info{}, fmt.Errorf("ffprobe: %v; exiftool: %w", ffErr, exErr)
}

func probeFFprobe(ctx context.Context, path string) (Info, error) {
	cmd := exec.CommandContext(ctx, "ffprobe",
		"-v", "error",
		"-show_entries", "format=duration:stream=codec_name,width,height",
		"-of", "json",
		path,
	)
	out, err := cmd.Output()
	if err != nil {
		return Info{}, fmt.Errorf("ffprobe %s: %w", path, err)
	}
	var parsed ffprobeOutput
	if err := json.Unmarshal(out, &parsed); err != nil {
		return Info{}, fmt.Errorf("parse ffprobe output for %s: %w", path, err)
	}
	info := Info{}
	if d, err := strconv.ParseFloat(parsed.Format.Duration, 64); err == nil {
		info.DurationSec = int(d + 0.5)
	}
	for _, s := range parsed.Streams {
		if s.Width > 0 && s.Height > 0 {
			info.Resolution = ResolutionLabel(s.Width, s.Height)
			info.Codec = strings.ToUpper(s.CodecName)
			break
		}
	}
	if info.Resolution == "" && len(parsed.Streams) > 0 {
		info.Codec = strings.ToUpper(parsed.Streams[0].CodecName)
	}
	if info.DurationSec == 0 && info.Resolution == "" {
		return Info{}, fmt.Errorf("ffprobe returned no duration or resolution for %s", path)
	}
	return info, nil
}

func probeExiftool(ctx context.Context, path string) (Info, error) {
	cmd := exec.CommandContext(ctx, "exiftool",
		"-api", "LargeFileSupport=1",
		"-n", "-j", "-Duration", "-ImageWidth", "-ImageHeight", "-VideoCodec", path)
	out, err := cmd.Output()
	if err != nil {
		return Info{}, fmt.Errorf("exiftool %s: %w", path, err)
	}
	return parseExiftool(out)
}

func parseExiftool(out []byte) (Info, error) {
	var rows []exiftoolOutput
	if err := json.Unmarshal(out, &rows); err != nil {
		return Info{}, fmt.Errorf("parse exiftool output: %w", err)
	}
	if len(rows) == 0 {
		return Info{}, fmt.Errorf("exiftool returned no entries")
	}
	r := rows[0]
	duration := parseDuration(r.Duration)
	if duration <= 0 && r.ImageWidth == 0 {
		return Info{}, fmt.Errorf("exiftool returned no duration or resolution")
	}
	info := Info{DurationSec: int(duration + 0.5), Codec: strings.ToUpper(r.VideoCodec)}
	if r.ImageWidth > 0 && r.ImageHeight > 0 {
		info.Resolution = ResolutionLabel(r.ImageWidth, r.ImageHeight)
	}
	return info, nil
}

// parseDuration accepts the two shapes exiftool emits: a number of seconds
// (-n) or a "HH:MM:SS.ffffff" string for Matroska tags it cannot numericise.
func parseDuration(raw json.RawMessage) float64 {
	s := strings.Trim(strings.TrimSpace(string(raw)), `"`)
	if s == "" || s == "null" {
		return 0
	}
	if f, err := strconv.ParseFloat(s, 64); err == nil {
		return f
	}
	parts := strings.Split(s, ":")
	if len(parts) != 3 {
		return 0
	}
	h, err1 := strconv.Atoi(parts[0])
	m, err2 := strconv.Atoi(parts[1])
	sec, err3 := strconv.ParseFloat(parts[2], 64)
	if err1 != nil || err2 != nil || err3 != nil {
		return 0
	}
	return float64(h*3600+m*60) + sec
}

// ResolutionLabel maps a frame size to the conventional label.
func ResolutionLabel(w, h int) string {
	switch {
	case h >= 2000:
		return "2160p"
	case h >= 1000:
		return "1080p"
	case h >= 700:
		return "720p"
	case h >= 500:
		return "540p"
	case h >= 400:
		return "480p"
	default:
		return fmt.Sprintf("%dx%d", w, h)
	}
}
