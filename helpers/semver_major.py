#!/usr/bin/env python3
"""A major semver finding fires the architect hold.

    helpers/semver-run.sh Cargo.toml semver-report.txt
    python3 semver_major.py semver-report.txt
    python3 semver_major.py --selftest

The report is what `cargo semver-checks` prints (progress and findings together; the tool has no
JSON output). Exit 0 means the summary says a new major version is required, and the caller adds
`needs-architect`; 1 means nothing major; 2 means the report could not be read, which the caller
routes to a person rather than to a label. The per-pull-request run is the rule that holds a merge
(the weekly semver job is a report, since a deliberate break between releases waits for its
release). The baseline is chosen by helpers/semver-run.sh: the previous release tag, else the last
published version. A crate with neither has no baseline, the tool says it is not in the registry,
and this script reads that as "nothing major yet" rather than as a failure.
"""

import re
import sys

MAJOR = re.compile(r'Summary semver requires new major version: (\d+) major')
FAILURE = re.compile(r'^--- failure (\w+): (.*) ---$', re.MULTILINE)
SUMMARY = re.compile(r'Summary (no semver update required|semver requires new (major|minor) version)')
NO_BASELINE = 'not found in registry'


def judge(text):
    """(code, lines): 0 major, 1 nothing major, 2 unreadable."""
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    if not text.strip():
        return 1, ['semver_major: the report is empty; nothing was checked']
    if MAJOR.search(text):
        found = [f'semver: major break: {lint}: {what}' for lint, what in FAILURE.findall(text)]
        return 0, found or ['semver: major break (the summary names no lint)']
    if SUMMARY.search(text):
        return 1, ['==> semver: no major break against the baseline']
    if NO_BASELINE in text:
        return 1, ['semver_major: no baseline (no release tag, not on crates.io); nothing major yet']
    return 2, ['semver_major: the report has no summary and no known baseline note']


def selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: expected {want}, got {got}')
    check('empty', judge('')[0], 1)
    check('clean', judge('     Summary no semver update required\n')[0], 1)
    check('minor', judge('     Summary semver requires new minor version: 0 major and 1 minor checks failed')[0], 1)
    code, lines = judge('--- failure function_missing: pub fn removed or renamed ---\n\n'
                        '     \x1b[1mSummary\x1b[0m semver requires new major version: 1 major and 0 minor checks failed\n')
    check('major', code, 0)
    check('major names the lint', lines, ['semver: major break: function_missing: pub fn removed or renamed'])
    check('colored summary still parses', judge('\x1b[32mSummary\x1b[0m no semver update required')[0], 1)
    check('no baseline', judge('jh7110_entropy not found in registry (crates.io).')[0], 1)
    check('noise is unreadable', judge('error: could not compile `x`')[0], 2)
    print('semver_major selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ['--selftest']:
        return selftest()
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        text = open(argv[1]).read()
    except OSError as e:
        print(f'semver_major: could not read the report: {e}', file=sys.stderr)
        return 2
    code, lines = judge(text)
    for line in lines:
        print(line, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv))
