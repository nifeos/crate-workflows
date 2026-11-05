#!/bin/sh
# shellcheck shell=sh
#
# helpers/publish-rehearsal.sh: everything the release's publish job does short of publishing.
#
#     helpers/publish-rehearsal.sh <manifest> [--token-present]
#
# It runs `cargo publish --dry-run` (the package builds and verifies) and then
# helpers/publish_mode.py, which says whether the real release would use trusted publishing or the
# first-publish token. It needs no credential and sends nothing to crates.io beyond the read-only
# lookup of the crate's name. `--token-present` stands in for the CRATES_IO_FIRST_PUBLISH_TOKEN
# secret, so a maintainer sees the first-publish door before creating the secret. The release
# workflow's publish step runs the same two commands, behind the `crates-io` environment.

set -eu

manifest="$1"
shift
here="$(dirname "$0")"

cargo publish --manifest-path "$manifest" --dry-run
python3 "$here/publish_mode.py" plan "$manifest" "$@"
