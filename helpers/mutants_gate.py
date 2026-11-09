#!/usr/bin/env python3
"""A mutation survivor fails the run unless the caller exempted it with a reason.

    python3 mutants_gate.py [--diff] <mutants.out-dir> [<exempts-file>]

cargo-mutants writes `outcomes.json` in its `mutants.out` directory. The directory given here is
either one such directory, or a directory whose subdirectories each hold one: the shards of one
run (`cargo mutants --shard k/n`), judged together, since an exemption that names no survivor can
only be called stale once every shard has reported.

A mutant whose tests did not catch it is a survivor: either the tests do not cover the mutation,
or the mutation is genuinely equivalent behavior, and only the second is worth keeping. A mutant
whose tests ran past cargo-mutants' timeout is judged the same way, since a hang is not a catch.
The exempt file carries one mutant per line, matched on its `file:line` prefix, with the reason in
words on the same line after a `#`. One line covers every mutant on that source line. An exempt
line without a reason is refused, and a mutant listed in the file that no longer exists is refused
too, so the list can only shrink by a diff that says why.

`--diff` judges a run over a pull request's changed lines (`cargo mutants --in-diff`). Such a run
generates the mutants of the changed lines only, so an exemption that names no survivor in it is
not stale, only out of reach, and the stale-exemption check is skipped. A survivor or a timeout
that is not exempted fails the same way. The full mutation run, without `--diff`, is the one that
calls an exemption stale.

There is no triage ledger or census here: survive, exempt with a reason, or fail.
"""

import json
import re
import sys
from pathlib import Path


# The outcome summaries that fail the gate unless exempted, and the word the failure prints.
JUDGED = {'MissedMutant': 'SURVIVOR', 'Timeout': 'TIMEOUT'}


def outcome_files(out_dir):
    """The `outcomes.json` of one run, or of every shard under `out_dir`, in a stable order."""
    out_dir = Path(out_dir)
    if (out_dir / 'outcomes.json').is_file():
        return [out_dir / 'outcomes.json']
    return sorted(out_dir.glob('*/outcomes.json'))


def survivors(out_dir):
    """[(file, line, name, verdict)] for every mutant the tests did not catch, over every shard.

    cargo-mutants (27.x) writes `outcomes.json`: one entry per run, `summary` naming the verdict,
    `scenario.Mutant` carrying the mutant's file, span and name. A mutant the tests did not catch
    is summary `MissedMutant`; one whose tests hung is `Timeout`.
    """
    files = outcome_files(out_dir)
    if not files:
        raise FileNotFoundError(f'no outcomes.json in {out_dir} or in any directory under it')
    out = []
    for path in files:
        for entry in json.loads(path.read_text()).get('outcomes', []):
            verdict = JUDGED.get(entry.get('summary'))
            if verdict is None:
                continue
            mutant = (entry.get('scenario') or {}).get('Mutant') or {}
            line = ((mutant.get('span') or {}).get('start') or {}).get('line', '?')
            out.append((mutant.get('file', '?'), line, mutant.get('name', ''), verdict))
    return out


def parse_exempts(text):
    """{(file:line)} and problems. A line is `<file>:<line> <reason>`; a raise needs a reason."""
    lines, problems = {}, []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^(\S+?):\s*(\d+)\s*#\s*(.+)$', line)
        if not m:
            problems.append(f'{n}: want `<file>:<line> # <reason>`, got {line!r}')
            continue
        lines[f'{m.group(1)}:{m.group(2)}'] = m.group(3).strip()
    return lines, problems


def main(argv):
    if '--selftest' in argv[1:]:
        return selftest()
    diff_only = '--diff' in argv[1:]
    args = [a for a in argv[1:] if a != '--diff']
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    out_dir, exempt_path = args[0], (args[1] if len(args) > 1 else None)
    exempts, problems = {}, []
    if exempt_path:
        try:
            exempts, problems = parse_exempts(open(exempt_path).read())
        except FileNotFoundError:
            problems = []
    for p in problems:
        print(f'mutants_gate: {exempt_path}:{p}', file=sys.stderr)
    try:
        live = survivors(out_dir)
    except FileNotFoundError as e:
        print(f'mutants_gate: {e}', file=sys.stderr)
        return 1
    bad = bool(problems)
    used = set()
    for f, line, desc, verdict in live:
        key = f'{f}:{line}'
        if key in exempts:
            print(f'==> mutant exempted: {key}: {desc} ({exempts[key]})')
            used.add(key)
        else:
            print(f'mutants_gate: {verdict} {key}: {desc}', file=sys.stderr)
            bad = True
    for key in ([] if diff_only else sorted(set(exempts) - used)):
        print(f'mutants_gate: {exempt_path}: {key} is exempted but no such survivor exists now',
              file=sys.stderr)
        bad = True
    if not bad:
        print(f'==> mutation: {len(live)} survivor(s), all exempted with reasons'
              if live else '==> mutation: no survivors')
    return 1 if bad else 0


def selftest():
    import tempfile
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    def mutant(file, line, name, summary):
        return {'scenario': {'Mutant': {'name': name, 'file': file,
                                        'span': {'start': {'line': line, 'column': 5}}}},
                'summary': summary}

    def run(argv):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(argv)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'mutants.out'
        out.mkdir()
        (out / 'outcomes.json').write_text(json.dumps({'outcomes': [
            {'scenario': 'Baseline', 'summary': 'Success'},
            mutant('src/lib.rs', 4, 'src/lib.rs:4:5: replace x with 0', 'CaughtMutant'),
            mutant('src/lib.rs', 9, 'src/lib.rs:9:12: replace > with >=', 'MissedMutant'),
        ]}))
        expect('one survivor', survivors(out),
               [('src/lib.rs', 9, 'src/lib.rs:9:12: replace > with >=', 'SURVIVOR')])
        lines, problems = parse_exempts('# c\n\nsrc/lib.rs:9 # equivalent arithmetic\nbad line\n')
        expect('exempt parsed', list(lines), ['src/lib.rs:9'])
        expect('bad line refused', len(problems), 1)

        # Shards: one directory per shard, judged as one run. A survivor in two shards, a timeout,
        # and two survivors on one line, in different shards, that one exempt line covers.
        shards = Path(tmp) / 'shards'
        for k, outcomes in enumerate([
            [mutant('src/a.rs', 3, 'src/a.rs:3:5: replace + with -', 'MissedMutant'),
             mutant('src/a.rs', 7, 'src/a.rs:7:9: replace | with ^', 'MissedMutant')],
            [mutant('src/a.rs', 7, 'src/a.rs:7:2: replace | with ^', 'MissedMutant'),
             mutant('src/b.rs', 5, 'src/b.rs:5:1: replace += with *=', 'Timeout')],
            [mutant('src/b.rs', 8, 'src/b.rs:8:1: replace f with ()', 'CaughtMutant')],
        ]):
            (shards / f'mutants-shard-{k}').mkdir(parents=True)
            (shards / f'mutants-shard-{k}' / 'outcomes.json').write_text(
                json.dumps({'outcomes': [{'scenario': 'Baseline', 'summary': 'Success'}] + outcomes}))
        expect('shards merged', sorted((f, l, v) for f, l, _, v in survivors(shards)),
               [('src/a.rs', 3, 'SURVIVOR'), ('src/a.rs', 7, 'SURVIVOR'),
                ('src/a.rs', 7, 'SURVIVOR'), ('src/b.rs', 5, 'TIMEOUT')])
        exempt = Path(tmp) / 'exempts'
        every = 'src/a.rs:3 # equivalent\nsrc/a.rs:7 # equivalent\nsrc/b.rs:5 # loops forever\n'
        exempt.write_text(every)
        expect('every shard exempted passes', run(['gate', str(shards), str(exempt)]), 0)
        exempt.write_text('src/a.rs:3 # equivalent\nsrc/a.rs:7 # equivalent\n')
        expect('an unexempted timeout fails', run(['gate', str(shards), str(exempt)]), 1)
        exempt.write_text('src/a.rs:7 # equivalent\nsrc/b.rs:5 # loops forever\n')
        expect('an unexempted survivor in one shard fails', run(['gate', str(shards), str(exempt)]), 1)
        exempt.write_text(every + 'src/c.rs:1 # gone\n')
        expect('a stale exemption fails across shards', run(['gate', str(shards), str(exempt)]), 1)
        expect('no outcomes fails', run(['gate', str(Path(tmp) / 'nothing')]), 1)

        # --diff: a changed-lines run reaches only some mutants, so an exemption it does not reach
        # is not stale there; an unexempted survivor or timeout still fails, and a bad line is
        # still refused.
        exempt.write_text(every + 'src/c.rs:1 # out of this diff\'s reach\n')
        expect('--diff skips the stale check', run(['gate', '--diff', str(shards), str(exempt)]), 0)
        expect('--diff in any position', run(['gate', str(shards), str(exempt), '--diff']), 0)
        exempt.write_text('src/a.rs:3 # equivalent\nsrc/a.rs:7 # equivalent\n')
        expect('--diff still fails a timeout', run(['gate', '--diff', str(shards), str(exempt)]), 1)
        exempt.write_text(every + 'no reason here\n')
        expect('--diff still refuses a bad line', run(['gate', '--diff', str(shards), str(exempt)]), 1)
        expect('--diff with no outcomes fails', run(['gate', '--diff', str(Path(tmp) / 'nothing')]), 1)

    # fixtures/mutation/pass and fail: two shards each, the one survivor in pass exempted, and a
    # second, unexempted survivor in fail's other shard.
    fixtures = Path(__file__).resolve().parent.parent / 'fixtures' / 'mutation'
    for case, want in (('pass', 0), ('fail', 1)):
        expect('fixture %s' % case,
               run(['gate', str(fixtures / case), str(fixtures / case / 'mutants-exempts')]), want)
    print('mutants_gate selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
