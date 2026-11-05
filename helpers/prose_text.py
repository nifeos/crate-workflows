#!/usr/bin/env python3
"""The prose of a Markdown or Rust file, shared by the acronym and banned-figure gates.

    python3 prose_text.py --selftest
"""
import sys


def prose_lines(path, text):
    """[(line number, text, is_heading)] for the sentences of one file. Not yet written."""
    raise NotImplementedError


def selftest():
    cases = [
        # (path, source, wanted [(line, text, is_heading)])
        ('a.md', 'Plain `code` words.\n', [(1, 'Plain `` words.', False)]),
        ('a.md', '# Title EFI\nBody\n', [(1, '# Title EFI', True), (2, 'Body', False)]),
        ('a.md', '```\nEFI\n```\nafter\n', [(4, 'after', False)]),
        ('a.md', '<!-- EFI -->\nafter\n', [(2, 'after', False)]),
        ('a.md', '---\nk: EFI\n---\nafter\n', [(4, 'after', False)]),
        ('a.md', 'See <https://x.example/EFI> and [text](https://x.example/EFI).\n',
         [(1, 'See  and [text]().', False)]),
        ('a.rs', 'let EFI = 1; // EFI\n/// Doc line.\n//! Inner doc.\n', [(2, 'Doc line.', False), (3, 'Inner doc.', False)]),
        ('a.rs', '/// ```\n/// EFI\n/// ```\n/// after\n', [(4, 'after', False)]),
        ('a.txt', 'EFI\n', []),
    ]
    failed = 0
    for path, src, want in cases:
        got = prose_lines(path, src)
        if got != want:
            failed += 1
            print(f'FAIL {path} {src!r} gave {got}, wanted {want}', file=sys.stderr)
    print('prose_text selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else 2)
