#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff-selftest.sh: helpers/mutation-diff.sh against the fixture crate, with the
# real cargo-mutants, on three diffs from fixtures/mutation-diff/:
#
# - exempted.patch touches the clamp line, whose one survivor .github/mutants-exempts lists: pass,
#   although the exemptions also name proof-file lines this run cannot reach;
# - untested.patch adds a function no test pins: its survivors fail the check;
# - a change to sample/README.md alone makes no mutants: pass, saying so.
#
# Each case is committed on a throwaway detached worktree of this checkout (a shallow checkout
# holds one, where a clone may not) and judged against its parent.

set -eu

cd "$(dirname "$0")/.."
root="$(pwd)"
work="$(mktemp -d)"
trap 'git -C "$root" worktree remove --force "$work/repo" 2>/dev/null; rm -rf "$work"' EXIT
git worktree add -q --detach "$work/repo" HEAD
cd "$work/repo"

case_of() {
	# $1 = label, $2 = expected exit (0 or 1); the change is already in the working tree.
	git -c user.name=selftest -c user.email=selftest@invalid commit -q -am "$1"
	rc=0
	sh "$root/helpers/mutation-diff.sh" sample/Cargo.toml HEAD^ .github/mutants-exempts 5 || rc=$?
	git reset -q --hard HEAD^
	if [ "$rc" -ne "$2" ]; then
		echo "mutation-diff selftest: $1 exited $rc, want $2" >&2
		exit 1
	fi
	echo "==> mutation-diff selftest: $1 exited $rc, as it should"
}

git apply "$root/fixtures/mutation-diff/exempted.patch"
case_of "an exempted survivor on a changed line" 0
git apply "$root/fixtures/mutation-diff/untested.patch"
case_of "an untested function" 1
printf '\nOne more line.\n' >>sample/README.md
case_of "a diff with no Rust" 0
echo "mutation-diff selftest: ok"
