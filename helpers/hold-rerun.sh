#!/bin/sh
# shellcheck shell=sh
#
# helpers/hold-rerun.sh: once a hold is released, rerun every failed or cancelled hold run on a
# pull request's current head, so the newest result is the one GitHub counts. Ported from nife's
# helper of the same behavior (#1766: the release landed, an older red run still counted, and the
# pull request sat out of the queue until a person reran it by hand).
#
#     helpers/hold-rerun.sh <pr-number> <owner/repo> [workflow-file]
#
# Exit 0: done (reran something, or nothing needed it). 1: a hold label is still on, so nothing was
# rerun. 2: the API could not be read. Caller: the ruled.yml workflow, on `architect-ruled` added
# or `needs-architect` / `held-by-lane` removed.
#
# "Released" is hold.yml's own test, copied because the required check runs with no checkout:
# `held-by-lane` holds; else `architect-ruled` releases; else `needs-architect` holds; else
# released. Change one and you must change the other.
#
# Runs still in flight are waited for first (bounded by HOLD_RERUN_WAIT tries of HOLD_RERUN_SLEEP
# seconds), because a run started by the label that was just removed can still land red after this
# pass. The labels are read after that wait. A rerun race with another trigger loses its `gh run
# rerun` call and logs it, rather than failing.

set -u
pr="$1"
repo="$2"
workflow="${3:-hold.yml}"
tries="${HOLD_RERUN_WAIT:-12}"
nap="${HOLD_RERUN_SLEEP:-15}"

sha="$(gh api "repos/$repo/pulls/$pr" --jq .head.sha 2>/dev/null)" || sha=""
if [ -z "$sha" ]; then
	echo "hold-rerun: could not read the head of PR #$pr" >&2
	exit 2
fi

runs() {
	gh api "repos/$repo/actions/workflows/$workflow/runs?head_sha=$sha&event=pull_request&per_page=100" 2>/dev/null
}

json=""
i=0
while :; do
	json="$(runs)" || {
		echo "hold-rerun: could not list hold runs for $sha" >&2
		exit 2
	}
	busy="$(printf '%s' "$json" | jq '[.workflow_runs[] | select(.status != "completed")] | length')" || exit 2
	[ "$busy" = 0 ] && break
	i=$((i + 1))
	if [ "$i" -ge "$tries" ]; then
		echo "hold-rerun: $busy hold run(s) on $sha still running after $tries tries; rerunning what has finished" >&2
		break
	fi
	sleep "$nap"
done

labels="$(gh api "repos/$repo/issues/$pr" --jq '.labels[].name' 2>/dev/null)" || {
	echo "hold-rerun: could not read the labels of PR #$pr" >&2
	exit 2
}
has() { printf '%s\n' "$labels" | grep -qx "$1"; }
if has held-by-lane; then
	echo "hold-rerun: PR #$pr still carries held-by-lane; nothing rerun"
	exit 1
fi
if ! has architect-ruled && has needs-architect; then
	echo "hold-rerun: PR #$pr still carries needs-architect; nothing rerun"
	exit 1
fi

ids="$(printf '%s' "$json" | jq -r '.workflow_runs[]
  | select(.status == "completed" and (.conclusion == "failure" or .conclusion == "cancelled"))
  | .id')" || exit 2
if [ -z "$ids" ]; then
	echo "hold-rerun: no failed hold run on $sha"
	exit 0
fi
for id in $ids; do
	if gh run rerun "$id" --repo "$repo" 2>&1; then
		echo "RERAN #$pr run $id"
	else
		echo "hold-rerun: could not rerun run $id (another rerun may have started it); not fatal" >&2
	fi
done
exit 0
