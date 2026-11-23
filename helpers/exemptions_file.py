#!/usr/bin/env python3
"""Read a caller's per-entry exemptions file for one gate of `check / standalone`.

    python3 exemptions_file.py --selftest

Three gates have no other way to accept a finding: the file length cap (`file_length.py`), the
function length limit (`function_length.py`) and the acronym rule (`prose_acronyms.py`). A
repository that carries code another project owns, such as a fork that sends its fixes upstream,
cannot split or reword that code without making every fix unmergeable there. It lists each such
finding in the gate's file under `.github/`, one entry per line: the fields the gate names, then the
reason. Blank lines and lines starting `#` are ignored.

Each gate holds its entries to the finding they were written for. An entry that matches no finding
fails, so the list can only shrink; a length entry records the measured length, and the file or
function must stay at exactly that length, so code added to it fails until the entry changes in a
reviewed diff. There is no switch that exempts a whole crate, directory or gate.

A missing file exempts nothing. An entry with too few fields, no reason, an absolute path, a path
with `..` in it, a length that is not a whole number, or a second entry for the same finding exits
2 and names the line, since that is a broken configuration rather than a finding.

Name: provisional, from the upstream-size-exemptions lane.
"""

import os
import sys
from pathlib import PurePosixPath


def normal_path(path):
    """A path as the gates compare it: relative, `./` and doubled slashes dropped."""
    return os.path.normpath(path).replace(os.sep, '/')


def load(path, fields, lengths=()):
    """`({key: entry}, [errors])` from an exemptions file; a missing or absent file is empty.

    `fields` names the fields before the reason; the first is a path. Fields named in `lengths` are
    whole numbers. The key is the tuple of the fields that are not lengths, and the entry is a dict
    of every field, the reason and the line number.
    """
    entries, errors = {}, []
    if not path:
        return entries, errors
    try:
        text = open(path, encoding='utf-8').read()
    except FileNotFoundError:
        return entries, errors
    name = os.path.basename(path)
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        parts = stripped.split(None, len(fields))
        if len(parts) <= len(fields):
            errors.append(f'{name}:{number}: wants {", ".join(fields)} and a reason')
            continue
        entry = dict(zip(fields, parts), reason=parts[-1], line=number)
        where = PurePosixPath(entry[fields[0]])
        if where.is_absolute() or '..' in where.parts:
            errors.append(f'{name}:{number}: {entry[fields[0]]} is not a relative path inside the '
                          'repository')
            continue
        entry[fields[0]] = normal_path(entry[fields[0]])
        bad = [f for f in lengths if not entry[f].isdigit()]
        if bad:
            errors.append(f'{name}:{number}: {bad[0]} {entry[bad[0]]!r} is not a whole number')
            continue
        for f in lengths:
            entry[f] = int(entry[f])
        key = tuple(entry[f] for f in fields if f not in lengths)
        if key in entries:
            errors.append(f'{name}:{number}: repeats the entry on line {entries[key]["line"]}')
            continue
        entries[key] = entry
    return entries, errors


def length_verdicts(entries, over, name, length_field, describe, unit=None):
    """`(unexempted, findings, kept)` for a length gate.

    `over` is `{key: measured length}` for every item over the limit. An item with no entry is
    `unexempted`, for the gate to report as it always has. An item whose entry records another
    length is a finding, and so is an entry whose item is not over the limit or was not read.
    `describe(key)` names an item in a message, and `unit` its length (the field name by default).
    """
    unit = unit or length_field
    unexempted, found, kept = [], [], []
    for key, measured in over.items():
        entry = entries.get(key)
        if entry is None:
            unexempted.append(key)
        elif entry[length_field] != measured:
            found.append(f'{describe(key)} is {measured} {unit}, but its exemption '
                         f'({name}:{entry["line"]}) records {entry[length_field]}; an exemption '
                         'holds the length it was written for')
        else:
            kept.append(key)
    for key, entry in entries.items():
        if key not in over:
            found.append(f'{name}:{entry["line"]}: {describe(key)} is not over the limit in this run; '
                         'remove the entry')
    return unexempted, found, kept


def selftest():
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'file-length-exemptions')
        expect('missing file', load(path, ('path', 'lines'), ('lines',)), ({}, []))
        expect('no file named', load(None, ('path', 'lines'), ('lines',)), ({}, []))
        with open(path, 'w', encoding='utf-8') as out:
            out.write('# a comment\n\n./src/a.rs 2400 upstream code, unchanged\n'
                      'src/b.rs 2100\n/src/c.rs 2100 why\nsrc/../d.rs 2100 why\n'
                      'src/e.rs many why\nsrc/a.rs 2500 again\n')
        entries, errors = load(path, ('path', 'lines'), ('lines',))
        expect('entries', entries, {('src/a.rs',): {'path': 'src/a.rs', 'lines': 2400,
                                                   'reason': 'upstream code, unchanged', 'line': 3}})
        expect('errors', errors, [
            'file-length-exemptions:4: wants path, lines and a reason',
            'file-length-exemptions:5: /src/c.rs is not a relative path inside the repository',
            'file-length-exemptions:6: src/../d.rs is not a relative path inside the repository',
            "file-length-exemptions:7: lines 'many' is not a whole number",
            'file-length-exemptions:8: repeats the entry on line 3'])
        held = {('a',): {'lines': 10, 'line': 1}, ('b',): {'lines': 10, 'line': 2},
                ('c',): {'lines': 10, 'line': 3}}
        got = length_verdicts(held, {('a',): 10, ('b',): 11, ('d',): 12}, 'x', 'lines',
                              lambda key: key[0])
        expect('length verdicts', got, ([('d',)], [
            'b is 11 lines, but its exemption (x:2) records 10; an exemption holds the length it '
            'was written for',
            'x:3: c is not over the limit in this run; remove the entry'], [('a',)]))
    print('exemptions_file selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        sys.exit(selftest())
    print(__doc__, file=sys.stderr)
    sys.exit(2)
