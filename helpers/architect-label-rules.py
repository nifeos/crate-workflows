#!/usr/bin/env python3
"""The architect rules a crate repository keeps: a dependency new to the crate's graph.

    git diff --unified=1000000 <base> HEAD | python3 architect-label-rules.py --base-rev <base>

Exit 0 means a rule fired and the caller adds `needs-architect`; 1 means nothing fired; 2 usage;
3 crash. The caller routes 2 and 3 to a person. `--ask` reads findings back and prints the
question each one asks, for the finding comment.

This is nife's labeler reduced to the one rule a standalone crate keeps. The dropped rules (the
ABI surface, the spawn protocol, the syscall errors, the decisions tree) watch files only nife
has. `unified=1000000` turns each changed file's hunk into that file's whole content, so the diff
on stdin is enough to say WHICH manifests changed; the graphs themselves are read from the
worktree (head) and from `git show <base>:<path>` (base), because a dependency "new to the graph"
means new against every manifest at the base, not just the ones this diff touches: adding a
dependency to one crate is new even when another crate already had it. `Cargo.lock` is not a
manifest and is skipped. A path dependency on another member of the same workspace is how one
crate of a repository of several uses another, so it is not a dependency new to the graph (the
member is read as a manifest of its own). Any other path, a vendored third-party crate included,
is a dependency like the rest.

Two standing approvals are skipped, and only in a fuzz crate: a manifest at `<dir>/fuzz/Cargo.toml`
whose package has `publish = false` (or `publish = []`) and `[package.metadata] cargo-fuzz = true`.
In its `[dependencies]` table, `libfuzzer-sys` from crates.io with a requirement inside 0.4 (`0.4`,
`0.4.N`, with an optional `^`, `~` or `=`) is approved, and so is a path dependency on `<dir>`
itself, the crate under test, when its name matches the package `<dir>/Cargo.toml` declares. Any
other dependency of a fuzz crate fires, as does `libfuzzer-sys` anywhere else. A dependency on
another crate of the organization outside a fuzz crate still fires: its approval asks for a git pin
on that repository's main branch, which the labeler cannot check from the diff alone.

The second rule (a semver break new against the last release) is not here:
it needs `cargo-semver-checks` run against the crate twice, which helpers/semver-rule.sh does as
the calling workflow's own step, merged into the same findings list.
"""

import argparse
import os
import re
import subprocess
import sys
import tomllib

TABLES = ('dependencies', 'dev-dependencies', 'build-dependencies', 'workspace.dependencies')


def workspace_member_dirs(path):
    """The real directories of the workspace's members, for the manifest at `path`; empty when
    cargo cannot say (no such manifest, no cargo), which exempts nothing."""
    try:
        import crate_info
        return {os.path.dirname(os.path.realpath(m['manifest'])) for m in crate_info.members(path)}
    except (ImportError, RuntimeError, OSError):
        return set()


LIBFUZZER_REQUIREMENT = re.compile(r'[\^~=]?0\.4(\.\d+)?')


def package_name(path):
    """The package name the manifest at `path` declares in the worktree, or None."""
    try:
        with open(path, 'rb') as f:
            name = tomllib.load(f).get('package', {}).get('name')
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        return None
    return name if isinstance(name, str) else None


def unpublished_fuzz_crate(data, path):
    """True when `path` is a cargo-fuzz crate's `fuzz/Cargo.toml` whose package is never published."""
    if os.path.basename(path) != 'Cargo.toml' or os.path.basename(os.path.dirname(path)) != 'fuzz':
        return False
    package = data.get('package')
    if not isinstance(package, dict) or package.get('publish') not in (False, []):
        return False
    metadata = package.get('metadata')
    return isinstance(metadata, dict) and metadata.get('cargo-fuzz') is True


def fuzz_approved(table, name, spec, path, crate_name):
    """True when a standing approval covers this dependency of an unpublished fuzz crate."""
    if table != 'dependencies':
        return False
    if name == 'libfuzzer-sys':
        if isinstance(spec, dict):
            if set(spec) - {'version', 'features', 'default-features'}:
                return False  # git, path, registry or a renamed package: not the approved crate
            spec = spec.get('version')
        return isinstance(spec, str) and LIBFUZZER_REQUIREMENT.fullmatch(spec.strip()) is not None
    if not isinstance(spec, dict) or not isinstance(spec.get('path'), str):
        return False
    if set(spec) - {'path', 'version', 'features', 'default-features', 'package'}:
        return False
    crate_dir = os.path.dirname(os.path.dirname(path))
    target = os.path.join(os.path.dirname(path), spec['path'])
    return (os.path.normpath(target) == os.path.normpath(crate_dir or '.')
            and crate_name is not None and spec.get('package', name) == crate_name)


def manifest_deps(text, path, member_dirs=frozenset(), crate_name=None):
    """{(name, version-req)} from one manifest's dependency tables, or () when it parses to nothing.

    A path dependency that resolves to a directory in `member_dirs` is left out, and so is one a
    standing approval covers in an unpublished fuzz crate, whose crate under test is `crate_name`."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        print(f'architect-label-rules: {path} does not parse: {e}', file=sys.stderr)
        return set()
    fuzz = unpublished_fuzz_crate(data, path)
    out = set()
    for table in TABLES:
        node = data
        for part in table.split('.'):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        if not isinstance(node, dict):
            continue
        for name, spec in node.items():
            if (isinstance(spec, dict) and isinstance(spec.get('path'), str) and 'git' not in spec
                    and os.path.realpath(os.path.join(os.path.dirname(path), spec['path'])) in member_dirs):
                continue
            if fuzz and fuzz_approved(table, name, spec, path, crate_name):
                continue
            req = spec if isinstance(spec, str) else (spec or {}).get('version', '*')
            out.add((name, req))
    return out


def changed_tomls(diff_text):
    """The b/ paths of *.toml files in a full-content diff, excluding Cargo.lock."""
    out = []
    for line in diff_text.splitlines():
        m = re.match(r'^\+\+\+ b/(\S+)$', line)
        if m and m.group(1).endswith('.toml') and not m.group(1).endswith('Cargo.lock'):
            out.append(m.group(1))
    return sorted(set(out))


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def base_manifests(base_rev):
    out = {}
    files = git('ls-tree', '-r', '--name-only', base_rev).splitlines()
    for f in files:
        if f.endswith('Cargo.toml'):
            out[f] = git('show', f'{base_rev}:{f}')
    return out


def run(base_rev, diff_text):
    changed = changed_tomls(diff_text)
    if not changed:
        return []
    base = set()
    for path, text in base_manifests(base_rev).items():
        base |= manifest_deps(text, path)
    found = []
    for path in changed:
        try:
            head = open(path).read()
        except FileNotFoundError:
            continue  # deleted in this diff; a deletion adds nothing to the graph
        crate_name = package_name(os.path.join(os.path.dirname(os.path.dirname(path)), 'Cargo.toml'))
        for name, req in sorted(manifest_deps(head, path, workspace_member_dirs(path), crate_name) - base):
            found.append(f'dependency: {path}: {name} {req}')
    return found


QUESTIONS = {
    'dependency': 'A dependency is a decision, not a convenience. What does this one buy, what '
                  'does it cost the proof story, and is there prior art we should have taken '
                  'instead?',
}


def asks(report):
    out = []
    for line in report.splitlines():
        rule = line.split(':', 1)[0]
        out.append(f'- {QUESTIONS.get(rule, rule)} ({line})')
    return '\n'.join(out)


def selftest():
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    diff = '+++ b/Cargo.toml\n(some whole file)\n+++ b/Cargo.lock\n'
    expect('changed tomls', changed_tomls(diff), ['Cargo.toml'])
    deps = manifest_deps("""
[dependencies]
log = "0.4"
thing = { version = "1.2", features = ["x"] }

[dev-dependencies]
trybuild = "1"
""", 'Cargo.toml')
    expect('three deps, one per table', len(deps), 3)
    sibling = os.path.realpath('sibling')
    text = ('[dependencies]\nsibling = { path = "../sibling", version = "0.1" }\n'
            'vendored = { path = "../vendor/thing", version = "2" }\n')
    expect('a path dependency on a workspace member is not a new dependency',
           manifest_deps(text, 'c/Cargo.toml', {sibling}), {('vendored', '2')})
    expect('with no member known, a path dependency counts',
           manifest_deps(text, 'c/Cargo.toml'), {('sibling', '0.1'), ('vendored', '2')})
    expect('workspace table', len(manifest_deps('[workspace.dependencies]\nlog = "0.4"\n', 'w')), 1)
    expect('bad toml is empty, not a crash', manifest_deps('not [ toml', 'x'), set())

    fuzz_head = ('[package]\nname = "c-fuzz"\nversion = "0.0.0"\npublish = false\n\n'
                 '[package.metadata]\ncargo-fuzz = true\n\n')
    fuzz_deps = ('[dependencies]\nlibfuzzer-sys = "0.4"\n\n'
                 '[dependencies.c]\npath = ".."\n')
    expect('an unpublished fuzz crate: libfuzzer-sys 0.4 and the crate itself are approved',
           manifest_deps(fuzz_head + fuzz_deps, 'fuzz/Cargo.toml', crate_name='c'), set())
    expect('the approvals hold in a fuzz crate below the root',
           manifest_deps(fuzz_head + fuzz_deps, 'crates/c/fuzz/Cargo.toml', crate_name='c'), set())
    for req in ('0.4.7', '^0.4', '~0.4.1', '=0.4.9'):
        expect(f'libfuzzer-sys {req} is inside 0.4', manifest_deps(
            fuzz_head + f'[dependencies]\nlibfuzzer-sys = {{ version = "{req}" }}\n',
            'fuzz/Cargo.toml', crate_name='c'), set())
    for req in ('0.5', '*', '>=0.4', '0.4, <0.4.9', '0.40'):
        expect(f'libfuzzer-sys {req} fires', manifest_deps(
            fuzz_head + f'[dependencies]\nlibfuzzer-sys = "{req}"\n',
            'fuzz/Cargo.toml', crate_name='c'), {('libfuzzer-sys', req)})
    expect('libfuzzer-sys from git fires', manifest_deps(
        fuzz_head + '[dependencies]\nlibfuzzer-sys = { git = "https://example.org/x", version = "0.4" }\n',
        'fuzz/Cargo.toml', crate_name='c'), {('libfuzzer-sys', '0.4')})
    expect('a renamed libfuzzer-sys fires', manifest_deps(
        fuzz_head + '[dependencies]\nlibfuzzer-sys = { package = "other", version = "0.4" }\n',
        'fuzz/Cargo.toml', crate_name='c'), {('libfuzzer-sys', '0.4')})
    expect('libfuzzer-sys as a dev-dependency fires', manifest_deps(
        fuzz_head + '[dev-dependencies]\nlibfuzzer-sys = "0.4"\n',
        'fuzz/Cargo.toml', crate_name='c'), {('libfuzzer-sys', '0.4')})
    expect('any other dependency of a fuzz crate fires', manifest_deps(
        fuzz_head + fuzz_deps.replace('\n\n', '\narbitrary = "1"\n\n'), 'fuzz/Cargo.toml',
        crate_name='c'),
        {('arbitrary', '1')})
    expect('a path dependency to another directory fires', manifest_deps(
        fuzz_head + '[dependencies]\nc = { path = "../vendor/c" }\n',
        'fuzz/Cargo.toml', crate_name='c'), {('c', '*')})
    expect('a path dependency to .. under another name fires', manifest_deps(
        fuzz_head + fuzz_deps, 'fuzz/Cargo.toml', crate_name='d'),
        {('c', '*')})
    expect('a path dependency to .. with no crate known fires', manifest_deps(
        fuzz_head + fuzz_deps, 'fuzz/Cargo.toml'), {('c', '*')})
    expect('a path dependency to .. that also names git fires', manifest_deps(
        fuzz_head + '[dependencies]\nc = { path = "..", git = "https://example.org/c" }\n',
        'fuzz/Cargo.toml', crate_name='c'), {('c', '*')})
    published = fuzz_head.replace('publish = false', 'publish = true')
    expect('a published fuzz crate gets no approval',
           manifest_deps(published + fuzz_deps, 'fuzz/Cargo.toml', crate_name='c'),
           {('libfuzzer-sys', '0.4'), ('c', '*')})
    unset = fuzz_head.replace('publish = false\n', '')
    expect('a fuzz crate that does not set publish gets no approval',
           manifest_deps(unset + fuzz_deps, 'fuzz/Cargo.toml', crate_name='c'),
           {('libfuzzer-sys', '0.4'), ('c', '*')})
    expect('publish = [] is unpublished', manifest_deps(
        fuzz_head.replace('publish = false', 'publish = []') + fuzz_deps,
        'fuzz/Cargo.toml', crate_name='c'), set())
    expect('a fuzz/ crate without cargo-fuzz metadata gets no approval', manifest_deps(
        fuzz_head.replace('cargo-fuzz = true', 'other = true') + fuzz_deps,
        'fuzz/Cargo.toml', crate_name='c'), {('libfuzzer-sys', '0.4'), ('c', '*')})
    expect('libfuzzer-sys in the crate\'s own manifest fires', manifest_deps(
        fuzz_head + fuzz_deps, 'Cargo.toml', crate_name='c'),
        {('libfuzzer-sys', '0.4'), ('c', '*')})
    expect('an unpublished crate outside fuzz/ gets no approval', manifest_deps(
        fuzz_head + fuzz_deps, 'tools/Cargo.toml', crate_name='c'),
        {('libfuzzer-sys', '0.4'), ('c', '*')})
    report = 'dependency: Cargo.toml: log 0.4'
    expect('ask names the rule', asks(report).startswith('- A dependency is a decision'), True)
    print('architect-label-rules selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if '--selftest' in argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--base-rev')
    ap.add_argument('--ask', action='store_true')
    args = ap.parse_args(argv[1:])
    if args.ask:
        print(asks(sys.stdin.read()))
        return 0
    if not args.base_rev:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        found = run(args.base_rev, sys.stdin.read())
    except subprocess.CalledProcessError as e:
        print(f'architect-label-rules: git failed: {e.stderr}', file=sys.stderr)
        return 3
    for f in found:
        print(f)
    return 0 if found else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
