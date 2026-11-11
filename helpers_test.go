package mediadetect

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func writeFile(t *testing.T, root, name string) string {
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

func offlineOptions() Options {
	return Options{ProbeMode: ProbeOff, MatchMode: MatchOff}
}

func detectOK(t *testing.T, path string, opts Options) Result {
	t.Helper()
	result, err := Detect(context.Background(), path, opts)
	if err != nil {
		t.Fatalf("Detect: %v", err)
	}
	return result
}

func detectErrorCode(t *testing.T, path string, opts Options) string {
	t.Helper()
	_, err := Detect(context.Background(), path, opts)
	if err == nil {
		t.Fatal("expected an error")
	}
	e, ok := err.(*Error)
	if !ok {
		t.Fatalf("error type = %T", err)
	}
	return e.Code
}
