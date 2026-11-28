#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff-exempt-selftest.sh: proves helpers/mutation-diff-exempt.sh. Each case sets
# the two inputs and the pull request's fields, then names the verdict the helper must write. The
# first case is the exempt one; every other case changes one field of it and must not be exempt.
# Run it from the repository root: sh helpers/mutation-diff-exempt-selftest.sh

set -eu

cd "$(dirname "$0")/.."
helper="$PWD/helpers/mutation-diff-exempt.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

failures=0

# case <name> <want> <exempt author> <prefix> <author> <author type> <head repo> <base repo> <head ref>
case_() {
	name="$1"
	want="$2"
	: >"$work/out"
	if ! EXEMPT_AUTHOR="$3" EXEMPT_BRANCH_PREFIX="$4" AUTHOR="$5" AUTHOR_TYPE="$6" \
		HEAD_REPOSITORY="$7" BASE_REPOSITORY="$8" HEAD_REF="$9" GITHUB_OUTPUT="$work/out" \
		sh "$helper" >"$work/log" 2>&1; then
		echo "FAIL $name: the helper exited non-zero"
		cat "$work/log"
		failures=$((failures + 1))
		return
	fi
	got="$(sed -n 's/^exempt=//p' "$work/out")"
	if [ "$got" != "$want" ]; then
		echo "FAIL $name: exempt=$got, want $want"
		cat "$work/log"
		failures=$((failures + 1))
	fi
}

app='sync-app[bot]'
repo='owner/crate'
prefix='upstream-sync/'
ref='upstream-sync/0123456789ab'

case_ "the app's pull request from its own branch" true "$app" "$prefix" "$app" Bot "$repo" "$repo" "$ref"
case_ "no exemption configured" false '' '' "$app" Bot "$repo" "$repo" "$ref"
case_ "author input only" false "$app" '' "$app" Bot "$repo" "$repo" "$ref"
case_ "prefix input only" false '' "$prefix" "$app" Bot "$repo" "$repo" "$ref"
case_ "exempt author that is not an app" false 'someone' "$prefix" 'someone' Bot "$repo" "$repo" "$ref"
case_ "a person's pull request on the branch" false "$app" "$prefix" 'someone' User "$repo" "$repo" "$ref"
case_ "the app's login with a person's type" false "$app" "$prefix" "$app" User "$repo" "$repo" "$ref"
case_ "another app" false "$app" "$prefix" 'other-app[bot]' Bot "$repo" "$repo" "$ref"
case_ "a fork's branch" false "$app" "$prefix" "$app" Bot 'someone/crate' "$repo" "$ref"
case_ "a deleted fork" false "$app" "$prefix" "$app" Bot '' "$repo" "$ref"
case_ "another branch" false "$app" "$prefix" "$app" Bot "$repo" "$repo" 'fix-something'
case_ "the prefix inside the branch name" false "$app" "$prefix" "$app" Bot "$repo" "$repo" 'x/upstream-sync/0123'

if [ "$failures" -ne 0 ]; then
	echo "mutation-diff-exempt selftest: $failures case(s) failed"
	exit 1
fi
echo "mutation-diff-exempt selftest: all cases pass"
