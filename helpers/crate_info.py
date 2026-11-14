#!/usr/bin/env python3
"""What the workflows need to know about one crate in a repository of one crate or several.

    python3 crate_info.py name         MANIFEST      # the package name
    python3 crate_info.py version      MANIFEST      # the version, workspace inheritance resolved
    python3 crate_info.py rust-version MANIFEST      # the rust-version, or nothing
    python3 crate_info.py published    MANIFEST      # prints yes or no; exit 0 for yes, 1 for no
    python3 crate_info.py release-target MANIFEST     # prints yes or no; exit 0 for yes, 1 for no
    python3 crate_info.py tag-prefix   MANIFEST      # `v`, or `<name>-v` in a repository of several crates
    python3 crate_info.py tag          MANIFEST VERSION
    python3 crate_info.py workspace-root MANIFEST    # the workspace's directory, absolute
    python3 crate_info.py prefix       MANIFEST      # the crate's directory under the workspace's, `` or `dir/`
    python3 crate_info.py members      MANIFEST [--release-targets]   # manifests, one per line
    python3 crate_info.py names        MANIFEST      # package names, one per line
    python3 crate_info.py --selftest

Every answer comes from `cargo metadata --no-deps`, which resolves `version.workspace = true` and
the like, so a member that inherits from a workspace answers the same as one that does not. MANIFEST
is the Cargo.toml of one crate, or the root of a virtual workspace for `members` and `names`.

PUBLISHED. A package may be published unless it says `publish = false` (or an empty registry list).
A crate that may not be published is never packaged for release, never checked against crates.io
and never given a first-publish door.

RELEASE TARGET. A crate that may be published, or the only crate of its repository. A repository
of one crate keeps its old behavior (a crate carrying `publish = false` there is still checked
against its own release tags and owes its stranger-test record); in a repository of several, a
member that may not be published has no release to compare against and nobody to be a stranger
to, so the semver and stranger-test gates pass it over.

TAG. A repository whose workspace holds one crate tags a release `v<version>`. A repository whose
workspace holds several tags `<name>-v<version>`, because two crates at one version would otherwise
ask for the same tag, and a tag that names no crate says nothing about which crate it released.
"""

import json
import os
import subprocess
import sys
import tempfile


WORKSPACE_ROOT = 'workspace_root'


def metadata(manifest):
    run = subprocess.run(['cargo', 'metadata', '--no-deps', '--format-version', '1',
                          '--manifest-path', manifest], capture_output=True, text=True, check=False)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or 'cargo metadata failed')
    return json.loads(run.stdout)


def members(manifest):
    """Every package of the workspace, as {name, version, rust_version, published, manifest}."""
    meta = metadata(manifest)
    wanted = set(meta['workspace_members'])
    out = []
    for p in meta['packages']:
        if p['id'] in wanted:
            out.append({'name': p['name'], 'version': p['version'],
                        'rust_version': p.get('rust_version') or '',
                        'published': p.get('publish') is None or bool(p['publish']),
                        'manifest': p['manifest_path']})
    return sorted(out, key=lambda m: m['name'])


def own(manifest):
    """(package of this manifest, every package of its workspace); a virtual root has no package."""
    everyone = members(manifest)
    here = os.path.realpath(manifest)
    for m in everyone:
        if os.path.realpath(m['manifest']) == here:
            return m, everyone
    raise RuntimeError(f'{manifest} is not a package of its workspace (a virtual root names none)')


def tag_prefix(pkg, everyone):
    return f"{pkg['name']}-v" if len(everyone) > 1 else 'v'


def release_target(pkg, everyone):
    return pkg['published'] or len(everyone) == 1


def relative(path):
    return os.path.relpath(path)


def workspace_root(manifest):
    return metadata(manifest)[WORKSPACE_ROOT]


def prefix(manifest):
    """The crate's directory under its workspace's, with a trailing slash, or '' at the root.

    cargo-mutants names every file from the workspace root, so a crate in a directory of its own
    has its sources at `<prefix>src/lib.rs` in a mutants.out and in `.github/mutants-exempts`.
    """
    here = os.path.dirname(os.path.realpath(manifest))
    rel = os.path.relpath(here, os.path.realpath(workspace_root(manifest)))
    return '' if rel == '.' else rel + '/'


def selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: expected {want!r}, got {got!r}')

    def crate(root, name, extra=''):
        os.makedirs(os.path.join(root, name, 'src'))
        with open(os.path.join(root, name, 'src', 'lib.rs'), 'w') as f:
            f.write('')
        with open(os.path.join(root, name, 'Cargo.toml'), 'w') as f:
            f.write(f'[package]\nname = "{name}"\nversion = "0.3.0"\nedition = "2024"\n{extra}\n')

    with tempfile.TemporaryDirectory() as d:
        single = os.path.join(d, 'single')
        crate(d, 'single', 'rust-version = "1.85"\npublish = false')
        pkg, everyone = own(os.path.join(single, 'Cargo.toml'))
        check('single: tag prefix', tag_prefix(pkg, everyone), 'v')
        check('single: unpublished', pkg['published'], False)
        check('single: still a release target', release_target(pkg, everyone), True)
        check('single: rust-version', pkg['rust_version'], '1.85')

        ws = os.path.join(d, 'ws')
        os.makedirs(ws)
        with open(os.path.join(ws, 'Cargo.toml'), 'w') as f:
            f.write('[workspace]\nresolver = "3"\nmembers = ["contract", "fixture", "inheriting"]\n'
                    '[workspace.package]\nversion = "2.0.0"\n')
        crate(ws, 'contract')
        crate(ws, 'fixture', 'publish = false')
        crate(ws, 'inheriting')
        with open(os.path.join(ws, 'inheriting', 'Cargo.toml'), 'w') as f:
            f.write('[package]\nname = "inheriting"\nversion.workspace = true\nedition = "2024"\n'
                    'publish = []\n')
        pkg, everyone = own(os.path.join(ws, 'contract', 'Cargo.toml'))
        check('workspace: published', pkg['published'], True)
        check('workspace: tag prefix names the crate', tag_prefix(pkg, everyone), 'contract-v')
        check('workspace: the published one is a target', release_target(pkg, everyone), True)
        pkg, everyone = own(os.path.join(ws, 'fixture', 'Cargo.toml'))
        check('workspace: unpublished', pkg['published'], False)
        check('workspace: an unpublished member is no release target', release_target(pkg, everyone), False)
        pkg, everyone = own(os.path.join(ws, 'inheriting', 'Cargo.toml'))
        check('workspace: inherited version resolves', pkg['version'], '2.0.0')
        check('workspace: an empty registry list is unpublished', pkg['published'], False)
        check('workspace: a member sits under its directory', prefix(os.path.join(ws, 'contract', 'Cargo.toml')),
              'contract/')
        check('workspace: workspace root', os.path.realpath(workspace_root(os.path.join(ws, 'contract', 'Cargo.toml'))),
              os.path.realpath(ws))
        check('single: no prefix', prefix(os.path.join(single, 'Cargo.toml')), '')
        check('workspace: names', [m['name'] for m in members(os.path.join(ws, 'Cargo.toml'))],
              ['contract', 'fixture', 'inheriting'])
        try:
            own(os.path.join(ws, 'Cargo.toml'))
            check('a virtual root has no package of its own', 'returned', 'raised')
        except RuntimeError:
            pass
    print('crate_info selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ['--selftest']:
        return selftest()
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    command, manifest, rest = argv[1], argv[2], argv[3:]
    try:
        if command in ('members', 'names'):
            everyone = members(manifest)
            if command == 'names':
                print('\n'.join(m['name'] for m in everyone))
                return 0
            for m in everyone:
                if '--release-targets' not in rest or release_target(m, everyone):
                    print(relative(m['manifest']))
            return 0
        if command == 'workspace-root':
            print(os.path.realpath(workspace_root(manifest)))
            return 0
        if command == 'prefix':
            print(prefix(manifest))
            return 0
        pkg, everyone = own(manifest)
    except (RuntimeError, OSError) as e:
        print(f'crate_info: {e}', file=sys.stderr)
        return 2
    if command == 'name':
        print(pkg['name'])
    elif command == 'version':
        print(pkg['version'])
    elif command == 'rust-version':
        print(pkg['rust_version'])
    elif command in ('published', 'release-target'):
        yes = pkg['published'] if command == 'published' else release_target(pkg, everyone)
        print('yes' if yes else 'no')
        return 0 if yes else 1
    elif command == 'tag-prefix':
        print(tag_prefix(pkg, everyone))
    elif command == 'tag' and len(rest) == 1:
        print(tag_prefix(pkg, everyone) + rest[0])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
