package mediadetect

import "github.com/dream-365/MediaDetect/probe"

// ErrProbeUnavailable reports that the configured prober could not read
// technical metadata. It is the same sentinel as probe.ErrUnavailable, so
// errors.Is works with either value.
var ErrProbeUnavailable = probe.ErrUnavailable

// Top-level error codes. Match infrastructure failures live in Match.Error
// instead and are not returned as a top-level error.
const (
	ErrInputRequired   = "ERR_INPUT_REQUIRED"
	ErrInputMultiple   = "ERR_INPUT_MULTIPLE"
	ErrInputInvalid    = "ERR_INPUT_INVALID"
	ErrFlagInvalid     = "ERR_FLAG_INVALID"
	ErrPathNotFound    = "ERR_PATH_NOT_FOUND"
	ErrInputSymlink    = "ERR_INPUT_SYMLINK"
	ErrPathUnreadable  = "ERR_PATH_UNREADABLE"
	ErrInternal        = "ERR_INTERNAL"
	ErrCanceled        = "ERR_CANCELED"
	ErrTMDBKeyMissing  = "ERR_TMDB_KEY_MISSING"
	ErrTMDBUnavailable = "ERR_TMDB_UNAVAILABLE"
)

// Error is the structured error returned by Detect. The CLI serializes it
// into the minimal {"ok":false,...} object.
type Error struct {
	Code    string
	Message string
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}
	if e.Message == "" {
		return e.Code
	}
	return e.Code + ": " + e.Message
}

func newError(code, message string) *Error {
	return &Error{Code: code, Message: message}
}
