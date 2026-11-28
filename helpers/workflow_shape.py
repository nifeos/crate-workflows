#!/usr/bin/env python3
"""The template's workflows keep their shape: reusable ones declare permissions, the
per-pull-request, weekly and mutation workflows start with the lag check, and no job loses its budget.

    python3 workflow_shape.py [--workflows-dir .github/workflows] [--selftest]

This is the rung-two gate for the two invariants the lag check and the budget check each depend
on. The lag check is "the first job of every reusable workflow": a workflow reordered so some
other job runs first lets a stale pin burn twenty minutes of runner before it finds out. The
budget lint (helpers/job_budget.py) is the other half and runs beside this one.

A reusable workflow declares its permissions at the top, or else on every job but the ones
INHERITS_CALLER names, each with its reason. Such a job holds exactly what the caller grants: a
job that asked by name for a permission the caller had not granted would fail the caller's whole
run at startup, so a job whose permission is the caller's choice can only inherit it.
"""

import re
import sys
from pathlib import Path

# Which files are reusable at all, and which must open with the lag job.
LAG_FIRST = ('check.yml', 'proofs.yml', 'weekly.yml', 'fuzz.yml', 'mutation.yml')
REUSABLE = LAG_FIRST + ('release.yml', 'label.yml', 'hold.yml', 'ruled.yml')

# {workflow: {job: reason}}: the jobs that take the caller's token as granted.
INHERITS_CALLER = {
    'mutation.yml': {
        'mutation-issue': 'files the crate\'s issue with issues: write when the caller grants it, '
                          'and warns when it does not, without failing the run',
    },
}


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


def jobs_without_permissions(text):
    """[job keys] whose block has no `permissions:` of its own, in file order."""
    out, in_jobs, job, seen = [], False, None, False
    for line in text.splitlines() + ['end:']:
        if re.match(r'^jobs:\s*$', line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        top = re.match(r'^\S', line) and not line.startswith('#')
        m = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
        if (m or top) and job is not None and not seen:
            out.append(job)
        if top:
            break
        if m:
            job, seen = m.group(1), False
        elif re.match(r'^    permissions:', line):
            seen = True
    return out


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
            allowed = INHERITS_CALLER.get(name, {})
            bare = [j for j in jobs_without_permissions(text) if j not in allowed]
            if bare:
                out.append(f'{name}: no top-level permissions, and {", ".join(bare)} name none; '
                           'those jobs inherit the caller token\'s full reach')
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

        # No top-level block: every job names its own, but a job INHERITS_CALLER lists.
        each = ('on:\n  workflow_call:\njobs:\n  lag:\n    runs-on: x\n    permissions:\n'
                '      contents: read\n  mutation-issue:\n    runs-on: x\n')
        (root / 'mutation.yml').write_text(each)
        expect('a listed job inherits', problems(root, ('mutation.yml',)), [])
        (root / 'mutation.yml').write_text(each + '  other:\n    runs-on: x\n')
        got = problems(root, ('mutation.yml',))
        expect('an unlisted job may not', (len(got), 'other' in got[0]), (1, True))
        (root / 'check.yml').write_text(each.replace('mutation-issue', 'fmt'))
        got = problems(root, ('check.yml',))
        expect('the list is per workflow', (len(got), 'fmt' in got[0]), (1, True))
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
