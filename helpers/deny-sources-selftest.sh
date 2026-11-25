#!/bin/sh
#
# helpers/deny-sources-selftest.sh: proves the `[sources.allow-org]` table in deny.toml (and its copy
# in scaffold/) does what the supply-chain job needs. It writes three throwaway crates and runs
# `cargo deny check sources` on each with the template's policy:
# - a git dependency on the allowed organization, pinned by `rev`: passes;
# - a git dependency on another organization: fails;
# - no git dependency: passes, with the warning that no source fell under the organization.
# It fetches the one allowed git repository, so it needs the network. Run it from the repository
# root: helpers/deny-sources-selftest.sh

set -eu

cd "$(dirname "$0")/.."

fail() {
	echo "deny-sources-selftest: $1" >&2
	exit 1
}

# A landed commit of an allowed repository, and one of a repository outside the organization.
allowed_url="https://github.com/partsfoundry/block_roster_contract"
allowed_rev="8454327d86017e741090dcfe333669d7725cb78c"
other_url="https://github.com/rust-lang/cfg-if"
other_rev="14432a28e180ec717933714aed7828fc7ed2fd29"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

crate() {
	mkdir -p "$work/$1/src"
	: >"$work/$1/src/lib.rs"
	printf '[package]\nname = "%s"\nversion = "0.0.0"\nedition = "2021"\npublish = false\n\n[dependencies]\n%s\n' \
		"$1" "$2" >"$work/$1/Cargo.toml"
}

crate allowed "sibling = { package = \"block_roster_contract\", git = \"$allowed_url\", rev = \"$allowed_rev\" }"
crate foreign "cfg-if = { git = \"$other_url\", rev = \"$other_rev\" }"
crate plain ""

for policy in deny.toml scaffold/deny.toml; do
	check() {
		cargo deny --manifest-path "$work/$1/Cargo.toml" --config "$policy" check sources 2>"$work/$1.log"
	}
	echo "==> $policy"
	check allowed || { cat "$work/allowed.log" >&2; fail "$policy refused a git dependency on the organization"; }
	check plain || { cat "$work/plain.log" >&2; fail "$policy refused a crate with no git dependency"; }
	grep -q 'no crate source fell under' "$work/plain.log" || fail "$policy gave no organization warning for a crate with no git dependency"
	if check foreign; then
		fail "$policy allowed a git dependency outside the organization"
	fi
	grep -q 'source-not-allowed' "$work/foreign.log" || {
		cat "$work/foreign.log" >&2
		fail "$policy refused a foreign git dependency for some reason other than its source"
	}
done
echo "ok"
