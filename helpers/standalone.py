#!/usr/bin/env python3
"""Whether a crate stands alone: the checks nife ran on a crate from outside, run inside.

    python3 standalone.py [--manifest-dir DIR] [--allow-unpublished] [--selftest]

`--allow-unpublished` exists for fixture crates, `sample/` among them, that must never reach
crates.io. A crate repository that means to release does not pass it, and `publish = false` in its
manifest is then a finding.

What each check is, and where it came from:

- files: a README, `LICENSE-MIT` and `LICENSE-APACHE` at the crate root, and
  `license = "MIT OR Apache-2.0"`. Both files, because GitHub's license detection reads nife
  itself as Apache-2.0 although the tree carries both (calef, 2026-10-11 UTC).
- manifest: no workspace inheritance left (`lints.workspace = true` dies here), a `rust-version`
  so `weekly / msrv` has something to build, and `[lints]` carrying `unsafe_op_in_unsafe_fn` and
  `missing_docs` themselves, which is the workspace-lints row of nife's table inlined where a
  standalone crate must carry it.
- vocabulary: the citations nife's `crate-standalone` refuses, read in the crate's own text files.
  A standalone crate cites issues in its own repository, not another tree's milestones, sections,
  or provenance blocks. The path regex (`design/`, `notes/`, `script/`, `helpers/`, `briefs/`) can
  false-positive on a crate that keeps its own `scripts/` and writes prose about it; that is a
  reviewable finding, not a silent pass.
- rustfmt: stable channel only, so `unstable_features`, `group_imports` and
  `imports_granularity` (nife's two unstable options plus the switch that enables them) are
  refused in `rustfmt.toml`.
- headings: the README carries `## EXAMPLES` and `## BUGS`. nife has no mechanical gate for its own
  documentation standard; a published crate can afford one, so the template runs it.

Exit 0 stands alone; 1 lists findings. `--selftest` checks the logic on fixtures, not a real crate.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

LICENSE = 'MIT OR Apache-2.0'
LICENSE_FILES = ('LICENSE-MIT', 'LICENSE-APACHE')
TEXT = ('.rs', '.toml', '.md', '.patch', '.txt')

CITATIONS = [
    ('section citation', re.compile(r'§\s?\d+')),
    ('milestone citation', re.compile(r'\bmilestones? \d+', re.I)),
    ('path into the nife tree', re.compile(r'\b(?:design|notes|script|helpers|briefs)/[\w.-]')),
    ('provenance block', re.compile(r'\bName: *(?:provisional|ratified|recorded|unrecorded)', re.I)),
    ("architect's name", re.compile(r'\bcalef\b')),
    ('nife target_os', re.compile(r'target_os\s*=\s*"nife"')),
]
INCLUDE = re.compile(r'include_(?:bytes|str)!\(\s*"([^"]+)"')
RUSTFMT_UNSTABLE = ('unstable_features', 'group_imports', 'imports_granularity')
REQUIRED_LINTS = ('unsafe_op_in_unsafe_fn', 'missing_docs')


def _normpath(parts):
    out = []
    for p in parts:
        if p in ('', '.'):
            continue
        if p == '..':
            if not out:
                return None
            out.pop()
        else:
            out.append(p)
    return out


def text_files(root):
    """{relative path: text} under root, for the extensions a citation can hide in."""
    out = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in TEXT:
            continue
        parts = path.relative_to(root).parts
        if any(p in ('.git', 'target', '.crate-workflows') for p in parts):
            continue
        try:
            out['/'.join(parts)] = path.read_text()
        except UnicodeDecodeError:
            continue
    return out


def file_findings(root_names, manifest):
    found = []
    if not any(n.upper().startswith('README') for n in root_names):
        found.append('no README')
    found += [f'no {f}' for f in LICENSE_FILES if f not in root_names]
    pkg = manifest.get('package', {})
    if pkg.get('license') != LICENSE:
        found.append(f'license field is {pkg.get("license")!r}, not {LICENSE!r}')
    return found


def manifest_findings(manifest, allow_unpublished):
    found = []
    pkg = manifest.get('package', {})
    if not pkg.get('rust-version'):
        found.append('no rust-version')
    if pkg.get('publish') is False and not allow_unpublished:
        found.append('publish = false, which no released crate carries')
    if manifest.get('lints', {}).get('workspace'):
        found.append('lints.workspace = true inherits a workspace that is not here')
    have = set()
    for table in ('rust', 'clippy', 'all'):
        have |= set((manifest.get('lints', {}) or {}).get(table, {}) or {})
    for lint in REQUIRED_LINTS:
        if lint not in have:
            found.append(f'[lints] does not set {lint}')
    return found


def citation_findings(files):
    sites = {}
    for path, text in sorted(files.items()):
        for n, line in enumerate(text.split('\n'), 1):
            for label, rx in CITATIONS:
                if rx.search(line):
                    sites.setdefault(label, []).append(f'{path}:{n}')
        here = path.split('/')[:-1]
        for inc in INCLUDE.finditer(text):
            if _normpath(here + inc.group(1).split('/')) is None:
                line = text.count('\n', 0, inc.start()) + 1
                sites.setdefault('file read from outside the crate', []).append(f'{path}:{line}')
    return [f'{len(s)} {label} line(s), first {s[0]}' for label, s in sites.items()]


def rustfmt_findings(root):
    path = root / 'rustfmt.toml'
    if not path.is_file():
        return []  # the defaults are stable; nife's options are what needed a file
    text = path.read_text()
    return [f'rustfmt.toml sets {name}, which needs nightly' for name in RUSTFMT_UNSTABLE
            if re.search(r'^\s*' + name + r'\s*=', text, re.M)]


def heading_findings(root):
    readme = next((p for p in sorted(root.glob('*')) if p.name.upper().startswith('README')), None)
    if readme is None:
        return []
    text = readme.read_text()
    missing = [h for h in ('EXAMPLES', 'BUGS')
               if not re.search(r'^##\s+' + h + r'\s*$', text, re.M)]
    return [f'README has no "## {h}" heading' for h in missing]


def findings(root, allow_unpublished):
    root = Path(root)
    files = text_files(root)
    try:
        manifest = tomllib.loads((root / 'Cargo.toml').read_text())
    except FileNotFoundError:
        return ['no Cargo.toml at the crate root']
    found = file_findings({p.name for p in root.iterdir()}, manifest)
    found += manifest_findings(manifest, allow_unpublished)
    found += citation_findings(files)
    found += rustfmt_findings(root)
    found += heading_findings(root)
    return found


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
        manifest = """
[package]
name = "example"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
license = "MIT OR Apache-2.0"

[lints.rust]
missing_docs = "deny"
unsafe_op_in_unsafe_fn = "deny"
"""
        (root / 'Cargo.toml').write_text(manifest)
        (root / 'src').mkdir()
        (root / 'src' / 'lib.rs').write_text('//! A crate.\n')
        (root / 'README.md').write_text('# example\n\n## EXAMPLES\n\n```rust\nlet x = 1;\n```\n\n## BUGS\n\nNone yet.\n')
        (root / 'LICENSE-MIT').write_text('MIT\n')
        (root / 'LICENSE-APACHE').write_text('Apache\n')
        expect('clean crate', findings(root, allow_unpublished=False), [])

        (root / 'Cargo.toml').write_text(manifest + '\n[package.publish]\nfalse = true\n')
        # A malformed publish table is still "not false": tomllib reads the table, not a bool.
        expect('publish table is not false', [f for f in findings(root, allow_unpublished=False)
                                              if 'publish' in f], [])

        (root / 'Cargo.toml').write_text(manifest.replace('license = "MIT OR Apache-2.0"',
                                                          'license = "MIT OR Apache-2.0"\npublish = false'))
        expect('publish = false refused',
               [f for f in findings(root, allow_unpublished=False) if 'publish' in f],
               ['publish = false, which no released crate carries'])
        expect('publish = false allowed for a fixture', [], [f for f in findings(root, True)
                                                             if 'publish' in f])

        (root / 'Cargo.toml').write_text(manifest)
        (root / 'src' / 'lib.rs').write_text('//! See milestones 813. And calef.\n')
        got = citation_findings(text_files(root))
        expect('two citation kinds', len(got), 2)

        (root / 'src' / 'lib.rs').write_text('//! A crate.\n')
        (root / 'rustfmt.toml').write_text('unstable_features = true\n')
        expect('unstable rustfmt refused', ['rustfmt.toml sets unstable_features, which needs nightly'],
               rustfmt_findings(root))

        (root / 'rustfmt.toml').unlink()
        (root / 'README.md').write_text('# example\n\n## EXAMPLES\n\nText.\n')
        expect('missing BUGS heading', ['README has no "## BUGS" heading'], heading_findings(root))

    print('standalone selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest-dir', default='.')
    ap.add_argument('--allow-unpublished', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    found = findings(args.manifest_dir, args.allow_unpublished)
    for f in found:
        print(f'standalone: {f}', file=sys.stderr)
    if found:
        print('standalone: this crate does not stand alone yet', file=sys.stderr)
        return 1
    print('==> standalone: the crate stands alone')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
