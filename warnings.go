package mediadetect

import "sort"

type warningSet struct {
	items map[string]Warning
}

func newWarningSet() *warningSet {
	return &warningSet{items: map[string]Warning{}}
}

func (w *warningSet) add(code, detail string, file *string) {
	fileValue := ""
	if file != nil {
		fileValue = *file
	}
	key := code + "\x00" + fileValue
	if _, exists := w.items[key]; exists {
		return
	}
	var fileCopy *string
	if file != nil {
		v := *file
		fileCopy = &v
	}
	w.items[key] = Warning{Code: code, Detail: detail, File: fileCopy}
}

func (w *warningSet) list() []Warning {
	out := make([]Warning, 0, len(w.items))
	for _, item := range w.items {
		out = append(out, item)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Code != out[j].Code {
			return out[i].Code < out[j].Code
		}
		left, right := "", ""
		if out[i].File != nil {
			left = *out[i].File
		}
		if out[j].File != nil {
			right = *out[j].File
		}
		return left < right
	})
	return out
}

// has reports whether a code was recorded at least once.
func (w *warningSet) has(code string) bool {
	for _, item := range w.items {
		if item.Code == code {
			return true
		}
	}
	return false
}
