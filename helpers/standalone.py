#!/usr/bin/env python3
"""Whether a crate stands alone: the checks nife ran on a crate from outside, run inside.

    python3 standalone.py [--manifest-dir DIR] [--allow-unpublished] [--fork-file FILE] [--selftest]

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

Fork mode. A repository that carries another project's crate and sends its fixes upstream
declares itself a fork in `.github/fork-upstream.toml`, which `check / standalone` passes as
`--fork-file`. The file names the upstream source and nothing else:

    repository = "https://github.com/<owner>/<repository>"
    commit = "<the 40-hex commit the fork starts from>"
    path = "<the crate's directory there, or empty for the root>"

The upstream manifest is read at that commit (`raw.githubusercontent.com`, so the source is
public and the commit fixed), following `license.workspace = true` to the root manifest. Fork mode
applies to the crate whose package name equals upstream's; any other crate in the repository is
checked as usual. In fork mode:

- the license field must equal upstream's license field exactly, and each license that field
  names must have its file holding that license's text: `LICENSE-APACHE` for `Apache-2.0` and
  `LICENSE-MIT` for `MIT`, or a `LICENSE` holding that text. An SPDX notice in the crate whose
  license upstream's field does not name is a finding;
- `[lints]` need not set `unsafe_op_in_unsafe_fn`, `missing_docs` or the `cfg(kani)` entry of
  `unexpected_cfgs`, since upstream's manifest does not, and the fork keeps it as upstream's so
  each fix can go upstream unchanged. The `cfg(kani)` entry is skipped for the same reason: it is a
  line of upstream's `[lints]` table, and the failure it prevents is not lost, because
  `check / clippy` runs with `-D warnings` and refuses a `#[cfg(kani)]` that cargo does not know;
- every other check above still runs.

A fork file that cannot be read, names a source in another shape, or whose upstream manifest cannot
be fetched is a finding, and the crate is checked as usual. A crate with no fork file is never in
fork mode, so a crate that copies a fork's license field still fails.

Exit 0 stands alone; 1 lists findings. `--selftest` checks the logic on fixtures, not a real crate.
"""

import argparse
import re
import sys
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

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

FORK_KEYS = ('repository', 'commit', 'path')
FORK_REPOSITORY = re.compile(r'^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$')
FORK_COMMIT = re.compile(r'^[0-9a-f]{40}$')
# The license file each upstream license needs in fork mode, and lines its text must hold. The
# lines are from the license texts themselves, so a placeholder file does not pass.
FORK_LICENSE_FILES = {
    'Apache-2.0': ('LICENSE-APACHE', ('Apache License', 'Version 2.0, January 2004')),
    'MIT': ('LICENSE-MIT', ('Permission is hereby granted, free of charge',)),
}


def lint_findings(manifest, fork=False):
    """[(lint, why)] for the [lints] table a standalone crate must carry itself.

    nife's workspace states these once; a standalone crate has no workspace, so the crate's own
    `[lints]` is the one place they can live. `unexpected_cfgs` needs `cfg(kani)` in its check-cfg
    list, because the model checker sets that cfg and cargo does not know it: without the line,
    the ordinary clippy pass refuses every proof module with `-D warnings`. A fork keeps
    upstream's `[lints]` table, so in fork mode only the workspace inheritance is a finding.
    """
    found = []
    lints = manifest.get('lints', {}) or {}
    if lints.get('workspace'):
        found.append(('lints.workspace = true inherits a workspace that is not here', ''))
        return found
    if fork:
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


def license_identifiers(field):
    """The license identifiers an SPDX expression names, without its operators and parentheses."""
    return set(re.findall(r'[A-Za-z0-9][A-Za-z0-9.+-]*', field)) - EXPRESSION_WORDS


def notice_findings(root, manifest, fork=None):
    """Findings where the license field and the notices the crate carries disagree.

    In fork mode the crate's field is upstream's, and a notice is allowed when that field names
    its license; there are no `AND` terms to match.
    """
    field = manifest.get('package', {}).get('license')
    if fork is not None:
        if field != fork['license']:
            return []  # the fork license finding already names it
        named = license_identifiers(field)
        return [f'{where} carries the {ident} notice, which upstream\'s license field {field!r} '
                'does not name' for ident, where in sorted(notice_licenses(root).items())
                if ident not in named]
    if not license_ok(field):
        return []  # the shape finding already names it
    terms = set(field[len(f'({LICENSE}) AND '):].split(' AND ')) if field != LICENSE else set()
    notices = notice_licenses(root)
    found = [f'{where} carries the {ident} notice, which the license field {field!r} does not name'
             for ident, where in sorted(notices.items()) if ident not in terms]
    found += [f'license field names {term}, but no file carries an SPDX-License-Identifier: {term} notice'
              for term in sorted(terms - set(notices))]
    return found


def fork_license_findings(root, manifest, fork):
    """Findings for a fork's license: upstream's field, and each license's file with its text."""
    field = manifest.get('package', {}).get('license')
    found = []
    if field != fork['license']:
        found.append(f'license field is {field!r}, but upstream\'s at {fork["commit"][:12]} is '
                     f'{fork["license"]!r}, and a fork keeps upstream\'s license')
    for ident in sorted(license_identifiers(fork['license'])):
        if ident not in FORK_LICENSE_FILES:
            found.append(f'upstream\'s license names {ident}, and fork mode knows no license file '
                         'for it')
            continue
        name, lines = FORK_LICENSE_FILES[ident]
        holders = [n for n in (name, 'LICENSE') if (root / n).is_file()
                   and all(line in (root / n).read_text(errors='replace') for line in lines)]
        if not holders:
            found.append(f'no {name}, or LICENSE, holding the {ident} text that upstream\'s '
                         'license field names')
    return found


def file_findings(root_names, manifest, fork=None):
    found = []
    if not any(n.upper().startswith('README') for n in root_names):
        found.append('no README')
    if fork is not None:
        return found  # fork_license_findings holds the license and its files
    found += [f'no {f}' for f in LICENSE_FILES if f not in root_names]
    pkg = manifest.get('package', {})
    if not license_ok(pkg.get('license')):
        found.append(f'license field is {pkg.get("license")!r}, not {LICENSE!r}'
                     f' (optionally followed by AND and one of {", ".join(NOTICE_LICENSES)})')
    return found


def manifest_findings(manifest, allow_unpublished, fork=False):
    found = []
    pkg = manifest.get('package', {})
    if not pkg.get('rust-version'):
        found.append('no rust-version')
    if pkg.get('publish') is False and not allow_unpublished:
        found.append('publish = false, which no released crate carries')
    found += [why for why, _fix in lint_findings(manifest, fork)]
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


def fetch_url(url):
    """The text at url, read once with a short timeout; any failure raises."""
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode()


def read_fork_file(path):
    """`(declaration, [findings])` from a fork file; `(None, [])` when there is none."""
    path = Path(path)
    if not path.is_file():
        return None, []
    where = path.name
    try:
        declared = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as err:
        return None, [f'{where} is not TOML: {err}']
    found = [f'{where} sets {key}, which a fork file does not carry'
             for key in sorted(declared) if key not in FORK_KEYS]
    found += [f'{where} does not set {key}' for key in FORK_KEYS
              if not isinstance(declared.get(key), str)]
    if found:
        return None, found
    if not FORK_REPOSITORY.match(declared['repository']):
        found.append(f'{where} repository {declared["repository"]!r} is not '
                     'https://github.com/<owner>/<repository>')
    if not FORK_COMMIT.match(declared['commit']):
        found.append(f'{where} commit {declared["commit"]!r} is not a full 40-hex commit')
    sub = PurePosixPath(declared['path'])
    if declared['path'] and (sub.is_absolute() or '..' in sub.parts):
        found.append(f'{where} path {declared["path"]!r} is not relative inside the repository')
    return (None, found) if found else (declared, [])


def upstream_license(declared, fetch):
    """`(name, license, [findings])` of the upstream manifest the fork file names."""
    owner, repository = FORK_REPOSITORY.match(declared['repository']).groups()
    base = f'https://raw.githubusercontent.com/{owner}/{repository}/{declared["commit"]}'
    sub = declared['path'].strip('/')
    url = f'{base}/{sub}/Cargo.toml' if sub else f'{base}/Cargo.toml'
    try:
        package = tomllib.loads(fetch(url)).get('package', {})
        license_field = package.get('license')
        if isinstance(license_field, dict) and license_field.get('workspace') is True:
            root_url = f'{base}/Cargo.toml'
            workspace = tomllib.loads(fetch(root_url)).get('workspace', {})
            license_field = workspace.get('package', {}).get('license')
    except Exception as err:  # noqa: BLE001 - any failure to read upstream is one finding
        return None, None, [f'upstream manifest {url} could not be read: {err}']
    if not isinstance(license_field, str):
        return None, None, [f'upstream manifest {url} has no license field to keep']
    return package.get('name'), license_field, []


def fork_mode(manifest, fork_file, fetch):
    """`(fork, [findings], note)`: fork is upstream's source and license when this crate is the fork."""
    if fork_file is None:
        return None, [], None
    declared, found = read_fork_file(fork_file)
    if declared is None:
        return None, found, None
    name, license_field, found = upstream_license(declared, fetch)
    if found:
        return None, found, None
    own = manifest.get('package', {}).get('name')
    if own != name:
        return None, [], f'{own} is not upstream\'s {name}, so it is checked as usual'
    fork = dict(declared, license=license_field)
    return fork, [], (f'fork mode for {own}: upstream {declared["repository"]} at '
                      f'{declared["commit"][:12]}, license {license_field!r}; [lints] keeps '
                      "upstream's table")


def findings(root, allow_unpublished, fork_file=None, fetch=fetch_url, notes=None):
    root = Path(root)
    files = text_files(root)
    try:
        manifest = tomllib.loads((root / 'Cargo.toml').read_text())
    except FileNotFoundError:
        return ['no Cargo.toml at the crate root']
    fork, found, note = fork_mode(manifest, fork_file, fetch)
    if note and notes is not None:
        notes.append(note)
    found += file_findings({p.name for p in root.iterdir()}, manifest, fork)
    if fork is not None:
        found += fork_license_findings(root, manifest, fork)
    found += notice_findings(root, manifest, fork)
    found += manifest_findings(manifest, allow_unpublished, fork is not None)
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

    fork_selftest(expect)
    print('standalone selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def fork_selftest(expect):
    """Fork mode on fixtures, with upstream's manifests served from a table instead of the network."""
    import tempfile
    commit = 'b' * 40
    base = f'https://raw.githubusercontent.com/upstream-owner/upstream-repository/{commit}'
    apache = 'Apache License\nVersion 2.0, January 2004\n\nTERMS AND CONDITIONS\n'
    upstream_manifest = ('[package]\nname = "forked"\nversion = "0.9.0"\nedition.workspace = true\n'
                         'license = "Apache-2.0"\n')
    served = {f'{base}/crates/forked/Cargo.toml': upstream_manifest}

    def fetch(url):
        if url not in served:
            raise OSError(f'404 {url}')
        return served[url]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'forked'
        root.mkdir()
        fork_file = Path(tmp) / 'fork-upstream.toml'
        declaration = ('repository = "https://github.com/upstream-owner/upstream-repository"\n'
                       f'commit = "{commit}"\npath = "crates/forked"\n')
        fork_file.write_text(declaration)
        manifest = ('[package]\nname = "forked"\nversion = "0.10.0-fork.1"\nedition = "2024"\n'
                    'rust-version = "1.85"\nlicense = "Apache-2.0"\n')
        (root / 'Cargo.toml').write_text(manifest)
        (root / 'src').mkdir()
        (root / 'src' / 'lib.rs').write_text('//! A crate.\n')
        (root / 'README.md').write_text('# forked\n\n## EXAMPLES\n\nText.\n\n## BUGS\n\nNone yet.\n')
        (root / 'LICENSE-APACHE').write_text(apache)

        def run(**kw):
            return findings(root, False, kw.get('fork_file', fork_file), kw.get('fetch', fetch))

        expect('fork keeps upstream license and lints', run(), [])
        notes = []
        findings(root, False, fork_file, fetch, notes)
        expect('fork mode is announced', [n.split(':')[0] for n in notes], ['fork mode for forked'])

        (root / 'LICENSE-APACHE').rename(root / 'LICENSE')
        expect('fork LICENSE holding the Apache text', run(), [])
        (root / 'LICENSE').write_text('MIT License\n')
        want_file = ["no LICENSE-APACHE, or LICENSE, holding the Apache-2.0 text that upstream's "
                     'license field names']
        expect('fork LICENSE holding other text', run(), want_file)
        (root / 'LICENSE').unlink()
        (root / 'LICENSE-APACHE').write_text('Apache\n')
        expect('fork placeholder LICENSE-APACHE', run(), want_file)
        (root / 'LICENSE-APACHE').unlink()
        expect('fork with no license file', run(), want_file)
        (root / 'LICENSE-APACHE').write_text(apache)

        (root / 'Cargo.toml').write_text(manifest.replace('"Apache-2.0"', '"MIT OR Apache-2.0"'))
        expect('fork that relicenses', run(),
               ["license field is 'MIT OR Apache-2.0', but upstream's at bbbbbbbbbbbb is "
                "'Apache-2.0', and a fork keeps upstream's license"])
        (root / 'Cargo.toml').write_text(manifest)

        served[f'{base}/crates/forked/Cargo.toml'] = upstream_manifest.replace(
            'license = "Apache-2.0"', 'license.workspace = true')
        served[f'{base}/Cargo.toml'] = '[workspace.package]\nlicense = "Apache-2.0"\n'
        expect('fork follows upstream workspace license', run(), [])
        served[f'{base}/Cargo.toml'] = '[workspace.package]\nlicense = "MIT"\n'
        expect('fork against an inherited MIT license', run(),
               ["license field is 'Apache-2.0', but upstream's at bbbbbbbbbbbb is 'MIT', and a "
                "fork keeps upstream's license",
                "no LICENSE-MIT, or LICENSE, holding the MIT text that upstream's license field names"])
        served[f'{base}/crates/forked/Cargo.toml'] = upstream_manifest

        (root / 'LICENSE-BSD').write_text('SPDX-License-Identifier: BSD-3-Clause\n')
        expect('fork notice upstream does not name', run(),
               ["LICENSE-BSD carries the BSD-3-Clause notice, which upstream's license field "
                "'Apache-2.0' does not name"])
        (root / 'LICENSE-BSD').unlink()

        # Fork mode skips the lint rows and nothing else.
        (root / 'Cargo.toml').write_text(manifest.replace('rust-version = "1.85"\n', '')
                                         + '\n[lints]\nworkspace = true\n')
        (root / 'CHANGES.md').write_text('Run script/apply-settings again.\nSee milestone 12.\n')
        (root / 'rustfmt.toml').write_text('group_imports = "StdExternalCrate"\n')
        (root / 'README.md').write_text('# forked\n\n## EXAMPLES\n\nText.\n')
        expect('fork still runs every other check', run(),
               ['no rust-version', 'lints.workspace = true inherits a workspace that is not here',
                '1 path into the nife tree line(s), first CHANGES.md:1',
                '1 milestone citation line(s), first CHANGES.md:2',
                'rustfmt.toml sets group_imports, which needs nightly',
                'README has no "## BUGS" heading'])
        (root / 'Cargo.toml').write_text(manifest)
        (root / 'CHANGES.md').unlink()
        (root / 'rustfmt.toml').unlink()
        (root / 'README.md').write_text('# forked\n\n## EXAMPLES\n\nText.\n\n## BUGS\n\nNone yet.\n')

        # A crate that copies the fork's license without declaring a fork still fails, and so does
        # one whose package is not upstream's.
        non_fork = ['no LICENSE-MIT',
                    f"license field is 'Apache-2.0', not {LICENSE!r} (optionally followed by AND "
                    f'and one of {", ".join(NOTICE_LICENSES)})',
                    '[lints] does not set unsafe_op_in_unsafe_fn', '[lints] does not set missing_docs',
                    'unexpected_cfgs']
        expect('non-fork with the fork license', run(fork_file=Path(tmp) / 'absent.toml'), non_fork)
        expect('no fork file argument', run(fork_file=None), non_fork)
        (root / 'Cargo.toml').write_text(manifest.replace('name = "forked"', 'name = "other"'))
        notes = []
        expect('another crate beside the fork', findings(root, False, fork_file, fetch, notes),
               non_fork)
        expect('another crate is told why', notes,
               ["other is not upstream's forked, so it is checked as usual"])
        (root / 'Cargo.toml').write_text(manifest)

        # A broken declaration is a finding, and the crate is checked as usual beside it.
        for label, text, first in (
                ('short commit', declaration.replace(commit, 'b' * 12),
                 f"fork-upstream.toml commit {'b' * 12!r} is not a full 40-hex commit"),
                ('extra key', declaration + 'license = "Apache-2.0"\n',
                 'fork-upstream.toml sets license, which a fork file does not carry'),
                ('no repository', declaration.split('\n', 1)[1],
                 'fork-upstream.toml does not set repository'),
                ('not github', declaration.replace('https://github.com', 'https://example.com'),
                 "fork-upstream.toml repository 'https://example.com/upstream-owner/"
                 "upstream-repository' is not https://github.com/<owner>/<repository>"),
                ('escaping path', declaration.replace('crates/forked', '../forked'),
                 "fork-upstream.toml path '../forked' is not relative inside the repository"),
                ('not toml', 'repository = \n', None)):
            fork_file.write_text(text)
            got = run()
            if first is None:
                expect(f'fork file {label}', got[0].startswith('fork-upstream.toml is not TOML'), True)
            else:
                expect(f'fork file {label}', got[0], first)
            expect(f'fork file {label} checks as usual', got[1:], non_fork)
        fork_file.write_text(declaration)
        got = run(fetch=lambda url: (_ for _ in ()).throw(OSError('offline')))
        expect('upstream unreachable', got[0],
               f'upstream manifest {base}/crates/forked/Cargo.toml could not be read: offline')
        expect('upstream unreachable checks as usual', got[1:], non_fork)
        served[f'{base}/crates/forked/Cargo.toml'] = '[package]\nname = "forked"\n'
        expect('upstream without a license', run()[0],
               f'upstream manifest {base}/crates/forked/Cargo.toml has no license field to keep')


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--manifest-dir', default='.')
    ap.add_argument('--allow-unpublished', action='store_true')
    ap.add_argument('--fork-file', help='a fork declaration; a missing file is not a fork')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    notes = []
    found = findings(args.manifest_dir, args.allow_unpublished, args.fork_file, notes=notes)
    for note in notes:
        print(f'==> standalone: {note}')
    for f in found:
        print(f'standalone: {f}', file=sys.stderr)
    if found:
        print('standalone: this crate does not stand alone yet', file=sys.stderr)
        return 1
    print('==> standalone: the crate stands alone')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
