package mediadetect

// matchPlan is the top-level decision made before any TMDB request.
type matchPlan struct {
	run     bool
	status  string
	reason  string
	code    string
	message string
}

// planMatch implements the SPEC-001 4.3.1/4.5.2 priority: local type first,
// then match mode and key availability, and only then an actual match run.
func planMatch(mode MatchMode, key string, hasMovies bool) matchPlan {
	if !hasMovies {
		return matchPlan{status: "not_applicable", reason: "local_type_not_movie"}
	}
	switch mode {
	case MatchOff:
		return matchPlan{status: "disabled", reason: "match_disabled"}
	case MatchAuto:
		if key == "" {
			return matchPlan{status: "disabled", reason: "no_tmdb_key"}
		}
		return matchPlan{run: true}
	case MatchOn:
		if key == "" {
			return matchPlan{status: "error", reason: "tmdb_key_missing", code: ErrTMDBKeyMissing, message: "TMDB_API_KEY is not set"}
		}
		return matchPlan{run: true}
	default:
		return matchPlan{status: "disabled", reason: "match_disabled"}
	}
}

func notApplicableMatch(file *string) Match {
	return Match{
		Status:     "not_applicable",
		Reason:     ptrString("local_type_not_movie"),
		File:       file,
		Candidates: []Candidate{},
	}
}

func matchForPlan(plan matchPlan, file *string) Match {
	m := Match{
		Status:     plan.status,
		Reason:     ptrString(plan.reason),
		File:       file,
		Candidates: []Candidate{},
	}
	if plan.status == "error" {
		m.Error = &ErrorObject{Code: plan.code, Message: plan.message}
	}
	return m
}

func unavailableMatch(file *string) Match {
	return Match{
		Status:     "unavailable",
		Reason:     ptrString("tmdb_unavailable"),
		File:       file,
		Candidates: []Candidate{},
	}
}

func matchError(file, reason, code, message string) Match {
	return Match{
		Status:     "error",
		Reason:     ptrString(reason),
		File:       &file,
		Candidates: []Candidate{},
		Error:      &ErrorObject{Code: code, Message: message},
	}
}
