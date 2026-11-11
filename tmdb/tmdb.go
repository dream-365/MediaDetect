// Package tmdb is the TMDB adapter: search, details, caching and rate limits.
package tmdb

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Movie is the subset of a TMDB entry that mstruct uses.
type Movie struct {
	ID            int
	Title         string
	OriginalTitle string
	ReleaseDate   string
	Popularity    float64
	Runtime       int
	IMDbID        string
}

// Year returns the release year, or 0 when unknown.
func (m Movie) Year() int {
	if len(m.ReleaseDate) < 4 {
		return 0
	}
	y, err := strconv.Atoi(m.ReleaseDate[:4])
	if err != nil || y < 1888 {
		return 0
	}
	return y
}

// Options configures a Client. The zero value is valid.
type Options struct {
	APIKey     string
	BaseURL    string
	Language   string
	HTTPClient *http.Client // nil => 10s-timeout default client
	CacheLimit int          // 0 => 10000 entries per in-process map
}

// Client talks to the TMDB API.
type Client struct {
	key          string
	baseURL      string
	lang         string
	includeAdult bool
	http         *http.Client
	cacheLimit   int

	requests atomic.Int64

	mu      sync.Mutex
	search  map[string][]Movie
	details map[int]Movie
	aliases map[int][]string
}

// Requests reports how many HTTP attempts this client has made. Successful
// cache hits do not count. Callers use it to decide whether TMDB attribution
// is actually required.
func (c *Client) Requests() int64 {
	return c.requests.Load()
}

// New builds a client with the legacy three-argument signature. baseURL
// defaults to the public API.
func New(key, baseURL, lang string) *Client {
	return NewWithOptions(Options{APIKey: key, BaseURL: baseURL, Language: lang})
}

// NewWithOptions builds a client with explicit transport and cache settings.
func NewWithOptions(o Options) *Client {
	baseURL := o.BaseURL
	if baseURL == "" {
		baseURL = "https://api.themoviedb.org/3"
	}
	lang := o.Language
	if lang == "" {
		lang = "zh-CN"
	}
	hc := o.HTTPClient
	if hc == nil {
		hc = &http.Client{Timeout: 10 * time.Second}
	}
	limit := o.CacheLimit
	if limit <= 0 {
		limit = 10000
	}
	return &Client{
		key:     o.APIKey,
		baseURL: strings.TrimRight(baseURL, "/"),
		lang:    lang,
		// Personal library: adult titles are legitimate entries, and TMDB
		// hides them from search unless explicitly requested.
		includeAdult: true,
		http:         hc,
		cacheLimit:   limit,
		search:       map[string][]Movie{},
		details:      map[int]Movie{},
		aliases:      map[int][]string{},
	}
}

type searchResponse struct {
	Results []struct {
		ID            int     `json:"id"`
		Title         string  `json:"title"`
		OriginalTitle string  `json:"original_title"`
		ReleaseDate   string  `json:"release_date"`
		Popularity    float64 `json:"popularity"`
	} `json:"results"`
}

type detailResponse struct {
	ID            int    `json:"id"`
	Title         string `json:"title"`
	OriginalTitle string `json:"original_title"`
	ReleaseDate   string `json:"release_date"`
	Runtime       int    `json:"runtime"`
	IMDbID        string `json:"imdb_id"`
}

// Search returns candidates for a title. year is an optional hint; passing 0
// searches without a year so that wrong file-name years do not hide the entry.
func (c *Client) Search(ctx context.Context, query string, year int) ([]Movie, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, nil
	}
	key := fmt.Sprintf("%s|%d|%s", query, year, c.lang)
	c.mu.Lock()
	if v, ok := c.search[key]; ok {
		c.mu.Unlock()
		return v, nil
	}
	c.mu.Unlock()

	q := url.Values{}
	q.Set("query", query)
	q.Set("language", c.lang)
	q.Set("include_adult", strconv.FormatBool(c.includeAdult))
	if year > 0 {
		q.Set("year", strconv.Itoa(year))
	}
	var resp searchResponse
	if err := c.get(ctx, "/search/movie", q, &resp); err != nil {
		return nil, err
	}
	out := make([]Movie, 0, len(resp.Results))
	for _, r := range resp.Results {
		out = append(out, Movie{
			ID: r.ID, Title: r.Title, OriginalTitle: r.OriginalTitle,
			ReleaseDate: r.ReleaseDate, Popularity: r.Popularity,
		})
	}
	c.mu.Lock()
	if len(c.search) < c.cacheLimit {
		c.search[key] = out
	}
	c.mu.Unlock()
	return out, nil
}

// Details fetches runtime and IMDb id for one entry.
func (c *Client) Details(ctx context.Context, id int) (Movie, error) {
	c.mu.Lock()
	if v, ok := c.details[id]; ok {
		c.mu.Unlock()
		return v, nil
	}
	c.mu.Unlock()

	q := url.Values{}
	q.Set("language", c.lang)
	var resp detailResponse
	if err := c.get(ctx, fmt.Sprintf("/movie/%d", id), q, &resp); err != nil {
		return Movie{}, err
	}
	m := Movie{
		ID: resp.ID, Title: resp.Title, OriginalTitle: resp.OriginalTitle,
		ReleaseDate: resp.ReleaseDate, Runtime: resp.Runtime * 60, IMDbID: resp.IMDbID,
	}
	c.mu.Lock()
	if len(c.details) < c.cacheLimit {
		c.details[id] = m
	}
	c.mu.Unlock()
	return m, nil
}

type altTitlesResponse struct {
	Titles []struct {
		Title string `json:"title"`
	} `json:"titles"`
}

// Aliases returns every title variant TMDB knows for a movie, across regions
// and languages.
func (c *Client) Aliases(ctx context.Context, id int) ([]string, error) {
	c.mu.Lock()
	if v, ok := c.aliases[id]; ok {
		c.mu.Unlock()
		return v, nil
	}
	c.mu.Unlock()

	q := url.Values{}
	var resp altTitlesResponse
	if err := c.get(ctx, fmt.Sprintf("/movie/%d/alternative_titles", id), q, &resp); err != nil {
		return nil, err
	}
	out := make([]string, 0, len(resp.Titles))
	for _, t := range resp.Titles {
		if t.Title != "" {
			out = append(out, t.Title)
		}
	}
	c.mu.Lock()
	if len(c.aliases) < c.cacheLimit {
		c.aliases[id] = out
	}
	c.mu.Unlock()
	return out, nil
}

func (c *Client) get(ctx context.Context, endpointPath string, q url.Values, dst any) error {
	if c.key == "" {
		return errors.New("TMDB API key is empty")
	}
	values := url.Values{}
	for k, v := range q {
		values[k] = append([]string(nil), v...)
	}
	if !strings.HasPrefix(c.key, "eyJ") {
		values.Set("api_key", c.key)
	}
	endpoint := c.baseURL + endpointPath + "?" + values.Encode()

	attempts429, attemptsOther := 0, 0
	backoff429, backoffOther := time.Second, 2*time.Second
	var lastErr error
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
		if err != nil {
			// Do not echo the endpoint: it contains the query string.
			return fmt.Errorf("tmdb %s: request error", endpointPath)
		}
		req.Header.Set("Accept", "application/json")
		if strings.HasPrefix(c.key, "eyJ") {
			req.Header.Set("Authorization", "Bearer "+c.key)
		}
		c.requests.Add(1)
		resp, err := c.http.Do(req)
		if err != nil {
			if ctxErr := ctx.Err(); ctxErr != nil {
				return ctxErr
			}
			attemptsOther++
			lastErr = fmt.Errorf("tmdb %s: network error", endpointPath)
			if attemptsOther >= 3 {
				return givingUp(endpointPath, attemptsOther, lastErr)
			}
			if err := sleep(ctx, backoffOther); err != nil {
				return err
			}
			backoffOther = nextBackoff(backoffOther, 30*time.Second)
			continue
		}
		body, readErr := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
		resp.Body.Close()
		if readErr != nil {
			if ctxErr := ctx.Err(); ctxErr != nil {
				return ctxErr
			}
			attemptsOther++
			lastErr = fmt.Errorf("tmdb %s: response read error", endpointPath)
			if attemptsOther >= 3 {
				return givingUp(endpointPath, attemptsOther, lastErr)
			}
			if err := sleep(ctx, backoffOther); err != nil {
				return err
			}
			backoffOther = nextBackoff(backoffOther, 30*time.Second)
			continue
		}
		switch {
		case resp.StatusCode == http.StatusOK:
			if err := json.Unmarshal(body, dst); err != nil {
				return fmt.Errorf("tmdb %s: decode error: %w", endpointPath, err)
			}
			return nil
		case resp.StatusCode == http.StatusTooManyRequests:
			attempts429++
			lastErr = fmt.Errorf("tmdb %s: status 429", endpointPath)
			if attempts429 >= 5 {
				return givingUp(endpointPath, attempts429, lastErr)
			}
			if err := sleep(ctx, backoff429); err != nil {
				return err
			}
			backoff429 = nextBackoff(backoff429, time.Minute)
		case resp.StatusCode >= 500:
			attemptsOther++
			lastErr = fmt.Errorf("tmdb %s: status %d", endpointPath, resp.StatusCode)
			if attemptsOther >= 3 {
				return givingUp(endpointPath, attemptsOther, lastErr)
			}
			if err := sleep(ctx, backoffOther); err != nil {
				return err
			}
			backoffOther = nextBackoff(backoffOther, 30*time.Second)
		default:
			// Never include the response body: it may echo request data.
			return fmt.Errorf("tmdb %s: status %d", endpointPath, resp.StatusCode)
		}
	}
}

func givingUp(path string, attempts int, err error) error {
	return fmt.Errorf("tmdb %s: giving up after %d attempts: %w", path, attempts, err)
}

func sleep(ctx context.Context, d time.Duration) error {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

func nextBackoff(cur, max time.Duration) time.Duration {
	cur *= 2
	if cur > max {
		return max
	}
	return cur
}
