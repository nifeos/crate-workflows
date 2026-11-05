#!/bin/sh
#
# helpers/fuzz-ci-selftest.sh: the offline proof of the weekly fuzz job, run by script/lint.
#
# Two halves. The first reads the workflow and its scaffold caller and holds the rules that keep the
# job safe: no fork pull request, no self-hosted runner, no write permission, no step that files an
# issue or an advisory, and an upload of the crashing inputs. The second runs helpers/fuzz-weekly.sh
# against a stand-in cargo and holds its verdicts: red on a seeded crash, green on a clean target,
# green with a note on a crate with no fuzz targets, and a time per target that never exceeds the
# total. The live proof, with the real cargo-fuzz, is the selftest workflow's fuzz jobs.

set -eu

cd "$(dirname "$0")/.."

fail() {
	echo "fuzz-ci-selftest: $1" >&2
	exit 1
}

workflow=.github/workflows/fuzz.yml
caller=scaffold/caller-workflows/fuzz.yml
script=helpers/fuzz-weekly.sh

# The workflow.
grep -q 'head.repo.fork' "$workflow" || fail "$workflow does not refuse a pull request from a fork"
grep -q 'upload-artifact' "$workflow" || fail "$workflow does not upload the crashing inputs"
grep -q 'fuzz/artifacts' "$workflow" || fail "$workflow does not upload fuzz/artifacts"
if grep -nE 'self-hosted|pull_request_target|(issues|security-events|pull-requests|contents|actions|checks):[[:space:]]*write|gh (issue|api|pr|secret)|advisor|--auto-file|curl ' \
	"$workflow" "$script" "$caller" | grep -v '^[^:]*:[0-9]*:[[:space:]]*#'; then
	fail "the fuzz job names a runner, trigger, permission or command that could file something or run fork code"
fi
if grep -q 'pull_request' "$caller"; then
	fail "the scaffold caller runs on pull_request; fuzzing belongs on the schedule"
fi
grep -q 'schedule:' "$caller" || fail "the scaffold caller has no schedule"
grep -q 'workflow_dispatch:' "$caller" || fail "the scaffold caller has no workflow_dispatch"

# The script, against a stand-in cargo.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"
cat >"$work/bin/cargo" <<'SHIM'
#!/bin/sh
# Stand-in for `cargo +nightly fuzz list` and `cargo +nightly fuzz run TARGET -- -max_total_time=N`.
case "$3" in
list) printf '%s' "$SHIM_TARGETS" ;;
run)
	printf '%s %s\n' "$4" "$6" >>"$SHIM_LOG"
	case " $SHIM_CRASH " in
	*" $4 "*)
		mkdir -p "fuzz/artifacts/$4"
		: >"fuzz/artifacts/$4/crash-seeded"
		exit 77
		;;
	esac
	;;
esac
SHIM
chmod +x "$work/bin/cargo"
export PATH="$work/bin:$PATH"
export SHIM_LOG="$work/log"

crate() {
	rm -rf "$work/crate"
	mkdir -p "$work/crate/fuzz"
	: >"$work/crate/Cargo.toml"
	: >"$work/crate/fuzz/Cargo.toml"
	: >"$SHIM_LOG"
}

run() {
	SHIM_TARGETS="$1" SHIM_CRASH="$2" sh "$script" "$work/crate/Cargo.toml" "$3" "$4" >/dev/null 2>&1
}

crate
run 'alpha
beta
' '' 300 1200 || fail "a clean crate was red"
[ ! -e "$work/crate/fuzz/artifacts" ] || fail "a clean run left crashing inputs"
[ "$(wc -l <"$SHIM_LOG")" -eq 2 ] || fail "the clean run did not run both targets"

crate
if run 'alpha
beta
' 'beta' 300 1200; then
	fail "a seeded crash was green"
fi
[ -f "$work/crate/fuzz/artifacts/beta/crash-seeded" ] || fail "the seeded crash left no input to upload"
[ "$(wc -l <"$SHIM_LOG")" -eq 2 ] || fail "a crash in one target stopped the others"

crate
rm "$work/crate/fuzz/Cargo.toml"
run '' '' 300 1200 || fail "a crate with no fuzz directory was red"
[ ! -s "$SHIM_LOG" ] || fail "a crate with no fuzz directory ran a target"

crate
run '' '' 300 1200 || fail "a crate with an empty target list was red"

# The time per target: the per-target cap, the even split of the total, and the 10-second floor.
crate
run 'a
b
c
d
' '' 300 600 || fail "the split run was red"
[ "$(cut -d' ' -f2 "$SHIM_LOG" | sort -u)" = "-max_total_time=150" ] || fail "600 seconds over 4 targets was not 150 each"
crate
run 'a
' '' 120 1200 || fail "the capped run was red"
[ "$(cut -d' ' -f2 "$SHIM_LOG")" = "-max_total_time=120" ] || fail "the per-target cap did not hold"
crate
run 'a
b
' '' 300 5 || fail "the floor run was red"
[ "$(cut -d' ' -f2 "$SHIM_LOG" | sort -u)" = "-max_total_time=10" ] || fail "the 10-second floor did not hold"

if sh "$script" "$work/crate/Cargo.toml" ten 5 >/dev/null 2>&1; then
	fail "a non-numeric time was accepted"
fi
echo "fuzz-ci-selftest: ok"
