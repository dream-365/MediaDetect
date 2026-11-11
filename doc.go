// Package mediadetect classifies one file or directory as a movie, TV
// episode/season/series, non-feature content, auxiliary file or other.
//
// Detect is read-only and stateless: it does not create an index, cache or
// temporary file. Movie metadata can be matched against TMDB; TV detection is
// local only in this version.
package mediadetect
