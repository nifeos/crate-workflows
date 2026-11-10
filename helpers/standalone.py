#!/usr/bin/env python3
"""Whether a crate stands alone: the checks nife ran on a crate from outside, run inside.

    python3 standalone.py [--manifest-dir DIR] [--allow-unpublished] [--selftest]

`--allow-unpublished` exists for fixture crates, `sample/` among them, that must never reach
crates.io. A crate repository that means to release does not pass it, and `publish = false` in its
manifest is then a finding.

What each check is, and where it came from:

- files: a README, `LICENSE-MIT` and `LICENSE-APACHE` at the crate root, and
  `license = "MIT OR Apache-2.0"`. Both files, because GitHub's license detection reads nife
  itself as Apache-2.0 although the tree carries both (calef, 2026-10-11 UTC). A crate that follows
  permissive source (BSD or ISC) carries that source's notice, and its field says so by adding
  `AND <id>` for each such license after the pair in parentheses, as in
  `(MIT OR Apache-2.0) AND BSD-3-Clause`. The ids allowed are `BSD-2-Clause`, `BSD-3-Clause` and
  `ISC`; any other field is a finding. The field and the notices must also agree in each direction: every
  notice opens with a line `SPDX-License-Identifier: <id>` (after any comment marker) naming its
  license, and the set of those ids must equal the `AND` terms of the field. A notice with no term
  and a term with no notice each fail, naming the file or the term. `LICENSE-<name>` files at the
  root are read as well as the text files, since a repository may keep a notice there.
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
NOTICE_LICENSES = ('BSD-2-Clause', 'BSD-3-Clause', 'ISC')
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


def lint_findings(manifest):
    """[(lint, why)] for the [lints] table a standalone crate must carry itself.

    nife's workspace states these once; a standalone crate has no workspace, so the crate's own
    `[lints]` is the one place they can live. `unexpected_cfgs` needs `cfg(kani)` in its check-cfg
    list, because the model checker sets that cfg and cargo does not know it: without the line,
    the ordinary clippy pass refuses every proof module with `-D warnings`.
    """
    found = []
    lints = manifest.get('lints', {}) or {}
    if lints.get('workspace'):
        found.append(('lints.workspace = true inherits a workspace that is not here', ''))
        return found
    have = {}
    for table in ('rust', 'clippy', 'all'):
        for k, v in (lints.get(table, {}) or {}).items():
            have.setdefault(k, str(v))
    for lint in REQUIRED_LINTS:
        if lint not in have:
            found.append((f'[lints] does not set {lint}', ''))
    got = have.get('unexpected_cfgs', '')
    if 'kani' not in got:
        found.append(('unexpected_cfgs', "[lints.rust] needs "
                      'unexpected_cfgs = { level = "warn", check-cfg = [\'cfg(kani)\'] }, '
                      'or -D warnings refuses every proof module'))
    return found


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
    """{relative path: text} under root, for the extensions a citation can hide in.

    Repository plumbing is excluded: `.github/` and CONTRIBUTING.md legitimately describe the
    organization's process (the disclosure line, how contributions are reviewed), and a gate that
    reads them for nife's vocabulary would refuse the scaffold itself. The crate's own text,
    source, manifests and patches are what must stand alone.
    """
    out = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in TEXT:
            continue
        parts = path.relative_to(root).parts
        if any(p in ('.git', 'target', '.crate-workflows') for p in parts):
            continue
        if '.github' in parts or path.name == 'CONTRIBUTING.md':
            continue
        try:
            out['/'.join(parts)] = path.read_text()
        except UnicodeDecodeError:
            continue
    return out


def license_ok(field):
    """True for the pair alone, or the pair in parentheses followed by `AND <notice license>` terms."""
    if field == LICENSE:
        return True
    if not isinstance(field, str) or not field.startswith(f'({LICENSE}) AND '):
        return False
    terms = field[len(f'({LICENSE}) AND '):].split(' AND ')
    return all(term in NOTICE_LICENSES for term in terms) and len(set(terms)) == len(terms)


NOTICE_LINE = re.compile(r'^\s*(?://[!/]?|#|\*)?\s*SPDX-License-Identifier:(.*)$', re.M)
OWN_IDENTIFIERS = {'MIT', 'Apache-2.0'}
EXPRESSION_WORDS = {'AND', 'OR', 'WITH'}


def notice_licenses(root):
    """{identifier: first file whose notice opens with it}, minus the crate's own pair.

    Only a line that begins with the marker counts, so prose that quotes one (a table of the
    licenses of sources that were read and not adapted) is not a notice.
    """
    root = Path(root)
    found = {}
    for path in sorted(root.rglob('*')):
        parts = path.relative_to(root).parts
        if (not path.is_file() or any(p in ('.git', 'target', '.crate-workflows') for p in parts)
                or path.name in LICENSE_FILES
                or not (path.suffix in TEXT or path.name.startswith('LICENSE-'))):
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for m in NOTICE_LINE.finditer(text):
            for ident in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+-]*', m.group(1)):
                if ident not in OWN_IDENTIFIERS | EXPRESSION_WORDS:
                    found.setdefault(ident, '/'.join(parts))
    return found


def notice_findings(root, manifest):
    """Findings where the license field and the notices the crate carries disagree."""
    field = manifest.get('package', {}).get('license')
    if not license_ok(field):
        return []  # the shape finding already names it
    terms = set(field[len(f'({LICENSE}) AND '):].split(' AND ')) if field != LICENSE else set()
    notices = notice_licenses(root)
    found = [f'{where} carries the {ident} notice, which the license field {field!r} does not name'
             for ident, where in sorted(notices.items()) if ident not in terms]
    found += [f'license field names {term}, but no file carries an SPDX-License-Identifier: {term} notice'
              for term in sorted(terms - set(notices))]
    return found


def file_findings(root_names, manifest):
    found = []
    if not any(n.upper().startswith('README') for n in root_names):
        found.append('no README')
    found += [f'no {f}' for f in LICENSE_FILES if f not in root_names]
    pkg = manifest.get('package', {})
    if not license_ok(pkg.get('license')):
        found.append(f'license field is {pkg.get("license")!r}, not {LICENSE!r}'
                     f' (optionally followed by AND and one of {", ".join(NOTICE_LICENSES)})')
    return found


def manifest_findings(manifest, allow_unpublished):
    found = []
    pkg = manifest.get('package', {})
    if not pkg.get('rust-version'):
        found.append('no rust-version')
    if pkg.get('publish') is False and not allow_unpublished:
        found.append('publish = false, which no released crate carries')
    found += [why for why, _fix in lint_findings(manifest)]
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
    found += notice_findings(root, manifest)
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
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(kani)'] }
"""
        (root / 'Cargo.toml').write_text(manifest)
        (root / 'src').mkdir()
        (root / 'src' / 'lib.rs').write_text('//! A crate.\n')
        (root / 'README.md').write_text('# example\n\n## EXAMPLES\n\n```rust\nlet x = 1;\n```\n\n## BUGS\n\nNone yet.\n')
        (root / 'LICENSE-MIT').write_text('MIT\n')
        (root / 'LICENSE-APACHE').write_text('Apache\n')
        expect('clean crate', findings(root, allow_unpublished=False), [])
        for field, want in ((f'({LICENSE}) AND BSD-3-Clause AND BSD-2-Clause', True),
                            (f'({LICENSE}) AND ISC', True), (f'({LICENSE}) AND GPL-2.0-only', False),
                            (f'({LICENSE}) AND ISC AND ISC', False), (f'{LICENSE} AND ISC', False),
                            ('MIT', False), (None, False)):
            expect(f'license {field!r}', license_ok(field), want)

        isc_field = f'license = "({LICENSE}) AND ISC"'
        isc_manifest = manifest.replace(f'license = "{LICENSE}"', isc_field)
        (root / 'Cargo.toml').write_text(isc_manifest)
        expect('term with no notice', notice_findings(root, tomllib.loads(isc_manifest)),
               ['license field names ISC, but no file carries an SPDX-License-Identifier: ISC notice'])
        (root / 'LICENSE-ISC').write_text('SPDX-License-Identifier: ISC\n\nCopyright (c) someone\n')
        expect('notice and term agree', findings(root, allow_unpublished=False), [])
        (root / 'Cargo.toml').write_text(manifest)
        expect('notice with no term', notice_findings(root, tomllib.loads(manifest)),
               ['LICENSE-ISC carries the ISC notice, which the license field '
                "'MIT OR Apache-2.0' does not name"])
        (root / 'LICENSE-ISC').write_text('The ISC license requires this notice.\n')
        (root / 'src' / 'lib.rs').write_text('//! Read, not adapted: `// SPDX-License-Identifier: GPL-2.0`.\n')
        expect('prose is not a notice', notice_findings(root, tomllib.loads(manifest)), [])
        (root / 'LICENSE-ISC').unlink()
        (root / 'src' / 'lib.rs').write_text('//! A crate.\n')

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
