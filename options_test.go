package mediadetect

import (
	"errors"
	"testing"

	"github.com/dream-365/MediaDetect/probe"
)

func TestMediaInfoConversion(t *testing.T) {
	want := MediaInfo{DurationSec: 90, Resolution: "1920x1080", Codec: "hevc"}
	got := MediaInfo(probe.Info(want))
	if got != want {
		t.Fatalf("round trip = %+v, want %+v", got, want)
	}
	if probe.Info(want) != (probe.Info{DurationSec: 90, Resolution: "1920x1080", Codec: "hevc"}) {
		t.Fatalf("conversion changed fields: %+v", probe.Info(want))
	}
}

func TestErrProbeUnavailable(t *testing.T) {
	if !errors.Is(ErrProbeUnavailable, probe.ErrUnavailable) {
		t.Fatal("ErrProbeUnavailable is not the probe sentinel")
	}
	err := errors.Join(ErrProbeUnavailable, errors.New("boom"))
	if !errors.Is(err, probe.ErrUnavailable) {
		t.Fatal("joined error lost the probe sentinel")
	}
}
