package main

import (
	"io"
	"os"
	"strings"

	"github.com/dream-365/MediaTitle"
)

func resolveInput(positional []string, stdin io.Reader) (string, *cliError) {
	if len(positional) > 1 {
		return "", &cliError{code: mediadetect.ErrInputMultiple, message: "exactly one path is allowed"}
	}
	if len(positional) == 1 && positional[0] != "-" {
		if strings.TrimSpace(positional[0]) == "" {
			return "", &cliError{code: mediadetect.ErrInputRequired, message: "a path is required"}
		}
		return positional[0], nil
	}
	if len(positional) == 1 || !isTTY(stdin) {
		path, err := readStdinPath(stdin)
		if err != nil {
			return "", err
		}
		return path, nil
	}
	return "", &cliError{code: mediadetect.ErrInputRequired, message: "a path is required"}
}

func readStdinPath(stdin io.Reader) (string, *cliError) {
	data, err := io.ReadAll(io.LimitReader(stdin, 1<<20))
	if err != nil {
		return "", &cliError{code: mediadetect.ErrInputInvalid, message: "cannot read stdin"}
	}
	if strings.ContainsRune(string(data), '\x00') {
		return "", &cliError{code: mediadetect.ErrInputInvalid, message: "stdin contains a NUL byte"}
	}
	var lines []string
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			lines = append(lines, line)
		}
	}
	switch len(lines) {
	case 0:
		return "", &cliError{code: mediadetect.ErrInputRequired, message: "stdin is empty"}
	case 1:
		return lines[0], nil
	default:
		return "", &cliError{code: mediadetect.ErrInputMultiple, message: "stdin must contain exactly one path"}
	}
}

func isTTY(r io.Reader) bool {
	f, ok := r.(*os.File)
	if !ok {
		return false
	}
	info, err := f.Stat()
	if err != nil {
		return false
	}
	return info.Mode()&os.ModeCharDevice != 0
}
