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

exec cargo mutants \
	--exclude-re 'verification::' \
	--exclude-re 'proofs::' \
	--exclude-re 'interleavings::' \
	--exclude '**/src/**/proofs.rs' \
	--exclude '**/src/**/verification.rs' \
	--exclude '**/src/**/interleavings.rs' \
	"$@"
