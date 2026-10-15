#!/usr/bin/env python3
"""A Rust source file stays under 2,000 lines (nife's §266 rule, no baseline file here).

    python3 file_length.py [--limit 2000] [PATH...]

Every path is judged, comments and blank lines counted, because a reader loads every line. A new
crate repository starts under the cap, so unlike nife there is no baseline of already-over files;
a file that needs 2,001 lines is a split, and the diff that says otherwise owes its reason to a
budget file nobody has invented here yet.
"""

import sys
from pathlib import Path

DEFAULT_LIMIT = 2000


def over(path, limit):
    n = len(Path(path).read_text().splitlines())
    return (n, n > limit)


def main(argv):
    limit = DEFAULT_LIMIT
    paths = []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--limit':
            limit = int(args[i + 1]); i += 2
        else:
            paths.append(args[i]); i += 1
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2
    bad = False
    for p in paths:
        n, bad_file = over(p, limit)
        if bad_file:
            print(f'file_length: {p} is {n} lines, over the {limit}-line cap', file=sys.stderr)
            bad = True
    if not bad:
        print(f'==> file length: every file is under {limit} lines')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
