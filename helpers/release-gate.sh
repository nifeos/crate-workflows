#!/bin/sh
# shellcheck shell=sh
#
# helpers/release-gate.sh: refuse a release whose check or proof runs are not green on the commit
# being released.
#
#     helpers/release-gate.sh <owner/repo> <sha>
#
# The release gate reads the Actions API for runs of the caller's two gating workflows at exactly
# the released commit. "Green" means a completed run with conclusion success; a run still in
# flight is a refusal, not a wait, because the dispatch re-runs in seconds and a gate that waits
# on a run that may yet fail has decided nothing. On a dry run this is still enforced: a rehearsal
# of a commit nobody checked is not a rehearsal of anything.
#
# The workflow filenames are the scaffold's (ci.yml, proofs.yml). A caller that renames them
# raises the release gate's red rather than silently passing, which is the right direction.

set -eu

repo="$1"
sha="$2"

green() {
	# $1 = workflow filename. The API matches on head_sha, so a re-run of an older commit
	# cannot stand in for this one. jq -e fails when no completed, successful run exists,
	# which covers "still in flight" and "never ran" alike.
	gh api "repos/$repo/actions/workflows/$1/runs?head_sha=$sha&per_page=100" |
		jq -e '.workflow_runs[]? | select(.status == "completed" and .conclusion == "success")' >/dev/null
}

for workflow in ci.yml proofs.yml; do
	if green "$workflow"; then
		echo "release-gate: $workflow is green on $sha"
	else
		echo "release-gate: no completed, green run of $workflow on $sha." >&2
		echo "release-gate: merge first and let the push run on main finish; then dispatch the release. A pull request run does not count: it is recorded at the pull request head, not at this commit." >&2
		exit 1
	fi
done
echo "release-gate: $sha is green on both gates"
