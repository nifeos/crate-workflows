#!/bin/sh
#
# helpers/loom-check.sh MANIFEST_PATH [MAX_PREEMPTIONS]
#
# The loom run for one crate: its tests build and run in release mode with `--cfg loom` and
# `-D warnings`, so every `loom::model` in a `#[cfg(loom)]` test explores the interleavings of its
# threads. A model that finds a bad interleaving panics, the test fails, and so does this script.
#
# MAX_PREEMPTIONS, when given, is exported as LOOM_MAX_PREEMPTIONS, which `loom::model` reads. Empty
# means no bound: loom explores every interleaving. A model that sets `preemption_bound` on its own
# `loom::model::Builder` keeps its own value.
#
# A run that checks nothing fails too. The crate's Rust files must name `loom::model` somewhere
# outside `target/` and hidden directories, and the run must pass at least one test. Whether each
# model reaches the code it means to check is the crate's own assertion to make; this script cannot
# see it.
#
# Exit codes: 0 when the models ran and held; 1 when a model failed or the run checked nothing; 2
# for a mistake in the arguments.

set -u

manifest="${1:-}"
bound="${2:-}"

if [ -z "$manifest" ] || [ "$#" -gt 2 ]; then
	echo "usage: loom-check.sh MANIFEST_PATH [MAX_PREEMPTIONS]" >&2
	exit 2
fi
if [ ! -f "$manifest" ]; then
	echo "loom-check: no manifest at $manifest" >&2
	exit 2
fi
case "$bound" in
*[!0-9]*)
	echo "loom-check: '$bound' is not a whole number of preemptions" >&2
	exit 2
	;;
esac

dir="$(dirname "$manifest")"
failed=0

# target/ holds build output, and a hidden directory holds tools: the template's own checkout sits at
# .crate-workflows/ beside a crate at the repository root, and its loom fixture names loom::model.
models="$(find "$dir" ! -path "$dir" \( -name target -o -name '.?*' \) -prune -o -name '*.rs' \
	-exec grep -lE '(^|[^A-Za-z0-9_])loom::model([^A-Za-z0-9_]|$)' {} + 2>/dev/null)"
if [ -z "$models" ]; then
	echo "loom-check: the crate depends on loom but no Rust file under $dir names loom::model" >&2
	failed=1
fi

if [ -n "$bound" ]; then
	LOOM_MAX_PREEMPTIONS="$bound"
	export LOOM_MAX_PREEMPTIONS
	echo "==> loom: at most $bound preemptions per execution"
else
	echo "==> loom: no preemption bound"
fi

log="$(mktemp)"
status="$(mktemp)"
trap 'rm -f "$log" "$status"' EXIT

{
	RUSTFLAGS="--cfg loom -D warnings" cargo test --release --manifest-path "$manifest" --tests 2>&1
	echo "$?" >"$status"
} | tee "$log"

if [ "$(cat "$status")" != 0 ]; then
	echo "loom-check: the loom run failed; a model found a bad interleaving, or the build failed" >&2
	exit 1
fi

passed="$(sed -n 's/^test result: ok\. \([0-9][0-9]*\) passed.*/\1/p' "$log" |
	awk '{ n += $1 } END { print n + 0 }')"
if [ "$passed" -eq 0 ]; then
	echo "loom-check: no test passed under --cfg loom, so no model ran" >&2
	failed=1
fi

if [ "$failed" -ne 0 ]; then
	exit 1
fi
echo "==> loom: $passed test(s) passed under --cfg loom"
