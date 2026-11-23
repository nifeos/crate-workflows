#!/usr/bin/env python3
"""Drop the files a crate exempts from the naming checks, and print the rest.

    python3 naming_exempt_paths.py [--exempts .github/naming-exempt-paths] PATH...
    python3 naming_exempt_paths.py --selftest

The naming step of `check / standalone` hands every `.rs` file of the crate to the naming checks
(spelled_out, unit_symbols, register_names, british_spelling, service_model, contract_names and
question_shape), and every tracked file to service_model's prose pass. A repository that carries
another project's code, such as a fork that sends its fixes upstream, keeps that project's names:
renaming them here would make every fix unmergeable upstream. It lists those paths in
`.github/naming-exempt-paths`, one entry per line, `<path> <reason>`, where the path is a file or a
directory (ending `/`) relative to the repository root, and the reason says whose names the files
keep. Blank lines and lines starting `#` are ignored.

This prints each PATH argument that no entry covers, one per line, for the step to pass on. A
missing file exempts nothing. An entry without a reason, an absolute path or a path with `..` in it
exits 2 and names the line, since that is a broken configuration rather than a finding. An entry
that covers no PATH is reported on standard error and exits 1, so an exemption cannot outlive the
code it was written for.

Only the naming checks read this. Every other gate, the abbreviations report included, still reads
the exempt files.

Name: provisional, from the naming-exempt-paths lane.
"""

import argparse
import sys
from pathlib import PurePosixPath


def load(path):
    """`([(entry, reason)], [errors])` from the exemptions file; a missing file is empty."""
    entries, errors = [], []
    try:
        text = open(path, encoding='utf-8').read()
    except FileNotFoundError:
        return entries, errors
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        entry, _, reason = line.partition(' ')
        parts = PurePosixPath(entry.rstrip('/')).parts
        if not reason.strip() or entry.startswith('/') or '..' in parts or not parts:
            errors.append(f'{path}:{number}: write `<path> <reason>`, with a path relative to the '
                          f'repository root and a reason that says whose names the files keep')
            continue
        entries.append((entry, reason.strip()))
    return entries, errors


def covers(entry, path):
    if entry.endswith('/'):
        return path.startswith(entry)
    return path == entry


def split(entries, paths):
    """`(kept paths, entries that cover none of them)`."""
    used, kept = set(), []
    for path in paths:
        hit = [entry for entry, _ in entries if covers(entry, path)]
        used.update(hit)
        if not hit:
            kept.append(path)
    return kept, [entry for entry, _ in entries if entry not in used]


def main(argv):
    if '--selftest' in argv:
        return selftest()
    parser = argparse.ArgumentParser()
    parser.add_argument('--exempts', default='.github/naming-exempt-paths')
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args(argv)
    entries, errors = load(args.exempts)
    for error in errors:
        print('naming_exempt_paths: ' + error, file=sys.stderr)
    if errors:
        return 2
    kept, unused = split(entries, [p.removeprefix('./') for p in args.paths])
    for path in kept:
        print(path)
    for entry in unused:
        print(f'naming_exempt_paths: {args.exempts}: {entry} covers no file; remove the entry',
              file=sys.stderr)
    return 1 if unused else 0


def selftest():
    import os
    import tempfile
    failures = []

    def expect(label, got, want):
        if got != want:
            failures.append('%s: got %r, want %r' % (label, got, want))

    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, 'good')
        with open(good, 'w', encoding='utf-8') as f:
            f.write('# comment\n\nsrc/ upstream names\nfuzz/lib.rs upstream names\n')
        entries, errors = load(good)
        expect('a good file has no errors', errors, [])
        kept, unused = split(entries, ['src/a.rs', 'src/x/b.rs', 'fuzz/lib.rs', 'tests/t.rs',
                                       'srcx/c.rs'])
        expect('a directory entry covers what is under it, not a sibling prefix', kept,
               ['tests/t.rs', 'srcx/c.rs'])
        expect('every entry used', unused, [])
        kept, unused = split(entries, ['tests/t.rs'])
        expect('an entry that covers nothing is reported', unused, ['src/', 'fuzz/lib.rs'])
        expect('a missing file exempts nothing', load(os.path.join(tmp, 'none')), ([], []))
        bad = os.path.join(tmp, 'bad')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('src/\n/abs reason\n../up reason\n')
        expect('no reason, absolute and parent paths each refused', len(load(bad)[1]), 3)
    for line in failures:
        print('FAIL ' + line, file=sys.stderr)
    if failures:
        return 1
    print('naming_exempt_paths selftest ok')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
