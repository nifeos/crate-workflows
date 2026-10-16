#!/usr/bin/env python3
"""A mutation survivor fails the run unless the caller exempted it with a reason.

    python3 mutants_gate.py <mutants.out-dir> [<exempts-file>]

cargo-mutants writes `out.json` in the directory it was given. A mutant whose tests did not catch
it is a survivor: either the tests do not cover the mutation, or the mutation is genuinely
equivalent behavior, and only the second is worth keeping. The exempt file carries one mutant per
line, matched on its `file:line` prefix, with the reason in words on the same line after a `#`.
An exempt line without a reason is refused, and a mutant listed in the file that no longer exists
is refused too, so the list can only shrink by a diff that says why.

nife's mutation gate reports into a weekly census with triage labels; a standalone crate cannot
afford that machinery, so this is the one-line version: survive, exempt with a reason, or fail.
"""

import json
import re
import sys
from pathlib import Path


def survivors(out_dir):
    """[(file, line, description)] for every mutant the tests did not catch."""
    path = Path(out_dir) / 'out.json'
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get('results', [])
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        missed = _missed(entry)
        if missed:
            out.append((entry.get('file', '?'), entry.get('line', '?'),
                        entry.get('description', '')))
    return out


def _missed(entry):
    summary = entry.get('summary') or {}
    if isinstance(summary, dict) and summary.get('Missed'):
        return True
    results = entry.get('results')
    if isinstance(results, dict):
        return any(isinstance(r, dict) and r.get('class') == 'Missed' for r in results.values())
    if isinstance(results, list):
        return any(isinstance(r, dict) and r.get('class') == 'Missed' for r in results)
    return False


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
    if not argv[1:]:
        print(__doc__, file=sys.stderr)
        return 2
    out_dir, exempt_path = argv[1], (argv[2] if len(argv) > 2 else None)
    exempts, problems = {}, []
    if exempt_path:
        try:
            exempts, problems = parse_exempts(open(exempt_path).read())
        except FileNotFoundError:
            problems = []
    for p in problems:
        print(f'mutants_gate: {exempt_path}:{p}', file=sys.stderr)
    live = survivors(out_dir)
    bad = bool(problems)
    for f, line, desc in live:
        key = f'{f}:{line}'
        if key in exempts:
            print(f'==> mutant exempted: {key}: {desc} ({exempts[key]})')
            del exempts[key]
        else:
            print(f'mutants_gate: SURVIVOR {key}: {desc}', file=sys.stderr)
            bad = True
    for key in sorted(exempts):
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

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'mutants.out'
        out.mkdir()
        (out / 'out.json').write_text(json.dumps([
            {'file': 'src/lib.rs', 'line': 4, 'description': 'replace + with -',
             'summary': {'Caught': 2, 'Missed': 1}},
            {'file': 'src/lib.rs', 'line': 9, 'description': 'replace == with !=',
             'results': {'t': {'class': 'Caught'}}},
        ]))
        expect('one survivor', survivors(out), [('src/lib.rs', 4, 'replace + with -')])
        lines, problems = parse_exempts('# c\n\nsrc/lib.rs:4 # equivalent arithmetic\nbad line\n')
        expect('exempt parsed', list(lines), ['src/lib.rs:4'])
        expect('bad line refused', len(problems), 1)
    print('mutants_gate selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
