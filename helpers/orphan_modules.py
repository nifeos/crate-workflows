#!/usr/bin/env python3
"""Every Rust file under src/ sits in the module tree (nife's orphan-file rule, no allowlist).

    python3 orphan_modules.py [--src DIR]...

Roots are `lib.rs`, `main.rs`, `src/bin/*.rs`, `src/bin/*/main.rs`, the integration tests, and every
`#[path = "..."]` a module declaration names. `mod foo;` resolves the way rustc resolves it: to
`foo.rs` or `foo/mod.rs` beside a crate root or a `mod.rs`, and inside a directory named for the
declaring file otherwise (`a.rs` declares `a/b.rs`). Comments and string literals name no module. A `.rs` file that nothing declares is reported: dead on arrival, or a
second binary pretending to be a module, and both readings deserve a pull request comment.

nife keeps an allowlist for its historical strays. A new crate repository starts with none, so
this one has nowhere to hide an entry.
"""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rust_names  # noqa: E402


def module_declarations(text):
    """`(name, path_attribute, inline_dirs)` for every `mod name;` in `text`, read from the tokens
    so a comment, a string or a raw string never names a module. `inline_dirs` lists the inline
    modules around the declaration, whose names are directories on the way to the file."""
    toks = [t for t in rust_names.tokens(text) if t.kind != 'doc']
    found, inline, depth = [], [], 0
    path, i, n = None, 0, len(toks)
    while i < n:
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < n else None
        if t.text == '#' and t.kind == 'punct' and nxt is not None and nxt.text == '[':
            end = rust_names._match(toks, i + 1)
            body = toks[i + 2:end - 1]
            if len(body) >= 3 and body[0].text == 'path' and body[1].text == '=' \
                    and body[2].kind == 'str':
                path = body[2].text
            i = end
            continue
        if t.kind == 'ident' and t.text == 'pub':
            i += 1
            if i < n and toks[i].text == '(' and toks[i].kind == 'punct':
                i = rust_names._match(toks, i)
            continue
        if t.kind == 'ident' and t.text == 'mod' and nxt is not None and nxt.kind == 'ident':
            after = toks[i + 2] if i + 2 < n else None
            if after is not None and after.kind == 'punct' and after.text == ';':
                found.append((nxt.text, path, tuple(name for name, _ in inline)))
            elif after is not None and after.kind == 'punct' and after.text == '{':
                inline.append((nxt.text, depth))
                depth += 1
                i += 3
                path = None
                continue
            path = None
            i += 2
            continue
        if t.kind == 'punct' and t.text == '{':
            depth += 1
        elif t.kind == 'punct' and t.text == '}':
            depth -= 1
            if inline and inline[-1][1] == depth:
                inline.pop()
        path = None
        i += 1
    return found


def children_dir(f, is_root):
    """Where `mod x;` inside `f` looks for `x`: beside a crate root or a `mod.rs`, and inside a
    directory named for the file otherwise (`a.rs` declares `a/b.rs`)."""
    if is_root or f.name == 'mod.rs':
        return f.parent
    return f.parent / f.stem


def roots(root):
    """The crate roots: lib.rs, main.rs, src/bin/*.rs, src/bin/*/main.rs and the integration tests."""
    found = []
    for name in ('lib.rs', 'main.rs'):
        p = root / 'src' / name
        if p.is_file():
            found.append(p)
    bindir = root / 'src' / 'bin'
    if bindir.is_dir():
        found.extend(sorted(bindir.glob('*.rs')))
        found.extend(sorted(bindir.glob('*/main.rs')))
    tests = root / 'tests'
    if tests.is_dir():
        found.extend(sorted(tests.glob('*.rs')))
        found.extend(sorted(tests.glob('*/main.rs')))
    return [p.resolve() for p in found if p.is_file()]


def declared(root):
    """The set of .rs files reachable from the roots, as absolute Path objects."""
    seen = set()
    top = set(roots(root))
    queue = list(top)
    while queue:
        f = queue.pop()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        base = children_dir(f, f in top)
        text = f.read_text(encoding='utf-8', errors='replace')
        for name, path, inline in module_declarations(text):
            if path:
                queue.append((f.parent.joinpath(*inline, path)).resolve())
                continue
            here = base.joinpath(*inline)
            plain = here / (name + '.rs')
            queue.append((plain if plain.is_file() else here / name / 'mod.rs').resolve())
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

    # False orphans: files rustc does reach.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / 'src'
        for d in ('a/b', 'bin/tool', 'm', 'inline'):
            (src / d).mkdir(parents=True)
        (root / 'Cargo.toml').write_text('[package]\nname = "x"\n')
        files = {
            # A child of a non-mod.rs file lives in a directory named for the parent.
            'lib.rs': 'mod a;\nmod m;\nmod one; mod two;\nmod model;\n#[path = "p.rs"] mod p;\n'
                      '#[path = "q.rs"]\n#[cfg(test)]\nmod q;\n/* mod ghost; */\n'
                      'const URL: &str = "http://example.test/*"; mod after;\n'
                      'mod inline { mod deep; }\n',
            'a.rs': 'pub mod b;\n',
            'a/b.rs': 'pub(crate) mod c;\n',
            'a/b/c.rs': '//! grandchild\n',
            'm/mod.rs': 'mod n;\n',
            'm/n.rs': '//! beside mod.rs\n',
            'one.rs': '', 'two.rs': '', 'p.rs': '', 'q.rs': '', 'model.rs': '',
            'bin/tool/main.rs': 'mod helper;\n',
            'bin/tool/helper.rs': '//! a bin directory target\n',
            'bin/flat.rs': 'mod flat_child;\n',
            'bin/flat_child.rs': '//! beside a crate root, not under bin/flat/\n',
            'after.rs': '', 'inline/deep.rs': '',
            'ghost.rs': '//! only a block comment names me\n',
        }
        for name, body in files.items():
            (src / name).write_text(body)
        reach = declared(root)
        orphans = sorted(str(p.relative_to(src)) for p in src.rglob('*.rs') if p.resolve() not in reach)
        expect('only the commented-out module is an orphan', orphans, ['ghost.rs'])
    print('orphan_modules selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
