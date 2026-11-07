#!/bin/sh
# shellcheck shell=sh
#
# helpers/semver-rule.sh: the labeler's semver rule. Holds a pull request only for a major break it
# introduces, not for one its base branch already carries.
#
#     helpers/semver-rule.sh <manifest> <merge-base> <findings.txt>
#     helpers/semver-rule.sh --selftest
#
# Run from the root of the checked-out pull request (HEAD), with full history and tags. Exit 0 with
# the findings written to <findings.txt> (empty when nothing new is major); exit 2 when a report
# could not be judged, which the caller routes to a person.
#
# The steps, cheapest first:
# 1. The diff from <merge-base> to HEAD must touch a `.rs` file (build scripts included) or a
#    `Cargo.toml`. Nothing else can change the public interface cargo-semver-checks reads, so a
#    `_typos.toml`, a document or a workflow edit does not run the tool. `Cargo.lock` is left out on
#    purpose: a library's dependents resolve their own lockfile, and the tool reads the crate's own
#    items, so a lockfile bump moves no item the check can see.
# 2. HEAD is checked against the baseline (helpers/semver-run.sh: the newest release tag, else the
#    last published version). No major finding ends the rule there.
# 3. Otherwise the merge base is checked against the same baseline, in its own worktree outside the
#    checkout (two copies of one package under one root make cargo-semver-checks refuse both), and
#    helpers/semver_major.py keeps only the major findings the merge base did not have. A break
#    that reached the base branch in an earlier pull request was ruled there, and waits for its
#    release.

set -u

here="$(cd "$(dirname "$0")" && pwd)"

rule() {
	manifest="$1"
	base="$2"
	out="$3"
	: >"$out"
	if ! git diff --name-only "$base" HEAD | grep -qE '(\.rs|(^|/)Cargo\.toml)$'; then
		echo "semver-rule: no Rust source or manifest change; the tool does not run"
		return 0
	fi
	"$here/semver-run.sh" "$manifest" semver-report.txt HEAD || return 2
	python3 "$here/semver_major.py" semver-report.txt >"$out"
	rc=$?
	case "$rc" in
	1)
		: >"$out"
		echo "semver-rule: no major break against the baseline"
		return 0
		;;
	0) ;;
	*) return 2 ;;
	esac
	echo "semver-rule: a major break against the baseline; checking whether the merge base carries it"
	head="$(git rev-parse HEAD)"
	scratch="$(mktemp -d)"
	tree="$scratch/base"
	git worktree add --quiet --detach "$tree" "$base" || return 2
	# The baseline is named from HEAD, so both reports use the same one.
	"$here/semver-run.sh" "$tree/$manifest" semver-base-report.txt "$head"
	cargo semver-checks --list >semver-lints.txt 2>/dev/null
	git worktree remove --force "$tree"
	rm -rf "$scratch"
	python3 "$here/semver_major.py" semver-report.txt --carried semver-base-report.txt --lints semver-lints.txt >"$out"
	rc=$?
	case "$rc" in
	0) echo "semver-rule: a major break new in this pull request" ;;
	1)
		cat "$out"
		: >"$out"
		;;
	*) return 2 ;;
	esac
	return 0
}

# --selftest: build a throwaway crate repository, run the rule over five pull requests, and check
# what it decides. Needs cargo and cargo-semver-checks on PATH.
selftest() {
	work="$(mktemp -d)"
	repo="$work/repo"
	mkdir -p "$repo/src"
	cd "$repo" || return 1
	git init -q
	git config user.name selftest
	git config user.email selftest@example.invalid
	git config commit.gpgsign false
	git config tag.gpgsign false
	cat >Cargo.toml <<-'EOF'
		[package]
		name = "fixture"
		version = "0.1.0"
		edition = "2021"
		publish = false
	EOF
	printf '/target\n/Cargo.lock\n' >.gitignore
	printf '[default]\nlocale = "en-us"\n' >_typos.toml
	printf 'pub fn kept() {}\npub fn doomed() {}\npub fn other() {}\n' >src/lib.rs
	git add -A
	git commit -qm release
	git tag v0.1.0
	released="$(git rev-parse HEAD)"
	failed=0

	# expect <name> <base> <ran|skipped> <fires|quiet> [<text the findings name>] [<text they omit>]
	expect() {
		rm -f semver-report.txt
		if ! rule Cargo.toml "$2" findings.txt >"$work/log" 2>&1; then
			echo "FAIL $1: the rule could not judge it"
			cat "$work/log"
			failed=1
			return
		fi
		ran=skipped
		[ -f semver-report.txt ] && ran=ran
		fired=quiet
		[ -s findings.txt ] && fired=fires
		if [ "$ran" != "$3" ] || [ "$fired" != "$4" ]; then
			echo "FAIL $1: expected the tool $3 and the rule $4, got $ran and $fired"
			cat "$work/log" findings.txt
			failed=1
			return
		fi
		if [ -n "${5:-}" ] && ! grep -qF "$5" findings.txt; then
			echo "FAIL $1: the findings do not name $5"
			failed=1
			return
		fi
		if [ -n "${6:-}" ] && grep -qF "$6" findings.txt; then
			echo "FAIL $1: the findings name $6, which the base already carried"
			failed=1
			return
		fi
		echo "ok $1"
	}

	# A pull request that changes Rust and breaks nothing passes.
	git checkout -q -b trivial "$released"
	printf '/// Kept.\npub fn kept() {}\npub fn doomed() {}\npub fn other() {}\n' >src/lib.rs
	git commit -qam 'document kept'
	expect 'a pull request adding no break passes' "$released" ran quiet

	# A pull request that removes a released function fires.
	git checkout -q -b breaking "$released"
	printf 'pub fn kept() {}\npub fn other() {}\n' >src/lib.rs
	git commit -qam 'remove doomed'
	expect 'a pull request adding a break fires' "$released" ran fires 'fixture::doomed'

	# That break merges to main after its ruling. A later pull request that only documents a
	# function inherits the break and does not fire.
	main="$(git rev-parse breaking)"
	git checkout -q -b later "$main"
	printf '/// Kept.\npub fn kept() {}\npub fn other() {}\n' >src/lib.rs
	git commit -qam 'document kept'
	expect 'a break already on the base does not fire on a later trivial pull request' "$main" ran quiet

	# A later pull request that adds a second break of the same lint fires for that one only.
	git checkout -q -b second "$main"
	printf 'pub fn kept() {}\n' >src/lib.rs
	git commit -qam 'remove other'
	expect 'a second break beside a carried one fires for the second only' "$main" ran fires 'fixture::other' 'fixture::doomed'

	# A pull request that only edits the spelling configuration never runs the tool.
	git checkout -q -b spelling "$released"
	printf '[default]\nlocale = "en-us"\n\n[default.extend-words]\nfixture = "fixture"\n' >_typos.toml
	git commit -qam 'extend the spelling words'
	expect 'a _typos.toml-only diff does not run the tool' "$released" skipped quiet

	# The labeler checks out with `filter: blob:none`, so the release's files are not on disk and
	# cargo-semver-checks, which clones the checkout locally, cannot read them unless they are
	# fetched first. A partial clone of the fixture stands for that checkout.
	git config uploadpack.allowFilter true
	git config uploadpack.allowAnySHA1InWant true
	git clone -q --no-local --filter=blob:none --no-checkout "file://$repo" "$work/partial"
	cd "$work/partial" || return 1
	git config user.name selftest
	git config user.email selftest@example.invalid
	git config commit.gpgsign false
	git checkout -q -b breaking_partial origin/breaking
	expect 'a blobless clone still has the baseline files' "$released" ran fires 'fixture::doomed'

	cd / && rm -rf "$work"
	if [ "$failed" -ne 0 ]; then
		echo "semver-rule selftest: FAILED"
		return 1
	fi
	echo "semver-rule selftest: ok"
}

if [ "${1:-}" = "--selftest" ]; then
	selftest
	exit $?
fi
if [ "$#" -ne 3 ]; then
	sed -n '7,8p' "$0" >&2
	exit 2
fi
rule "$1" "$2" "$3"
