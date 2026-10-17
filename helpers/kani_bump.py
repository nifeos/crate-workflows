#!/usr/bin/env python3
"""Decide whether `.kani-version` is behind the newest kani-verifier on crates.io.

    python3 helpers/kani_bump.py plan [--pin .kani-version] [--index-file FILE]
    python3 helpers/kani_bump.py --selftest

`plan` prints `current=`, `newest=` and `bump=true|false` as `key=value` lines, for appending to
$GITHUB_OUTPUT. It reads the crates.io API (stdlib only, no third-party action); `--index-file`
reads the same JSON from a file, which is how the selftest and a person without network run it.

The rule: the newest version that is neither yanked nor a prerelease. A bump is proposed only when
that version is strictly greater than the pin; a pin that is ahead of crates.io (a yank, a stale
mirror) is left alone, because "propose a bump, never apply one" must not become a downgrade.
"""

import json
import re
import sys
import urllib.request

API = 'https://crates.io/api/v1/crates/kani-verifier'
# crates.io asks for a contact in the User-Agent.
AGENT = 'nifeos-crate-workflows kani-bump (https://github.com/nifeos/crate-workflows)'
STABLE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')


def parse(version):
    m = STABLE.match(version.strip())
    if not m:
        raise ValueError(f'not an exact X.Y.Z version: {version!r}')
    return tuple(int(p) for p in m.groups())


def newest(index):
    """The highest unyanked, non-prerelease version in a crates.io crate document, or None."""
    found = [parse(v['num']) for v in index.get('versions', [])
             if not v.get('yanked') and STABLE.match(v['num'])]
    return '.'.join(map(str, max(found))) if found else None


def decide(current, index):
    """(newest, bump): bump is true only when newest is strictly above current."""
    top = newest(index)
    if top is None:
        raise ValueError('no stable unyanked kani-verifier version in the index')
    return top, parse(top) > parse(current)


def fetch():
    req = urllib.request.Request(API, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def selftest():
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    # A trailing "!" marks a yanked version in these fixtures; strip it for the num itself.
    def mk(*nums):
        return {'versions': [{'num': n.rstrip('!'), 'yanked': n.endswith('!')} for n in nums]}

    expect('newer available', decide('0.68.0', mk('0.69.0', '0.68.0')), ('0.69.0', True))
    expect('already current', decide('0.68.0', mk('0.68.0', '0.67.0')), ('0.68.0', False))
    expect('numeric not lexical', decide('0.9.0', mk('0.10.0', '0.9.0')), ('0.10.0', True))
    expect('pin ahead of the index is not a downgrade', decide('0.69.0', mk('0.68.0')), ('0.68.0', False))
    expect('yanked newest is skipped', decide('0.68.0', mk('0.69.0!', '0.68.0')), ('0.68.0', False))
    expect('prerelease is skipped', decide('0.68.0', mk('0.69.0-rc.1', '0.68.0')), ('0.68.0', False))
    expect('newline in the pin file is fine', decide('0.68.0\n', mk('0.68.1')), ('0.68.1', True))
    for bad in ('0.68', 'v0.68.0', '^0.68.0', '0.68.0-rc.1', ''):
        try:
            parse(bad)
            expect(f'pin {bad!r} is refused', 'accepted', 'refused')
        except ValueError:
            pass
    try:
        decide('0.68.0', mk('0.69.0!'))
        expect('an index with nothing usable fails', 'passed', 'raised')
    except ValueError:
        pass
    print('kani_bump selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    args = argv[1:]
    if '--selftest' in args:
        return selftest()
    if not args or args[0] != 'plan':
        print(__doc__, file=sys.stderr)
        return 2
    pin = args[args.index('--pin') + 1] if '--pin' in args else '.kani-version'
    with open(pin) as f:
        current = f.read().strip()
    if '--index-file' in args:
        with open(args[args.index('--index-file') + 1]) as f:
            index = json.load(f)
    else:
        index = fetch()
    top, bump = decide(current, index)
    print(f'current={current}')
    print(f'newest={top}')
    print(f'bump={"true" if bump else "false"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
