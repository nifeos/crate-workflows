#!/usr/bin/env python3
"""Hold the badge row under a crate README's title: present, in order, and true to the repository.

    python3 readme_badges.py [--crate-dir DIR] [--repository OWNER/NAME]
                             [--workflows-dir .github/workflows] [--published unknown|yes|no|lookup]
                             [--published-only] [--report-only] [--summary FILE]
    python3 readme_badges.py --add-published [--crate-dir DIR] [--repository OWNER/NAME]
    python3 readme_badges.py --selftest

A reader who opens the repository page sees, before the first sentence, whether the main branch
is green, whether its proofs hold, what license it carries and which Rust it needs. The row is a
block of `[![<alt>](<image>)](<link>)` lines directly under the `# <package name>` title, then a
blank line, then the summary. Markdown joins the lines into one row.

| alt | image | link | |
|---|---|---|---|
| `crates.io` | `img.shields.io/crates/v/<name>.svg` | `crates.io/crates/<name>` | once published |
| `docs.rs` | `img.shields.io/docsrs/<name>` | `docs.rs/<name>` | once published |
| `check` | the caller of `check.yml`, its Actions badge on `main` | that workflow's runs on `main` | required |
| `proofs` | the caller of `proofs.yml`, the same | the same | required |
| `license` | `img.shields.io/badge/license-<license>-blue.svg` | the README's `## License` | required |
| `minimum Rust version` | `img.shields.io/badge/rust-<rust-version>%2B-blue.svg` | the crate's `Cargo.toml` on `main` | required |

**What it reads.** The README at the crate root; the crate's `Cargo.toml` (`name`, `license`,
`rust-version`); and the workflows under `--workflows-dir`, to find which file calls the shared
`check.yml` and which calls `proofs.yml`. The repository is `--repository`, else
`$GITHUB_REPOSITORY`, else the `repository` URL in `Cargo.toml`.

**What it reports.** No row directly under the title; a badge that is not in the table (images
come only from the repository's own Actions badges and img.shields.io, so no tracking service);
a badge whose image or link is not the exact form above for this repository, which catches a link
to another repository and a minimum-Rust-version badge that disagrees with `rust-version`; a
required badge that is missing; one listed twice or out of order; a badge line elsewhere in the
README; and the two crates.io badges alone without each other.

**Published or not.** crates.io and docs.rs answer "not found" for a crate that was never
published, so their badges wait for the first publish. `--published unknown` (the default, which
`check` uses, offline) accepts the pair or neither. `yes` requires the pair and `no` refuses it;
`lookup` asks the crates.io API and is `yes` on 200, `no` on 404, and a failure otherwise. The
weekly workflow runs `--published lookup --published-only`, which judges only the pair. After the
first publish, `--add-published` writes the pair at the head of the row, once.

**Exit.** 1 on a finding, 0 with `--report-only` whatever it finds, 2 on a README or manifest that
cannot be read or a lookup that fails.

Name: provisional, from the README badges lane.
"""
import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import readme_documents  # noqa: E402

LABEL = 'readme_badges'
BADGE = re.compile(r'\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)')
BADGE_LINE = re.compile(r'^\s*(?:\[!\[[^\]]*\]\([^)\s]+\)\]\([^)\s]+\)\s*)+$')
FENCE = re.compile(r'\s*(```|~~~)')
PUBLISHED = ('crates.io', 'docs.rs')
ORDER = PUBLISHED + ('check', 'proofs', 'license', 'minimum Rust version')
ALLOWED_IMAGE = re.compile(r'^https://(img\.shields\.io/|github\.com/[^/]+/[^/]+/actions/workflows/)')


class Unreadable(Exception):
    """A file the gate needs cannot be read; the message says which."""


def shields(text):
    """A static shields.io badge's text: `-` and `_` doubled, spaces as `%20`."""
    return text.replace('-', '--').replace('_', '__').replace(' ', '%20')


def callers(workflows_dir, reusable):
    """Sorted names of the workflow files that call the shared `reusable` workflow."""
    call = re.compile(r'^\s*uses:\s*(?:\./|[\w.-]+/crate-workflows/)\.github/workflows/%s\b'
                      % re.escape(reusable), re.M)
    directory = Path(workflows_dir)
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.glob('*.y*ml')
                  if p.is_file() and call.search(p.read_text(encoding='utf-8', errors='replace')))


def expected(repository, name, license_, rust_version, check_files, proofs_files, manifest_path='Cargo.toml'):
    """{alt: [(image, link)]}: every form this repository's row may take for each badge."""
    site = f'https://github.com/{repository}'
    out = {
        'crates.io': [(f'https://img.shields.io/crates/v/{name}.svg', f'https://crates.io/crates/{name}')],
        'docs.rs': [(f'https://img.shields.io/docsrs/{name}', f'https://docs.rs/{name}')],
        'license': [(f'https://img.shields.io/badge/license-{shields(license_ or "")}-blue.svg',
                     f'{site}#license')],
        'minimum Rust version': [(f'https://img.shields.io/badge/rust-{shields(rust_version or "")}%2B-blue.svg',
                                  f'{site}/blob/main/{manifest_path}')],
    }
    for alt, files in (('check', check_files), ('proofs', proofs_files)):
        out[alt] = [(f'{site}/actions/workflows/{f}/badge.svg?branch=main',
                     f'{site}/actions/workflows/{f}?query=branch%3Amain') for f in files]
    return out


def row_of(text):
    """(title line, [(line, alt, image, link)] of the row, [lines of badge lines outside it])."""
    lines = text.split('\n')
    title = next((n for n, line in enumerate(lines, 1) if line.strip()), None)
    if title is None or not lines[title - 1].startswith('# '):
        return None, [], []
    n = title
    while n < len(lines) and not lines[n].strip():
        n += 1
    row, outside, fence = [], [], None
    while n < len(lines) and BADGE_LINE.match(lines[n]):
        row += [(n + 1, *m.groups()) for m in BADGE.finditer(lines[n])]
        n += 1
    for k in range(n, len(lines)):
        mark = FENCE.match(lines[k])
        if mark:
            fence = None if fence == mark.group(1) else (fence or mark.group(1))
        elif not fence and BADGE_LINE.match(lines[k]):
            outside.append(k + 1)
    return title, row, outside


def findings(text, manifest, repository, check_files, proofs_files, published='unknown', published_only=False,
             manifest_path='Cargo.toml'):
    """[(line, message)] for one README; `manifest` is the parsed `[package]` table."""
    name = manifest.get('name')
    license_ = manifest.get('license')
    rust_version = manifest.get('rust-version')
    out = []
    if not published_only:
        for key, value in (('name', name), ('license', license_), ('rust-version', rust_version)):
            if not isinstance(value, str) or not value:
                out.append((1, f'Cargo.toml has no `{key}`, which the row reads'))
        if not repository:
            out.append((1, 'no repository: pass --repository, or set `repository` in Cargo.toml'))
        if not check_files:
            out.append((1, 'no workflow under the workflows directory calls the shared check.yml'))
        if not proofs_files:
            out.append((1, 'no workflow under the workflows directory calls the shared proofs.yml'))
    title, row, outside = row_of(text)
    if title is None:
        return sorted(out + [(1, 'the README does not open with a `# <package name>` title')])
    if not row:
        if not published_only:
            out.append((title + 1, 'no badge row directly under the title: copy the row in the scaffold\'s '
                                   'README-crate.md, with this repository\'s name'))
            out += [(line, 'a badge line outside the row under the title') for line in outside]
        if published == 'yes':
            out.append((title + 1, 'the crate is on crates.io: add the crates.io and docs.rs badges '
                                   '(readme_badges.py --add-published)'))
        return sorted(out)
    forms = expected(repository or '', name or '', license_, rust_version, check_files, proofs_files, manifest_path)
    seen, last = {}, -1
    for line, alt, image, link in row:
        if published_only and alt not in PUBLISHED:
            continue
        if alt not in forms:
            why = ('its image is not the repository\'s own Actions badge or img.shields.io; '
                   if not ALLOWED_IMAGE.match(image) else '')
            out.append((line, f'a `{alt}` badge, which the row does not carry ({why}the row is '
                              + ', '.join(f'`{a}`' for a in ORDER) + ')'))
            continue
        if alt in seen:
            out.append((line, f'the `{alt}` badge appears twice (first at line {seen[alt]})'))
            continue
        seen[alt] = line
        if ORDER.index(alt) < last:
            out.append((line, f'the `{alt}` badge comes after `{ORDER[last]}`; the order is '
                              + ', '.join(f'`{a}`' for a in ORDER)))
        last = max(last, ORDER.index(alt))
        if not forms[alt]:
            continue
        want_image, want_link = forms[alt][0]
        if (image, link) in forms[alt]:
            continue
        if alt == 'minimum Rust version' and image != want_image:
            shown = re.search(r'/rust-(.*?)%2B-', image)
            out.append((line, f'the minimum Rust version badge says {shown.group(1) if shown else image!r} '
                              f'but Cargo.toml\'s rust-version is {rust_version!r}: write {want_image}'))
        elif image not in [i for i, _ in forms[alt]]:
            out.append((line, f'the `{alt}` badge\'s image is {image}; write {want_image}'))
        if link not in [k for _, k in forms[alt]]:
            out.append((line, f'the `{alt}` badge links {link}; write {want_link}'))
    if not published_only:
        for alt in ORDER[len(PUBLISHED):]:
            if alt not in seen:
                out.append((row[0][0], f'the row has no `{alt}` badge'))
        for line in outside:
            out.append((line, 'a badge line outside the row under the title'))
    has = [alt for alt in PUBLISHED if alt in seen]
    if published == 'yes' and len(has) < 2:
        out.append((row[0][0], 'the crate is on crates.io: add the crates.io and docs.rs badges '
                               '(readme_badges.py --add-published)'))
    elif published == 'no' and has:
        out.append((seen[has[0]], 'the crate is not on crates.io, so its crates.io and docs.rs badges '
                                  'render "not found"; add them after the first publish'))
    elif published == 'unknown' and len(has) == 1:
        out.append((seen[has[0]], 'the crates.io and docs.rs badges come as a pair'))
    return sorted(out)


def add_published(text, name):
    """The README with the crates.io and docs.rs badges at the head of the row; unchanged if present."""
    title, row, _ = row_of(text)
    if title is None or any(alt in PUBLISHED for _, alt, _, _ in row):
        return text
    forms = expected('', name, '', '', [], [])
    pair = [f'[![{alt}]({forms[alt][0][0]})]({forms[alt][0][1]})' for alt in PUBLISHED]
    lines = text.split('\n')
    at = row[0][0] - 1 if row else title
    if not row:
        pair = [''] + pair
    return '\n'.join(lines[:at] + pair + lines[at:])


def read_manifest(crate_dir):
    path = Path(crate_dir, 'Cargo.toml')
    try:
        return tomllib.loads(path.read_text(encoding='utf-8')).get('package', {})
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise Unreadable(f'{path}: {error}') from error


def manifest_link(crate_dir):
    """The manifest's path in the repository, from the checkout root; a crate directory outside the
    checkout (a fixture) is linked as a manifest at the root."""
    path = Path(os.path.relpath(Path(crate_dir, 'Cargo.toml'))).as_posix()
    return 'Cargo.toml' if path.startswith('../') else path


def repository_of(given, manifest):
    if given:
        return given
    if os.environ.get('GITHUB_REPOSITORY'):
        return os.environ['GITHUB_REPOSITORY']
    m = re.match(r'^https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$', manifest.get('repository') or '')
    return m.group(1) if m else None


def run(argv, lookup=None):
    parser = argparse.ArgumentParser(prog='readme_badges.py')
    parser.add_argument('--crate-dir', default='.')
    parser.add_argument('--repository')
    parser.add_argument('--workflows-dir', default='.github/workflows')
    parser.add_argument('--published', choices=('unknown', 'yes', 'no', 'lookup'), default='unknown')
    parser.add_argument('--published-only', action='store_true')
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--add-published', action='store_true')
    parser.add_argument('--summary')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    readme = readme_documents.readme_path(args.crate_dir)
    try:
        manifest = read_manifest(args.crate_dir)
        if readme is None:
            raise Unreadable(f'{args.crate_dir}: no README')
        text = readme.read_text(encoding='utf-8')
    except (Unreadable, OSError) as error:
        print(f'{LABEL}: {error}', file=sys.stderr)
        return 2
    if args.add_published:
        new = add_published(text, manifest.get('name', ''))
        if new != text:
            readme.write_text(new, encoding='utf-8')
        print(f'{LABEL}: {readme}: ' + ('added the crates.io and docs.rs badges' if new != text
                                         else 'the crates.io and docs.rs badges are already there'))
        return 0
    published = args.published
    if published == 'lookup':
        if lookup is None:
            import publish_mode
            lookup = publish_mode.crate_exists
        try:
            published = 'yes' if lookup(manifest.get('name', '')) else 'no'
        except Exception as error:  # noqa: BLE001 (any failure to look is one failure to report)
            print(f'{LABEL}: could not tell whether {manifest.get("name")} is on crates.io ({error})',
                  file=sys.stderr)
            return 2
    found = findings(text, manifest, repository_of(args.repository, manifest),
                     callers(args.workflows_dir, 'check.yml'), callers(args.workflows_dir, 'proofs.yml'),
                     published, args.published_only, manifest_link(args.crate_dir))
    lines = [f'{readme}:{n}: {message}' for n, message in found]
    mode = ' (report only)' if args.report_only else ''
    lines.append(f'{LABEL}: {len(found)} badge-row findings{mode}; crates.io: {published}')
    print('\n'.join(lines))
    if args.summary:
        with open(args.summary, 'a', encoding='utf-8') as summary:
            summary.write(f'### README badge row{mode}\n\n{lines[-1]}\n\n')
            if found:
                summary.write('```\n' + '\n'.join(lines[:-1]) + '\n```\n')
    return 0 if args.report_only or not found else 1


REPO = 'owner/example'
SITE = f'https://github.com/{REPO}'
MANIFEST = {'name': 'example', 'license': 'MIT OR Apache-2.0', 'rust-version': '1.88'}
ROW = f'''[![check]({SITE}/actions/workflows/ci.yml/badge.svg?branch=main)]({SITE}/actions/workflows/ci.yml?query=branch%3Amain)
[![proofs]({SITE}/actions/workflows/proofs.yml/badge.svg?branch=main)]({SITE}/actions/workflows/proofs.yml?query=branch%3Amain)
[![license](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)]({SITE}#license)
[![minimum Rust version](https://img.shields.io/badge/rust-1.88%2B-blue.svg)]({SITE}/blob/main/Cargo.toml)
'''
PAIR = '''[![crates.io](https://img.shields.io/crates/v/example.svg)](https://crates.io/crates/example)
[![docs.rs](https://img.shields.io/docsrs/example)](https://docs.rs/example)
'''
GOOD = f'# example\n\n{ROW}\nOne line.\n\n## EXAMPLES\n\n```markdown\n[![x](https://a.example/x.svg)](https://a.example)\n```\n'


def selftest():
    import contextlib
    import io
    import tempfile
    failed = []

    def expect(label, text, want, published='unknown', only=False, manifest=MANIFEST):
        got = [m for _, m in findings(text, manifest, REPO, ['ci.yml'], ['proofs.yml'], published, only)]
        if len(got) != len(want) or not all(any(w in g for g in got) for w in want):
            failed.append(f'{label}: gave {got}, wanted {want}')

    expect('the row', GOOD, [])
    expect('the row with the published pair', GOOD.replace(ROW, PAIR + ROW), [])
    expect('no row', GOOD.replace(ROW, ''), ['no badge row directly under the title'])
    expect('a paragraph before the row', GOOD.replace(ROW, 'Text.\n\n' + ROW),
           ['no badge row directly under the title', 'outside the row', 'outside the row',
            'outside the row', 'outside the row'])
    expect('another repository', GOOD.replace(f'{SITE}/actions/workflows/ci.yml?',
                                              'https://github.com/other/repo/actions/workflows/ci.yml?'),
           ['the `check` badge links https://github.com/other/repo/'])
    expect('another repository\'s image', GOOD.replace(f'{SITE}/actions/workflows/proofs.yml/badge',
                                                       'https://github.com/other/repo/actions/workflows/proofs.yml/badge'),
           ['the `proofs` badge\'s image is https://github.com/other/repo/'])
    expect('a stale minimum Rust version', GOOD.replace('rust-1.88%2B', 'rust-1.85%2B'),
           ["says '1.85' but Cargo.toml's rust-version is '1.88'"])
    expect('a missing badge', GOOD.replace(ROW.split('\n')[1] + '\n', ''), ['the row has no `proofs` badge'])
    expect('out of order', GOOD.replace(ROW, '\n'.join(ROW.split('\n')[1::-1] + ROW.split('\n')[2:])),
           ['the `check` badge comes after `proofs`'])
    expect('twice', GOOD.replace(ROW, ROW + ROW.split('\n')[0] + '\n'), ['the `check` badge appears twice'])
    expect('a tracking badge', GOOD.replace(ROW, ROW + '[![coverage](https://codecov.io/x.svg)](https://codecov.io/x)\n'),
           ["a `coverage` badge, which the row does not carry (its image is not the repository's own"])
    expect('half the pair', GOOD.replace(ROW, PAIR.split('\n')[0] + '\n' + ROW), ['come as a pair'])
    expect('published, no pair', GOOD, ['the crate is on crates.io'], published='yes')
    expect('published, the pair', GOOD.replace(ROW, PAIR + ROW), [], published='yes')
    expect('unpublished, the pair', GOOD.replace(ROW, PAIR + ROW), ['the crate is not on crates.io'], published='no')
    expect('published-only ignores the rest', GOOD.replace(ROW, ''), [], published='no', only=True)
    expect('published-only, no row', GOOD.replace(ROW, ''), ['the crate is on crates.io'], published='yes', only=True)
    expect('no rust-version', GOOD, ['Cargo.toml has no `rust-version`', 'the minimum Rust version badge says'],
           manifest={k: v for k, v in MANIFEST.items() if k != 'rust-version'})
    if [m for _, m in findings(GOOD.replace('main/Cargo.toml', 'main/sub/Cargo.toml'), MANIFEST, REPO, ['ci.yml'],
                               ['proofs.yml'], manifest_path='sub/Cargo.toml')]:
        failed.append('a crate below the root does not link its own manifest')
    if add_published(GOOD, 'example') != GOOD.replace(ROW, PAIR + ROW):
        failed.append('add_published does not put the pair at the head of the row')
    if add_published(GOOD.replace(ROW, PAIR + ROW), 'example') != GOOD.replace(ROW, PAIR + ROW):
        failed.append('add_published is not idempotent')
    if [m for _, m in findings(add_published(GOOD.replace(ROW, ''), 'example'), MANIFEST, REPO, ['ci.yml'],
                               ['proofs.yml'], 'yes', True)]:
        failed.append('add_published on a README without a row leaves a finding for the pair')
    with tempfile.TemporaryDirectory() as scratch, contextlib.redirect_stdout(io.StringIO()) as out, \
            contextlib.redirect_stderr(io.StringIO()):
        crate, flows = Path(scratch, 'crate'), Path(scratch, 'flows')
        crate.mkdir()
        flows.mkdir()
        (crate / 'Cargo.toml').write_text('[package]\nname = "example"\nlicense = "MIT OR Apache-2.0"\n'
                                          'rust-version = "1.88"\nrepository = "https://github.com/owner/example"\n')
        (crate / 'README.md').write_text(GOOD)
        (flows / 'ci.yml').write_text('jobs:\n  check:\n    uses: owner/crate-workflows/.github/workflows/check.yml@0\n')
        (flows / 'proofs.yml').write_text('jobs:\n  proofs:\n    uses: ./.github/workflows/proofs.yml\n')
        base = ['--crate-dir', str(crate), '--workflows-dir', str(flows), '--repository', REPO]
        if run(base) != 0:
            failed.append(f'the good crate fails: {out.getvalue()!r}')
        (crate / 'README.md').write_text(GOOD.replace('rust-1.88', 'rust-1.80'))
        if run(base) != 1 or run(base + ['--report-only']) != 0:
            failed.append('a finding does not fail, or fails under --report-only')
        (crate / 'README.md').write_text(GOOD)
        if run(base + ['--published', 'lookup'], lookup=lambda name: True) != 1:
            failed.append('a published crate without the pair passes the lookup')
        if run(base + ['--published', 'lookup'], lookup=lambda name: False) != 0:
            failed.append('an unpublished crate without the pair fails the lookup')

        def broken(name):
            raise OSError('offline')
        if run(base + ['--published', 'lookup'], lookup=broken) != 2:
            failed.append('a failed lookup is not exit 2')
        run(base + ['--add-published'])
        if run(base + ['--published', 'yes']) != 0:
            failed.append('--add-published does not satisfy --published yes')
        (flows / 'ci.yml').unlink()
        if run(base) != 1:
            failed.append('a repository without a caller of check.yml passes')
    for message in failed:
        print(f'{LABEL} selftest: FAIL {message}', file=sys.stderr)
    print(f'{LABEL} selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
