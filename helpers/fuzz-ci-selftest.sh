#!/bin/sh
#
# helpers/fuzz-ci-selftest.sh: the offline proof of the weekly fuzz job, run by script/lint.
#
# Two halves. The first reads the workflow and its scaffold caller and holds the rules that keep the
# job safe: no fork pull request, no self-hosted runner, no write permission, no step that files an
# issue or an advisory, and an upload of the crashing inputs. The second runs helpers/fuzz-weekly.sh
# against a stand-in cargo and holds its verdicts: red on a seeded crash, green on a clean target,
# green with a note on a crate with no fuzz targets, each target started from its committed seeds when it has them, and a time per target that never exceeds the
# total. The third part runs helpers/unsafe_scan.py on the fixtures in fixtures/unsafe-scan and holds
# that an opt-in is refused for shipped `unsafe` and passes otherwise. The live proof, with the real cargo-fuzz, is the selftest workflow's fuzz jobs.

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
grep -q 'public-crash-inputs:' "$workflow" || fail "$workflow has no public-crash-inputs opt-in"
grep -A8 'public-crash-inputs:' "$workflow" | grep -q 'default: false' || fail "the opt-in does not default to false"
grep -q 'if: ${{ inputs.public-crash-inputs }}' "$workflow" || fail "$workflow runs a step without the opt-in"
[ "$(grep -c 'fuzz every target' "$workflow")" -eq 1 ] || fail "$workflow does not have exactly one fuzz step"
grep -A2 'fuzz every target' "$workflow" | grep -q 'inputs.public-crash-inputs' || fail "the fuzz step runs without the opt-in"
grep -q 'public-crash-inputs: false' "$caller" || fail "the scaffold caller does not default to not opted in"
grep -q 'unsafe_scan' helpers/fuzz-weekly.sh || fail "the fuzz script does not refuse unsafe code"
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
# Stand-in for `cargo +nightly fuzz list` and
# `cargo +nightly fuzz run TARGET CORPUS... -- -max_total_time=N`. Logs the target, the time and
# the corpus directories, and refuses a corpus directory that does not exist, as libFuzzer does.
case "$3" in
list) printf '%s' "$SHIM_TARGETS" ;;
run)
	target="$4"
	shift 4
	corpora=""
	while [ "$1" != "--" ]; do
		[ -d "$1" ] || exit 2
		corpora="$corpora $1"
		shift
	done
	printf '%s %s%s\n' "$target" "$2" "$corpora" >>"$SHIM_LOG"
	case " $SHIM_CRASH " in
	*" $target "*)
		mkdir -p "fuzz/artifacts/$target"
		: >"fuzz/artifacts/$target/crash-seeded"
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
	mkdir -p "$work/crate/fuzz" "$work/crate/src"
	: >"$work/crate/src/lib.rs"
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

# A target with committed seeds starts from them, after the corpus it writes; one without starts
# from its corpus alone.
crate
mkdir -p "$work/crate/fuzz/seeds/alpha"
run 'alpha
beta
' '' 300 1200 || fail "the seeded run was red"
grep -qx 'alpha -max_total_time=300 fuzz/corpus/alpha fuzz/seeds/alpha' "$SHIM_LOG" ||
	fail "a target with fuzz/seeds/<target> did not start from it: $(cat "$SHIM_LOG")"
grep -qx 'beta -max_total_time=300 fuzz/corpus/beta' "$SHIM_LOG" ||
	fail "a target with no seeds was not run on its corpus alone: $(cat "$SHIM_LOG")"

# The opt-in is refused for a crate with shipped unsafe code, and the script fuzzes nothing then.
crate
printf 'pub fn f() {\n    unsafe {}\n}\n' >"$work/crate/src/lib.rs"
if run 'alpha
' '' 300 1200; then
	fail "a crate with unsafe code was fuzzed"
fi
[ ! -s "$SHIM_LOG" ] || fail "a refused crate ran a target"

if sh "$script" "$work/crate/Cargo.toml" ten 5 >/dev/null 2>&1; then
	fail "a non-numeric time was accepted"
fi

# The scan, against the fixtures. Each line is: fixture, expected exit code.
scan() {
	code=0
	python3 -I helpers/unsafe_scan.py "fixtures/unsafe-scan/$1" >"$work/scan.out" 2>&1 || code=$?
	[ "$code" -eq "$2" ] || fail "the unsafe scan on $1 exited $code, expected $2"
}
scan no-unsafe 0
scan unsafe-block 1
grep -q 'unsafe-block/src/lib.rs:5:' "$work/scan.out" || fail "the refusal does not name the file and line"
scan comment-and-string-only 0
scan forbid 0
scan unsafe-only-in-tests 0
scan unsafe-fn-after-test-module 1
scan forbid-only-in-lib 1
echo "fuzz-ci-selftest: ok"
