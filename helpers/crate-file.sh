#!/bin/sh
# shellcheck shell=sh
#
# helpers/crate-file.sh: where a crate's own copy of a repository file is, or the repository's.
#
#     helpers/crate-file.sh <manifest-path> <path-under-the-repository>
#
# Prints an absolute path. A file under `.github/` that names source lines (`mutants-exempts`,
# `coverage-exemptions`) names them relative to one crate, so in a repository of several crates two
# crates' `src/lib.rs:16` are different lines, and one list would call the other's entries stale.
# The crate's own file, `<crate-dir>/<path>`, wins when it exists; otherwise the repository's
# `<path>` is the answer, which is the only file a repository of one crate has.

set -eu

[ $# -eq 2 ] || {
	echo "usage: crate-file.sh <manifest-path> <path>" >&2
	exit 2
}
root="${GITHUB_WORKSPACE:-$(pwd)}"
dir="$(dirname "$1")"
if [ -f "$dir/$2" ]; then
	echo "$(cd "$dir" && pwd)/$2"
else
	echo "$root/$2"
fi
