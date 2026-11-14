#!/usr/bin/env python3
"""Name the semver baseline: the newest release tag before the commit being checked.

    python3 helpers/semver_baseline.py [--ref REV] [--repo DIR] [--tag-prefix P]   # prints a tag, exit 0
    python3 helpers/semver_baseline.py --selftest

The baseline is a revision, so a crate that has never reached crates.io still has one. The rule:
among the tags named `<prefix><major>.<minor>.<patch>` that are ancestors of REV (default HEAD), leave out
a tag that points at REV itself, and take the highest by version. Exit 1 and print nothing when no
tag qualifies; the caller then falls back to the last published version, which is what
`cargo semver-checks` picks by default. Pre-release tags (`v1.0.0-rc.1`) are not baselines.

The prefix is `v` in a repository of one crate. In a repository of several it is `<crate>-v`
(`helpers/crate_info.py tag-prefix` says which), so one crate's baseline is never another crate's
release: `filesystem_contract-v0.2.0` is a baseline for `filesystem_contract` and for nothing else.

A release is dispatched from the commit that will carry its tag, so the tag does not exist yet on
the release commit and the previous tag is the newest one. Checked again on the tagged commit, the
tag at REV is skipped and the one before it is the baseline.
"""

import re
import subprocess
import sys

DEFAULT_PREFIX = 'v'


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, check=False)


def baseline(tags_at_rev, ancestor_tags, prefix=DEFAULT_PREFIX):
    """The highest qualifying tag, or None. The tag arguments are lists of tag names."""
    best = None
    pattern = re.compile('^' + re.escape(prefix) + r'(\d+)\.(\d+)\.(\d+)$')
    for tag in ancestor_tags:
        m = pattern.match(tag)
        if not m or tag in tags_at_rev:
            continue
        key = tuple(int(x) for x in m.groups())
        if best is None or key > best[0]:
            best = (key, tag)
    return best[1] if best else None


def from_repo(repo, ref, prefix=DEFAULT_PREFIX):
    at = git(repo, 'tag', '--points-at', ref)
    ancestors = git(repo, 'tag', '--merged', ref)
    if at.returncode or ancestors.returncode:
        raise RuntimeError((at.stderr or ancestors.stderr).strip() or 'git failed')
    return baseline(at.stdout.split(), ancestors.stdout.split(), prefix)


def selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: expected {want}, got {got}')
    check('no tags', baseline([], []), None)
    check('one tag', baseline([], ['v0.1.0']), 'v0.1.0')
    check('the tag at the commit is skipped', baseline(['v0.1.1'], ['v0.1.0', 'v0.1.1']), 'v0.1.0')
    check('only the tag at the commit', baseline(['v0.1.0'], ['v0.1.0']), None)
    check('numeric, not lexical, order', baseline([], ['v0.9.0', 'v0.10.0']), 'v0.10.0')
    check('pre-releases and strangers are not baselines',
          baseline([], ['v1.0.0-rc.1', 'nightly', 'v0.2.0']), 'v0.2.0')
    several = ['a-v0.1.0', 'a-v0.2.0', 'b-v0.9.0', 'v0.3.0', 'xa-v0.8.0']
    check('a crate-named prefix takes only its own tags', baseline([], several, 'a-v'), 'a-v0.2.0')
    check('another crate has its own baseline', baseline([], several, 'b-v'), 'b-v0.9.0')
    check('the plain prefix ignores crate-named tags', baseline([], several), 'v0.3.0')
    check('a crate with no release has no baseline', baseline([], several, 'c-v'), None)
    check('a prefix is literal, not a pattern', baseline([], ['a.v0.1.0'], 'a.v'), 'a.v0.1.0')
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        def run(*a):
            subprocess.run(['git', '-C', d, '-c', 'user.name=t', '-c', 'user.email=t@t',
                            '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *a],
                           check=True, capture_output=True)
        run('init', '-q')
        for tag in ('v0.1.0', 'v0.1.1'):
            open(os.path.join(d, 'f'), 'w').write(tag)
            run('add', 'f')
            run('commit', '-q', '-m', tag)
            run('tag', tag)
        check('repo at the second tag', from_repo(d, 'HEAD'), 'v0.1.0')
        check('repo at the first tag', from_repo(d, 'HEAD~1'), None)
        run('commit', '-q', '--allow-empty', '-m', 'work')
        check('repo past the second tag', from_repo(d, 'HEAD'), 'v0.1.1')
    print('semver_baseline selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ['--selftest']:
        return selftest()
    ref, repo, prefix = 'HEAD', '.', DEFAULT_PREFIX
    args = argv[1:]
    while args:
        flag = args.pop(0)
        if flag in ('--ref', '--repo', '--tag-prefix') and args:
            if flag == '--ref':
                ref = args.pop(0)
            elif flag == '--repo':
                repo = args.pop(0)
            else:
                prefix = args.pop(0)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    try:
        tag = from_repo(repo, ref, prefix)
    except RuntimeError as e:
        print(f'semver_baseline: {e}', file=sys.stderr)
        return 2
    if tag is None:
        return 1
    print(tag)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
