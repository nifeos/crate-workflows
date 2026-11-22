#!/usr/bin/env python3
"""Name the semver baseline: the newest release tag before the commit being checked.

    python3 helpers/semver_baseline.py [--ref REV] [--repo DIR] [--tag-prefix P]   # prints a tag, exit 0
    python3 helpers/semver_baseline.py --selftest

The baseline is a revision, so a crate that has never reached crates.io still has one. The rule:
among the tags named `<prefix><major>.<minor>.<patch>`, with or without a pre-release suffix
(`v0.1.0-pre.2`), that are ancestors of REV (default HEAD), leave out a tag that points at REV
itself, and take the highest by semver precedence. Exit 1 and print nothing when no tag qualifies;
the caller then falls back to the last published version, which is what `cargo semver-checks` picks
by default.

A pre-release tag is a baseline because a crate held from crates.io carries only pre-release tags,
and the semver rule exists to hold a break against them. Precedence follows the semver
specification: `v0.1.0-pre.2` sorts below `v0.1.0`, numeric identifiers compare as numbers
(`pre.10` above `pre.9`), and a numeric identifier sorts below an alphanumeric one. Build metadata
(`+...`) is not part of a baseline tag.

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


NUMBER = r'(0|[1-9]\d*)'
IDENTIFIER = r'(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)'


def precedence(core, pre):
    """A sort key for semver precedence: a release sorts above each of its pre-releases."""
    if pre is None:
        return (core, 1, ())
    identifiers = tuple((0, int(x), '') if x.isdigit() else (1, 0, x) for x in pre.split('.'))
    return (core, 0, identifiers)


def baseline(tags_at_rev, ancestor_tags, prefix=DEFAULT_PREFIX):
    """The highest qualifying tag, or None. The tag arguments are lists of tag names."""
    best = None
    pattern = re.compile('^' + re.escape(prefix) + NUMBER + r'\.' + NUMBER + r'\.' + NUMBER
                         + r'(?:-(' + IDENTIFIER + r'(?:\.' + IDENTIFIER + r')*))?$')
    for tag in ancestor_tags:
        m = pattern.match(tag)
        if not m or tag in tags_at_rev:
            continue
        key = precedence(tuple(int(x) for x in m.groups()[:3]), m.group(4))
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
    check('strangers are not baselines', baseline([], ['nightly', 'v0.2', 'v0.2.0+build']), None)
    check('a pre-release is a baseline', baseline([], ['v0.1.0-pre.1']), 'v0.1.0-pre.1')
    check('a release sorts above its pre-releases',
          baseline([], ['v0.1.0-pre.2', 'v0.1.0', 'v0.1.0-rc.1']), 'v0.1.0')
    check('a pre-release of a later version sorts above an earlier release',
          baseline([], ['v0.2.0', 'v1.0.0-rc.1']), 'v1.0.0-rc.1')
    check('numeric pre-release identifiers compare as numbers',
          baseline([], ['v0.1.0-pre.9', 'v0.1.0-pre.10']), 'v0.1.0-pre.10')
    check('a numeric identifier sorts below an alphanumeric one',
          baseline([], ['v0.1.0-rc', 'v0.1.0-1']), 'v0.1.0-rc')
    check('a longer pre-release sorts above its prefix',
          baseline([], ['v0.1.0-pre', 'v0.1.0-pre.1']), 'v0.1.0-pre.1')
    check('a leading zero is not a version', baseline([], ['v0.01.0', 'v0.1.0-pre.01']), None)
    check('the pre-release at the commit is skipped',
          baseline(['v0.1.0-pre.2'], ['v0.1.0-pre.1', 'v0.1.0-pre.2']), 'v0.1.0-pre.1')
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
        run('tag', 'v0.2.0-pre.1')
        run('commit', '-q', '--allow-empty', '-m', 'more work')
        check('repo past a pre-release tag', from_repo(d, 'HEAD'), 'v0.2.0-pre.1')
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
