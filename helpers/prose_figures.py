"""A figurative or vague phrase is replaced by a plain one.

    python3 prose_figures.py FILE...
    python3 prose_figures.py --selftest

A figure of speech makes a reader decode it, and a vague boast claims what the prose does not show.
In a crate's README, CHANGELOG, `docs/*.md` and Rust doc comments (`///` and `//!`), each phrase in
`prose_figures.toml` fails, and the message gives the plain replacement. Ceiling 0, no baseline.

Each entry in the toml is `[[figure]]` with `phrase`, a regular expression matched in any case
between word boundaries (so `tale` does not match `table`, and `oracle` does not match `miracle`),
and `instead`, the text the failure shows. Every entry needs both. Inline code, fenced code,
addresses, HTML comments and front matter are not read; headings are.

Name: provisional, from the prose gates lane.
"""
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prose_text import prose_lines  # noqa: E402


def violations(path, text, figures):
    """[(line, phrase as written, instead)] for each banned phrase in the file's prose."""
    out = []
    for n, line, _ in prose_lines(path, text):
        for pattern, instead in figures:
            for m in re.finditer(r'\b(?:%s)\b' % pattern, line, re.I):
                out.append((n, m.group(0), instead))
    return out


def load_figures():
    path = Path(__file__).resolve().with_name('prose_figures.toml')
    entries = tomllib.loads(path.read_text(encoding='utf-8'))['figure']
    for e in entries:
        if not e.get('phrase') or not e.get('instead'):
            raise SystemExit(f'prose_figures: {path.name}: an entry needs a phrase and an instead')
    return [(e['phrase'], e['instead']) for e in entries]


FIGURES = [(r'oracle', 'an independent implementation that the tests compare against'),
           (r'battle[- ]tested', 'say which tests or uses back the claim')]


def selftest():
    cases = [
        ('The reference is an oracle for the tests.\n', ['oracle']),
        ('A battle-tested parser, and a Battle tested one.\n', ['battle-tested', 'Battle tested']),
        ('An independent implementation that the tests compare against.\n', []),
        ('The `oracle` code span is exempt.\n', []),
        ('```\noracle\n```\n', []),
        ('# The oracle heading\n', ['oracle']),
        ('Oracles are plural, and miracle is another word.\n', []),
    ]
    failed = 0
    for src, want in cases:
        got = [p for _, p, _ in violations('a.md', src, FIGURES)]
        if got != want:
            failed += 1
            print(f'FAIL {src!r} gave {got}, wanted {want}', file=sys.stderr)
    got = [p for _, p, _ in violations('a.rs', '/// An oracle.\nlet oracle = 1; // oracle\n', FIGURES)]
    if got != ['oracle']:
        failed += 1
        print(f'FAIL rust gave {got}', file=sys.stderr)
    print('prose_figures selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


def main(argv):
    if '--selftest' in argv:
        return selftest()
    files = argv[1:]
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    figures = load_figures()
    bad = 0
    for f in files:
        try:
            text = open(f, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for line, phrase, instead in violations(f, text, figures):
            print(f'prose_figures: {f}:{line}: "{phrase}": write {instead}', file=sys.stderr)
            bad += 1
    if not bad:
        print(f'==> figures: none in {len(files)} files')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
