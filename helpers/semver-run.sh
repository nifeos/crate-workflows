#!/bin/sh
# shellcheck shell=sh
#
# helpers/semver-run.sh: run cargo-semver-checks against the previous release tag.
#
#     helpers/semver-run.sh <manifest> <report.txt> [ref]
#
# The baseline is the newest `v<x>.<y>.<z>` tag before <ref> (default HEAD), named by
# helpers/semver_baseline.py and passed as --baseline-rev, so a crate that has never been
# published has a baseline too. With no such tag the tool is left to its default, the last version
# on crates.io; a crate with neither has no baseline and the report says so.
#
# The report is the text the tool prints, progress and findings together (it has no JSON output),
# also copied to semver.err for the callers' failure paths; the exit status of the tool is swallowed here on purpose,
# because a finding is the caller's to judge (helpers/semver_major.py), and this script says so on
# stderr. The baseline chosen goes to stdout as `baseline: <tag>`, or `baseline: last published`.
# Needs full history with tags (checkout fetch-depth 0).

set -u

manifest="$1"
report="$2"
ref="${3:-HEAD}"
here="$(dirname "$0")"

tag=""
if tag="$(python3 "$here/semver_baseline.py" --ref "$ref")"; then
	echo "baseline: $tag"
	cargo semver-checks --manifest-path "$manifest" --baseline-rev "$tag" --color never >"$report" 2>&1
else
	rc=$?
	if [ "$rc" -ne 1 ]; then
		echo "semver-run: could not choose a baseline tag (exit $rc)" >&2
		exit 1
	fi
	echo "baseline: last published"
	cargo semver-checks --manifest-path "$manifest" --color never >"$report" 2>&1
fi
rc=$?
cp "$report" semver.err
echo "semver-run: cargo semver-checks exited $rc; the report is judged by semver_major.py" >&2
exit 0
