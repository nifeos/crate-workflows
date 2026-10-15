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
manifest and is skipped.

The second rule nife kept for crates (a semver break against the last release) is not here: it
needs `cargo-semver-checks` run against the crate, which the calling workflow does as its own
step and merges into the same findings list.
"""

import argparse
import re
import subprocess
import sys
import tomllib

TABLES = ('dependencies', 'dev-dependencies', 'build-dependencies', 'workspace.dependencies')


def manifest_deps(text, path):
    """{(name, version-req)} from one manifest's dependency tables, or () when it parses to nothing."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        print(f'architect-label-rules: {path} does not parse: {e}', file=sys.stderr)
        return set()
    out = set()
    for table in TABLES:
        node = data
        for part in table.split('.'):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        if not isinstance(node, dict):
            continue
        for name, spec in node.items():
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
        for name, req in sorted(manifest_deps(head, path) - base):
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
    expect('workspace table', len(manifest_deps('[workspace.dependencies]\nlog = "0.4"\n', 'w')), 1)
    expect('bad toml is empty, not a crash', manifest_deps('not [ toml', 'x'), set())
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
