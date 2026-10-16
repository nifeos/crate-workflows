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

Exit 0 only when every record holds. Name: provisional, from milestone 887's lane.
"""

import argparse
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


def records(root):
    """[(file, line, fn, state, path, reason)] for every Kani harness under root."""
    out = []
    for f in sorted((root / 'src').rglob('*.rs')):
        lines = f.read_text().splitlines()
        for n, raw in enumerate(lines):
            if ATTR not in raw:
                continue
            name = None
            for later in lines[n + 1:n + 12]:
                m = re.match(r'\s*(?:pub\s+)?(?:unsafe\s+)?(?:async\s+)?fn\s+(\w+)', later)
                if m:
                    name = m.group(1)
                    break
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
    ap.add_argument('--check', action='store_true', help='form only: no Kani run')
    ap.add_argument('--limit', type=int, default=900)
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    root = Path(args.manifest_path).resolve().parent
    recs = records(root)
    if not recs:
        print('falsify: no #[kani::proof] harness under src/; nothing to falsify')
        return 0
    bad = check(root, recs)
    if not args.check:
        bad = replay(root, recs, args.limit) or bad
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
    print('falsify selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
