"""A README states how to run the tests, not how many there are.

    python3 readme_test_counts.py README...
    python3 readme_test_counts.py --selftest

A count of tests in prose goes stale at the next test added or removed, and nothing ties it to the
source. This gate refuses a README sentence that states one as a number, for example `118 unit
tests`, `7 simulator tests`, `all 147 tests pass` or `tests: 118`, and the failure tells the author
to state the test command instead, for example `cargo test`. Ceiling 0, no baseline.

What it refuses. A test noun (`tests`, `doctests`, `test cases`, `test functions`, always plural)
with a number before it: a digit string (`118`, `1,024`) or a spelled-out number from `one` to
`ninety-nine`, plus `hundred`, `thousand` and `dozen`. Between the number and the noun it allows any
number of kind words (`unit`, `integration`, `simulator`, `passing`, ...) and one other word, so
`118 parser tests` is refused. A kind word may be joined to another by `and` or `or`, so `118 unit
and simulator tests` is refused. The form `tests: 118` and `tests (118)` is refused too.

What it leaves. The word `test` on its own; a count of anything else (harnesses, patches, steps,
bytes, crates), which a number beside `harnesses and tests` does not turn into a test count because
`and` joins only kind words; a verb (`Step 3 tests the checksum`, a `tests` followed by an article);
a path (`tests/`); and the singular (`one test`), which is nearly always an adjective or a verb.
Spelled-out numbers above ninety-nine other than the words listed are not read.

What it does not read. Inline code, fenced code blocks, HTML comments, front matter, addresses and
badge rows (`helpers/prose_text.py`). A fenced block is where a README shows the output of
`cargo test`, and that output is a transcript, not a claim the author keeps true by hand; the
command in the block is the thing the gate wants. Headings are read.

Exemptions are in `readme_test_counts.toml`, each with a reason. Only README files are read: the
rule is about the page a reader opens first.

Name: provisional, from the README test counts lane.
"""
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prose_text import prose_lines  # noqa: E402

UNITS = ('one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
         'sixteen seventeen eighteen nineteen').split()
TENS = 'twenty thirty forty fifty sixty seventy eighty ninety'.split()
SPELLED = set(UNITS) | set(TENS) | {'hundred', 'hundreds', 'thousand', 'dozen'} | {
    f'{t}-{u}' for t in TENS for u in UNITS[:9]}
DIGITS = re.compile(r'^\d[\d,_]*$')
NOUNS = {'tests', 'doctests', 'cases', 'functions'}
# `cases` and `functions` count only after `test`; the check is in `refused`.
KINDS = set('''unit integration simulator doc property regression fuzz loom model conformance
acceptance host board hardware smoke golden round-trip passing failing passed failed ignored
automated separate distinct individual named new existing own'''.split())
CONNECTORS = {'and', 'or'}
# Words after `tests` that make it a verb.
VERB_NEXT = {'the', 'a', 'an', 'that', 'each', 'every', 'whether', 'if', 'how', 'this', 'these',
             'those', 'it', 'its'}
TOKEN = re.compile(r"\d[\d,_]*\d|\d|[A-Za-z][A-Za-z'-]*[A-Za-z]|[A-Za-z]|\S")


def is_number(token):
    return token.lower() in SPELLED or bool(DIGITS.match(token))


def stream(text):
    """[(token, line)] of the file's prose; a gap between paragraphs becomes a `.` token."""
    out, last = [], None
    for n, line, _ in prose_lines('README.md', text):
        if last is not None and n != last + 1:
            out.append(('.', last))
        out.extend((t, n) for t in TOKEN.findall(line))
        last = n
    return out


def refused(tokens, i):
    """The number token's index when the test noun at i has a number before it, else None."""
    word = tokens[i][0].lower()
    if word not in NOUNS:
        return None
    if word in ('cases', 'functions'):
        if i == 0 or tokens[i - 1][0].lower() != 'test':
            return None
        i -= 1
        nxt = i + 2
    else:
        nxt = i + 1
    after = tokens[nxt][0].lower() if nxt < len(tokens) else ''
    if after in VERB_NEXT or after == '/':
        return None
    j, other = i - 1, 0
    while j >= 0:
        t = tokens[j][0]
        if is_number(t):
            return j
        low = t.lower()
        if low in KINDS:
            j -= 1
        elif low in CONNECTORS and j > 0 and tokens[j - 1][0].lower() in KINDS:
            j -= 1
        elif re.fullmatch(r"[A-Za-z][A-Za-z'-]*", t) and low not in CONNECTORS and other == 0:
            other += 1
            j -= 1
        else:
            return None
    return None


def after_form(tokens, i):
    """`tests: 118` and `tests (118)`: the number token's index, else None."""
    if tokens[i][0].lower() not in ('tests', 'doctests'):
        return None
    j = i + 1
    if j < len(tokens) and tokens[j][0] in (':', '=', '('):
        j += 1
        if j < len(tokens) and is_number(tokens[j][0]):
            return j
    return None


def violations(text, exempt=()):
    """[(line, refused text)] for each stated test count in a README's prose."""
    tokens = stream(text)
    out = []
    for i in range(len(tokens)):
        j = refused(tokens, i)
        if j is not None:
            span = tokens[j:i + 1]
        else:
            j = after_form(tokens, i)
            if j is None:
                continue
            span = tokens[i:j + 1]
        shown = ' '.join(t for t, _ in span)
        if any(re.search(p, shown, re.I) for p in exempt):
            continue
        out.append((span[0][1], shown))
    return out


def load_exemptions():
    path = Path(__file__).resolve().with_name('readme_test_counts.toml')
    entries = tomllib.loads(path.read_text(encoding='utf-8')).get('exempt', [])
    for e in entries:
        if not e.get('phrase') or not e.get('reason'):
            raise SystemExit(f'readme_test_counts: {path.name}: an exemption needs a phrase and a reason')
    return [e['phrase'] for e in entries]


def selftest():
    bad = [
        'It has 118 unit tests and 7 simulator tests.\n',
        'All 147 tests pass.\n',
        'The crate ships twelve doctests.\n',
        'It has twenty-one test cases.\n',
        '118 unit and simulator tests run on the host.\n',
        '118 parser tests.\n',
        'Tests: 118\n',
        'There are 1,024 test functions.\n',
        'The suite has 118 unit\ntests across the crate.\n',
        '# 7 simulator tests\n',
        'About a hundred tests cover it.\n',
        'It has 118 tests for the parser.\n',
    ]
    good = [
        'Run `cargo test` to run the tests.\n',
        'Seven harnesses, 3 patches, 12 steps and 4096 bytes in 2 crates.\n',
        'Step 3 tests the checksum.\n',
        'Run 7 harnesses and tests.\n',
        'One test command runs them all.\n',
        'Three kinds of tests run in CI.\n',
        'The tests/ directory holds 3 files.\n',
        '```\ntest result: ok. 118 passed; 0 failed\n118 tests\n```\n',
        'The command `118 tests` is a span.\n',
        '3 crates run tests nightly.\n',
        'The tests pass.\n\n12\n\ntests follow.\n',
        'It has 7 harnesses.\nTests follow.\n',
    ]
    failed = 0
    for src in bad:
        if not violations(src):
            failed += 1
            print(f'FAIL not refused: {src!r}', file=sys.stderr)
    for src in good:
        got = violations(src)
        if got:
            failed += 1
            print(f'FAIL refused {src!r}: {got}', file=sys.stderr)
    shown = [s for _, s in violations('It has 118 unit tests and 7 simulator tests.\n')]
    if shown != ['118 unit tests', '7 simulator tests']:
        failed += 1
        print(f'FAIL shown {shown}', file=sys.stderr)
    if violations('It has 118 unit tests.\n', ['^118 unit tests$']):
        failed += 1
        print('FAIL an exemption did not apply', file=sys.stderr)
    print('readme_test_counts selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


def main(argv):
    if '--selftest' in argv:
        return selftest()
    files = argv[1:]
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    exempt = load_exemptions()
    bad = 0
    for f in files:
        try:
            text = open(f, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for line, shown in violations(text, exempt):
            print(f'readme_test_counts: {f}:{line}: "{shown}": state the test command instead, '
                  'for example `cargo test`; a count of tests goes stale', file=sys.stderr)
            bad += 1
    if not bad:
        print(f'==> test counts: none in {len(files)} files')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
