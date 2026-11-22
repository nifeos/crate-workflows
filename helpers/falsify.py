#!/usr/bin/env python3
"""The falsification gate: every proof harness carries a patch or a reason, and each patch turns
its harness red at its own assertion.

    python3 falsify.py [--manifest-path Cargo.toml] [--check] [--limit 900] [--jobs N]

This is nife's falsification sweep reduced to what a standalone crate carries. Kani harnesses
only: a crate has no kernel tests or swish checks, and a host-test harness cites its patch the way
its nife original does when one exists.

A record is the comment run immediately above `#[kani::proof]`. Its first line is

    /// Falsification: replayable `falsifications/<module.path>.<harness>.patch`

or

    /// Falsification: unfalsifiable, followed by at least a 200-character reason.

`--check` is form only: every harness carries a record, the named patch exists, contains a
unified diff, applies with `git apply --check -p1`, and an `unfalsifiable` reason is long enough
to be a reason. This is the half nife runs in its lint, and the half that never needs Kani.

Without `--check` the patches replay: each is applied, its harness runs alone, and the run must
FAIL. The verdict comes from Kani's own summary line, `N successfully verified harnesses, M
failures, T total`: the patch did its work only when exactly one harness ran and it failed. A
harness that still passes with its patch applied is a survivor, and survivors fail this gate; a
run whose summary cannot be parsed is an error, which is neither red nor a survivor and also
fails. A patch that no longer applies is a failure, never a skip: a stale patch is a record that
lies.

`--loom` reads loom models instead, for the loom job. A loom model is a `#[test]` whose body names
`loom::model`. Its record is opt-in: a model with no `Falsification:` line above it (attributes
such as `#[should_panic]` may sit between) is not counted, and a crate whose models carry none has
nothing to falsify. A record has the same form and the same `--check`. The replay applies the
patch, runs that one model with `RUSTFLAGS="--cfg loom -D warnings" cargo test --release --lib
<module path>::<model> -- --exact`, and reads cargo's summary: the patch did its work only when
exactly one test ran and it failed (`running 1 test`, `test result: FAILED. 0 passed; 1 failed`).
A model that still passes is a survivor, and a run that selects no test or several is an error.

Exit 0 only when every record holds. Name: provisional, from milestone 887's lane; `--loom` is
provisional too.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

STATES = ('replayable', 'unfalsifiable')
REASON_MIN = 200
VERDICT = re.compile(r'(\d+) successfully verified harnesses, (\d+) failures, (\d+) total')
ATTR = '#[kani::proof]'
CONVENTIONAL = re.compile(r'^falsifications/[\w.]+\.patch$')


def git_apply(root, patch_rel, mode):
    """git apply a crate-relative patch.

    `git apply` run inside a subdirectory SILENTLY IGNORES patches whose paths resolve outside
    that subdirectory (exit 0, "0 files changed"), so a patch for `src/lib.rs` applied from a
    crate that is not the repository root would do nothing and call it success. The apply goes
    through the repository root with `--directory=<crate prefix>` instead, which is also why the
    form check's `--check` cannot lie the same way.
    """
    prefix = subprocess.run(['git', 'rev-parse', '--show-prefix'], cwd=root,
                            capture_output=True, text=True).stdout.strip()
    args = ['git']
    if prefix:
        args += ['-C', subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=root,
                                      capture_output=True, text=True).stdout.strip()]
        args += ['apply', f'--directory={prefix.rstrip("/")}']
    else:
        args += ['apply']
    args += ([mode] if mode else []) + ['-p1', str(patch_rel) if not prefix else str(Path(root) / patch_rel)]
    return subprocess.run(args, capture_output=True, text=True)


def blank_non_code(text):
    """text with comments, string literals and char literals blanked to spaces, newlines kept, so
    offsets and line numbers still match and a brace or `mod` inside them is never read."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != '\n':
                out[k] = ' '

    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif text.startswith('/*', i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith('/*', j):
                    depth, j = depth + 1, j + 2
                elif text.startswith('*/', j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(i, j)
            i = j
        elif c == 'r' and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_')) \
                and re.match(r'r#*"', text[i:i + 40]):
            hashes = len(re.match(r'r(#*)"', text[i:i + 40]).group(1))
            end = text.find('"' + '#' * hashes, i + 2 + hashes)
            j = n if end < 0 else end + 1 + hashes
            blank(i, j)
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            blank(i, j + 1)
            i = j + 1
        elif c == "'":
            m = re.match(r"'(?:\\[^']*|[^\\'])'", text[i:i + 12])
            if m:
                blank(i, i + m.end())
                i += m.end()
            else:
                i += 1  # a lifetime
        else:
            i += 1
    return ''.join(out)


MOD_OPEN = re.compile(r'(?:^|[^\w])mod\s+(\w+)\s*$')


def inline_modules(text):
    """[(line index, [enclosing inline module names])] for every line of text, outermost first.

    A `mod name {` pushes its name; any other `{` pushes nothing but is still matched by its `}`;
    `mod name;` never opens a block and so is never pushed. The names in force at the start of
    each line are what the harness on it sits inside.
    """
    code = blank_non_code(text)
    stack, per_line, line = [], [], 0
    per_line.append(list(n for n in stack if n))
    for i, c in enumerate(code):
        if c == '{':
            m = MOD_OPEN.search(code[max(0, i - 200):i])
            stack.append(m.group(1) if m else None)
        elif c == '}':
            if stack:
                stack.pop()
        elif c == '\n':
            per_line.append([n for n in stack if n])
    return per_line


def records(root):
    """[(file, line, fn, state, path, reason)] for every Kani harness under root.

    fn is the harness name inside its file: the enclosing inline modules, then the function
    (`verification::h`). The file's own module path is added in front when Kani is asked for it.
    """
    out = []
    for f in sorted((root / 'src').rglob('*.rs')):
        source = f.read_text()
        lines = source.splitlines()
        nested = inline_modules(source)
        for n, raw in enumerate(lines):
            if ATTR not in raw:
                continue
            name = None
            for later in lines[n + 1:n + 12]:
                m = re.match(r'\s*(?:pub\s+)?(?:unsafe\s+)?(?:async\s+)?fn\s+(\w+)', later)
                if m:
                    name = m.group(1)
                    break
            if name is not None and n < len(nested) and nested[n]:
                name = '::'.join(nested[n] + [name])
            if name is None:
                out.append((f, n + 1, None, '', '', 'no fn follows the harness attribute'))
                continue
            comment, start = [], n
            while start > 0 and lines[start - 1].lstrip().startswith('///'):
                comment.insert(0, lines[start - 1].lstrip()[3:].strip())
                start -= 1
            text = ' '.join(comment)
            m = re.match(r'Falsification:\s*(\w+)[,: ]*(.*)', text)
            if not m:
                out.append((f, n + 1, name, '', '',
                            'the comment above the harness carries no "Falsification:" record'))
                continue
            state, rest = m.group(1), m.group(2)
            if state not in STATES:
                out.append((f, n + 1, name, state, '',
                            f'unknown state {state!r}; want replayable or unfalsifiable'))
                continue
            path = ''
            pm = re.search(r'`([^`]+\.patch)`', rest)
            if pm:
                path = pm.group(1)
            out.append((f, n + 1, name, state, path, rest))
    return out


TEST_ATTR = re.compile(r'^\s*#\[test\]\s*$')
LOOM_MODEL = re.compile(r'(?:^|[^\w])loom::model(?:[^\w]|$)')


def body_of(code, start):
    """The text of the first `{ ... }` block at or after offset start in blanked code, braces
    matched, or '' when none opens."""
    i = code.find('{', start)
    if i < 0:
        return ''
    depth = 0
    for j in range(i, len(code)):
        if code[j] == '{':
            depth += 1
        elif code[j] == '}':
            depth -= 1
            if depth == 0:
                return code[i:j + 1]
    return code[i:]


def loom_records(root):
    """[(file, line, fn, state, path, reason)] for every loom model under root that carries a
    `Falsification:` record. A loom model is a `#[test]` whose body names `loom::model`; a model
    without a record is skipped, since loom records are opt-in."""
    out = []
    for f in sorted((root / 'src').rglob('*.rs')):
        source = f.read_text()
        lines = source.splitlines()
        code = blank_non_code(source)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line) + 1)
        nested = inline_modules(source)
        for n, raw in enumerate(lines):
            if not TEST_ATTR.match(raw):
                continue
            name, at = None, None
            for k, later in enumerate(lines[n + 1:n + 12], n + 1):
                m = re.match(r'\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', later)
                if m:
                    name, at = m.group(1), k
                    break
            if name is None or not LOOM_MODEL.search(body_of(code, offsets[at])):
                continue
            if n < len(nested) and nested[n]:
                name = '::'.join(nested[n] + [name])
            start = n
            while start > 0 and lines[start - 1].lstrip().startswith('#['):
                start -= 1
            comment = []
            while start > 0 and lines[start - 1].lstrip().startswith('///'):
                comment.insert(0, lines[start - 1].lstrip()[3:].strip())
                start -= 1
            record = next((i for i, c in enumerate(comment) if c.startswith('Falsification:')), None)
            if record is None:
                continue
            m = re.match(r'Falsification:\s*(\w+)[,: ]*(.*)', ' '.join(comment[record:]))
            state, rest = m.group(1), m.group(2)
            if state not in STATES:
                out.append((f, n + 1, name, state, '',
                            f'unknown state {state!r}; want replayable or unfalsifiable'))
                continue
            pm = re.search(r'`([^`]+\.patch)`', rest)
            out.append((f, n + 1, name, state, pm.group(1) if pm else '', rest))
    return out


def loom_verdict(out):
    """('red' | 'survivor' | 'error', detail) from one model's `cargo test` output."""
    ran = [int(k) for k in re.findall(r'^running (\d+) tests?$', out, re.M)]
    if not ran:
        return 'error', 'the test binary never ran; the patch may not compile'
    if sum(ran) != 1:
        return 'error', f'the filter selected {sum(ran)} tests, not 1'
    if re.search(r'test result: ok\. 1 passed', out):
        return 'survivor', 'the model passed with the patch applied'
    if re.search(r'test result: FAILED\. 0 passed; 1 failed', out):
        return 'red', 'the model failed'
    return 'error', 'no test result line could be read'


def replay_loom(root, recs, limit):
    bad = False
    env = dict(os.environ, RUSTFLAGS='--cfg loom -D warnings')
    for f, line, name, state, path, _rest in recs:
        if state != 'replayable' or not path:
            continue
        qualified = module_prefix(f, root) + name
        apply_in = git_apply(root, Path(path), '')
        if apply_in.returncode != 0:
            print(f'falsify: {f.relative_to(root)}:{line}: patch {path} would not apply: '
                  f'{apply_in.stderr.strip()}', file=sys.stderr)
            bad = True
            continue
        try:
            r = subprocess.run(['cargo', 'test', '--release', '--lib', qualified, '--', '--exact'],
                               cwd=root, capture_output=True, text=True, timeout=limit, env=env)
            verdict, detail = loom_verdict(r.stdout + r.stderr)
            if verdict == 'red':
                print(f'==> falsify: {qualified}: red under loom (patch {path})')
            elif verdict == 'survivor':
                print(f'falsify: {qualified}: SURVIVOR: {detail} ({path})', file=sys.stderr)
                bad = True
            else:
                print(f'falsify: {qualified}: {detail} (exit {r.returncode})', file=sys.stderr)
                bad = True
        except subprocess.TimeoutExpired:
            print(f'falsify: {qualified}: exceeded {limit}s; raise --limit only with a reason',
                  file=sys.stderr)
            bad = True
        finally:
            git_apply(root, Path(path), '-R')
    return bad


def module_path(f, root):
    """The crate-relative module path of a file, for the conventional patch name."""
    rel = f.relative_to(root / 'src').with_suffix('')
    parts = list(rel.parts)
    if parts and parts[-1] == 'mod':
        parts = parts[:-1]
    if parts[:1] == ['lib'] or parts[:1] == ['main']:
        parts = parts[1:]
    return parts


def check(root, recs):
    bad = False
    for f, line, name, state, path, rest in recs:
        where = f'{f.relative_to(root)}:{line}'
        if name is None:
            print(f'falsify: {where}: {rest}', file=sys.stderr)
            bad = True
            continue
        if state == 'unfalsifiable':
            if len(rest) < REASON_MIN:
                print(f'falsify: {where}: an unfalsifiable reason is {len(rest)} characters; '
                      f'want at least {REASON_MIN}, so it argues rather than asserts', file=sys.stderr)
                bad = True
            continue
        if not path:
            print(f'falsify: {where}: replayable with no patch path', file=sys.stderr)
            bad = True
            continue
        if not CONVENTIONAL.match(path):
            print(f'falsify: {where}: {path} is not falsifications/<module.path>.<harness>.patch',
                  file=sys.stderr)
            bad = True
        p = root / path
        if not p.is_file():
            print(f'falsify: {where}: patch {path} does not exist', file=sys.stderr)
            bad = True
            continue
        text = p.read_text()
        if 'diff --git' not in text:
            print(f'falsify: {where}: {path} carries no unified diff', file=sys.stderr)
            bad = True
            continue
        if not text.startswith(('diff --git', '///', '/*', '#')) and not re.match(r'^\s*///', text):
            pass  # prose above the first hunk is checked by applying, not by guessing formats
        r = git_apply(root, Path(path), '--check')
        if r.returncode != 0:
            print(f'falsify: {where}: patch {path} no longer applies: {r.stderr.strip()}',
                  file=sys.stderr)
            bad = True
    return bad


def module_prefix(f, root):
    parts = module_path(f, root)
    return '::'.join(parts) + '::' if parts else ''


def replay(root, recs, limit):
    bad = False
    for f, line, name, state, path, _rest in recs:
        if state != 'replayable' or not path:
            continue
        apply_in = git_apply(root, Path(path), '')
        if apply_in.returncode != 0:
            print(f'falsify: {f.relative_to(root)}:{line}: patch {path} would not apply: '
                  f'{apply_in.stderr.strip()}', file=sys.stderr)
            bad = True
            continue
        try:
            qualified = module_prefix(f, root) + name
            r = subprocess.run(['cargo', 'kani', '--harness', qualified, '--exact'],
                               cwd=root, capture_output=True, text=True, timeout=limit)
            out = r.stdout + r.stderr
            m = VERDICT.search(out)
            if m is None:
                print(f'falsify: {qualified}: no Kani verdict line; the run errored', file=sys.stderr)
                bad = True
            else:
                verified, failures, total = (int(g) for g in m.groups())
                if total == 1 and failures == 1:
                    print(f'==> falsify: {qualified}: red at its own assertion (patch {path})')
                elif total == 1 and failures == 0:
                    print(f'falsify: {qualified}: SURVIVOR: the harness passed with {path} applied',
                          file=sys.stderr)
                    bad = True
                else:
                    print(f'falsify: {qualified}: ran {total} harnesses ({failures} failures); '
                          f'the patch must turn exactly one red', file=sys.stderr)
                    bad = True
        except subprocess.TimeoutExpired:
            print(f'falsify: {qualified}: exceeded {limit}s; raise --limit only with a reason',
                  file=sys.stderr)
            bad = True
        finally:
            git_apply(root, Path(path), '-R')
    return bad


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest-path', default='Cargo.toml')
    ap.add_argument('--check', action='store_true', help='form only: no Kani or loom run')
    ap.add_argument('--loom', action='store_true',
                    help='the loom models\' records, replayed under --cfg loom, not the Kani harnesses')
    ap.add_argument('--limit', type=int, default=900)
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    root = Path(args.manifest_path).resolve().parent
    recs = loom_records(root) if args.loom else records(root)
    if not recs:
        if args.loom:
            print('falsify: no loom model under src/ carries a Falsification: record; nothing to falsify')
        else:
            print('falsify: no #[kani::proof] harness under src/; nothing to falsify')
        return 0
    bad = check(root, recs)
    if not args.check:
        bad = (replay_loom if args.loom else replay)(root, recs, args.limit) or bad
    if bad:
        print('falsify: a record does not hold; see the findings above', file=sys.stderr)
        return 1
    print(f'==> falsify: {len(recs)} harness record(s) hold')
    return 0


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
        (root / 'src').mkdir()
        harness = """//! Module docs.

/// Falsification: replayable `falsifications/src.lib.check_add.patch`
#[kani::proof]
fn check_add() {
    let x: u8 = kani::any();
    assert!(x.wrapping_add(1) >= x);
}
"""
        (root / 'src' / 'lib.rs').write_text(harness)
        recs = records(root)
        expect('one record', len(recs), 1)
        expect('state', recs[0][3], 'replayable')
        expect('path', recs[0][4], 'falsifications/src.lib.check_add.patch')
        expect('module path', module_path(recs[0][0], root), [])
        expect('conventional matches', bool(CONVENTIONAL.match(recs[0][4])), True)

        (root / 'src' / 'lib.rs').write_text(
            '/// A comment with no record.\n#[kani::proof]\nfn h() {}\n')
        recs = records(root)
        expect('missing record found', 'no "Falsification:" record' in recs[0][5], True)

        (root / 'src' / 'lib.rs').write_text(
            '/// Falsification: unfalsifiable, because ' + 'x' * 250 + '\n#[kani::proof]\nfn h() {}\n')
        recs = records(root)
        expect('unfalsifiable parsed', recs[0][3], 'unfalsifiable')
        expect('reason long enough', check(root, recs), False)

        (root / 'src' / 'lib.rs').write_text(
            '/// Falsification: unfalsifiable, too short\n#[kani::proof]\nfn h() {}\n')
        recs = records(root)
        expect('short reason refused', check(root, recs), True)

        def qualified(rel, text):
            path = root / 'src' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            rec = [r for r in records(root) if r[0] == path]
            return [module_prefix(r[0], root) + r[2] for r in rec]

        for stale in (root / 'src').rglob('*.rs'):
            stale.unlink()
        proof = '#[kani::proof]\nfn h() {}\n'
        expect('root harness unchanged', qualified('lib.rs', proof), ['h'])
        expect('inline module',
               qualified('lib.rs', '#[cfg(kani)]\nmod verification {\n' + proof + '}\n'),
               ['verification::h'])
        expect('nested inline modules',
               qualified('lib.rs', 'mod a {\n    pub mod b {\n' + proof + '    }\n}\n'),
               ['a::b::h'])
        expect('file module plus inline',
               qualified('a/b.rs', 'mod verification {\n' + proof + '}\n'),
               ['a::b::verification::h'])
        expect('mod.rs file plus inline',
               qualified('a/mod.rs', 'mod verification {\n' + proof + '}\n'),
               ['a::verification::h'])
        expect('closed module and declaration not read',
               qualified('lib.rs', 'mod x;\nmod done {\n    fn f() { if true { } }\n}\n' + proof),
               ['h'])
        expect('mod in comment and string not read',
               qualified('lib.rs', '// mod fake {\nconst S: &str = "mod fake2 { {";\n'
                         "const C: char = '{';\n/* mod fake3 { */\n" + proof),
               ['h'])
        expect('sibling after inline module',
               qualified('lib.rs', 'mod v {\n' + proof + '}\n' + proof.replace('h', 'g')),
               ['v::h', 'g'])
        for stale in (root / 'src').rglob('*.rs'):
            stale.unlink()
        (root / 'src' / 'lib.rs').write_text(
            '#[cfg(test)]\n#[cfg(loom)]\nmod interleavings {\n'
            '    /// **A property.**\n'
            '    ///\n'
            '    /// Falsification: replayable `falsifications/interleavings.m.patch`\n'
            '    #[test]\n    fn m() {\n        loom::model(|| {});\n    }\n\n'
            '    /// Falsification: replayable `falsifications/interleavings.p.patch`\n'
            '    #[test]\n    #[should_panic]\n    fn p() {\n        loom::model::Builder::new().check(|| {});\n    }\n\n'
            '    /// No record: not counted.\n'
            '    #[test]\n    fn q() {\n        loom::model(|| {});\n    }\n\n'
            '    /// Falsification: replayable `falsifications/interleavings.h.patch`\n'
            '    #[test]\n    fn h() {\n        let s = "loom::model";\n    }\n}\n')
        loom = loom_records(root)
        expect('loom records', [r[2] for r in loom], ['interleavings::m', 'interleavings::p'])
        expect('loom patch path', loom[0][4], 'falsifications/interleavings.m.patch')
        expect('loom ignores Kani', records(root), [])
        expect('loom red', loom_verdict('running 1 test\ntest result: FAILED. 0 passed; 1 failed;')[0], 'red')
        expect('loom survivor', loom_verdict('running 1 test\ntest result: ok. 1 passed;')[0], 'survivor')
        expect('loom none selected', loom_verdict('running 0 tests\ntest result: ok. 0 passed;')[0], 'error')
        expect('loom never ran', loom_verdict('error[E0308]: mismatched types')[0], 'error')
    print('falsify selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
