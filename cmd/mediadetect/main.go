// Command mediadetect inspects one file or directory and prints one JSON
// object. It never creates an index, cache or temporary file.
package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"

	"github.com/dream-365/MediaTitle/mediadetect"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) (exit int) {
	defer func() {
		if recovered := recover(); recovered != nil {
			writeError(stdout, stderr, mediadetect.ErrInternal, "internal error", 3, false)
			exit = 3
		}
	}()

	cfg, positional, parseErr := parseArgs(args)
	if parseErr != nil {
		return writeError(stdout, stderr, parseErr.code, parseErr.message, 1, false)
	}
	if cfg.help {
		fmt.Fprint(stdout, helpText)
		return 0
	}
	if cfg.version {
		writeVersion(stdout, cfg.pretty)
		return 0
	}

	path, inputErr := resolveInput(positional, stdin)
	if inputErr != nil {
		return writeError(stdout, stderr, inputErr.code, inputErr.message, 1, cfg.pretty)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	result, err := mediadetect.Detect(ctx, path, cfg.toOptions())
	if err != nil {
		code := mediadetect.ErrInternal
		message := err.Error()
		exit := 3
		if e, ok := err.(*mediadetect.Error); ok {
			code = e.Code
			message = e.Message
			exit = exitCodeFor(code)
		}
		return writeError(stdout, stderr, code, message, exit, cfg.pretty)
	}
	if ctx.Err() != nil {
		return writeError(stdout, stderr, mediadetect.ErrCanceled, "detection canceled", 130, cfg.pretty)
	}
	if cfg.verbose {
		writeVerbose(stderr, result)
	}
	if err := writeJSON(stdout, result, cfg.pretty); err != nil {
		return writeError(stdout, stderr, mediadetect.ErrInternal, "json encoding failed", 3, cfg.pretty)
	}

	if result.Match.Status == "error" && result.Match.Error != nil {
		return 4
	}
	return 0
}
