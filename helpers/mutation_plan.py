#!/usr/bin/env python3
"""When the full mutation run runs, and when an unchanged tree lets it finish in seconds.

    python3 mutation_plan.py schedule <repository-name>
    python3 mutation_plan.py window --event E --repository OWNER/NAME --now ISO-8601 [--stagger B]
    python3 mutation_plan.py fingerprint --crate-dir DIR --template-dir DIR
    python3 mutation_plan.py compare --event E --repository OWNER/NAME --workflow-ref REF
        --branch B --run-id N --now ISO-8601 --fingerprint HEX [--skip-unchanged B]
    python3 mutation_plan.py verify OWNER/NAME SHA [--workflow mutation.yml]
    python3 mutation_plan.py --selftest

THE WEEKDAY. Each repository runs on its own weekday, derived from its name alone (the part after
the slash, lowercased): the SHA-256 of the name, as a number, modulo 7 is the cron weekday (0 is
Sunday), and the quotient modulo 60 is the minute. `schedule` prints the cron line for a name, three
tries on that day, at 08, 10 and 12 UTC. Two names may share a day; the minute differs.

THE WINDOW. A scheduled run that starts outside 08:00-13:00 UTC is deferred: it exits green at once
with a notice, so a start the scheduler delayed into the working day does not take hosted runners
for hours. A scheduled run on another weekday than the name's fails: the caller's cron is wrong, and
the failure prints the line to use. A dispatch is never deferred, since a person asked for it.

THE FINGERPRINT. The SHA-256 over every tracked file's mode, blob and path, except under `.github/`
(which keeps `.github/mutants-exempts`) and `docs/`, plus the output of `rustc -vV`, `cargo -V` and
`cargo mutants --version` in the crate directory (so a rust-toolchain file is resolved), plus the
template's own `mutation.yml` and `helpers/mutants_gate.py`. So the crate's sources, tests,
Cargo.lock, rust-toolchain, mutants configuration and exemptions are all in it, as are the resolved
toolchain and tool versions; a README change is in it too, since a README may carry doctests.

THE RECORD. Every run names one job `mutation record: <record>`, and that job name is where the
fingerprint is stored: it is part of the run, returned by the jobs API to any token that can read
the repository's Actions runs (the default GITHUB_TOKEN with `contents: read` on a public
repository), and it lasts as long as the run does, past the expiry of logs and artifacts. A record
is one of:

    full <fingerprint>                      this run tested every mutant
    unchanged <fingerprint> since run <N>   run N, a green full run, tested this same tree
    deferred                                started outside the window; nothing was tested
    repeat since run <N>                    run N already ran today; nothing was tested

THE COMPARISON. The newest completed full run on this branch decides. When it is green and its
fingerprint is this one, this run records `unchanged` and tests nothing. Anything else (no full run,
a red or cancelled one, another fingerprint) runs the whole sharded pass. A red full run is never
skipped past: the next run tests everything again until a green one exists. On a scheduled run, an
earlier scheduled run the same UTC day that recorded `full` or `unchanged` makes this one a
`repeat`, so the later tries of the day cost seconds even after a red run. Only the branch's
newest 30 runs are read, so an unchanged tree is tested again about every ten weeks.

THE RELEASE GATE. `verify` passes when a green run of the mutation workflow at exactly the released
commit recorded `full`, or recorded `unchanged <fingerprint> since run N` where run N is a green
run of the same workflow whose record is `full` with that same fingerprint. A `deferred` or
`repeat` run tested nothing and never counts, and neither does a red run, whatever it recorded.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

WINDOW_START_HOUR = 8
WINDOW_END_HOUR = 13
TRY_HOURS = (8, 10, 12)
# How many of the branch's newest runs the comparison reads: about ten weeks at three tries a week.
# A green full run further back than this is not found, and the run tests everything again.
HISTORY_RUNS = 30
RECORD_JOB = re.compile(r'mutation record: (\S.*?)\s*$')
FULL = re.compile(r'^full ([0-9a-f]{64})$')
UNCHANGED = re.compile(r'^unchanged ([0-9a-f]{64}) since run (\d+)$')
CRON_DAYS = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')


def name_hash(repository):
    """The name's number: the part after the slash, lowercased, as GitHub compares names."""
    name = repository.rsplit('/', 1)[-1].lower()
    return int(hashlib.sha256(name.encode()).hexdigest(), 16)


def cron_weekday(repository):
    return name_hash(repository) % 7


def cron_line(repository):
    h = name_hash(repository)
    return '%d %s * * %d' % ((h // 7) % 60, ','.join(map(str, TRY_HOURS)), h % 7)


def parse_now(text):
    return datetime.datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)


def window(event, now, repository, stagger=True):
    """('deferred' | 'run' | 'error', message). Only a scheduled run is held to the window."""
    if event != 'schedule' or not stagger:
        return 'run', 'a %s run is not held to the window' % event
    if not WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR:
        return 'deferred', ('deferred: this scheduled run started at %s UTC, outside %02d:00-%02d:00 '
                            'UTC; nothing was tested, and the next try or next week runs it'
                            % (now.strftime('%H:%M'), WINDOW_START_HOUR, WINDOW_END_HOUR))
    today = (now.weekday() + 1) % 7
    want = cron_weekday(repository)
    if today != want:
        return 'error', ('this scheduled run started on a %s, and %s runs on %ss; the caller\'s cron '
                         'line is "%s"' % (CRON_DAYS[today], repository, CRON_DAYS[want],
                                           cron_line(repository)))
    return 'run', 'inside the window on %s\'s day' % repository


def parse_record(text):
    """(kind, fingerprint, source run) from a record, or None for an empty or unknown one."""
    text = (text or '').strip()
    m = FULL.match(text)
    if m:
        return ('full', m.group(1), None)
    m = UNCHANGED.match(text)
    if m:
        return ('unchanged', m.group(1), int(m.group(2)))
    if text == 'deferred' or re.match(r'^repeat since run \d+$', text):
        return (text.split()[0], None, None)
    return None


def record_of(job_names):
    """The record a run's jobs carry, as text, or '' when no job is a record job."""
    for name in job_names:
        m = RECORD_JOB.search(name)
        if m:
            return m.group(1)
    return ''


def compare(event, now, fingerprint, runs, run_id, skip_unchanged=True):
    """(mode, record, message) for this run. `runs` are this branch's runs of this workflow, newest
    first, each {id, status, conclusion, event, created_at, record}; a record may be a function
    that fetches it, so a run older than the deciding one costs no request."""
    full = ('full', 'full %s' % fingerprint)
    if not skip_unchanged:
        return full + ('skip-unchanged is off; testing every mutant',)
    today = now.strftime('%Y-%m-%d')
    for run in runs:
        if run['id'] == run_id or run.get('status') != 'completed':
            continue
        text = run['record']() if callable(run.get('record')) else run.get('record')
        record = parse_record(text)
        if not record:
            continue
        if (event == 'schedule' and run.get('event') == 'schedule'
                and record[0] in ('full', 'unchanged') and run.get('created_at', '')[:10] == today):
            return ('repeat', 'repeat since run %d' % run['id'],
                    'run %d already ran today; nothing to test' % run['id'])
        if record[0] != 'full':
            continue
        if run.get('conclusion') != 'success':
            return full + ('the newest full run, %d, was %s; testing every mutant'
                           % (run['id'], run.get('conclusion')),)
        if record[1] != fingerprint:
            return full + ('the tree changed since run %d, the newest green full run; testing '
                           'every mutant' % run['id'],)
        return ('unchanged', 'unchanged %s since run %d' % (fingerprint, run['id']),
                'unchanged since run %d, a green full run of this same tree; nothing to test'
                % run['id'])
    return full + ('no full run on record; testing every mutant',)


def tracked(repo_root):
    """[(mode, blob, path)] for every tracked file, from `git ls-files -s`."""
    out = subprocess.run(['git', 'ls-files', '-s', '-z'], cwd=repo_root, check=True,
                         capture_output=True).stdout.decode()
    rows = []
    for entry in filter(None, out.split('\0')):
        meta, path = entry.split('\t', 1)
        mode, blob, _stage = meta.split()
        rows.append((mode, blob, path))
    return rows


def counted(path):
    if path.startswith('docs/'):
        return False
    return not path.startswith('.github/') or path == '.github/mutants-exempts'


def fingerprint_of(rows, versions, template_files):
    """The hex SHA-256 over the counted files, the tool versions, and the template's files."""
    h = hashlib.sha256()
    for mode, blob, path in sorted(rows, key=lambda r: r[2]):
        if counted(path):
            h.update(('%s %s %s\n' % (mode, blob, path)).encode())
    for text in versions:
        h.update(b'version\n' + text.encode() + b'\n')
    for name, data in template_files:
        h.update(b'template ' + name.encode() + b'\n' + data + b'\n')
    return h.hexdigest()


def fingerprint(crate_dir, template_dir):
    repo_root = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=crate_dir, check=True,
                               capture_output=True, text=True).stdout.strip()
    versions = [subprocess.run(cmd, cwd=crate_dir, check=True, capture_output=True,
                               text=True).stdout.strip()
                for cmd in (['rustc', '-vV'], ['cargo', '-V'], ['cargo', 'mutants', '--version'])]
    names = ('.github/workflows/mutation.yml', 'helpers/mutants_gate.py')
    template = [(n, (Path(template_dir) / n).read_bytes()) for n in names]
    return fingerprint_of(tracked(repo_root), versions, template)


def gh_json(path):
    out = subprocess.run(['gh', 'api', path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def run_record(repository, run_id):
    jobs = gh_json('repos/%s/actions/runs/%d/jobs?per_page=100' % (repository, run_id))
    return record_of(j.get('name', '') for j in jobs.get('jobs', []))


def history(repository, workflow_ref, branch):
    """This branch's runs of the calling workflow, newest first, each record fetched on demand."""
    workflow = workflow_ref.split('@', 1)[0].rsplit('/', 1)[-1]
    listing = gh_json('repos/%s/actions/workflows/%s/runs?branch=%s&per_page=%d'
                      % (repository, workflow, urllib.parse.quote(branch, safe=''), HISTORY_RUNS))
    return [{'id': run['id'], 'status': run.get('status'), 'event': run.get('event'),
             'conclusion': run.get('conclusion'), 'created_at': run.get('created_at', ''),
             'record': (lambda rid=run['id']: run_record(repository, rid))}
            for run in listing.get('workflow_runs', [])]


def verify(sha_runs, fetch_run, workflow_path):
    """(ok, message). `sha_runs` are the workflow's green runs at the released commit, each with
    `id` and `record`; `fetch_run(n)` returns run n as {id, conclusion, path, record}, or None."""
    for run in sha_runs:
        text = run['record']() if callable(run.get('record')) else run.get('record')
        record = parse_record(text)
        if not record:
            continue
        if record[0] == 'full':
            return True, 'run %d tested every mutant at this commit and was green' % run['id']
        if record[0] != 'unchanged':
            continue
        source = fetch_run(record[2])
        if not source:
            continue
        src = parse_record(source.get('record'))
        if (source.get('conclusion') == 'success' and source.get('path') == workflow_path
                and src and src[0] == 'full' and src[1] == record[1]):
            return True, ('run %d found this commit unchanged since run %d, a green full run of '
                          'the same fingerprint' % (run['id'], source['id']))
    return False, ('no green full mutation run at this commit, and no green unchanged run pointing '
                   'at a green full run of the same fingerprint')


def emit(outputs, message, notice=True):
    """Write step outputs to GITHUB_OUTPUT (or stdout) and the message to the log and summary."""
    target = os.environ.get('GITHUB_OUTPUT')
    lines = ''.join('%s=%s\n' % kv for kv in outputs.items())
    if target:
        with open(target, 'a') as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)
    print(('::notice::mutation: %s' if notice else '==> mutation: %s') % message)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write('### Mutation plan\n\n%s\n\n' % message)


def flag(text):
    if text not in ('true', 'false'):
        raise argparse.ArgumentTypeError('want true or false, got %r' % text)
    return text == 'true'


def main(argv):
    if '--selftest' in argv[1:]:
        return selftest()
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('schedule')
    s.add_argument('repository')
    w = sub.add_parser('window')
    w.add_argument('--event', required=True)
    w.add_argument('--repository', required=True)
    w.add_argument('--now', required=True, type=parse_now)
    w.add_argument('--stagger', type=flag, default=True)
    f = sub.add_parser('fingerprint')
    f.add_argument('--crate-dir', required=True)
    f.add_argument('--template-dir', required=True)
    c = sub.add_parser('compare')
    for name in ('--event', '--repository', '--workflow-ref', '--branch', '--fingerprint'):
        c.add_argument(name, required=True)
    c.add_argument('--run-id', required=True, type=int)
    c.add_argument('--now', required=True, type=parse_now)
    c.add_argument('--skip-unchanged', type=flag, default=True)
    v = sub.add_parser('verify')
    v.add_argument('repository')
    v.add_argument('sha')
    v.add_argument('--workflow', default='mutation.yml')
    a = p.parse_args(argv[1:])
    if a.command == 'verify':
        return verify_live(a.repository, a.sha, a.workflow)
    if a.command == 'schedule':
        print(cron_line(a.repository))
        return 0
    if a.command == 'window':
        mode, message = window(a.event, a.now, a.repository, a.stagger)
        if mode == 'error':
            print('::error::mutation: %s' % message)
            return 1
        emit({'mode': mode, 'record': 'deferred' if mode == 'deferred' else ''}, message,
             notice=mode == 'deferred')
        return 0
    if a.command == 'fingerprint':
        print(fingerprint(a.crate_dir, a.template_dir))
        return 0
    if not re.match(r'^[0-9a-f]{64}$', a.fingerprint):
        print('::error::mutation: %r is not a SHA-256 fingerprint' % a.fingerprint)
        return 1
    runs = history(a.repository, a.workflow_ref, a.branch) if a.skip_unchanged else []
    mode, record, message = compare(a.event, a.now, a.fingerprint, runs, a.run_id, a.skip_unchanged)
    emit({'mode': mode, 'record': record}, message, notice=mode != 'full')
    return 0


def verify_live(repository, sha, workflow):
    try:
        listing = gh_json('repos/%s/actions/workflows/%s/runs?head_sha=%s&status=success&per_page=100'
                          % (repository, workflow, sha))
    except subprocess.CalledProcessError as e:
        print('release-gate: %s: the runs could not be read (%s); the repository needs the caller '
              '.github/workflows/%s' % (workflow, (e.stderr or '').strip(), workflow), file=sys.stderr)
        return 1
    sha_runs = [{'id': r['id'], 'record': (lambda rid=r['id']: run_record(repository, rid))}
                for r in listing.get('workflow_runs', []) if r.get('conclusion') == 'success']

    def fetch_run(n):
        try:
            run = gh_json('repos/%s/actions/runs/%d' % (repository, n))
        except subprocess.CalledProcessError:
            return None
        return {'id': n, 'conclusion': run.get('conclusion'), 'path': run.get('path'),
                'record': run_record(repository, n)}

    ok, message = verify(sha_runs, fetch_run, '.github/workflows/%s' % workflow)
    print('release-gate: %s: %s' % (workflow, message), file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def selftest():
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print('FAIL %s: got %r want %r' % (label, got, want), file=sys.stderr)

    # The fixtures: one JSON file a case, each a run's situation and the decision it must reach.
    # fixtures/mutation/pass and fail are a full run's two verdicts, mutants_gate.py's to test.
    fixtures = Path(__file__).resolve().parent.parent / 'fixtures' / 'mutation'
    cases = sorted(fixtures.glob('*.json'))
    expect('the unchanged-skip and deferred cases exist',
           {'unchanged-skip', 'deferred'} <= {c.stem for c in cases}, True)
    for path in cases:
        case = json.loads(path.read_text())
        now = parse_now(case['now'])
        mode, _ = window(case['event'], now, case['repository'], case.get('stagger', True))
        if mode == 'run':
            mode, record, _ = compare(case['event'], now, case['fingerprint'], case['runs'],
                                      case['run_id'], case.get('skip_unchanged', True))
        else:
            record = 'deferred' if mode == 'deferred' else None
        expect('%s: mode' % path.stem, mode, case['expect']['mode'])
        expect('%s: record' % path.stem, record, case['expect'].get('record'))

    # The release gate's cases: the green runs at the released commit, the runs they point at.
    releases = sorted((fixtures / 'release').glob('*.json'))
    expect('release cases', len(releases) >= 5, True)
    for path in releases:
        case = json.loads(path.read_text())
        sources = {r['id']: r for r in case.get('sources', [])}
        ok_, _ = verify(case['sha_runs'], sources.get, '.github/workflows/mutation.yml')
        expect('release %s' % path.stem, ok_, case['expect'])

    expect('cron line', cron_line('nifeos/example_thing'), '9 8,10,12 * * 0')
    expect('name only, any case', cron_line('Example_Thing'), cron_line('other/example_thing'))
    expect('record from job names', record_of(['mutation / lag (template release)',
                                               'mutation / mutation record: full ' + 'a' * 64]),
           'full ' + 'a' * 64)
    expect('an empty record', parse_record(record_of(['mutation / mutation record: '])), None)
    expect('unchanged parsed', parse_record('unchanged %s since run 7' % ('b' * 64)),
           ('unchanged', 'b' * 64, 7))
    expect('a short fingerprint is no record', parse_record('full abc'), None)

    rows = [('100644', '1' * 40, 'src/lib.rs'), ('100644', '2' * 40, '.github/workflows/ci.yml'),
            ('100644', '3' * 40, '.github/mutants-exempts'), ('100644', '4' * 40, 'docs/x.md')]
    base = fingerprint_of(rows, ['rustc 1.91.0'], [('t', b'x')])
    expect('a workflow edit is not counted', fingerprint_of(
        [r if r[2] != '.github/workflows/ci.yml' else (r[0], '9' * 40, r[2]) for r in rows],
        ['rustc 1.91.0'], [('t', b'x')]), base)
    expect('docs are not counted', fingerprint_of(rows[:3], ['rustc 1.91.0'], [('t', b'x')]), base)
    for label, other in [
            ('a source edit', fingerprint_of([('100644', '9' * 40, 'src/lib.rs')] + rows[1:],
                                             ['rustc 1.91.0'], [('t', b'x')])),
            ('an exemption edit', fingerprint_of(rows[:2] + [('100644', '9' * 40, rows[2][2])] +
                                                 rows[3:], ['rustc 1.91.0'], [('t', b'x')])),
            ('a toolchain change', fingerprint_of(rows, ['rustc 1.92.0'], [('t', b'x')])),
            ('a template change', fingerprint_of(rows, ['rustc 1.91.0'], [('t', b'y')]))]:
        expect('%s changes the fingerprint' % label, other != base, True)

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['git', 'init', '-q', tmp], check=True)
        Path(tmp, 'a.rs').write_text('fn main() {}\n')
        subprocess.run(['git', 'add', 'a.rs'], cwd=tmp, check=True)
        expect('git ls-files read', [r[2] for r in tracked(tmp)], ['a.rs'])
    print('mutation_plan selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
