package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestQueries(t *testing.T) {
	var gotAuth string
	var gotBody chatRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Errorf("path = %s", r.URL.Path)
		}
		gotAuth = r.Header.Get("Authorization")
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatal(err)
		}
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{
				{"message": map[string]string{"content": "```json\n{\"queries\":[\"Thirteen Lives\",\"十三条命\",\"Thirteen Lives\"]}\n```"}},
			},
		})
	}))
	defer srv.Close()

	c := New(Config{BaseURL: srv.URL, APIKey: "key", Model: "deepseek-flash"})
	got, err := c.Queries(context.Background(), "示例片14.2022.mkv", []string{"示例片14"}, 2022, 8820)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0] != "Thirteen Lives" {
		t.Fatalf("queries = %v", got)
	}
	if gotAuth != "Bearer key" {
		t.Fatalf("auth = %q", gotAuth)
	}
	if gotBody.Model != "deepseek-flash" || gotBody.Temperature != 0 {
		t.Fatalf("request = %+v", gotBody)
	}
	if len(gotBody.Messages) != 2 {
		t.Fatalf("messages = %d", len(gotBody.Messages))
	}
}

func TestParseQueriesRejectsGarbage(t *testing.T) {
	if _, err := parseQueries("sorry, I cannot help"); err == nil {
		t.Fatal("expected error for a response without JSON")
	}
	q, err := parseQueries(`{"queries":["  ","x","x","y"]}`)
	if err != nil {
		t.Fatal(err)
	}
	if len(q) != 2 || q[0] != "x" || q[1] != "y" {
		t.Fatalf("queries = %v", q)
	}
}

func TestFromEnv(t *testing.T) {
	t.Setenv("DEEPSEEK_API_KEY", "")
	if _, err := FromEnv(); err == nil {
		t.Fatal("expected error without a key")
	}
	t.Setenv("DEEPSEEK_API_KEY", "k")
	t.Setenv("DEEPSEEK_MODEL", "")
	c, err := FromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if c.cfg.Model != "deepseek-flash" {
		t.Fatalf("model = %s", c.cfg.Model)
	}
}
