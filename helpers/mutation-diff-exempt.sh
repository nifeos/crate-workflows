#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff-exempt.sh: says whether `check / mutation-diff` passes a pull request
# without mutating it, because the caller's own automation opened it to merge another project's
# history (an upstream merge). Such a pull request changes thousands of upstream lines, always
# reaches the 20-minute cap and would then wait on a full mutation run; the weekly full run still
# judges that code.
#
#     EXEMPT_AUTHOR=<app>[bot] EXEMPT_BRANCH_PREFIX=<prefix> AUTHOR=... AUTHOR_TYPE=... \
#     HEAD_REPOSITORY=... BASE_REPOSITORY=... HEAD_REF=... helpers/mutation-diff-exempt.sh
#
# The inputs are the caller's two check.yml inputs and five fields of the pull_request event. The
# pull request is exempt only when every one of these holds:
#
# - both inputs are set; either one empty exempts nothing;
# - EXEMPT_AUTHOR is an app's login, ending in `[bot]`;
# - the pull request's author is that login, and GitHub reports the author's type as `Bot`;
# - the head branch is in the base repository, not a fork;
# - the head branch name starts with EXEMPT_BRANCH_PREFIX.
#
# The author is what an ordinary contributor cannot supply. A pull request's author is the account
# that opened it, and it stays that account whatever is pushed later. A login ending in `[bot]` is an
# app's: an account's login cannot hold square brackets, and only a holder of the app's private key
# can open a pull request as the app. The branch and repository conditions narrow the exemption
# further; on their own they would not hold, since anyone with write access can name a branch.
#
# Prints the verdict and each refused condition, and writes `exempt=true` or `exempt=false` to
# GITHUB_OUTPUT when it is set. Exits 0 either way; an exit other than 0 is a bad invocation.

set -eu

exempt_author="${EXEMPT_AUTHOR:-}"
exempt_prefix="${EXEMPT_BRANCH_PREFIX:-}"
author="${AUTHOR:-}"
author_type="${AUTHOR_TYPE:-}"
head_repository="${HEAD_REPOSITORY:-}"
base_repository="${BASE_REPOSITORY:-}"
head_ref="${HEAD_REF:-}"

verdict() {
	echo "$2"
	if [ -n "${GITHUB_OUTPUT:-}" ]; then
		echo "exempt=$1" >>"$GITHUB_OUTPUT"
	fi
	exit 0
}

if [ -z "$exempt_author" ] && [ -z "$exempt_prefix" ]; then
	verdict false "mutation-diff: no exemption configured; mutating the changed lines"
fi
if [ -z "$exempt_author" ] || [ -z "$exempt_prefix" ]; then
	verdict false "mutation-diff: the exemption needs both mutation-diff-exempt-author and mutation-diff-exempt-branch-prefix; mutating the changed lines"
fi

refused=""
case "$exempt_author" in
*'[bot]') ;;
*) refused="$refused
- mutation-diff-exempt-author '$exempt_author' is not an app's login (<app>[bot])" ;;
esac
if [ "$author" != "$exempt_author" ]; then
	refused="$refused
- the pull request's author is '$author', not '$exempt_author'"
fi
if [ "$author_type" != "Bot" ]; then
	refused="$refused
- the pull request's author is of type '$author_type', not 'Bot'"
fi
if [ -z "$head_repository" ] || [ "$head_repository" != "$base_repository" ]; then
	refused="$refused
- the head branch is in '$head_repository', not '$base_repository'"
fi
case "$head_ref" in
"$exempt_prefix"*) ;;
*) refused="$refused
- the head branch '$head_ref' does not start with '$exempt_prefix'" ;;
esac

if [ -n "$refused" ]; then
	verdict false "mutation-diff: not an exempt upstream merge; mutating the changed lines. Refused:$refused"
fi
verdict true "mutation-diff: exempt. $author opened this pull request from $head_repository:$head_ref, which starts with $exempt_prefix; no mutant is run. The full mutation run judges this code."
