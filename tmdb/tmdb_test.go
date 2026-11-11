package tmdb

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSearchParsesAndCaches(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.URL.Path != "/search/movie" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.URL.Query().Get("api_key") != "key" {
			t.Errorf("api_key missing")
		}
		fmt.Fprint(w, `{"results":[{"id":1,"title":"示例电影","original_title":"Blood Diamond","release_date":"2006-12-08","popularity":10}]}`)
	}))
	defer srv.Close()

	c := New("key", srv.URL, "zh-CN")
	got, err := c.Search(context.Background(), "Blood Diamond", 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].Year() != 2006 || got[0].OriginalTitle != "Blood Diamond" {
		t.Fatalf("got %+v", got)
	}
	if _, err := c.Search(context.Background(), "Blood Diamond", 0); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatalf("calls = %d, want 1 (cache hit)", calls)
	}
}

func TestSearchRetriesOn429(t *testing.T) {
	attempts := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts == 1 {
			http.Error(w, "slow down", http.StatusTooManyRequests)
			return
		}
		fmt.Fprint(w, `{"results":[]}`)
	}))
	defer srv.Close()

	c := New("key", srv.URL, "zh-CN")
	if _, err := c.Search(context.Background(), "x", 0); err != nil {
		t.Fatal(err)
	}
	if attempts != 2 {
		t.Fatalf("attempts = %d, want 2", attempts)
	}
}

func TestDetails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"id":7,"title":"T","release_date":"2001-01-01","runtime":123,"imdb_id":"tt0000007"}`)
	}))
	defer srv.Close()

	c := New("key", srv.URL, "zh-CN")
	m, err := c.Details(context.Background(), 7)
	if err != nil {
		t.Fatal(err)
	}
	if m.Runtime != 123*60 || m.IMDbID != "tt0000007" {
		t.Fatalf("got %+v", m)
	}
}
