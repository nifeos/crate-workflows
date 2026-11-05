#!/usr/bin/env python3
"""A figurative or vague phrase is replaced by a plain one.

    python3 prose_figures.py FILE...
    python3 prose_figures.py --selftest

STUB: the implementation follows the selftest.
"""
import sys


def violations(path, text, figures):
    """[(line, phrase, instead)] for each banned phrase in the file's prose."""
    raise NotImplementedError


FIGURES = [(r'oracle', 'an independent implementation that the tests compare against'),
           (r'battle[- ]tested', 'say which tests or uses back the claim')]


def selftest():
    cases = [
        ('The reference is an oracle for the tests.\n', ['oracle']),
        ('A battle-tested parser, and a Battle tested one.\n', ['battle-tested', 'Battle tested']),
        ('An independent implementation that the tests compare against.\n', []),
        ('The `oracle` code span is exempt.\n', []),
        ('```\noracle\n```\n', []),
        ('# The oracle heading\n', ['oracle']),
        ('Oracles are plural, and miracle is another word.\n', []),
    ]
    failed = 0
    for src, want in cases:
        got = [p for _, p, _ in violations('a.md', src, FIGURES)]
        if got != want:
            failed += 1
            print(f'FAIL {src!r} gave {got}, wanted {want}', file=sys.stderr)
    got = [p for _, p, _ in violations('a.rs', '/// An oracle.\nlet oracle = 1; // oracle\n', FIGURES)]
    if got != ['oracle']:
        failed += 1
        print(f'FAIL rust gave {got}', file=sys.stderr)
    print('prose_figures selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else 2)
