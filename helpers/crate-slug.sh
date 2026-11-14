#!/bin/sh
# shellcheck shell=sh
#
# helpers/crate-slug.sh: the suffix that keeps one crate's artifacts and analyses apart from
# another's in the same workflow run.
#
#     helpers/crate-slug.sh <manifest-path>
#
# A repository of several crates calls each reusable workflow once for each crate, and every call
# lands in the same run, where two uploads under one artifact name collide and two code scans in one
# category overwrite each other. The suffix is empty for a manifest at the repository root, so a
# repository of one crate keeps the names it always had, and `-<directory>` for any other, with every
# character an artifact name refuses turned into a hyphen: `crates/a/Cargo.toml` is `-crates-a`.

set -eu

[ $# -eq 1 ] || {
	echo "usage: crate-slug.sh <manifest-path>" >&2
	exit 2
}
dir="$(dirname "$1")"
case "$dir" in
. | '') ;;
*) printf -- '-%s' "$(printf '%s' "${dir#./}" | tr -c 'A-Za-z0-9._\n-' '-')" ;;
esac
