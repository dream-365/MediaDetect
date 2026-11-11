package tmdb

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

func TestErrorsDoNotLeakKeyQueryOrBody(t *testing.T) {
	const secret = "super-secret-key"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		fmt.Fprintf(w, `{"error":"bad request for %s","echo":"%s"}`, r.URL.RawQuery, secret)
	}))
	defer srv.Close()

	c := New(secret, srv.URL, "zh-CN")
	_, err := c.Search(context.Background(), "Inception", 2010)
	if err == nil {
		t.Fatal("expected an error")
	}
	msg := err.Error()
	for _, bad := range []string{secret, "api_key", "query=", "bad request", "echo"} {
		if strings.Contains(msg, bad) {
			t.Fatalf("error leaked %q: %s", bad, msg)
		}
	}
}

func TestCacheLimitStopsGrowth(t *testing.T) {
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		fmt.Fprint(w, `{"results":[]}`)
	}))
	defer srv.Close()

	c := NewWithOptions(Options{APIKey: "key", BaseURL: srv.URL, CacheLimit: 1})
	ctx := context.Background()
	if _, err := c.Search(ctx, "a", 0); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Search(ctx, "b", 0); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Search(ctx, "b", 0); err != nil {
		t.Fatal(err)
	}
	if got := calls.Load(); got != 3 {
		t.Fatalf("calls = %d, want 3 (second query was not cached)", got)
	}
	if got := c.Requests(); got != int64(calls.Load()) {
		t.Fatalf("Requests() = %d, want %d", got, calls.Load())
	}
}

func TestHTTPClientIsInjectable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"results":[]}`)
	}))
	defer srv.Close()

	var used atomic.Bool
	c := NewWithOptions(Options{
		APIKey:  "key",
		BaseURL: srv.URL,
		HTTPClient: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
			used.Store(true)
			return http.DefaultTransport.RoundTrip(r)
		})},
	})
	if _, err := c.Search(context.Background(), "x", 0); err != nil {
		t.Fatal(err)
	}
	if !used.Load() {
		t.Fatal("injected HTTP client was not used")
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
