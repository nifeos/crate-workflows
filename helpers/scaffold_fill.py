#!/usr/bin/env python3
"""Fill the placeholders of a copied scaffold, and refuse to leave one behind.

    python3 scaffold_fill.py --name <repository name> --pins <40-hex commit SHA> DIR
    python3 scaffold_fill.py --selftest

DIR is a tree copied from `scaffold/` or `scaffold-workspace/` into a crate repository. Every workflow
file (`*.yml`, `*.yaml`) under it (`.git` excluded; prose that names a placeholder is left alone) has `@PINS@` replaced by the template commit and `@MUTATION_CRON@`
by the line `mutation_plan.py schedule <name>` prints: the repository's own weekday (chosen by its name, so
repositories do not all start together), tried at 08, 10 and 12 UTC, so repositories do not all start at once. Then the
whole tree is read again, and a file that still holds a token of the form `@NAME@` fails the run,
naming each file and line. A placeholder this script does not know is therefore loud, never a
workflow file GitHub rejects after the push. Exit 0 filled, 1 a placeholder left, 2 bad usage.
"""

import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mutation_plan  # noqa: E402

TOKEN = re.compile(r'@[A-Z][A-Z0-9_]*@')
SHA = re.compile(r'[0-9a-f]{40}')


def text_files(root):
    for path in sorted(Path(root).rglob('*')):
        if ('.git' in path.relative_to(root).parts or not path.is_file()
                or path.suffix not in ('.yml', '.yaml')):
            continue
        try:
            yield path, path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue


def fill(root, name, pins):
    """Replace the known placeholders under root; return the lines still holding one."""
    values = {'@PINS@': pins, '@MUTATION_CRON@': mutation_plan.cron_line(name)}
    for path, text in text_files(root):
        new = text
        for token, value in values.items():
            new = new.replace(token, value)
        if new != text:
            path.write_text(new, encoding='utf-8')
    left = []
    for path, text in text_files(root):
        for number, line in enumerate(text.splitlines(), 1):
            if TOKEN.search(line):
                left.append('%s:%d: %s' % (path, number, line.strip()))
    return left


def main(argv):
    if '--selftest' in argv:
        return selftest()
    args = list(argv)
    opts = {}
    while args and args[0] in ('--name', '--pins') and len(args) > 1:
        opts[args[0]] = args[1]
        args = args[2:]
    if len(args) != 1 or set(opts) != {'--name', '--pins'} or not Path(args[0]).is_dir():
        print('usage: scaffold_fill.py --name NAME --pins SHA DIR', file=sys.stderr)
        return 2
    if not SHA.fullmatch(opts['--pins']):
        print('scaffold_fill: --pins is not a full 40-hex commit SHA', file=sys.stderr)
        return 2
    left = fill(args[0], opts['--name'], opts['--pins'])
    if left:
        print('scaffold_fill: a placeholder is still unfilled:', file=sys.stderr)
        print('\n'.join(left), file=sys.stderr)
        return 1
    print('scaffold_fill: filled; schedule %s' % mutation_plan.cron_line(opts['--name']))
    return 0


def selftest():
    import tempfile
    pins = 'a' * 40
    failures = []

    def expect(label, got, want):
        if got != want:
            failures.append('%s: got %r, want %r' % (label, got, want))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'mutation.yml').write_text("- cron: '@MUTATION_CRON@'\nuses: x@PINS@\n")
        (root / 'sub').mkdir()
        (root / 'sub' / 'ci.yml').write_text('uses: y@PINS@\n')
        expect('known placeholders leave nothing', fill(root, 'entropy_contract', pins), [])
        body = (root / 'mutation.yml').read_text()
        expect('cron line is the planner line',
               body, "- cron: '%s'\nuses: x%s\n" % (mutation_plan.cron_line('entropy_contract'), pins))
        expect('line is the weekday form at 08, 10 and 12',
               bool(re.fullmatch(r"\d+ 8,10,12 \* \* \d", mutation_plan.cron_line('entropy_contract'))), True)
        (root / 'x.yml').write_text('a: @NEW_THING@\n')
        left = fill(root, 'entropy_contract', pins)
        expect('an unknown placeholder is reported', len(left), 1)
        expect('and it names the file', 'x.yml:1' in left[0], True)
    for line in failures:
        print('FAIL ' + line, file=sys.stderr)
    if failures:
        return 1
    print('scaffold_fill selftest ok')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
