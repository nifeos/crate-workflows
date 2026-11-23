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
# cover. The optional exemptions file names paths one per line, relative to the repository root
# (the directory this runs in), for files that cannot reach the floor without a change the
# repository may not make: code that cannot run on the host a coverage run executes on, or code
# another project owns. An exemption is a marked exception, so name the measured figure and the
# reason beside the path with a `#`. An entry whose file is missing from the report, or is at the
# floor after all, fails, so the list can only shrink. lcov names files by absolute path; the
# repository root is stripped from it before the comparison.
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

awk -v floor="$floor" -v exempt="$exempt" -v root="$(pwd -P)/" -v logical="$(pwd)/" '
BEGIN { if (exempt != "") { while ((getline line < exempt) > 0) { sub(/ *#.*/, "", line); gsub(/^[ \t]+|[ \t]+$/, "", line); sub(/^\.\//, "", line); if (line != "") skip[line] = 1 } } }
/^SF:/ { f = substr($0, 4); if (index(f, root) == 1) f = substr(f, length(root) + 1); else if (index(f, logical) == 1) f = substr(f, length(logical) + 1) }
/^LF:/ { lf = substr($0, 4) + 0 }
/^LH:/ { lh = substr($0, 4) + 0 }
/^end_of_record/ {
	if (lf > 0) {
		pct = int(lh * 100 / lf)
		if (f in skip) {
			used[f] = 1
			printf "%s %d%%, exempt\n", f, pct
			if (pct >= floor) {
				printf "coverage-floor: %s is %d%%, at the floor of %d%%; remove its exemption\n", f, pct, floor
				bad = 1
			}
		} else {
			printf "%s %d%%\n", f, pct
			if (pct < floor) {
				printf "coverage-floor: %s is %d%%, under the floor of %d%%\n", f, pct, floor
				bad = 1
			}
		}
	}
	f = ""; lf = 0; lh = 0
}
END {
	for (f in skip) if (!(f in used)) { printf "coverage-floor: %s is exempt but not in the report; remove its exemption\n", f; bad = 1 }
	if (bad) { print "coverage-floor: a file is under the floor. Add tests, or lower the floor only with a reason the pull request records." > "/dev/stderr"; exit 1 }
	print "coverage-floor: every file meets the floor of " floor "%"
}' "$lcov"
