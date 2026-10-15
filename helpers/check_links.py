#!/usr/bin/env python3
"""Every relative link in a Markdown file resolves (nife's markdown-links rule).

    python3 check_links.py [PATH...]

External links (http, https, mailto) are not fetched; this checks that a reader who clicks a link
into the repository lands on a file that exists. Anchors are stripped before the check, so a link
to `README.md#bugs` resolves when `README.md` does; whether the anchor itself exists is a check
nife does not run either, and a wrong anchor is a cosmetic bug rather than a dead one.
"""

import re
import sys
from pathlib import Path

LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')


def broken(path):
    out = []
    text = Path(path).read_text()
    for m in LINK.finditer(text):
        target = m.group(1)
        if re.match(r'^(https?:|mailto:|#)', target):
            continue
        bare = target.split('#', 1)[0]
        if not bare:
            continue
        here = Path(path).parent
        if not (here / bare).exists():
            out.append(target)
    return out


def main(argv):
    args = argv[1:]
    if args == ['--selftest']:
        return selftest()
    paths = [a for a in args if a.endswith('.md')]
    if not paths:
        paths = sorted(Path('.').rglob('*.md'))
    bad = False
    for p in paths:
        for target in broken(p):
            print(f'check_links: {p}: link to {target} does not resolve', file=sys.stderr)
            bad = True
    if not bad:
        print('==> markdown links: every relative link resolves')
    return 1 if bad else 0


def selftest():
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'README.md').write_text('[ok](LICENSE-MIT) [dead](GONE.md) [anchor](README.md#bugs) '
                                        '[external](https://example.com) [section](#x)\n')
        (root / 'LICENSE-MIT').write_text('MIT\n')
        expect('one dead link', broken(root / 'README.md'), ['GONE.md'])
    print('check_links selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
