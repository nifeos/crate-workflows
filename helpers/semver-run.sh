#!/bin/sh
# shellcheck shell=sh
#
# helpers/semver-run.sh: run cargo-semver-checks against the previous release tag.
#
#     helpers/semver-run.sh <manifest> <report.txt> [ref]
#
# The baseline is the newest release tag of this crate before <ref> (default HEAD): `v<x>.<y>.<z>`
# in a repository of one crate, `<crate>-v<x>.<y>.<z>` in a repository of several
# (helpers/crate_info.py tag-prefix), named by helpers/semver_baseline.py and passed as --baseline-rev, so a crate that has never been
# published has a baseline too. With no such tag the tool is left to its default, the last version
# on crates.io; a crate with neither has no baseline and the report says so.
#
# The report is the text the tool prints, progress and findings together (it has no JSON output),
# also copied to semver.err for the callers' failure paths; the exit status of the tool is swallowed here on purpose,
# because a finding is the caller's to judge (helpers/semver_major.py), and this script says so on
# stderr. The baseline chosen goes to stdout as `baseline: <tag>`, or `baseline: last published`.
# Needs full history with tags (checkout fetch-depth 0). A blobless checkout (`filter: blob:none`)
# is fine: the baseline's files are fetched here first, because cargo-semver-checks clones the
# checkout locally and a local clone cannot fetch a file the checkout lacks.

set -u

manifest="$1"
report="$2"
ref="${3:-HEAD}"
here="$(dirname "$0")"

prefix="$(python3 "$here/crate_info.py" tag-prefix "$manifest")" || {
	echo "semver-run: could not read the tag prefix of $manifest" >&2
	exit 1
}
tag=""
if tag="$(python3 "$here/semver_baseline.py" --ref "$ref" --tag-prefix "$prefix")"; then
	echo "baseline: $tag"
	# Reading every file of the tag fetches the missing ones in one batch; a full clone has them.
	top="$(git -C "$(dirname "$manifest")" rev-parse --show-toplevel)" || exit 1
	git -C "$top" archive "$tag" >/dev/null || {
		echo "semver-run: could not read the files of $tag" >&2
		exit 1
	}
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
