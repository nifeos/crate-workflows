#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff.sh: mutate the lines a pull request changed, and fail on a survivor or a
# timeout that .github/mutants-exempts does not list.
#
#     helpers/mutation-diff.sh <manifest-path> <base-rev> <exempts-file> [<cap-minutes>]
#
# The diff is `git diff <base-rev> HEAD`, taken relative to the crate's directory so its paths are
# the ones cargo-mutants reads there. `cargo mutants --in-diff` makes mutants on the changed lines
# only, so the run scales with the pull request rather than the crate. The verdict is
# `mutants_gate.py --diff`, against the same exemptions as the full run, without the stale check
# (a changed-lines run reaches only some survivors; the full run calls an exemption stale).
#
# The cap (default 20 minutes) is on the cargo-mutants run, and reaching it fails: a pull request
# whose changed lines take longer is split, or its survivors are judged by a full run. A diff with
# no Rust on its changed lines generates no mutants and passes, saying so.
#
# Exit 0: no survivor, or every survivor exempted with a reason. Exit 1: anything else, including
# a broken run, since a required check that fails open examined nothing.

set -eu

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
	echo "usage: mutation-diff.sh <manifest-path> <base-rev> <exempts-file> [<cap-minutes>]" >&2
	exit 1
fi
manifest="$1"
base="$2"
exempts="$3"
cap="${4:-20}"
gate="$(cd "$(dirname "$0")" && pwd)/mutants_gate.py"
case "$exempts" in
/*) ;;
*) exempts="$(pwd)/$exempts" ;;
esac
crate_dir="$(dirname "$manifest")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

summary() {
	if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
		printf '### Mutation of the changed lines\n\n%s\n' "$1" >>"$GITHUB_STEP_SUMMARY"
	fi
	echo "==> mutation-diff: $1"
}

cd "$crate_dir"
git rev-parse --verify --quiet "$base^{commit}" >/dev/null || {
	echo "mutation-diff: the base $base does not resolve; the check cannot guess the diff" >&2
	exit 1
}
git diff --relative "$base" HEAD >"$work/pr.diff"
rm -rf mutants.out mutants.out.old

rc=0
timeout --kill-after=30s "${cap}m" cargo mutants --in-diff "$work/pr.diff" --jobs 2 --timeout 300 || rc=$?
case "$rc" in
0 | 2 | 3) ;;
124 | 137)
	summary "The changed lines' mutants did not finish inside the $cap-minute cap. Split the pull request, or run the full mutation workflow on its branch. A cap reached is a failure, never a pass."
	exit 1
	;;
*)
	summary "cargo mutants exited $rc: a broken run, not a survivor count, and never a pass."
	exit 1
	;;
esac

# cargo-mutants writes outcomes.json whenever it had a mutant to test, so a clean exit without one
# means the diff made none: no Rust on the changed lines.
if [ ! -f mutants.out/outcomes.json ]; then
	summary "The diff made no mutants: no Rust on its changed lines. This pass is not a mutation result."
	exit 0
fi
python3 "$gate" --diff mutants.out "$exempts"
