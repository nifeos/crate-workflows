#!/bin/sh
#
# helpers/fuzz-weekly.sh MANIFEST_PATH [SECONDS_PER_TARGET [TOTAL_SECONDS]]
#
# The weekly fuzz run for one crate: every cargo-fuzz target gets a bounded time, and the run is red
# when any target ends in a crash, a timeout, an out-of-memory or a leak. It files nothing. A
# crashing input stays in fuzz/artifacts/<target>/ beside the manifest, where the workflow uploads
# it, and a person reads the run and decides what to do with it.
#
# Crash inputs are published where any signed-in GitHub user can read them, so the run first
# refuses a crate whose shipped source contains `unsafe` (helpers/unsafe_scan.py), and fuzzes nothing.
#
# Exit codes: 0 for a clean run, or for a crate with no fuzz targets; 1 when a target failed or the
# crate holds `unsafe`; 2 for a mistake in the arguments or a failure of cargo-fuzz itself that
# names no target.
#
# Each target starts from its committed seeds in fuzz/seeds/<target>/ when that directory exists,
# beside fuzz/corpus/<target>/, which libFuzzer creates and writes. New inputs go only to the corpus,
# so a run never changes the committed seeds.
#
# The time per target is the smaller of SECONDS_PER_TARGET and TOTAL_SECONDS divided by the number
# of targets, and never under 10 seconds, so a crate with many targets still ends inside the budget
# (the build time of each target is outside this bound).

set -u

manifest="${1:-}"
per_target="${2:-300}"
total="${3:-1200}"

if [ -z "$manifest" ]; then
	echo "usage: fuzz-weekly.sh MANIFEST_PATH [SECONDS_PER_TARGET [TOTAL_SECONDS]]" >&2
	exit 2
fi
for n in "$per_target" "$total"; do
	case "$n" in
	'' | *[!0-9]*)
		echo "fuzz-weekly: '$n' is not a whole number of seconds" >&2
		exit 2
		;;
	esac
done

summary() {
	[ -z "${GITHUB_STEP_SUMMARY:-}" ] || printf '%s\n' "$1" >>"$GITHUB_STEP_SUMMARY"
}

here="$(dirname "$0")"
if ! python3 -I "$here/unsafe_scan.py" "$(dirname "$manifest")"; then
	summary "### fuzz"
	summary "Refused: the crate's shipped source contains \`unsafe\` (or could not be read), and crash inputs are public. See the log for the file and line."
	exit 1
fi

cd "$(dirname "$manifest")" || exit 2

if [ ! -f fuzz/Cargo.toml ]; then
	echo "no fuzz targets: $(pwd)/fuzz/Cargo.toml does not exist, so there is nothing to run"
	summary "### fuzz"
	summary "No fuzz targets in this crate; nothing ran."
	exit 0
fi

if ! targets="$(cargo +nightly fuzz list)"; then
	echo "fuzz-weekly: cargo fuzz list failed" >&2
	exit 2
fi
count="$(printf '%s\n' "$targets" | grep -c .)"
if [ "$count" -eq 0 ]; then
	echo "no fuzz targets: cargo fuzz list printed none"
	summary "### fuzz"
	summary "No fuzz targets in this crate; nothing ran."
	exit 0
fi

seconds=$((total / count))
[ "$seconds" -le "$per_target" ] || seconds="$per_target"
[ "$seconds" -ge 10 ] || seconds=10

failed=""
for target in $targets; do
	mkdir -p "fuzz/corpus/$target"
	if [ -d "fuzz/seeds/$target" ]; then
		set -- "fuzz/corpus/$target" "fuzz/seeds/$target"
		echo "==> cargo fuzz run $target for $seconds seconds, from fuzz/seeds/$target"
	else
		set -- "fuzz/corpus/$target"
		echo "==> cargo fuzz run $target for $seconds seconds, with no committed seeds"
	fi
	if ! cargo +nightly fuzz run "$target" "$@" -- -max_total_time="$seconds"; then
		echo "==> $target failed"
		failed="$failed $target"
	fi
done

summary "### fuzz"
summary "$count target(s), $seconds seconds each."
if [ -n "$failed" ]; then
	summary "Failed:$failed. The inputs are in the \`fuzz-artifacts\` artifact of this run. Nothing was filed."
	echo "fuzz-weekly: failed targets:$failed" >&2
	exit 1
fi
summary "No target failed."
