#!/usr/bin/env python3
"""The template's workflows keep their shape: reusable ones declare permissions, the three
per-pull-request and weekly workflows start with the lag check, and no job loses its budget.

    python3 workflow_shape.py [--workflows-dir .github/workflows] [--selftest]

This is the rung-two gate for the two invariants the lag check and the budget check each depend
on. The lag check is "the first job of every reusable workflow": a workflow reordered so some
other job runs first lets a stale pin burn twenty minutes of runner before it finds out. The
budget lint (helpers/job_budget.py) is the other half and runs beside this one.
"""

import re
import sys
from pathlib import Path

# Which files are reusable at all, and which must open with the lag job.
LAG_FIRST = ('check.yml', 'proofs.yml', 'weekly.yml')
REUSABLE = LAG_FIRST + ('release.yml', 'label.yml', 'hold.yml', 'ruled.yml')


def jobs_of(text):
    """[job keys] in file order, top-level `jobs:` only, by indentation."""
    out, in_jobs = [], False
    for line in text.splitlines():
        if re.match(r'^jobs:\s*$', line):
            in_jobs = True
            continue
        if in_jobs and re.match(r'^\S', line) and not line.startswith('#'):
            break
        if in_jobs:
            m = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
            if m:
                out.append(m.group(1))
    return out


def has_workflow_call(text):
    return bool(re.search(r'^\s*workflow_call:\s*$', text, re.M)) or \
        'workflow_call: {}' in text


def has_permissions(text):
    return bool(re.search(r'^permissions:', text, re.M))


def problems(dirpath, subset=None):
    out = []
    root = Path(dirpath)
    for name in (subset or REUSABLE):
        path = root / name
        if not path.is_file():
            out.append(f'{path}: missing')
            continue
        text = path.read_text()
        if not has_workflow_call(text):
            out.append(f'{name}: no workflow_call; callers cannot reach it')
        if not has_permissions(text):
            out.append(f'{name}: no top-level permissions; jobs inherit the caller token\'s full reach')
        if name in LAG_FIRST:
            jobs = jobs_of(text)
            if not jobs or jobs[0] != 'lag':
                out.append(f'{name}: the first job is {jobs[0] if jobs else "none"!r}; the lag check goes first, '
                           'so a stale pin fails before anything burns runner time')
    return out


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
        (root / 'check.yml').write_text('name: check\non:\n  workflow_call:\npermissions: {}\njobs:\n'
                                        '  lag:\n    runs-on: x\n  fmt:\n    runs-on: x\n')
        (root / 'release.yml').write_text('on: workflow_call: {}\npermissions: {}\njobs:\n'
                                          '  gate:\n    steps: []\n')
        expect('clean', problems(root, ('check.yml', 'release.yml')), [])
        (root / 'check.yml').write_text('on:\n  workflow_call:\njobs:\n  fmt:\n    steps: []\n  lag:\n    steps: []\n')
        got = problems(root, ('check.yml',))
        expect('two findings when lag is not first and permissions are gone', len(got), 2)
        expect('the finding names the job', any('fmt' in g for g in got), True)
    print('workflow_shape selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    args = argv[1:]
    if '--selftest' in args:
        return selftest()
    directory = args[args.index('--workflows-dir') + 1] if '--workflows-dir' in args else '.github/workflows'
    found = problems(directory)
    for p in found:
        print(f'workflow_shape: {p}', file=sys.stderr)
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
