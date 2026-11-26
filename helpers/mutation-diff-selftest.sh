#!/bin/sh
# shellcheck shell=sh
#
# helpers/mutation-diff-selftest.sh: helpers/mutation-diff.sh against the fixture crate, with the
# real cargo-mutants, on three diffs from fixtures/mutation-diff/:
#
# - exempted.patch touches the clamp line, whose one survivor .github/mutants-exempts lists: pass;
# - untested.patch adds a function no test pins: its survivors fail the check;
# - a change to sample/README.md alone makes no mutants: pass, saying so;
# - untested-workspace-member.patch adds the same kind of function to a crate that is a member of
#   a workspace (sample-workspace/), whose mutants cargo-mutants names from the workspace root: the
#   diff must be taken from there too, or it matches nothing and the check passes having tested
#   nothing. The survivors must fail it.
#
# Then the cap, reached on purpose and not by runner speed: a stand-in `cargo` on PATH sleeps far
# past a cap of about a second, so `timeout` always ends the run, and a stand-in `gh` on PATH
# answers the Actions API reads `mutation_plan.py verify` makes. Its one green run of mutation.yml
# is at the commit in FAKE_GREEN_SHA, recorded as FAKE_RECORD:
#
# - no full run anywhere: fail;
# - a green full run at the head commit: pass;
# - a green full run at another commit: fail;
# - a green run at the head commit that tested nothing (`deferred`): fail.
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
	sh "$root/helpers/mutation-diff.sh" "${3:-sample/Cargo.toml}" HEAD^ .github/mutants-exempts 5 || rc=$?
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
git apply "$root/fixtures/mutation-diff/untested-workspace-member.patch"
case_of "an untested function in a workspace member" 1 sample-workspace/workspace_sample_contract/Cargo.toml
# The stand-in answers only the two reads verify makes; any other read is an error, so a change in
# what the helper asks is red here rather than silently unanswered.
mkdir -p "$work/bin"
cat >"$work/bin/gh" <<'GH'
#!/bin/sh
[ "$1" = api ] || { echo "stand-in gh: unexpected $*" >&2; exit 1; }
case "$2" in
repos/partsfoundry/example/actions/workflows/mutation.yml/runs\?head_sha=*)
	sha="${2#*head_sha=}"
	sha="${sha%%&*}"
	if [ -n "${FAKE_GREEN_SHA:-}" ] && [ "$sha" = "$FAKE_GREEN_SHA" ]; then
		echo '{"workflow_runs":[{"id":4242,"conclusion":"success"}]}'
	else
		echo '{"workflow_runs":[]}'
	fi
	;;
repos/partsfoundry/example/actions/runs/4242/jobs\?*)
	printf '{"jobs":[{"name":"mutation record [sample/Cargo.toml]: %s"}]}\n' "$FAKE_RECORD"
	;;
*)
	echo "stand-in gh: unexpected read $2" >&2
	exit 1
	;;
esac
GH
chmod +x "$work/bin/gh"
# helpers/cargo-mutants.sh execs `cargo mutants`, which this one turns into a sleep that outlasts
# every cap the cases pass. Any other cargo command (crate_info.py's `cargo metadata`) is the real one.
real_cargo="$(command -v cargo)"
cat >"$work/bin/cargo" <<CARGO
#!/bin/sh
[ "\$1" = mutants ] && exec sleep 300
exec "$real_cargo" "\$@"
CARGO
chmod +x "$work/bin/cargo"
full="full $(printf '%064d' 0 | tr 0 a)"

cap_case() {
	# $1 = label, $2 = expected exit, $3 = the green run's commit: none, head or other, $4 = its record.
	git apply "$root/fixtures/mutation-diff/untested.patch"
	git -c user.name=selftest -c user.email=selftest@invalid commit -q -am "$1"
	head="$(git rev-parse HEAD)"
	case "$3" in
	none) green="" ;;
	head) green="$head" ;;
	other) green="$(git rev-parse HEAD^)" ;;
	esac
	rc=0
	PATH="$work/bin:$PATH" FAKE_GREEN_SHA="$green" FAKE_RECORD="$4" \
		MUTATION_DIFF_REPOSITORY=partsfoundry/example MUTATION_DIFF_HEAD_SHA="$head" \
		MUTATION_DIFF_HEAD_REF=lane/example \
		sh "$root/helpers/mutation-diff.sh" sample/Cargo.toml HEAD^ .github/mutants-exempts 0.02 >"$work/out" 2>&1 || rc=$?
	git reset -q --hard HEAD^
	cat "$work/out"
	grep -q 'did not finish inside the 0.02-minute cap' "$work/out" || {
		echo "mutation-diff selftest: $1 did not reach the cap" >&2
		exit 1
	}
	if [ "$rc" -ne "$2" ]; then
		echo "mutation-diff selftest: $1 exited $rc, want $2" >&2
		exit 1
	fi
	if [ "$rc" -ne 0 ] && ! grep -qF 'gh workflow run mutation.yml -R partsfoundry/example --ref lane/example' "$work/out"; then
		echo "mutation-diff selftest: $1 failed without naming the dispatch command" >&2
		exit 1
	fi
	echo "==> mutation-diff selftest: $1 exited $rc, as it should"
}

cap_case "the cap reached, no full run" 1 none "$full"
cap_case "the cap reached, a green full run at the head" 0 head "$full"
cap_case "the cap reached, a green full run at another commit" 1 other "$full"
cap_case "the cap reached, a green run at the head that tested nothing" 1 head deferred
echo "mutation-diff selftest: ok"
