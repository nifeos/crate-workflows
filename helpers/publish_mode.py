#!/usr/bin/env python3
"""Decide how the release publishes: `trusted` (OIDC) or `token` (first publish only).

    python3 helpers/publish_mode.py plan MANIFEST [--token-present]   # prints the mode, writes $GITHUB_OUTPUT
    python3 helpers/publish_mode.py --selftest

crates.io binds a trusted publisher only to a crate that already exists, so the first publish of a
crate needs a token. The rule is by the crate's presence on crates.io, never by what secrets exist:

- crate absent (404): `token`, which needs the CRATES_IO_FIRST_PUBLISH_TOKEN environment secret
  (provisional name); a missing secret is a failure naming it.
- crate present (200): `trusted`, even when the secret is set. A token is never used for a crate
  that exists, and a failed trusted exchange is a red job, not a reason to try the token.
- any other answer (network, 5xx, 429): a failure. Guessing either way would publish through the
  wrong door.
"""

import json
import os
import sys
import tomllib
import urllib.error
import urllib.request

API = 'https://crates.io/api/v1/crates/'
AGENT = 'nifeos-crate-workflows publish-mode (https://github.com/nifeos/crate-workflows)'
SECRET = 'CRATES_IO_FIRST_PUBLISH_TOKEN'


def crate_exists(name):
    """True on 200, False on 404; anything else raises, because it answers nothing."""
    req = urllib.request.Request(API + name, headers={'User-Agent': AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def decide(name, exists, token_present):
    """(mode, problem); problem is a sentence when the release must not go on."""
    if exists:
        return 'trusted', None
    if token_present:
        return 'token', None
    return None, (f'{name} is not on crates.io, so its first publish needs a token: create the '
                  f'{SECRET} secret in the crates-io environment (scoped to publish-new, limited to '
                  f'the crate name {name}, short expiry). Its value is never needed here.')


def plan(manifest, token_present, lookup=crate_exists):
    with open(manifest, 'rb') as f:
        name = tomllib.load(f).get('package', {}).get('name', '')
    if not name:
        return None, f'{manifest} names no package'
    try:
        exists = lookup(name)
    except Exception as e:  # noqa: BLE001 (any failure to look is one failure to report)
        return None, f'could not tell whether {name} is on crates.io ({e}); not guessing'
    return decide(name, exists, token_present)


def selftest():
    import tempfile
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: expected {want}, got {got}')
    check('absent, secret set', decide('c', False, True), ('token', None))
    check('present, no secret', decide('c', True, False), ('trusted', None))
    check('present, secret set stays trusted', decide('c', True, True), ('trusted', None))
    mode, problem = decide('c', False, False)
    check('absent, no secret fails', mode, None)
    check('failure names the secret', SECRET in (problem or ''), True)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'Cargo.toml')
        open(path, 'w').write('[package]\nname = "demo"\nversion = "0.1.0"\n')
        seen = []
        check('plan reads the crate name and looks it up',
              plan(path, True, lookup=lambda n: seen.append(n) or False), ('token', None))
        check('lookup saw the manifest name', seen, ['demo'])

        def broken(_):
            raise OSError('timed out')
        mode, problem = plan(path, True, lookup=broken)
        check('a failed lookup is a failure, even with the secret set', mode, None)
        check('and says it is not guessing', 'not guessing' in (problem or ''), True)
        open(path, 'w').write('[workspace]\n')
        check('no package name fails', plan(path, True, lookup=lambda n: True)[0], None)
    print('publish_mode selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ['--selftest']:
        return selftest()
    if len(argv) < 3 or argv[1] != 'plan':
        print(__doc__, file=sys.stderr)
        return 2
    mode, problem = plan(argv[2], '--token-present' in argv[3:])
    if problem:
        print(f'publish_mode: {problem}', file=sys.stderr)
        return 1
    print(f'==> publish mode: {mode}')
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write(f'mode={mode}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
