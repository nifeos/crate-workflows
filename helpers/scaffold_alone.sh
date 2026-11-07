#!/bin/sh
#
# helpers/scaffold_alone.sh DIR: refuse any file under DIR that names another tree's vocabulary.
#
# DIR is the scaffold, which every crate repository copies. A crate repository stands alone, so the
# copied files never carry the sibling project's name, the maintainer's name, a roadmap citation
# (`fork 3`, `milestone`, a section sign) or a path into the design tree. The match is on whole
# words, case-insensitive, so the release app's secret names, which join the word to others with an
# underscore, are not matched here; the typos gate reads them separately. Run by script/lint over
# scaffold/ and over a bad and a good fixture. Exit 0 clean, 1 on a hit (printed), 2 on bad usage.

set -eu

[ $# -eq 1 ] && [ -d "$1" ] || { echo "usage: scaffold_alone.sh DIR" >&2; exit 2; }

hits="$(grep -rnIiE '(^|[^[:alnum:]_])(nife|calef)([^[:alnum:]_]|$)|fork [0-9]|milestone|design/|§[0-9]' "$1" || true)"
[ -z "$hits" ] || {
	echo "scaffold_alone: the scaffold names another tree's vocabulary:" >&2
	echo "$hits" >&2
	exit 1
}
