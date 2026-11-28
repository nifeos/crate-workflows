#!/bin/sh
# shellcheck shell=sh
#
# helpers/cargo-mutants.sh: `cargo mutants` with the template's standing exclusions, then the
# caller's own arguments.
#
#     helpers/cargo-mutants.sh [<cargo-mutants argument>...]
#
# Code behind `cfg(kani)` and `cfg(loom)` is never compiled by `cargo test`, so a mutant in a proof
# harness or a loom model always survives: it measures the harness, which has its own checker
# (the proofs and loom workflows), and not the crate. Every run here excludes them, so no crate
# has to exempt them line by line.
#
# cargo-mutants names a mutant by the path of its function within the file it parsed. A module
# written inline (`mod proofs { .. }`, `mod verification { .. }`, `mod interleavings { .. }`)
# therefore appears as `proofs::name`, which the name patterns catch. A module that is its own
# file appears with no prefix at all, so the file globs catch those. A crate's own
# `.cargo/mutants.toml` still applies beside these, since the tool merges the two.
#
# Every `cargo mutants` call in the template goes through this script, so the full run, the
# changed-lines run and the shard count all see the same set of mutants.

set -eu

# Each test process is held to an equal share of the machine's memory: the memory the machine has,
# divided by the mutants tested at once (`--jobs`, one when it is not given) and by its processors,
# one test process to a processor, and never under 1 GiB. A mutant can turn a loop's step into
# `*= 1` or a length into a product, and the test it reaches then allocates without end. A hosted
# runner has no memory limit of its own for the job, so that allocation takes the whole machine:
# the runner receives a shutdown signal and the shard ends with no outcomes, or loses contact and
# is cancelled when the job's timeout passes. Under the share the allocation fails, the test
# aborts, and the mutant is caught.
#
# The division by processors is exact under nextest, which runs each test in a process of its own.
# Under cargo test it is deliberately conservative: all of a test binary's tests share one process,
# so the share binds a whole binary. Dividing by `--jobs` alone would let each job's runaway take
# half the machine, and two of them take all of it, which is the fault this limit exists to stop.
#
# The share is an address-space limit (`prlimit --as`), set as cargo's runner for the host target,
# so it binds each test binary that cargo test or nextest starts, and not rustc or a build script.
# A crate whose tests need more than the share fails its unmutated baseline, which cargo-mutants
# runs under the same limit first, so a share too small turns the run red and never reads as a
# catch. MUTANTS_TEST_MEMORY_BYTES replaces the share; 0 turns the limit off. A runner the caller
# already set for the host target in the environment is kept, without a limit.
jobs=1
previous=
for argument in "$@"; do
	case "$previous" in --jobs | -j) jobs=$argument ;; esac
	case "$argument" in --jobs=*) jobs=${argument#--jobs=} ;; esac
	previous=$argument
done
share=${MUTANTS_TEST_MEMORY_BYTES:-}
if [ -z "$share" ] && [ -r /proc/meminfo ]; then
	memory_kibibytes=$(awk '$1 == "MemTotal:" { print $2 }' /proc/meminfo)
	[ -n "$memory_kibibytes" ] || {
		echo "cargo-mutants.sh: no MemTotal in /proc/meminfo; set MUTANTS_TEST_MEMORY_BYTES" >&2
		exit 1
	}
	share=$((memory_kibibytes * 1024 / (jobs * $(nproc))))
	[ "$share" -ge 1073741824 ] || share=1073741824
fi
host=$(rustc -vV | sed -n 's/^host: //p' | tr 'a-z-' 'A-Z_')
runner_variable="CARGO_TARGET_${host}_RUNNER"
if [ -n "$share" ] && [ "$share" != 0 ] && command -v prlimit >/dev/null &&
	[ -z "$(printenv "$runner_variable" || true)" ]; then
	echo "==> each test process is limited to $((share / 1048576)) MiB of address space ($runner_variable)" >&2
	export "$runner_variable=prlimit --as=$share --"
fi

exec cargo mutants \
	--exclude-re 'verification::' \
	--exclude-re 'proofs::' \
	--exclude-re 'interleavings::' \
	--exclude '**/src/**/proofs.rs' \
	--exclude '**/src/**/verification.rs' \
	--exclude '**/src/**/interleavings.rs' \
	"$@"
