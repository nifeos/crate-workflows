#!/usr/bin/env python3
"""A comment block stays under 40 lines (nife's §267 rule).

    python3 comment_blocks.py [--limit 40] [PATH...]

A block is a run of adjacent comment lines of one kind (`//`, `///`, `//!`, or `#` in a non-Rust
file). A block of 40 lines is allowed; 41 is over. Blank lines and code lines end a block. A new
crate repository starts under the cap, so there is no baseline: a block that needs 41 lines is a
document, and documents get their own files.
"""

import sys
from pathlib import Path

DEFAULT_LIMIT = 40
MARKERS = ('///', '//!', '//')


def blocks(text):
    """[(start line, length)] for every comment block, one marker kind per block."""
    out = []
    start, kind = None, None
    for n, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        marker = next((m for m in MARKERS if stripped.startswith(m)), None)
        if marker is not None and (kind == marker or start is None):
            if start is None:
                start, kind = n, marker
        elif marker is not None and kind != marker:
            out.append((start, n - start))
            start, kind = n, marker
        else:
            if start is not None:
                out.append((start, n - start))
            start, kind = None, None
    if start is not None:
        out.append((start, len(text.splitlines()) + 1 - start))
    return out


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
        try:
            text = Path(p).read_text()
        except UnicodeDecodeError:
            continue
        if not p.endswith('.rs'):
            continue
        for start, length in blocks(text):
            if length > limit:
                print(f'comment_blocks: {p}:{start} a comment block of {length} lines, over the '
                      f'{limit}-line cap', file=sys.stderr)
                bad = True
    if not bad:
        print(f'==> comment blocks: every block is within {limit} lines')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
