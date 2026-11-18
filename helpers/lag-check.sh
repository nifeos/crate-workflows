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
# pin (head): identical or ahead passes, anything else (diverged) fails, because a pin that is not
# on the release line is a fork of the template wearing its name.
#
# A pin behind the newest release gets a grace of one Dependabot cycle, so a release does not turn
# every crate red before its bump pull request can be merged. The pin passes, with a notice, when
# both hold: the newest release was published at most LAG_GRACE_DAYS (default 7) days ago, and the
# pin is at the release before the newest or later (behind by one release at most). Behind by more,
# or the newest release older than the grace, fails. The template tags weekly just before the
# crates' weekly Dependabot run, so the newest release is always inside the grace for a week and a
# pin that misses a whole cycle goes red. LAG_NOW (epoch seconds) replaces the clock for the selftest.

set -eu

repo="${TEMPLATE_REPO:-nifeos/crate-workflows}"
pin="${JOB_WORKFLOW_SHA:-}"
grace_days="${LAG_GRACE_DAYS:-7}"
now="${LAG_NOW:-$(date +%s)}"

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

# The two newest releases, newest first, as tag and publication time.
releases="$(gh api "repos/$repo/releases?per_page=2" --jq '.[] | [.tag_name, .published_at] | @tsv' 2>/dev/null)" || releases=""
if [ -z "$releases" ]; then
	echo "lag: $repo has no release yet; failing closed." >&2
	exit 1
fi
newest_tag="$(printf '%s\n' "$releases" | sed -n 1p | cut -f1)"
newest_at="$(printf '%s\n' "$releases" | sed -n 1p | cut -f2)"
previous_tag="$(printf '%s\n' "$releases" | sed -n 2p | cut -f1)"
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
	published="$(printf '%s' "$newest_at" | jq -Rr 'fromdateiso8601')"
	age_days=$(((now - published) / 86400))
	if [ "$age_days" -gt "$grace_days" ]; then
		echo "lag: this call is pinned at $pin, behind $newest_tag, which is $age_days days old (grace: $grace_days)." >&2
		echo "lag: bump the pin in the caller's workflow files to the commit of $newest_tag." >&2
		exit 1
	fi
	if [ -z "$previous_tag" ]; then
		echo "lag: pinned at $pin, behind the only release $newest_tag; inside the grace ($age_days of $grace_days days)."
		exit 0
	fi
	previous_sha="$(gh api "repos/$repo/commits/$previous_tag" --jq .sha)"
	previous_status="$(gh api "repos/$repo/compare/$previous_sha...$pin" --jq .status)" || previous_status="unknown"
	case "$previous_status" in
	identical | ahead)
		echo "lag: notice: pinned at $pin, one release behind $newest_tag ($previous_tag or later); inside the grace ($age_days of $grace_days days). Merge the bump."
		;;
	*)
		echo "lag: this call is pinned at $pin, more than one release behind $newest_tag (older than $previous_tag)." >&2
		echo "lag: bump the pin in the caller's workflow files to the commit of $newest_tag." >&2
		exit 1
		;;
	esac
	;;
*)
	echo "lag: the pinned commit $pin is not on the release line of $newest_tag ($status)." >&2
	echo "lag: pin a release's commit, not a branch or a fork." >&2
	exit 1
	;;
esac
