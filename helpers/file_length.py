#!/usr/bin/env python3
"""A Rust source file stays under 2,000 lines (nife's §266 rule, no baseline file here).

    python3 file_length.py [--limit 2000] [--exemptions FILE] [PATH...]
    python3 file_length.py --selftest

Every path is judged, comments and blank lines counted, because a reader loads every line. A new
crate repository starts under the cap, so unlike nife there is no baseline of already-over files;
a file that needs 2,001 lines is a split.

The one exception is code another project owns, which a fork keeps as that project wrote it so its
fixes can go upstream. The caller's `.github/file-length-exemptions` lists such a file as
`<path> <lines> <reason>`, the path relative to the repository root and the lines as measured. The
file then passes while it is exactly that long; a different length, or an entry for a file that is
not over the cap, fails (`exemptions_file.py` reads the entries).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exemptions_file  # noqa: E402

DEFAULT_LIMIT = 2000


def over(path, limit):
    n = len(Path(path).read_text().splitlines())
    return (n, n > limit)


def findings(paths, limit, entries, name='file-length-exemptions'):
    """`([finding], [kept path])` for the paths, with the exemption entries applied."""
    lengths = {}
    for p in paths:
        n, bad_file = over(p, limit)
        if bad_file:
            lengths[(exemptions_file.normal_path(p),)] = n
    unexempted, found, kept = exemptions_file.length_verdicts(
        entries, lengths, name, 'lines', lambda key: key[0])
    found = [f'{key[0]} is {lengths[key]} lines, over the {limit}-line cap' for key in unexempted] + found
    return found, [key[0] for key in kept]


def selftest():
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        short, long_one = Path(tmp) / 'short.rs', Path(tmp) / 'long.rs'
        short.write_text('fn a() {}\n' * 5)
        long_one.write_text('fn a() {}\n' * 12)
        paths = [str(short), str(long_one)]
        key = (exemptions_file.normal_path(str(long_one)),)
        expect('a file over the cap fails', findings(paths, 10, {}),
               ([f'{key[0]} is 12 lines, over the 10-line cap'], []))
        expect('an exemption at the measured length passes',
               findings(paths, 10, {key: {'lines': 12, 'line': 1}}), ([], [key[0]]))
        expect('a file that grew past its exemption fails',
               findings(paths, 10, {key: {'lines': 11, 'line': 1}})[0],
               [f'{key[0]} is 12 lines, but its exemption (file-length-exemptions:1) records 11; '
                'an exemption holds the length it was written for'])
        stale = (exemptions_file.normal_path(str(short)),)
        expect('an exemption for a file under the cap fails',
               findings(paths, 10, {key: {'lines': 12, 'line': 1}, stale: {'lines': 5, 'line': 2}})[0],
               [f'file-length-exemptions:2: {stale[0]} is not over the limit in this run; '
                'remove the entry'])
    print('file_length selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    limit, exemptions = DEFAULT_LIMIT, None
    paths = []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--selftest':
            return selftest()
        if args[i] == '--limit':
            limit = int(args[i + 1]); i += 2
        elif args[i] == '--exemptions':
            exemptions = args[i + 1]; i += 2
        else:
            paths.append(args[i]); i += 1
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2
    entries, errors = exemptions_file.load(exemptions, ('path', 'lines'), ('lines',))
    for e in errors:
        print(f'file_length: {e}', file=sys.stderr)
    if errors:
        return 2
    found, kept = findings(paths, limit, entries,
                           Path(exemptions).name if exemptions else 'file-length-exemptions')
    for p in kept:
        print(f'==> file length: {p} is over the cap and exempt at its measured length')
    for f in found:
        print(f'file_length: {f}', file=sys.stderr)
    if not found:
        print(f'==> file length: every other file is under {limit} lines')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
