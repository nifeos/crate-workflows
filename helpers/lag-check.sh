#!/bin/sh
# shellcheck shell=sh
#
# helpers/lag-check.sh: the first job of every reusable workflow in this repository.
#
#     JOB_WORKFLOW_SHA='${{ job.workflow_sha }}' helpers/lag-check.sh
#
# A crate repository calls these workflows pinned at one commit. The lag check fails when that
# commit is behind this repository's newest release, or on a diverged line, so a stale pin is a red
# run rather than a slow drift. Dependabot's github-actions ecosystem opens the bump; the weekly
# schedule in the caller runs the same check with no pull request open, so a repository nobody
# touches still finds out.
#
# `job.workflow_sha` is GitHub's own name for "the commit of the workflow file that defines the
# current job", which for a cross-repository call is the pinned commit in this repository. When no
# release exists yet the check fails closed: an unreleased template has nothing a caller may pin,
# and "the newest release" is not "whatever main looks like today".
#
# The comparison is the compare API's status between the newest release's commit (base) and the
# pin (head): identical or ahead passes, behind fails, anything else (diverged) fails, because a
# pin that is not on the release line is a fork of the template wearing its name.

set -eu

repo="${TEMPLATE_REPO:-nifeos/crate-workflows}"
pin="${JOB_WORKFLOW_SHA:-}"

# The template's own selftest calls these workflows in their own repository; such a call is the
# current source by construction, and there is no release for the check to compare against until
# the first one is cut. The check exists for cross-repository pins, so it stands down here.
if [ "${GITHUB_REPOSITORY:-}" = "$repo" ]; then
	echo "lag: same-repository call; the pin is this commit by construction."
	exit 0
fi

if [ -z "$pin" ]; then
	echo "lag: job.workflow_sha is empty, so this call's template version is unknown." >&2
	echo "lag: failing closed: a call whose version cannot be read may be any age." >&2
	exit 1
fi

newest_tag="$(gh api "repos/$repo/releases/latest" --jq .tag_name 2>/dev/null)" || {
	echo "lag: $repo has no release yet; failing closed." >&2
	exit 1
}
newest_sha="$(gh api "repos/$repo/commits/$newest_tag" --jq .sha)"
status="$(gh api "repos/$repo/compare/$newest_sha...$pin" --jq .status)" || {
	echo "lag: could not compare the pinned commit $pin with release $newest_tag ($newest_sha)." >&2
	exit 1
}

case "$status" in
identical | ahead)
	echo "lag: pinned at $pin; newest release $newest_tag ($status)."
	;;
behind)
	echo "lag: this call is pinned at $pin, behind the newest release $newest_tag." >&2
	echo "lag: bump the pin in the caller's workflow files to the commit of $newest_tag." >&2
	exit 1
	;;
*)
	echo "lag: the pinned commit $pin is not on the release line of $newest_tag ($status)." >&2
	echo "lag: pin a release's commit, not a branch or a fork." >&2
	exit 1
	;;
esac
