#!/usr/bin/env python3
"""Every Rust file under src/ sits in the module tree (nife's orphan-file rule, no allowlist).

    python3 orphan_modules.py [--src DIR]...

Roots are `lib.rs`, `main.rs`, everything under `src/bin/`, and every `#[path = "..."]` a module
declaration names. `mod foo;` resolves to `foo.rs` or `foo/mod.rs` beside the declaring file, the
way rustc resolves it. A `.rs` file that nothing declares is reported: dead on arrival, or a
second binary pretending to be a module, and both readings deserve a pull request comment.

nife keeps an allowlist for its historical strays. A new crate repository starts with none, so
this one has nowhere to hide an entry.
"""

import re
import sys
from pathlib import Path

MOD = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;')
PATH_ATTR = re.compile(r'^\s*#\[\s*path\s*=\s*"([^"]+)"')


def declared(root):
    """The set of .rs files reachable from the roots, as absolute Path objects."""
    seen = set()
    queue = []
    for name in ('lib.rs', 'main.rs'):
        p = root / 'src' / name
        if p.is_file():
            queue.append(p)
    bindir = root / 'src' / 'bin'
    if bindir.is_dir():
        queue.extend(sorted(bindir.glob('*.rs')))
    for tests in sorted(root.glob('tests')):
        queue.extend(p for p in sorted(tests.glob('*.rs')) if p.is_file())
    while queue:
        f = queue.pop()
        f = f.resolve()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        parent = f.parent
        pending = None  # a `#[path]` attribute waits for the `mod` line that follows it
        for raw in f.read_text().splitlines():
            m = PATH_ATTR.match(raw)
            if m:
                pending = m.group(1)
                continue
            m = MOD.match(raw)
            if m:
                name = m.group(1)
                if pending:
                    target = (parent / pending).resolve()
                    pending = None
                else:
                    plain = parent / (name + '.rs')
                    target = (plain if plain.is_file() else parent / name / 'mod.rs').resolve()
                queue.append(target)
            elif raw.strip() and not raw.strip().startswith('//') and pending is not None:
                pending = None  # the attribute decorated something else; drop it
    return seen


def main(argv):
    srcs = []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--selftest':
            return selftest()
        if args[i] == '--src':
            srcs.append(Path(args[i + 1])); i += 2
        else:
            srcs.append(Path(args[i])); i += 1
    if not srcs:
        srcs = [Path('.')]
    bad = False
    for root in srcs:
        if not (root / 'Cargo.toml').is_file():
            print(f'orphan_modules: no Cargo.toml in {root}', file=sys.stderr)
            bad = True
            continue
        reach = declared(root)
        for p in sorted((root / 'src').rglob('*.rs')):
            if p.resolve() not in reach:
                print(f'orphan_modules: {p} is in no module tree', file=sys.stderr)
                bad = True
    if not bad:
        print('==> orphan modules: every Rust file is declared')
    return 1 if bad else 0


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
        (root / 'src').mkdir(parents=True)
        (root / 'Cargo.toml').write_text('[package]\nname = "x"\n')
        (root / 'src' / 'lib.rs').write_text('mod a;\npub mod b;\n#[path = "renamed.rs"]\nmod c;\n')
        (root / 'src' / 'a.rs').write_text('//! a\n')
        (root / 'src' / 'b.rs').write_text('//! b\n')
        (root / 'src' / 'renamed.rs').write_text('//! c\n')
        (root / 'src' / 'orphan.rs').write_text('//! nobody declares me\n')
        reach = declared(root)
        expect('three declared', len(reach), 4)
        orphans = sorted(p.name for p in (root / 'src').rglob('*.rs') if p.resolve() not in reach)
        expect('one orphan', orphans, ['orphan.rs'])
        (root / 'tests').mkdir()
        (root / 'tests' / 'it.rs').write_text('//! an integration test is its own root\n')
        expect('integration test is a root', 'it.rs' in [p.name for p in declared(root)], True)
    print('orphan_modules selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
