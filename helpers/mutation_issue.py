#!/usr/bin/env python3
"""A red full mutation run files one issue in the crate's repository; a later green one closes it.

    python3 mutation_issue.py file --verdict RESULT --mode MODE --manifest-path PATH
        --findings FILE --repository OWNER/NAME --run-url URL --branch BRANCH --sha SHA
    python3 mutation_issue.py render ...the same arguments...   # print the body, call nothing
    python3 mutation_issue.py --selftest

mutation.yml's `mutation-issue` job runs `file` on a scheduled or dispatched run, after the
verdict. The full run is not a pull request gate, so without this a red run reaches nobody and its
survivors wait for the release gate to read the run.

# THE RULE

- One open issue for each crate, carrying the label `mutation-survivors` (provisional), which the
  job creates when the repository lacks it. A repository of several crates calls the workflow
  once for each crate, and the calls run at the same time, so each crate has an issue of its own,
  told apart by the marker `<!-- mutation-issue: <manifest-path> -->` on the body's first line:
  one shared issue would be edited by every call at once, and could close only when every crate
  was green.
- A red verdict (`failure`) opens the issue, or rewrites the open one's body and adds one comment
  that links the new run. The body names each SURVIVOR, TIMEOUT, stale exemption and malformed
  exemption line from the `--findings` file (helpers/mutants_gate.py writes it), links the run, and
  says how each is resolved. Over BODY_LIMIT characters, the rows that do not fit are counted
  instead; the run's log names every one. No findings file means the judge never ran: the plan or
  a shard failed first, and the body says so.
- A green verdict on a full run comments with the run's link and closes the open issue. A run that
  tested nothing (deferred, repeat, unchanged) leaves the issue as it is.
- Filing never changes the run's conclusion. Every refusal of the API (a caller whose token lacks
  `issues: write` is the usual one) is one `::warning::` line and exit 0, and the job carries
  `continue-on-error`, so a fault here cannot turn a green run red; the verdict job alone sets
  whether the run is red.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

LABEL = 'mutation-survivors'
LABEL_COLOR = 'fbca04'
LABEL_DESCRIPTION = 'The full mutation run is red: tests to write or exemptions to give a reason.'
BODY_LIMIT = 60_000  # characters; GitHub refuses an issue body over 65,536
EXEMPTS = '.github/mutants-exempts'


class ApiError(Exception):
    pass


def gh_api(method, path, body=None):
    """One `gh api` call, its JSON answer, or ApiError with gh's first line of complaint."""
    cmd = ['gh', 'api', '-X', method, path]
    if body is not None:
        cmd += ['--input', '-']
    try:
        done = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                              capture_output=True, text=True, check=False)
    except OSError as e:
        raise ApiError(f'gh did not start: {e}') from e
    if done.returncode != 0:
        lines = (done.stderr or done.stdout or 'no output').strip().splitlines() or ['no output']
        raise ApiError(f'{method} {path}: {lines[0]}')
    return json.loads(done.stdout) if done.stdout.strip() else None


def crate_key(manifest_path):
    """The manifest path as the marker names it: `./Cargo.toml` and `Cargo.toml` are one crate."""
    key = manifest_path.strip()
    while key.startswith('./'):
        key = key[2:]
    return key or 'Cargo.toml'


def marker(manifest_path):
    return f'<!-- mutation-issue: {crate_key(manifest_path)} -->'


def title(manifest_path):
    key = crate_key(manifest_path)
    if key == 'Cargo.toml':
        return 'The full mutation run is red'
    return f'The full mutation run is red for {key.rsplit("/Cargo.toml", 1)[0]}'


def code(text):
    """Inline code that survives backticks and a table's pipes."""
    text = str(text).replace('\n', ' ').replace('|', '\\|')
    fence = '``' if '`' in text else '`'
    pad = ' ' if fence == '``' else ''
    return f'{fence}{pad}{text}{pad}{fence}'


def load_findings(path):
    """The gate's findings, or None when the file is absent (the judge never ran)."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def render(findings, manifest_path, run_url, branch, sha, limit=BODY_LIMIT):
    """The issue body: what failed, where the run is, and how each finding is resolved."""
    key = crate_key(manifest_path)
    crate = '' if key == 'Cargo.toml' else f' for `{key}`'
    head = [marker(manifest_path), '',
            f'The [full mutation run]({run_url}){crate} on `{branch}` at `{sha[:12]}` is red. '
            'The run is not a pull request gate, so this issue holds its test gaps until a later '
            'full run is green, which closes it. Each red run rewrites this list.']
    tail = ['', '### How to resolve each', '',
            '- **SURVIVOR**: the tests passed with the mutation in place. Write a test that fails '
            'under it. `cargo mutants --file <file>` runs that file\'s mutants locally.',
            '- **TIMEOUT**: the tests ran past the timeout with the mutation in place. Write a test '
            'that ends with a failure under it, or exempt it as below when the mutation can only '
            'loop.',
            f'- **An equivalent mutant**, one no test can tell apart from the code: add '
            f'`<file>:<line> # <reason>` to `{EXEMPTS}`. One line covers every mutant on that '
            'source line, and the reason is required.',
            f'- **A stale exemption**: delete its line from `{EXEMPTS}`; no mutant on that line '
            'survives now.',
            f'- **A malformed exemption line**: rewrite it as `<file>:<line> # <reason>`.', '',
            'A dispatched run of the mutation workflow on the default branch checks the fix; a '
            'green one closes this issue.']
    body = []
    if findings is None:
        body += ['', 'The judge did not run: the plan or a mutation shard failed before it, so no '
                 'mutant was judged. The failing job\'s log in the run says why.']
    elif findings.get('error'):
        body += ['', f'The judge refused the run before judging any mutant: {findings["error"]}. The '
                 'failing job\'s log in the run says why.']
    refused = (findings or {}).get('refused') or []
    stale = (findings or {}).get('stale') or []
    malformed = (findings or {}).get('malformed') or []
    if findings is not None and not findings.get('error') and not (refused or stale or malformed):
        body += ['', 'The judge refused the run but named no mutant or exemption. The judge step\'s '
                 'log in the run says why.']

    sections = []
    if refused:
        rows = [f'| {r.get("verdict", "?")} | {code(r.get("where", "?"))} | '
                f'{code(r.get("mutant", ""))} |' for r in refused]
        sections.append((f'### Mutants the tests did not catch ({len(refused)})',
                         ['| verdict | where | mutation |', '| --- | --- | --- |'], rows))
    if stale:
        sections.append((f'### Stale exemptions ({len(stale)})',
                         [f'In `{EXEMPTS}`, naming no mutant that survives now:', ''],
                         [f'- {code(s)}' for s in stale]))
    if malformed:
        sections.append((f'### Malformed exemption lines ({len(malformed)})', [],
                         [f'- {code(m)}' for m in malformed]))

    size = sum(len(x) + 1 for x in head + body + tail)
    omitted = 0
    for heading, preamble, rows in sections:
        block = ['', heading, ''] + preamble
        need = sum(len(x) + 1 for x in block)
        if omitted or size + need + 200 > limit:
            omitted += len(rows)
            continue
        body += block
        size += need
        for i, row in enumerate(rows):
            if size + len(row) + 1 + 200 > limit:
                omitted += len(rows) - i
                break
            body.append(row)
            size += len(row) + 1
    if omitted:
        body += ['', f'{omitted} more not listed here for size; the judge step\'s log in the run '
                 'names every one.']
    return '\n'.join(head + body + tail) + '\n'


def open_issues(api, repository):
    """The open issues carrying LABEL, pull requests left out, every page."""
    out, page = [], 1
    while True:
        got = api('GET', f'repos/{repository}/issues?labels={LABEL}&state=open&per_page=100'
                  f'&page={page}') or []
        out += [i for i in got if 'pull_request' not in i]
        if len(got) < 100:
            return out
        page += 1


def find_issue(api, repository, manifest_path):
    """This crate's open issue, the oldest when somehow there are two, or None."""
    mine = [i for i in open_issues(api, repository)
            if (i.get('body') or '').startswith(marker(manifest_path))]
    return min(mine, key=lambda i: i['number']) if mine else None


def ensure_label(api, repository):
    try:
        api('GET', f'repos/{repository}/labels/{LABEL}')
    except ApiError:
        try:
            api('POST', f'repos/{repository}/labels',
                {'name': LABEL, 'color': LABEL_COLOR, 'description': LABEL_DESCRIPTION})
        except ApiError as e:
            # Another crate's call in the same run may have made it a moment ago; creating the
            # issue below names the label either way.
            print(f'==> label {LABEL} not created ({e}); the issue names it anyway')


def act(api, args, findings):
    """What the run's verdict asks of the issue. Returns a line saying what was done."""
    repository, manifest = args.repository, args.manifest_path
    if args.verdict == 'failure':
        body = render(findings, manifest, args.run_url, args.branch, args.sha)
        issue = find_issue(api, repository, manifest)
        if issue is None:
            ensure_label(api, repository)
            made = api('POST', f'repos/{repository}/issues',
                       {'title': title(manifest), 'body': body, 'labels': [LABEL]})
            return f'opened issue #{made["number"]}'
        n = issue['number']
        api('PATCH', f'repos/{repository}/issues/{n}', {'title': title(manifest), 'body': body})
        api('POST', f'repos/{repository}/issues/{n}/comments',
            {'body': f'The [full mutation run]({args.run_url}) at `{args.sha[:12]}` is red '
                     'again. The list above is this run\'s.'})
        return f'updated issue #{n}'
    if args.verdict == 'success' and args.mode == 'full':
        issue = find_issue(api, repository, manifest)
        if issue is None:
            return 'green, and no issue is open'
        n = issue['number']
        api('POST', f'repos/{repository}/issues/{n}/comments',
            {'body': f'The [full mutation run]({args.run_url}) at `{args.sha[:12]}` is green: '
                     'every mutant is caught or exempted with a reason. Closing.'})
        api('PATCH', f'repos/{repository}/issues/{n}',
            {'state': 'closed', 'state_reason': 'completed'})
        return f'closed issue #{n}'
    return f'verdict {args.verdict or "none"}, mode {args.mode or "none"}: the issue is left as it is'


def parser():
    p = argparse.ArgumentParser(prog='mutation_issue.py')
    p.add_argument('command', choices=('file', 'render'))
    for name in ('verdict', 'mode', 'manifest-path', 'findings', 'repository', 'run-url',
                 'branch', 'sha'):
        p.add_argument(f'--{name}', default='')
    return p


def main(argv, api=gh_api):
    if '--selftest' in argv[1:]:
        return selftest()
    args = parser().parse_args(argv[1:])
    args.manifest_path = args.manifest_path or 'Cargo.toml'
    findings = load_findings(args.findings) if args.findings else None
    if args.command == 'render':
        sys.stdout.write(render(findings, args.manifest_path, args.run_url, args.branch, args.sha))
        return 0
    try:
        print(f'==> mutation issue: {act(api, args, findings)}')
    except ApiError as e:
        print(f'::warning::mutation issue: not filed ({e}). The caller\'s mutation job grants '
              '`issues: write` for this; the run\'s own verdict stands either way.')
    except Exception as e:  # noqa: BLE001 - a fault here must never turn the run red
        print(f'::warning::mutation issue: not filed ({type(e).__name__}: {e}); the run\'s own '
              'verdict stands either way.')
    return 0


def selftest():
    import contextlib
    import io
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    findings = {'refused': [
        {'verdict': 'SURVIVOR', 'where': 'src/lib.rs:9', 'mutant': 'src/lib.rs:9:12: replace > with >='},
        {'verdict': 'TIMEOUT', 'where': 'src/lib.rs:20',
         'mutant': 'src/lib.rs:20:5: replace f -> Vec<u8> with vec![] | `x`'}],
        'stale': ['src/old.rs:3'], 'malformed': ['.github/mutants-exempts:4: want a reason'],
        'error': None}
    url = 'https://github.com/o/r/actions/runs/7'
    body = render(findings, './Cargo.toml', url, 'main', 'a' * 40)
    expect('marker first', body.splitlines()[0], '<!-- mutation-issue: Cargo.toml -->')
    expect('run linked', f'({url})' in body, True)
    for want in ('| SURVIVOR | `src/lib.rs:9` | `src/lib.rs:9:12: replace > with >=` |',
                 '`` src/lib.rs:20:5: replace f -> Vec<u8> with vec![] \\| `x` ``',
                 '### Stale exemptions (1)', '- `src/old.rs:3`', '### Malformed exemption lines (1)',
                 'Write a test that fails', '.github/mutants-exempts', 'aaaaaaaaaaaa'):
        expect(f'body holds {want!r}', want in body, True)
    expect('nothing omitted', 'more not listed' in body, False)
    expect('root title', title('Cargo.toml'), 'The full mutation run is red')
    expect('nested title', title('a_crate/Cargo.toml'), 'The full mutation run is red for a_crate')
    expect('nested marker', render(findings, 'a_crate/Cargo.toml', url, 'main', 'b' * 40)
           .splitlines()[0], '<!-- mutation-issue: a_crate/Cargo.toml -->')
    expect('no findings: the judge did not run',
           'The judge did not run' in render(None, 'Cargo.toml', url, 'main', 'c' * 40), True)
    expect('an error is named', 'shards left an outcomes.json' in render(
        {'refused': [], 'stale': [], 'malformed': [], 'error': '1 of 2 shards left an outcomes.json'},
        'Cargo.toml', url, 'main', 'c' * 40), True)

    many = {'refused': [{'verdict': 'SURVIVOR', 'where': f'src/a.rs:{n}', 'mutant': 'x' * 300}
                        for n in range(2000)], 'stale': ['src/b.rs:1'], 'malformed': [], 'error': None}
    big = render(many, 'Cargo.toml', url, 'main', 'd' * 40)
    expect('long body stays under the limit', len(big) <= BODY_LIMIT, True)
    shown = big.count('| SURVIVOR |')
    expect('some rows shown', shown > 0, True)
    expect('omission counted', f'{2000 - shown + 1} more not listed' in big, True)
    expect('resolution kept when cut', 'How to resolve each' in big, True)

    # The flow, against a stand-in for the API that keeps issues and labels in memory.
    class Fake:
        def __init__(self, issues=(), labels=(), refuse=()):
            self.issues = {i['number']: dict(i) for i in issues}
            self.labels = set(labels)
            self.refuse = set(refuse)
            self.calls = []

        def __call__(self, method, path, body=None):
            self.calls.append((method, path.split('?')[0]))
            if method in self.refuse:
                raise ApiError(f'{method} {path}: HTTP 403: Resource not accessible by integration')
            parts = path.split('?')[0].split('/')
            if parts[3] == 'labels':
                if method == 'GET':
                    if parts[4] not in self.labels:
                        raise ApiError('HTTP 404')
                    return {}
                self.labels.add(body['name'])
                return {}
            if method == 'GET':
                page = int(path.rsplit('page=', 1)[1])
                listed = [i for i in sorted(self.issues.values(), key=lambda i: i['number'])
                          if i['state'] == 'open' and LABEL in i.get('labels', [])]
                return listed[(page - 1) * 100:page * 100]
            if len(parts) == 4:
                n = max(self.issues, default=0) + 1
                self.issues[n] = dict(body, number=n, state='open', comments=[])
                return {'number': n}
            n = int(parts[4])
            if len(parts) == 6:
                self.issues[n]['comments'].append(body['body'])
                return {}
            self.issues[n].update(body)
            return {}

    def go(fake, **kw):
        a = dict(verdict='failure', mode='full', manifest_path='Cargo.toml',
                 findings_file=None, repository='o/r', run_url=url, branch='main', sha='e' * 40)
        a.update(kw)
        tmp_findings = Path(tempfile.mkdtemp()) / 'findings.json'
        tmp_findings.write_text(json.dumps(findings))
        argv = ['mutation_issue.py', 'file']
        for k in ('verdict', 'mode', 'manifest_path', 'repository', 'run_url', 'branch', 'sha'):
            argv += [f'--{k.replace("_", "-")}', a[k]]
        argv += ['--findings', str(tmp_findings)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(argv, api=fake)
        return rc, out.getvalue()

    fake = Fake()
    rc, out = go(fake)
    expect('red, none open: opened', (rc, 'opened issue #1' in out), (0, True))
    expect('label created', LABEL in fake.labels, True)
    expect('issue labeled', fake.issues[1]['labels'], [LABEL])
    rc, out = go(fake, sha='f' * 40)
    expect('red again: updated, not a second issue', ('updated issue #1' in out, len(fake.issues)),
           (True, 1))
    expect('red again: one comment', len(fake.issues[1]['comments']), 1)
    expect('red again: body rewritten', 'ffffffffffff' in fake.issues[1]['body'], True)
    rc, out = go(fake, manifest_path='b_crate/Cargo.toml')
    expect('another crate gets its own issue', ('opened issue #2' in out, len(fake.issues)), (True, 2))
    rc, out = go(fake, verdict='success', mode='unchanged')
    expect('nothing tested: left alone', (fake.issues[1]['state'], 'left as it is' in out),
           ('open', True))
    rc, out = go(fake, verdict='success')
    expect('green full run: closed', ('closed issue #1' in out, fake.issues[1]['state']),
           (True, 'closed'))
    expect('green full run: commented', 'is green' in fake.issues[1]['comments'][-1], True)
    expect('the other crate stays open', fake.issues[2]['state'], 'open')
    rc, out = go(fake, verdict='success')
    expect('green, none open: nothing', 'no issue is open' in out, True)
    rc, out = go(fake, verdict='cancelled')
    expect('cancelled: left alone', 'left as it is' in out, True)
    fake.issues[9] = {'number': 9, 'state': 'open', 'labels': [LABEL], 'pull_request': {},
                      'body': marker('Cargo.toml')}
    rc, out = go(fake)
    expect('a pull request is never the issue', 'opened issue #10' in out, True)

    # A token without issues: write: every write refused, a warning, and exit 0 all the same.
    denied = Fake(refuse={'POST', 'PATCH'})
    rc, out = go(denied)
    expect('not granted: exit 0', rc, 0)
    expect('not granted: a warning', '::warning::mutation issue: not filed' in out, True)
    expect('not granted: names the permission', 'issues: write' in out, True)
    unreadable = Fake(refuse={'GET'})
    rc, out = go(unreadable, verdict='success')
    expect('unreadable: exit 0 with a warning', (rc, '::warning::' in out), (0, True))

    def broken(method, path, body=None):
        raise KeyError('number')
    rc, out = go(broken)
    expect('a fault here: exit 0 with a warning', (rc, '::warning::' in out), (0, True))

    print('mutation_issue selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
