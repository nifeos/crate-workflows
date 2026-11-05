#!/usr/bin/env python3
"""A major semver finding fires the architect hold.

    helpers/semver-run.sh Cargo.toml semver-report.txt
    python3 semver_major.py semver-report.txt
    python3 semver_major.py semver-report.txt --carried base-report.txt --lints lints.txt
    python3 semver_major.py --selftest

The report is what `cargo semver-checks` prints (progress and findings together; the tool has no
JSON output). Exit 0 means the summary says a new major version is required, and the caller adds
`needs-architect`; 1 means nothing major; 2 means the report could not be read, which the caller
routes to a person rather than to a label. The per-pull-request run is the rule that holds a merge
(the weekly semver job is a report, since a deliberate break between releases waits for its
release). The baseline is chosen by helpers/semver-run.sh: the previous release tag, else the last
published version. A crate with neither has no baseline, the tool says it is not in the registry,
and this script reads that as "nothing major yet" rather than as a failure.

With `--carried`, the rule holds only a NEW break. The second report is the same check run at the
pull request's merge base against the same baseline (helpers/semver-rule.sh runs both), and exit 0
then means the pull request's report holds a major finding the merge base's report does not. A
break already on the base branch was ruled in its own pull request and waits for its release; it
must not hold every later pull request. A finding is its lint and its item with the source
location removed, since line numbers shift between the two trees. `--lints` is the table
`cargo semver-checks --list` prints, so only lints whose type is `major` count: a minor finding new
beside a carried major one is not a break. A merge-base report that cannot be read is no evidence
of what the base carried, so the pull request's own judgment stands, which holds.
"""

import re
import sys

MAJOR = re.compile(r'Summary semver requires new major version: (\d+) major')
FAILURE = re.compile(r'^--- failure (\w+): (.*) ---$', re.MULTILINE)
SUMMARY = re.compile(r'Summary (no semver update required|semver requires new (major|minor) version)')
NO_BASELINE = 'not found in registry'
# An item line under "Failed in:" ends with where it is: ", previously in file /p/lib.rs:2",
# " in /p/lib.rs:6" or ", in /p/lib.rs:3". The location differs between the two trees.
LOCATION = re.compile(r',?\s+(?:previously\s+)?in\s+(?:file\s+)?/\S.*:\d+\s*$')
LINT_TYPE = re.compile(r'^(\w+)\s+(major|minor)\s', re.MULTILINE)


def plain(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def findings(text):
    """{(lint, item)} for every item under every failure, the location removed."""
    out = set()
    blocks = re.split(r'^(?=--- )', plain(text), flags=re.MULTILINE)
    for block in blocks:
        head = FAILURE.match(block)
        if not head:
            continue
        lint = head.group(1)
        _, _, failed = block.partition('\nFailed in:\n')
        items = []
        for line in failed.splitlines():
            if not line.startswith('  ') or not line.strip():
                break
            items.append(LOCATION.sub('', line.strip()))
        out |= {(lint, item) for item in items} or {(lint, '')}
    return out


def lint_types(text):
    """{lint: 'major' or 'minor'} from `cargo semver-checks --list`."""
    return dict(LINT_TYPE.findall(plain(text)))


def judge(text):
    """(code, lines): 0 major, 1 nothing major, 2 unreadable."""
    text = plain(text)
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


def judge_new(head, base, types):
    """(code, lines) for the pull request's report against its merge base's: 0 a new major break,
    1 nothing new, 2 the pull request's own report is unreadable."""
    code, lines = judge(head)
    if code != 0:
        return code, lines
    base_code, _ = judge(base)
    if base_code == 2:
        return 0, lines + ['semver: the merge base report is unreadable; the pull request is judged alone']
    carried = findings(base) if base_code == 0 else set()
    new = sorted(f for f in findings(head) - carried if types.get(f[0], 'major') == 'major')
    if not new:
        return 1, ['==> semver: every major break here is already on the base branch; nothing new']
    return 0, [f'semver: new major break: {lint}: {item}' if item else f'semver: new major break: {lint}'
               for lint, item in new]


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

    def report(*failures):
        """A major report with one failure block per (lint, item, location)."""
        body = ''.join(f'--- failure {lint}: what ---\n\nDescription:\nwords\n\nFailed in:\n'
                       f'  {item}{where}\n\n' for lint, item, where in failures)
        return body + '     Summary semver requires new major version: 1 major and 0 minor checks failed\n'
    clean = '     Summary no semver update required\n'
    types = lint_types('id  type  description\n==  ====  ===\nfunction_missing  major  gone\n'
                       'auto_trait_impl_added  minor  gained\n')
    check('lint types', types, {'function_missing': 'major', 'auto_trait_impl_added': 'minor'})
    gone = ('function_missing', 'function c::doomed', ', previously in file /t/a/src/lib.rs:2')
    gone_elsewhere = ('function_missing', 'function c::doomed', ', previously in file /t/b/src/lib.rs:9')
    other = ('function_missing', 'function c::other', ', previously in file /t/a/src/lib.rs:3')
    check('locations are removed', findings(report(gone, ('enum_variant_added', 'variant E:B', ' in /t/src/lib.rs:7'),
                                                   ('function_parameter_count_changed', 'c::kept now takes 1',
                                                    ', in /t/src/lib.rs:3'))),
          {('function_missing', 'function c::doomed'), ('enum_variant_added', 'variant E:B'),
           ('function_parameter_count_changed', 'c::kept now takes 1')})
    check('no break passes', judge_new(clean, clean, types)[0], 1)
    check('a new break fires', judge_new(report(gone), clean, types), (0, [
        'semver: new major break: function_missing: function c::doomed']))
    check('a carried break does not fire', judge_new(report(gone), report(gone_elsewhere), types)[0], 1)
    check('a second item of a carried lint fires', judge_new(report(gone, other), report(gone), types), (0, [
        'semver: new major break: function_missing: function c::other']))
    check('a minor finding beside a carried break does not fire',
          judge_new(report(gone, ('auto_trait_impl_added', 'type c::S', ' in /t/src/lib.rs:4')), report(gone), types)[0], 1)
    check('an unreadable base report leaves the pull request judged alone',
          judge_new(report(gone), 'error: could not compile', types)[0], 0)
    check('an unreadable pull request report is unreadable', judge_new('error: x', clean, types)[0], 2)
    print('semver_major selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ['--selftest']:
        return selftest()
    args = argv[1:]
    if len(args) not in (1, 5) or (len(args) == 5 and (args[1], args[3]) != ('--carried', '--lints')):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        texts = [open(path).read() for path in args[0::2]]
    except OSError as e:
        print(f'semver_major: could not read a report: {e}', file=sys.stderr)
        return 2
    if len(texts) == 1:
        code, lines = judge(texts[0])
    else:
        code, lines = judge_new(texts[0], texts[1], lint_types(texts[2]))
    for line in lines:
        print(line, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv))
