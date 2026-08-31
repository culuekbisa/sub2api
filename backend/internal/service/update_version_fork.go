package service

import (
	"strconv"
	"strings"
)

// compareVersions compares the upstream semantic version and the optional
// fork revision. A plain upstream version is revision zero, so a fork build
// such as 0.1.183-fork.1 is newer than 0.1.183 without changing the upstream
// base version shown to operators.
//
// This file holds the fork-specific ordering logic in isolation so that
// backend/internal/service/update_service.go stays aligned with upstream and
// upstream-only changes to that file do not collide with fork edits here.
func compareVersions(current, latest string) int {
	currentParts := parseVersion(current)
	latestParts := parseVersion(latest)

	for i := 0; i < 3; i++ {
		if currentParts.core[i] < latestParts.core[i] {
			return -1
		}
		if currentParts.core[i] > latestParts.core[i] {
			return 1
		}
	}
	if currentParts.forkRevision < latestParts.forkRevision {
		return -1
	}
	if currentParts.forkRevision > latestParts.forkRevision {
		return 1
	}
	return 0
}

type comparableVersion struct {
	core         [3]int
	forkRevision int
}

func parseVersion(v string) comparableVersion {
	v = strings.TrimSpace(strings.TrimPrefix(v, "v"))
	coreAndSuffix := strings.SplitN(v, "-", 2)
	parts := strings.Split(coreAndSuffix[0], ".")
	result := comparableVersion{}
	for i := 0; i < len(parts) && i < len(result.core); i++ {
		if parsed, err := strconv.Atoi(parts[i]); err == nil {
			result.core[i] = parsed
		}
	}

	if len(coreAndSuffix) == 2 {
		suffixParts := strings.Split(coreAndSuffix[1], ".")
		if len(suffixParts) >= 2 && strings.EqualFold(suffixParts[0], "fork") {
			if parsed, err := strconv.Atoi(suffixParts[1]); err == nil && parsed >= 0 {
				result.forkRevision = parsed
			}
		}
	}

	return result
}
