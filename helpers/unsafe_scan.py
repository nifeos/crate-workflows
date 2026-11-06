#!/usr/bin/env python3
"""helpers/unsafe_scan.py CRATE_DIR: refuse a crate whose shipped source contains `unsafe`.

The weekly fuzz job publishes crash inputs where any signed-in GitHub user can read them, so it is
safe only for a crate in which a crash is a panic or a hang and never a memory-safety flaw. This is
the check that holds that line: it exits 1, naming every file and line, when src/**/*.rs has the
keyword `unsafe` (a block, fn, impl, trait, extern block or attribute) outside `#[cfg(test)]`.

Why a scan and not `cargo geiger`: geiger is a heavy install on every run, counts dependencies this
rule does not judge, and cannot be proven offline. This scan is the standard library alone and runs
in script/lint against fixtures. It is token-aware: comments (nested block comments too), string,
raw string, byte string and character literals are blanked before the search, so the word in a
comment or a string never counts, while a lifetime is not mistaken for a character literal.

`#![forbid(unsafe_code)]` at the top of every crate root (lib.rs, main.rs, bin/*.rs) passes the
crate without a search, since the compiler then refuses any `unsafe` in it. Fuzz targets and
dependencies are out of scope. A cfg other than exactly `cfg(test)` is not treated as test code,
so the scan errs toward refusing.

Exit codes: 0 clean; 1 `unsafe` found; 2 a mistake in the arguments or no source to read.
"""
import os
import re
import sys

RAW_OR_PLAIN = re.compile(r'(?:[bc]?r(#*)"|[bc]?")')
IDENT = re.compile(r'r#[A-Za-z_]\w*|[A-Za-z_]\w*')
CFG_TEST = re.compile(r'#\s*(!?)\s*\[\s*cfg\s*\(\s*test\s*\)\s*\]')
FORBID = re.compile(r'#\s*!\s*\[\s*forbid\s*\(\s*unsafe_code\s*\)\s*\]')
ATTR = re.compile(r'\s*#\s*!?\s*\[')


def blank(src):
    """Return src with comments and literals replaced by spaces; newlines stay, so lines hold."""
    out = list(src)
    n = len(src)

    def wipe(a, b):
        for k in range(a, min(b, n)):
            if out[k] != '\n':
                out[k] = ' '

    i = 0
    while i < n:
        c = src[i]
        prev_ident = i > 0 and (src[i - 1].isalnum() or src[i - 1] == '_')
        if src.startswith('//', i):
            j = src.find('\n', i)
            j = n if j < 0 else j
            wipe(i, j)
            i = j
        elif src.startswith('/*', i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith('/*', j):
                    depth, j = depth + 1, j + 2
                elif src.startswith('*/', j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            wipe(i, j)
            i = j
        elif not prev_ident and (m := RAW_OR_PLAIN.match(src, i)):
            hashes = m.group(1)
            j = m.end()
            if hashes is not None:
                end = src.find('"' + hashes, j)
                j = n if end < 0 else end + 1 + len(hashes)
            else:
                while j < n and src[j] != '"':
                    j += 2 if src[j] == '\\' else 1
                j += 1
            wipe(i, j)
            i = j
        elif c == "'":
            if src.startswith("'\\", i):
                j = src.find("'", i + 3)
                j = n if j < 0 else j + 1
                wipe(i, j)
                i = j
            elif i + 2 < n and src[i + 2] == "'":
                wipe(i, i + 3)
                i += 3
            else:
                i += 1  # a lifetime
        else:
            i += 1
    return ''.join(out)


def skip_balanced(text, i, open_c, close_c):
    depth = 0
    while i < len(text):
        if text[i] == open_c:
            depth += 1
        elif text[i] == close_c:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def drop_test_items(text):
    """Blank every item under #[cfg(test)] (and the whole text after an inner #![cfg(test)])."""
    out = list(text)
    for m in CFG_TEST.finditer(text):
        if m.group(1):
            end = len(text)
        else:
            i = m.end()
            while (a := ATTR.match(text, i)):
                i = skip_balanced(text, a.end() - 1, '[', ']')
            depth = 0
            while i < len(text):
                c = text[i]
                if c in '([':
                    depth += 1
                elif c in ')]':
                    depth -= 1
                elif c == '{' and depth == 0:
                    i = skip_balanced(text, i, '{', '}')
                    break
                elif c == ';' and depth == 0:
                    i += 1
                    break
                i += 1
            end = i
        for k in range(m.start(), end):
            if out[k] != '\n':
                out[k] = ' '
    return ''.join(out)


def code_of(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return drop_test_items(blank(f.read()))


def find_unsafe(code):
    hits = []
    for m in IDENT.finditer(code):
        if m.group(0) == 'unsafe':
            hits.append(code.count('\n', 0, m.start()) + 1)
    return hits


def roots_of(src):
    roots = [os.path.join(src, n) for n in ('lib.rs', 'main.rs')]
    bindir = os.path.join(src, 'bin')
    if os.path.isdir(bindir):
        for n in sorted(os.listdir(bindir)):
            p = os.path.join(bindir, n)
            roots.append(os.path.join(p, 'main.rs') if os.path.isdir(p) else p)
    return [r for r in roots if r.endswith('.rs') and os.path.isfile(r)]


def main(argv):
    if len(argv) != 2:
        print('usage: unsafe_scan.py CRATE_DIR', file=sys.stderr)
        return 2
    src = os.path.join(argv[1], 'src')
    files = sorted(os.path.join(d, f) for d, _, fs in os.walk(src) for f in fs if f.endswith('.rs'))
    if not files:
        print(f'unsafe-scan: no Rust source under {src}, so the crate cannot be judged', file=sys.stderr)
        return 2
    roots = roots_of(src)
    if roots and all(FORBID.search(code_of(r)) for r in roots):
        print('unsafe-scan: ok, every crate root has #![forbid(unsafe_code)]')
        return 0
    found = 0
    for path in files:
        for line in find_unsafe(code_of(path)):
            found += 1
            print(f'{path}:{line}: `unsafe` in shipped source')
            if os.environ.get('GITHUB_ACTIONS'):
                print(f'::error file={path},line={line}::`unsafe` in shipped source; '
                      'the weekly fuzz job publishes crash inputs, so it runs only for safe-Rust crates')
    if found:
        print(f'unsafe-scan: {found} use(s) of `unsafe`; refused', file=sys.stderr)
        return 1
    print('unsafe-scan: ok, no `unsafe` outside tests')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
