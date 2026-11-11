package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func runCLI(t *testing.T, args []string, stdin string) (string, string, int) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	exit := run(args, strings.NewReader(stdin), &stdout, &stderr)
	return stdout.String(), stderr.String(), exit
}

func writeMedia(t *testing.T, name string) string {
	t.Helper()
	root := t.TempDir()
	p := filepath.Join(root, name)
	if err := os.WriteFile(p, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func decodeSingle(t *testing.T, out string) map[string]any {
	t.Helper()
	dec := json.NewDecoder(strings.NewReader(out))
	var obj map[string]any
	if err := dec.Decode(&obj); err != nil {
		t.Fatalf("decode: %v (output=%q)", err, out)
	}
	var extra any
	if err := dec.Decode(&extra); err == nil {
		t.Fatalf("output contains more than one JSON value: %q", out)
	}
	if !strings.HasSuffix(out, "\n") {
		t.Fatalf("output must end with one newline: %q", out)
	}
	return obj
}

func TestCLIVersionAndHelp(t *testing.T) {
	out, _, exit := runCLI(t, []string{"--version"}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["name"] != "mediadetect" || obj["schema_version"] != "1" {
		t.Fatalf("version = %v", obj)
	}

	out, _, exit = runCLI(t, []string{"--help"}, "")
	if exit != 0 || !strings.Contains(out, "MediaDetect") || !strings.Contains(out, "--match") {
		t.Fatalf("help exit=%d output=%q", exit, out)
	}
}

func TestCLIFileGolden(t *testing.T) {
	t.Setenv("TMDB_API_KEY", "")
	path := writeMedia(t, "Inception.2010.1080p.mkv")
	out, _, exit := runCLI(t, []string{"--match=off", "--probe=off", path}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["ok"] != true || obj["media_type"] != "movie" || obj["confidence"] != "high" {
		t.Fatalf("result = %v", obj)
	}
	match := obj["match"].(map[string]any)
	if match["status"] != "disabled" || match["reason"] != "match_disabled" {
		t.Fatalf("match = %v", match)
	}
	files := obj["files"].([]any)
	file := files[0].(map[string]any)
	if file["role"] != "feature" || file["probe_status"] != "skipped" || file["duration_sec"] != nil {
		t.Fatalf("file = %v", file)
	}
	if file["group_key"] != "inception|2010" {
		t.Fatalf("group_key = %v", file["group_key"])
	}
}

func TestCLITVEpisode(t *testing.T) {
	path := writeMedia(t, "Show.2019.S01E01.1080p.mkv")
	out, _, exit := runCLI(t, []string{"--match=off", "--probe=off", path}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["media_type"] != "tv_episode" {
		t.Fatalf("media_type = %v", obj["media_type"])
	}
	file := obj["files"].([]any)[0].(map[string]any)
	if file["season_episode"] != "S01E01" || file["season"].(float64) != 1 || file["episode"].(float64) != 1 {
		t.Fatalf("file = %v", file)
	}
	if file["match"].(map[string]any)["status"] != "not_applicable" {
		t.Fatalf("match = %v", file["match"])
	}
	titles := file["title_candidates"].([]any)
	if len(titles) != 1 || titles[0] != "Show" {
		t.Fatalf("titles = %v", titles)
	}
}

func TestCLIDirectory(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "Show.S01E01.mkv"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, _, exit := runCLI(t, []string{"--match=off", "--probe=off", root}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["media_type"] != "tv_series" {
		t.Fatalf("media_type = %v", obj["media_type"])
	}
	if obj["input"].(map[string]any)["kind"] != "directory" {
		t.Fatalf("input = %v", obj["input"])
	}
}

func TestCLIStdinMatchesDirectPath(t *testing.T) {
	path := writeMedia(t, "Inception.2010.mkv")
	args := []string{"--match=off", "--probe=off", path}
	direct, _, _ := runCLI(t, args, "")
	fromStdin, _, exit := runCLI(t, []string{"--match=off", "--probe=off", "-"}, path+"\n")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	if direct != fromStdin {
		t.Fatalf("stdin output differs:\ndirect=%s\nstdin=%s", direct, fromStdin)
	}
}

func TestCLIInputErrors(t *testing.T) {
	cases := []struct {
		name string
		args []string
		in   string
		code string
	}{
		{name: "missing", args: nil, in: "", code: "ERR_INPUT_REQUIRED"},
		{name: "multiple args", args: []string{"a", "b"}, code: "ERR_INPUT_MULTIPLE"},
		{name: "multiple stdin", args: []string{"-"}, in: "a\nb\n", code: "ERR_INPUT_MULTIPLE"},
		{name: "nul stdin", args: []string{"-"}, in: "a\x00b", code: "ERR_INPUT_INVALID"},
		{name: "invalid flag", args: []string{"--match=maybe", "a"}, code: "ERR_FLAG_INVALID"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			out, _, exit := runCLI(t, tc.args, tc.in)
			if exit != 1 {
				t.Fatalf("exit = %d", exit)
			}
			obj := decodeSingle(t, out)
			if obj["ok"] != false {
				t.Fatalf("ok = %v", obj["ok"])
			}
			errObj := obj["error"].(map[string]any)
			if errObj["code"] != tc.code {
				t.Fatalf("code = %v, want %s", errObj["code"], tc.code)
			}
		})
	}
}

func TestCLIPathNotFound(t *testing.T) {
	out, _, exit := runCLI(t, []string{filepath.Join(t.TempDir(), "missing")}, "")
	if exit != 2 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["error"].(map[string]any)["code"] != "ERR_PATH_NOT_FOUND" {
		t.Fatalf("error = %v", obj["error"])
	}
}

func TestCLINoKeyModes(t *testing.T) {
	t.Setenv("TMDB_API_KEY", "")
	path := writeMedia(t, "Inception.2010.mkv")

	out, _, exit := runCLI(t, []string{"--match=auto", "--probe=off", path}, "")
	if exit != 0 {
		t.Fatalf("auto exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	if obj["match"].(map[string]any)["status"] != "disabled" {
		t.Fatalf("auto match = %v", obj["match"])
	}

	out, _, exit = runCLI(t, []string{"--match=on", "--probe=off", path}, "")
	if exit != 4 {
		t.Fatalf("on exit = %d", exit)
	}
	obj = decodeSingle(t, out)
	match := obj["match"].(map[string]any)
	if match["status"] != "error" || match["error"].(map[string]any)["code"] != "ERR_TMDB_KEY_MISSING" {
		t.Fatalf("on match = %v", match)
	}
}

func TestCLIMockTMDB(t *testing.T) {
	t.Setenv("TMDB_API_KEY", "key")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/search/movie":
			json.NewEncoder(w).Encode(map[string]any{"results": []map[string]any{{
				"id": 27205, "title": "Inception", "original_title": "Inception", "release_date": "2010-07-15",
			}}})
		case r.URL.Path == "/movie/27205":
			json.NewEncoder(w).Encode(map[string]any{
				"id": 27205, "title": "Inception", "release_date": "2010-07-15", "runtime": 148, "imdb_id": "tt1375666",
			})
		case strings.HasSuffix(r.URL.Path, "/alternative_titles"):
			json.NewEncoder(w).Encode(map[string]any{"titles": []string{}})
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	path := writeMedia(t, "Inception.2010.1080p.mkv")
	out, stderr, exit := runCLI(t, []string{"--match=auto", "--probe=off", "--verbose", "--tmdb-base-url", srv.URL, path}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	obj := decodeSingle(t, out)
	match := obj["match"].(map[string]any)
	if match["status"] != "high" {
		t.Fatalf("match = %v", match)
	}
	best := match["best"].(map[string]any)
	if best["imdb_id"] != "tt1375666" {
		t.Fatalf("best = %v", best)
	}
	if !strings.Contains(stderr, "best=27205") || !strings.Contains(stderr, "imdb=tt1375666") {
		t.Fatalf("verbose stderr missing best entry: %q", stderr)
	}
}

func TestCLIPrettyAppliesToErrorsAndVersion(t *testing.T) {
	out, _, exit := runCLI(t, []string{"--pretty", "/definitely/not/here.mkv"}, "")
	if exit != 2 {
		t.Fatalf("exit = %d", exit)
	}
	if !strings.Contains(out, "\n  \"error\"") {
		t.Fatalf("error JSON is not indented: %q", out)
	}

	out, _, exit = runCLI(t, []string{"--version", "--pretty"}, "")
	if exit != 0 {
		t.Fatalf("version exit = %d", exit)
	}
	if !strings.Contains(out, "\n  \"name\"") {
		t.Fatalf("version JSON is not indented: %q", out)
	}
}

func TestCLIFlagsAfterPath(t *testing.T) {
	path := writeMedia(t, "Inception.2010.mkv")
	out, _, exit := runCLI(t, []string{path, "--match=off", "--probe=off"}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	if decodeSingle(t, out)["media_type"] != "movie" {
		t.Fatalf("output = %s", out)
	}
}

func TestCLIZeroWrite(t *testing.T) {
	path := writeMedia(t, "Inception.2010.mkv")
	before := snapshot(t, filepath.Dir(path))
	_, _, exit := runCLI(t, []string{"--match=off", "--probe=off", path}, "")
	if exit != 0 {
		t.Fatalf("exit = %d", exit)
	}
	after := snapshot(t, filepath.Dir(path))
	if len(before) != len(after) {
		t.Fatalf("tree changed: before=%v after=%v", before, after)
	}
	for k, v := range before {
		if after[k] != v {
			t.Fatalf("%s changed: %v -> %v", k, v, after[k])
		}
	}
}

type snap struct {
	size  int64
	mtime int64
	inode uint64
	hash  [sha256.Size]byte
}

func snapshot(t *testing.T, root string) map[string]snap {
	t.Helper()
	out := map[string]snap{}
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(root, path)
		s := snap{size: info.Size(), mtime: info.ModTime().UnixNano()}
		if info.Mode().IsRegular() {
			data, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			s.hash = sha256.Sum256(data)
		}
		if st, ok := info.Sys().(*syscall.Stat_t); ok {
			s.inode = uint64(st.Ino)
		}
		out[rel] = s
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}
