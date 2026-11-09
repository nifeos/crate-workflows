#!/bin/sh
#
# helpers/install_actionlint.sh DIR: download the pinned actionlint release into DIR, verify its
# SHA-256 and unpack the binary there. `--version` prints the pinned version and does nothing else.
#
# This is the one place the actionlint pin lives; the selftest workflow's lint job and anyone
# running script/lint locally install through it. taiki-e/install-action, which installs the other
# tools, does not carry actionlint. Only linux amd64 is supported: the checksum below is that
# archive's. A bump changes VERSION and SHA256 together, and the -ignore patterns in script/lint
# are re-checked against the new release (a newer actionlint that knows a property makes its
# ignore dead, and the ignore is then deleted).

set -eu

VERSION=1.7.12
SHA256=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8

if [ "${1:-}" = "--version" ]; then
	echo "$VERSION"
	exit 0
fi
[ $# -eq 1 ] || {
	echo "usage: helpers/install_actionlint.sh DIR | --version" >&2
	exit 2
}
dir="$1"

archive="actionlint_${VERSION}_linux_amd64.tar.gz"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl --fail --silent --show-error --location --retry 3 \
	--output "$tmp/$archive" \
	"https://github.com/rhysd/actionlint/releases/download/v${VERSION}/${archive}"
echo "${SHA256}  $tmp/$archive" | sha256sum -c - >/dev/null || {
	echo "install_actionlint: checksum mismatch for $archive" >&2
	exit 1
}
mkdir -p "$dir"
tar -xzf "$tmp/$archive" -C "$dir" actionlint
echo "installed actionlint $VERSION into $dir"
