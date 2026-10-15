#!/usr/bin/env python3
"""A major semver report fires the architect hold.

    cargo semver-checks --json > report.json
    python3 semver_major.py report.json

Exit 0 means at least one finding requires a Major version bump, and the caller adds
`needs-architect`; 1 means nothing major; 2 means the report could not be read, which the caller
routes to a person rather than to a label. The per-pull-request run is the rule that holds a
merge (the weekly semver job is a report, since a deliberate break between releases waits for its
release). The baseline is the crate's last published version, exactly what `cargo-semver-checks`
picks by default; a crate never published has no baseline, the tool says so, and this script
reads that as "nothing major yet" rather than as a failure.
"""

import json
import sys


def majors(node):
    if isinstance(node, dict):
        update = node.get('required_update', '')
        if isinstance(update, str) and update.lower() == 'major':
            yield node.get('name', '(unnamed)')
        for v in node.values():
            yield from majors(v)
    elif isinstance(node, list):
        for v in node:
            yield from majors(v)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        text = open(argv[1]).read().strip()
    except OSError as e:
        print(f'semver_major: could not read the report: {e}', file=sys.stderr)
        return 2
    if not text:
        print('semver_major: the report is empty; no baseline (never published) or no findings')
        return 1
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # `cargo semver-checks` writes a "no baseline" note as plain text on some versions.
        if 'baseline' in text.lower():
            print(f'semver_major: no baseline to compare against ({text.splitlines()[0][:120]})')
            return 1
        print(f'semver_major: the report is not JSON: {e}', file=sys.stderr)
        return 2
    found = sorted(set(majors(data)))
    if not found:
        print('==> semver: no major break against the last release')
        return 1
    for name in found:
        print(f'semver: major break: {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
