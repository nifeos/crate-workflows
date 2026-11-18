#!/usr/bin/env python3
"""Fold the released entries of a CHANGELOG's `## Unreleased` section under a release heading.

    python3 helpers/changelog_fold.py notes  <released-changelog>
    python3 helpers/changelog_fold.py fold   <current-changelog> <released-changelog> <tag> <date>
    python3 helpers/changelog_fold.py --selftest

`notes` prints the Unreleased entries of the changelog as it stood at the released commit: the
release's notes. `fold` rewrites the changelog as it stands now: each entry (a `- ` bullet and its
indented continuation lines) that was already in the released commit's Unreleased section moves
under a new `## <tag> (<date>)` heading; an entry added after that commit stays under Unreleased,
which reads `Nothing yet.` when nothing is left. Nothing in the released entries changes.
"""

import sys

UNRELEASED = '## Unreleased'
EMPTY = 'Nothing yet.'


def split(text):
    """(before, entries, after): the lines above Unreleased, its bullets, the lines from the next heading."""
    lines = text.split('\n')
    start = lines.index(UNRELEASED)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    entries, cur = [], None
    for line in lines[start + 1:end]:
        if line.startswith('- '):
            cur = [line]
            entries.append(cur)
        elif cur is not None and line.strip():
            cur.append(line)
    return lines[:start], ['\n'.join(e) for e in entries], lines[end:]


def notes(released):
    entries = split(released)[1]
    return '\n'.join(entries) + '\n' if entries else EMPTY + '\n'


def fold(current, released, tag, date):
    before, entries, after = split(current)
    shipped = set(split(released)[1])
    out_shipped = [e for e in entries if e in shipped]
    kept = [e for e in entries if e not in shipped]
    if not out_shipped:
        return current
    unreleased = '\n'.join(kept) if kept else EMPTY
    block = [UNRELEASED, '', unreleased, '', f'## {tag} ({date})', '', '\n'.join(out_shipped), '']
    return '\n'.join(before + block + after)


def selftest():
    released = '# C\n\nintro\n\n## Unreleased\n\n- one\n  more of one\n- two\n\n## v1 (2026-01-01)\n\n- old\n'
    assert notes(released) == '- one\n  more of one\n- two\n'
    assert notes('## Unreleased\n\nNothing yet.\n\n## v1\n') == EMPTY + '\n'
    got = fold(released, released, 'v2', '2026-02-02')
    assert got == ('# C\n\nintro\n\n## Unreleased\n\nNothing yet.\n\n## v2 (2026-02-02)\n\n'
                   '- one\n  more of one\n- two\n\n## v1 (2026-01-01)\n\n- old\n'), got
    later = released.replace('## Unreleased\n\n', '## Unreleased\n\n- three\n')
    got = fold(later, released, 'v2', '2026-02-02')
    assert '## Unreleased\n\n- three\n\n## v2 (2026-02-02)\n\n- one\n  more of one\n- two\n\n## v1' in got, got
    assert fold('## Unreleased\n\nNothing yet.\n\n## v1\n', '## Unreleased\n\nNothing yet.\n\n## v1\n', 'v2', 'd') \
        == '## Unreleased\n\nNothing yet.\n\n## v1\n'
    print('changelog_fold: selftest ok')


def main(argv):
    if argv == ['--selftest']:
        selftest()
    elif len(argv) == 2 and argv[0] == 'notes':
        sys.stdout.write(notes(open(argv[1]).read()))
    elif len(argv) == 5 and argv[0] == 'fold':
        sys.stdout.write(fold(open(argv[1]).read(), open(argv[2]).read(), argv[3], argv[4]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
