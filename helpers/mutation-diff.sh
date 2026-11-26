#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff.sh: mutate the lines a pull request changed, and fail on a survivor or a
# timeout that .github/mutants-exempts does not list.
#
#     helpers/mutation-diff.sh <manifest-path> <base-rev> <exempts-file> [<cap-minutes>]
#
# The diff is `git diff <base-rev> HEAD`, taken relative to the crate's workspace root (which is the
# crate's directory unless the repository holds several crates) so its paths are the ones
# cargo-mutants reads. A diff relative to a member's own directory matches no mutant there, and
# cargo-mutants then says nothing is to be tested, so the root is what the paths must start from. `cargo mutants --in-diff` makes mutants on the changed lines
# only, so the run scales with the pull request rather than the crate. The verdict is
# `mutants_gate.py --diff`, against the same exemptions as the full run, without the stale check
# (a changed-lines run reaches only some survivors; the full run calls an exemption stale).
#
# The cap (default 20 minutes) is on the cargo-mutants run. Reaching it fails, unless the
# repository's full mutation workflow (`mutation.yml`) has a completed, green run at the pull
# request's exact head commit, as `mutation_plan.py verify` judges it for the release gate: a run
# that recorded `full`, or `unchanged` since a green `full` run of the same fingerprint. That run's
# own gate judged every survivor against the exemptions with the stale check, so it is strictly
# stronger than this one. A run at another commit, a cancelled or red run, and a run that tested
# nothing (`deferred`, `repeat`) do not count, and there is no label or bypass. The head comes from
# the environment: MUTATION_DIFF_REPOSITORY (owner/name), MUTATION_DIFF_HEAD_SHA and
# MUTATION_DIFF_HEAD_REF, read with GH_TOKEN; without the first two a reached cap fails. A diff with
# no Rust on its changed lines generates no mutants and passes, saying so.
#
# Exit 0: no survivor, or every survivor exempted with a reason, or a reached cap with a green full
# run at the head. Exit 1: anything else, including a broken run, since a required check that fails
# open examined nothing.

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
root="$(python3 "$(dirname "$gate")/crate_info.py" workspace-root "$manifest")"
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
git -C "$root" diff --relative "$base" HEAD >"$work/pr.diff"
rm -rf mutants.out mutants.out.old

rc=0
timeout --kill-after=30s "${cap}m" "$(dirname "$gate")/cargo-mutants.sh" --output "$(pwd)" --in-diff "$work/pr.diff" --jobs 2 --timeout 300 || rc=$?
case "$rc" in
0 | 2 | 3) ;;
124 | 137)
	repository="${MUTATION_DIFF_REPOSITORY:-}"
	head="${MUTATION_DIFF_HEAD_SHA:-}"
	if [ -n "$repository" ] && [ -n "$head" ] &&
		python3 "$(dirname "$gate")/mutation_plan.py" verify "$repository" "$head" --workflow mutation.yml --manifest-path "$manifest"; then
		summary "The changed lines' mutants did not finish inside the $cap-minute cap, and the full mutation workflow has a green run at the head commit $head, which judged every mutant. This pass is that run's."
		exit 0
	fi
	summary "The changed lines' mutants did not finish inside the $cap-minute cap, and no green full mutation run exists at the head commit ${head:-(not given)}. Split the pull request, or dispatch the full run on its head with \`gh workflow run mutation.yml -R ${repository:-<owner>/<name>} --ref ${MUTATION_DIFF_HEAD_REF:-<branch>}\` and, once it is green at that same commit, re-run this check. A run at any other commit does not count. A cap reached without one is a failure, never a pass."
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
