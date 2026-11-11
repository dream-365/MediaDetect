package probe

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestParseExiftool(t *testing.T) {
	out := []byte(`[{"SourceFile":"/x/a.mkv","Duration":7008.009,"ImageWidth":1920,"ImageHeight":1080,"VideoCodec":"HEVC"}]`)
	info, err := parseExiftool(out)
	if err != nil {
		t.Fatal(err)
	}
	if info.DurationSec != 7008 {
		t.Errorf("duration = %d", info.DurationSec)
	}
	if info.Resolution != "1080p" {
		t.Errorf("resolution = %q", info.Resolution)
	}
	if info.Codec != "HEVC" {
		t.Errorf("codec = %q", info.Codec)
	}
}

func TestParseExiftoolStringDuration(t *testing.T) {
	out := []byte(`[{"SourceFile":"/x/a.mkv","Duration":"01:47:59.019000000","ImageWidth":1920,"ImageHeight":722}]`)
	info, err := parseExiftool(out)
	if err != nil {
		t.Fatal(err)
	}
	if info.DurationSec != 6479 {
		t.Errorf("duration = %d, want 6479", info.DurationSec)
	}
	if info.Resolution != "720p" {
		t.Errorf("resolution = %q", info.Resolution)
	}
}

func TestParseExiftoolMissing(t *testing.T) {
	if _, err := parseExiftool([]byte(`[{"SourceFile":"/x/a.txt"}]`)); err == nil {
		t.Fatal("expected error for a file without duration or resolution")
	}
}

func TestProbeUnavailableOnlyWhenBothToolsMissing(t *testing.T) {
	path := filepath.Join(t.TempDir(), "a.mkv")
	if err := os.WriteFile(path, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", t.TempDir())
	if _, err := Probe(context.Background(), path); !errors.Is(err, ErrUnavailable) {
		t.Fatalf("both tools missing: err = %v, want ErrUnavailable", err)
	}

	dir := t.TempDir()
	ffprobe := filepath.Join(dir, "ffprobe")
	if err := os.WriteFile(ffprobe, []byte("#!/bin/sh\nexit 1\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir)
	if _, err := Probe(context.Background(), path); err == nil || errors.Is(err, ErrUnavailable) {
		t.Fatalf("ffprobe failed but exiftool missing: err = %v, want ordinary probe failure", err)
	}
}

func TestResolutionLabel(t *testing.T) {
	cases := map[[2]int]string{
		{3840, 2160}: "2160p",
		{1920, 1080}: "1080p",
		{1280, 720}:  "720p",
		{1920, 804}:  "720p",
		{720, 576}:   "540p",
		{640, 480}:   "480p",
	}
	for size, want := range cases {
		if got := ResolutionLabel(size[0], size[1]); got != want {
			t.Errorf("%dx%d = %q, want %q", size[0], size[1], got, want)
		}
	}
}
