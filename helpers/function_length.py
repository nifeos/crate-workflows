#!/usr/bin/env python3
"""A Rust function stays at 100 code lines, counted the way clippy's `too_many_lines` counts (nife's limit).

    python3 function_length.py [--limit 100] [--all] [--exemptions FILE] FILE...
    python3 function_length.py --selftest

Nife holds every function to 100 code lines, which is clippy's `too_many_lines` at its default
threshold. That lint is in clippy's pedantic group, so this template's `-D warnings` run never
turns it on; this script is the text derivation of the same count, and it needs no compiler. The
100 is nife's number (`--limit` exists for the selftest).

**The count is clippy's, line for line.** Take the body's source text, drop its outer braces, trim
it, and count each line that has code on it after leading whitespace and block comments are
skipped. A line that opens with `//` does not count; a line with code before a `//` does, and a
`//` inside a string literal ends the line's code there too. Blank lines never count. A block
that a `#[cfg]` removes from one target still counts, because clippy reads source text. Closures
are not functions here: their lines count in the function around them. A function of exactly 100
code lines passes and 101 fails.

**Which functions.** Every `fn` with a body in every file passed: library code, tests, benches,
examples and items under `#[cfg(test)]` alike. A `fn` written inside a `macro_rules!` body is
skipped, because clippy reports it at its span in the macro and this scan does not follow macros.

**A function's name** in a report is `Type::name` inside an `impl` (the self type, generics
dropped), `Trait::name` for a trait's default body, `outer::name` for a `fn` inside a `fn`, and the
bare name otherwise.

**No baseline.** Nife holds its already-long functions in a baseline file, one row each, that may
only shrink, and cross-checks this derivation against clippy's saved diagnostics. A new crate
repository starts under the limit, so there is no baseline, and a function over 100 code lines is
a split. There is no cross-check against clippy here either: this count is the only one.

The one exception is code another project owns, which a fork keeps as that project wrote it so its
fixes can go upstream. The caller's `.github/function-length-exemptions` lists such a function as
`<path> <name> <code lines> <reason>`, with the path relative to the repository root, the name as
this script reports it and the count as measured. The function then passes while it is exactly that
long; a different count, or an entry for a function that is not over the limit, fails
(`exemptions_file.py` reads the entries).

The scan is lexer-shaped, not a parser. Comments and literals are blanked first (the same
stripper nife uses for its source censuses), then braces are matched. Block comments do not nest
in the stripper, which Rust's do; a nested one could only add to a count, so it fails loud.

Name: provisional, from the gates lane. The file takes nife's helper name.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exemptions_file  # noqa: E402

DEFAULT_LIMIT = 100

# The comment and literal stripper: a comment block and a multi-line string both become blank
# lines, so what is left counts code lines, a quantity nobody can move by writing prose. The raw
# string body is `.*?` and never an alternation with `\n`, which would backtrack exponentially on
# an unterminated raw string.
_NON_CODE = re.compile(
    r'/\*.*?\*/'                        # block comment
    r'|//[^\n]*'                        # line comment, doc comment included
    r'|r(#*)".*?"\1'                    # raw string, any hash count
    r'|"(?:[^"\\\n]|\\.)*"'             # ordinary string
    r"|'(?:[^'\\]|\\.)'",               # char literal (a lifetime has no closing quote)
    re.S)


def strip_non_code(text):
    """Blank every comment and literal, keeping the line structure."""
    return _NON_CODE.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)


def code_lines(body):
    """`too_many_lines`' count over a body's source text, outer braces included in `body`."""
    if body.startswith('{') and body.endswith('}'):
        body = body[1:-1]
    count, in_comment = 0, False
    for line in body.strip().splitlines():
        code = False
        while True:
            line = line.lstrip()
            if not line:
                break
            if in_comment:
                i = line.find('*/')
                if i >= 0:
                    line = line[i + 2:]
                    in_comment = False
                    continue
            else:
                multi = line.find('/*')
                multi = len(line) if multi < 0 else multi
                single = line.find('//')
                single = len(line) if single < 0 else single
                code |= multi > 0 and single > 0
                if multi < single:
                    line = line[multi + 2:]
                    in_comment = True
                    continue
            break
        count += code
    return count


_FN = re.compile(r'\bfn\s+(r#)?([A-Za-z_]\w*)')
_QUALIFIERS = re.compile(
    r'(?:\bpub(?:\s*\([^)]*\))?|\bconst|\basync|\bunsafe|\bsafe|\bdefault|\bextern(?:\s+"[^"]*")?)\s*$')
_SCOPE = re.compile(r'\b(impl|trait|mod)\b')


def _match_brace(code, i):
    depth = 0
    for k in range(i, len(code)):
        c = code[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return k
    return len(code) - 1


def _body_open(code, start):
    """Index of the `{` that opens a fn body, or None for a declaration ending in `;`."""
    depth = 0
    for k in range(start, len(code)):
        c = code[k]
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif depth == 0 and c == ';':
            return None
        elif depth == 0 and c == '{':
            return k
    return None


def _impl_name(header):
    """The self type of an `impl` or the name of a `trait`, from its header text."""
    header = ' '.join(header.split())
    m = re.match(r'(?:unsafe\s+)?trait\s+(\w+)', header)
    if m:
        return m.group(1)
    header = re.sub(r'^(?:unsafe\s+)?impl\s*', '', header)
    header = re.sub(r'\bwhere\b.*$', '', header)
    if header.startswith('<'):
        depth = 0
        for k, c in enumerate(header):
            depth += (c == '<') - (c == '>')
            if depth == 0:
                header = header[k + 1:]
                break
    if re.search(r'\bfor\b', header):
        header = re.split(r'\bfor\b', header, maxsplit=1)[1]
    header = header.strip().lstrip('&').strip()
    header = re.sub(r"^'\w+\s+", '', header)
    header = re.sub(r'^(?:mut|dyn)\s+', '', header)
    name = re.split(r'[<\s{(]', header, maxsplit=1)[0]
    return name.split('::')[-1] or '?'


def functions(text):
    """[(name, start_line, code_lines)] for every fn with a body in one file's source text."""
    code = strip_non_code(text)
    scopes = []  # (open, close, kind, name)
    for m in re.finditer(r'\bmacro_rules!\s*\w+\s*([{(\[])', code):
        o = m.end() - 1
        closer = {'{': '}', '(': ')', '[': ']'}[code[o]]
        depth = 0
        for k in range(o, len(code)):
            depth += (code[k] == code[o]) - (code[k] == closer)
            if depth == 0:
                scopes.append((o, k, 'macro', ''))
                break
    for m in _SCOPE.finditer(code):
        kind = m.group(1)
        if kind == 'mod':
            continue
        line_start = code.rfind('\n', 0, m.start()) + 1
        before = code[line_start:m.start()]
        if before.strip() not in ('', 'unsafe', 'pub', 'pub(crate)', 'pub unsafe', 'default'):
            continue
        o = _body_open(code, m.end())
        if o is None:
            continue
        scopes.append((o, _match_brace(code, o), kind, _impl_name(code[m.start():o])))

    fns = []
    for m in _FN.finditer(code):
        o = _body_open(code, m.end())
        if o is None:
            continue
        if any(a < m.start() < b for a, b, kind, _ in scopes if kind == 'macro'):
            continue
        fns.append((m, o, _match_brace(code, o)))
    found = []
    for m, o, close in fns:
        owner = None
        for a, b, kind, name in scopes:
            if kind != 'macro' and a < m.start() < b and (owner is None or a > owner[0]):
                owner = (a, name)
        outer = None
        for m2, o2, c2 in fns:
            if o2 < m.start() < c2 and (outer is None or o2 > outer[0]):
                outer = (o2, m2.group(2))
        name = m.group(2)
        if outer and (owner is None or outer[0] > owner[0]):
            name = f'{outer[1]}::{name}'
        elif owner:
            name = f'{owner[1]}::{name}'
        # The item's first qualifier, which is where clippy's span starts.
        s = m.start()
        while True:
            q = _QUALIFIERS.search(text[:s])
            if not q or q.end() != s and text[q.end():s].strip():
                break
            if q.start() == s:
                break
            s = q.start()
        found.append((name, text.count('\n', 0, s) + 1, code_lines(text[o:close + 1])))
    return found


def selftest():
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    def fn(n, extra=''):
        return 'fn long() {\n' + '    work();\n' * n + extra + '}\n'

    def longest(text):
        return max((n for _name, _line, n in functions(text)), default=0)

    expect('100 lines is the limit', longest(fn(100)), 100)
    expect('101 lines is over', longest(fn(101)) > DEFAULT_LIMIT, True)
    expect('blank lines do not count', longest(fn(3, '\n\n\n')), 3)
    expect('a line comment does not count', longest(fn(3, '    // a note\n')), 3)
    expect('a doc comment inside does not count', longest(fn(3, '    /// a note\n')), 3)
    expect('code before a comment counts', longest(fn(3, '    work(); // why\n')), 4)
    expect('a block comment does not count',
           longest(fn(3, '    /* one\n       two */\n')), 3)
    expect('code after a block comment counts', longest(fn(3, '    /* c */ work();\n')), 4)
    expect('a slash pair inside a string is code', longest(fn(2, '    let u = "a // b";\n')), 3)
    expect('a multi-line string counts every line, as clippy reads source',
           longest('fn f() {\n    let s = "one\ntwo\nthree";\n}\n'), 3)
    expect('a closure counts in its function', longest('fn f() {\n    let c = |x| {\n        x\n    };\n}\n'), 3)
    expect('a declaration without a body is no function', functions('trait T { fn f(); }\n'), [])
    expect('a macro body is skipped',
           functions('macro_rules! m { () => { fn inner() { a(); } } }\n'), [])
    names = [n for n, _l, _c in functions(
        'struct S;\nimpl<T> S<T> {\n    pub fn a(&self) { b(); }\n}\n'
        'trait Tr {\n    fn d() { e(); }\n}\nfn outer() {\n    fn inner() { x(); }\n}\n')]
    expect('names', names, ['S::a', 'Tr::d', 'outer', 'outer::inner'])
    expect('the start line is the qualifier',
           functions('\n\npub(crate) const unsafe fn g() { h(); }\n')[0][1], 3)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'long.rs'
        source.write_text(fn(4) + 'fn short() {\n    a();\n}\n')
        path = exemptions_file.normal_path(str(source))
        expect('a function over the limit fails', findings([str(source)], 3, {}),
               ([f'{path}:1 long is 4 code lines, over the 3-line limit'], []))
        held = {(path, 'long'): {'code_lines': 4, 'line': 1}}
        expect('an exemption at the measured count passes', findings([str(source)], 3, held),
               ([], [(path, 'long')]))
        expect('a function that grew past its exemption fails',
               findings([str(source)], 3, {(path, 'long'): {'code_lines': 3, 'line': 1}})[0],
               [f'{path} long is 4 code lines, but its exemption (function-length-exemptions:1) '
                'records 3; an exemption holds the length it was written for'])
        expect('an exemption for a function within the limit fails',
               findings([str(source)], 3, {**held, (path, 'short'): {'code_lines': 1, 'line': 2}})[0],
               [f'function-length-exemptions:2: {path} short is not over the limit in this run; '
                'remove the entry'])
    print('function_length selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def findings(files, limit, entries, name='function-length-exemptions', show_all=False):
    """`([finding], [kept (path, name)])` for the files, with the exemption entries applied."""
    over, shown = {}, []
    for f in files:
        try:
            text = open(f, encoding='utf-8').read()
        except UnicodeDecodeError:
            continue
        path = exemptions_file.normal_path(f)
        for fn_name, start, n in functions(text):
            if n > limit:
                over[(path, fn_name)] = (n, start)
            elif show_all:
                print(f'{n}\t{f}:{start}\t{fn_name}')
    measured = {key: n for key, (n, _start) in over.items()}
    unexempted, found, kept = exemptions_file.length_verdicts(
        entries, measured, name, 'code_lines', lambda key: f'{key[0]} {key[1]}', 'code lines')
    found = [f'{key[0]}:{over[key][1]} {key[1]} is {over[key][0]} code lines, over the {limit}-line '
             'limit' for key in unexempted] + found
    return found, kept


def main(argv):
    limit, show_all, exemptions, files = DEFAULT_LIMIT, False, None, []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--selftest':
            return selftest()
        if args[i] == '--limit':
            limit = int(args[i + 1]); i += 2
        elif args[i] == '--all':
            show_all = True; i += 1
        elif args[i] == '--exemptions':
            exemptions = args[i + 1]; i += 2
        else:
            files.append(args[i]); i += 1
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    entries, errors = exemptions_file.load(exemptions, ('path', 'name', 'code_lines'),
                                           ('code_lines',))
    for e in errors:
        print(f'function_length: {e}', file=sys.stderr)
    if errors:
        return 2
    found, kept = findings(files, limit, entries,
                           Path(exemptions).name if exemptions else 'function-length-exemptions',
                           show_all)
    for path, fn_name in kept:
        print(f'==> function length: {path} {fn_name} is over the limit and exempt at its measured '
              'length')
    for f in found:
        print(f'function_length: {f}', file=sys.stderr)
    if not found:
        print(f'==> function length: every other function is within {limit} code lines')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
