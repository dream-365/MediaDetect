package parser

import "testing"

func TestGroupKeyUsesFirstTitleCandidateAndYear(t *testing.T) {
	h := Hints{TitleCandidates: []string{"Blood Diamond", "示例电影"}, YearCandidates: []int{2006}}
	if got := GroupKey("Blood.Diamond.2020.mkv", h); got != "blooddiamond|2006" {
		t.Fatalf("group key = %q", got)
	}
}

func TestGroupKeyFallsBackToBasename(t *testing.T) {
	h := Hints{}
	if got := GroupKey("Sub/无题 (2019).mkv", h); got != "无题2019|" {
		t.Fatalf("group key = %q", got)
	}
}

func TestGroupKeyKeepsSequelsDistinct(t *testing.T) {
	a := GroupKey("示例侦探.2015.mkv", Hints{TitleCandidates: []string{"示例侦探"}, YearCandidates: []int{2015}})
	b := GroupKey("示例侦探2.2018.mkv", Hints{TitleCandidates: []string{"示例侦探2"}, YearCandidates: []int{2018}})
	if a == b {
		t.Fatalf("sequel keys collided: %q", a)
	}
}
