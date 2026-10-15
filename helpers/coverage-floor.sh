#!/bin/sh
# shellcheck shell=sh
#
# helpers/coverage-floor: fail when any file's line coverage is under the floor.
#
#     helpers/coverage-floor <floor> <lcov.info> [exemptions.txt]
#
# The floor is a per-file line, not a whole-crate average (nife's rule since its coverage lane): a
# clean average hides one untested file behind nine tested ones. The record is lcov's `SF:`/`LF:`/
# `LH:` lines; a file with zero executable lines is skipped, because there is nothing in it to
# cover. The optional exemptions file names paths one per line, for files that cannot run on the
# host a coverage run executes on; an exemption is a marked exception, so name the reason beside
# the path with a `#`.
#
# Where nife's checker lives inside script/coverage, this is a helper so the reusable workflow
# stays readable and a caller can run the same check locally.

set -eu

[ $# -ge 2 ] || {
	echo "usage: helpers/coverage-floor <floor> <lcov.info> [exemptions.txt]" >&2
	exit 2
}
floor="$1"
lcov="$2"
exempt="${3:-}"

[ -f "$lcov" ] || {
	echo "coverage-floor: no lcov report at $lcov" >&2
	exit 2
}

awk -v floor="$floor" -v exempt="$exempt" '
BEGIN { if (exempt != "") { while ((getline line < exempt) > 0) { sub(/ *#.*/, "", line); gsub(/^[ \t]+|[ \t]+$/, "", line); if (line != "") skip[line] = 1 } } }
/^SF:/ { f = substr($0, 4) }
/^LF:/ { lf = substr($0, 4) + 0 }
/^LH:/ { lh = substr($0, 4) + 0 }
/^end_of_record/ {
	if (lf > 0 && !(f in skip)) {
		pct = int(lh * 100 / lf)
		printf "%s %d%%\n", f, pct
		if (pct < floor) {
			printf "coverage-floor: %s is %d%%, under the floor of %d%%\n", f, pct, floor
			bad = 1
		}
	}
	f = ""; lf = 0; lh = 0
}
END {
	if (bad) { print "coverage-floor: a file is under the floor. Add tests, or lower the floor only with a reason the pull request records." > "/dev/stderr"; exit 1 }
	print "coverage-floor: every file meets the floor of " floor "%"
}' "$lcov"
