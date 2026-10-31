#!/usr/bin/env python3
"""Every Rust module under src/ opens with a `//!` doc block, below any inner attributes.

    python3 module_blocks.py FILE...
    python3 module_blocks.py --selftest

Read this header first: it is an adaptation, and it says where it departs from nife.

**What nife holds.** Nife's module-block ratchet requires a provenance block, `Name: ...`, at the
top of every `.rs` file under a `src/` directory, on every document directly under three
directories, and on every `pub` item, and it holds the files without one to a baseline that only
falls. The block records who named the thing and when. A crate repository carries no nife
vocabulary and no provenance blocks (this template's AGENTS.md), so that block cannot be required
here; copying the ratchet would make every crate repository grow nife's naming scheme.

**What the template holds instead.** The rule the ratchet serves: a reader opening any file finds,
before the first item, a block that says what the module is. In a crate repository that block is
the module's own `//!` documentation. A file passes when a `//!` line (or `#![doc = ...]`) appears
before its first item. The block sits below the inner attributes: a `#![...]` line after the
first `//!` line fails, so every file reads attributes first and prose second, which is how nife's
own crate roots are written. Comments (`//`), blank lines and inner attributes may come before the
block; an outer doc comment (`///`), an item or any other code before it ends the search, and the
file fails.

**Scope.** The workflow passes every tracked `.rs` file under the crate's `src/`, which includes
`src/bin/` programs. `missing_docs` already demands the crate root's block; this check extends the
demand to private modules, which that lint skips.

**No baseline.** Nife lists every unblocked file in a baseline and refuses a new one. A new crate
repository starts with none, so the list is empty here and any file without a block fails.

**Not held.** What the block says, and the `pub` items (rustdoc and `missing_docs` read those).

Name: provisional, from the gates lane. Nife's name for the helper is `module_block_ratchet.py`.
The rule above is the lane's reading of a ruling that described it as crate-level doc blocks below
the attributes; nife's helper was the only match found, and it checks naming blocks instead.
"""

import re
import sys


def check(text):
    """None when the file passes; else a sentence saying why it does not."""
    seen_doc = False
    depth = 0           # brackets of an inner attribute that continues over lines
    for raw in text.splitlines():
        line = raw.strip()
        if depth:
            depth = max(depth + line.count('[') - line.count(']'), 0)
            continue
        if not line:
            continue
        if line.startswith('//!'):
            seen_doc = True
            continue
        if line.startswith('///') or line.startswith('/**'):
            break
        if line.startswith('//'):
            continue
        if line.startswith('#!['):
            if re.match(r'#!\[\s*doc\b', line):
                seen_doc = True
            elif seen_doc:
                return 'an inner attribute follows the `//!` block; attributes come first'
            depth = max(line.count('[') - line.count(']'), 0)
            continue
        break
    return None if seen_doc else 'no `//!` block before the first item'


def selftest():
    ok = True

    def expect(label, text, passes):
        nonlocal ok
        got = check(text) is None
        if got != passes:
            ok = False
            print(f'FAIL {label}: passes={got}, wanted {passes} ({check(text)})', file=sys.stderr)

    expect('a block then an item', '//! What this is.\n\npub fn f() {}\n', True)
    expect('attributes then the block', '#![no_std]\n//! What this is.\nfn f() {}\n', True)
    expect('a license comment, then the block', '// SPDX\n\n//! What.\nfn f() {}\n', True)
    expect('a doc attribute is a block', '#![doc = include_str!("../README.md")]\nfn f() {}\n', True)
    expect('a multi-line attribute, then the block',
           '#![cfg_attr(\n    not(test),\n    no_std\n)]\n//! What.\nfn f() {}\n', True)
    expect('two blocks apart still pass', '//! One.\n\n//! Two.\nfn f() {}\n', True)
    expect('no block fails', 'pub fn f() {}\n', False)
    expect('an empty file fails', '', False)
    expect('a block after the first item does not count', 'fn f() {}\n//! Late.\n', False)
    expect('an outer doc first means no module block', '/// An item.\nfn f() {}\n', False)
    expect('a plain comment is no block', '// What this is.\nfn f() {}\n', False)
    expect('an attribute after the block fails', '//! What.\n#![no_std]\nfn f() {}\n', False)
    expect('a multi-line attribute after the block fails',
           '//! What.\n#![cfg_attr(\n    not(test),\n    no_std\n)]\nfn f() {}\n', False)
    print('module_blocks selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    args = argv[1:]
    if '--selftest' in args:
        return selftest()
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    bad = False
    for f in args:
        try:
            text = open(f, encoding='utf-8').read()
        except UnicodeDecodeError:
            continue
        why = check(text)
        if why:
            print(f'module_blocks: {f}: {why}', file=sys.stderr)
            bad = True
    if not bad:
        print(f'==> module blocks: every one of {len(args)} files opens with a `//!` block')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
