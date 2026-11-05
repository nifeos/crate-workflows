#!/usr/bin/env python3
"""Passive voice in a crate's prose stays at 2 per 1,000 words (nife's rule 6 of its writing standards).

    python3 passive_voice.py [--per-1000 2] [--floor 200] [--list] FILE...
    python3 passive_voice.py --selftest

Nife's limit, kept exactly: a document carries at most 2 passive constructions per 1,000 prose
words, and a document under 200 prose words is too small to be asked. Both numbers are nife's
(its prose ratchet, `helpers/prose_ratchet.py`, with the counter in `helpers/passive_voice.py`);
`--per-1000` and `--floor` exist for the selftest and for a reader trying a number, and the
workflow passes neither.

**What a passive is.** A form of "be" (am, are, is, was, were, be, been, being), whitespace, then a
word ending in "ed" or one of the irregular past participles below, as whole words, in any case.
That is the `write-good.Passive` rule of the Vale style `errata-ai/write-good`, copied here and not
depended on. Its license travels with the copied list:

    The MIT License (MIT)

    Copyright (c) 2014 Brian Ford

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software
    and associated documentation files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or
    substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
    BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

It cannot see a word between the auxiliary and the participle ("is not used" reads as active), and
an adjective ending in "ed" after "is" ("is unchanged") reads as a passive. `NOT_PASSIVE` removes
three false readings nife measured often enough to move a count.

**Which words are prose.** The same reading nife's prose ratchet uses. Front matter, HTML comments,
fenced code, headings, table rows and block quotes are not sentences. A link counts as its text,
inline code as one word, and a quoted span is removed, because a writer cannot rewrite a speaker
into the active voice. The prose-word count is every word outside front matter, comments and
fences, which is the denominator nife divides by.

**Which files.** The workflow passes the crate's `README*`, `CHANGELOG.md` and `docs/*.md`, the
files `prose_caps.py` reads plus the crate's own documents. Nife reads Markdown only, and so does
this: Rust doc comments are not counted. Nife marks a deliberate exception with a comment in the
document and holds the already-over documents in a baseline file. This template has neither: a new
crate repository starts under the limit, and a document that needs more passives is a rewrite.

Name: provisional, from the gates lane. The file takes nife's helper name.
"""

import re
import sys

DEFAULT_PER_1000 = 2
DEFAULT_FLOOR = 200

AUXILIARIES = ('am', 'are', 'were', 'being', 'is', 'been', 'was', 'be')

# write-good's irregular past participles, in its order, less two British forms the house style
# refuses (helpers/house_style.py). Their American forms, learned and dreamed, end in "ed".
IRREGULAR = (
    'awoken', 'beat', 'become', 'been', 'begun', 'bent', 'beset', 'bet', 'bid', 'bidden', 'bitten',
    'bled', 'blown', 'born', 'bought', 'bound', 'bred', 'broadcast', 'broken', 'brought', 'built',
    'burnt', 'burst', 'cast', 'caught', 'chosen', 'clung', 'come', 'cost', 'crept', 'cut', 'dealt',
    'dived', 'done', 'drawn', 'driven', 'drunk', 'dug', 'eaten', 'fallen', 'fed', 'felt',
    'fit', 'fled', 'flown', 'flung', 'forbidden', 'foregone', 'forgiven', 'forgotten', 'forsaken',
    'fought', 'found', 'frozen', 'given', 'gone', 'gotten', 'ground', 'grown', 'heard', 'held',
    'hidden', 'hit', 'hung', 'hurt', 'kept', 'knelt', 'knit', 'known', 'laid', 'lain', 'leapt',
    'led', 'left', 'lent', 'let', 'lighted', 'lost', 'made', 'meant', 'met', 'misspelt',
    'mistaken', 'mown', 'overcome', 'overdone', 'overtaken', 'overthrown', 'paid', 'pled', 'proven',
    'put', 'quit', 'read', 'rid', 'ridden', 'risen', 'run', 'rung', 'said', 'sat', 'sawn', 'seen',
    'sent', 'set', 'sewn', 'shaken', 'shaven', 'shed', 'shod', 'shone', 'shorn', 'shot', 'shown',
    'shrunk', 'shut', 'slain', 'slept', 'slid', 'slit', 'slung', 'smitten', 'sold', 'sought',
    'sown', 'sped', 'spent', 'spilt', 'spit', 'split', 'spoken', 'spread', 'sprung', 'spun',
    'stolen', 'stood', 'stridden', 'striven', 'struck', 'strung', 'stuck', 'stung', 'stunk', 'sung',
    'sunk', 'swept', 'swollen', 'sworn', 'swum', 'swung', 'taken', 'taught', 'thought', 'thrived',
    'thrown', 'thrust', 'told', 'torn', 'trodden', 'understood', 'upheld', 'upset', 'wed', 'wept',
    'withheld', 'withstood', 'woken', 'won', 'worn', 'wound', 'woven', 'written', 'wrung',
)

# Words the pattern matches that are not a participle in prose. Nife measured these on its own
# documents and a sample of each read as no passive at all. An entry exempts every use of the word,
# so it must be wrong almost never as a verb.
NOT_PASSIVE = {
    'rung': 'the noun: "is rung two" names a step of a ladder, never the bell',
    'red': 'the color of a run ("is red on main"); "red" is no participle',
    'gone': '"go" takes no object, so it has no passive; "is gone" states that a thing left',
}

# One regex in write-good. Two steps here, for speed: the pattern finds an auxiliary and peeks at
# the next word without consuming it, and `_participle` tests that word. Peeking keeps "is is
# checked" finding its passive, as the one regex does.
PATTERN = re.compile(r'\b(?:%s)\s+(?=(\w+))' % '|'.join(AUXILIARIES), re.I)
_IRREGULAR = frozenset(IRREGULAR)


def _participle(word):
    word = word.lower()
    return (len(word) > 2 and word.endswith('ed') or word in _IRREGULAR) and word not in NOT_PASSIVE


def matches(text):
    """Every passive construction in `text` (prose already), as `re.Match` objects."""
    return [m for m in PATTERN.finditer(text) if _participle(m.group(1))]


# --- reading a document, as nife's prose ratchet reads it -------------------------------------------

FENCE = re.compile(r'^\s*(```|~~~)')
COMMENT = re.compile(r'<!--.*?-->', re.S)
FRONTMATTER = re.compile(r'\A---\n.*?\n---\n', re.S)
HEADING = re.compile(r'^\s{0,3}#{1,6}(\s|$)')
LIST_ITEM = re.compile(r'^\s*([-*+]|\d+[.)])\s+')
QUOTE_LINE = re.compile(r'^\s*>')
TABLE_ROW = re.compile(r'^\s*\|')
CODE_SPAN = re.compile(r'(`+)(.+?)\1', re.S)
LINK = re.compile(r'!?\[([^\]]*)\]\([^)]*\)')
QUOTED = re.compile(r'[*_]*["\u201c][^"\u201c\u201d]*["\u201d][*_]*')


def prose_lines(text):
    """[(line number, line)] outside front matter, comments and fenced code."""
    text = FRONTMATTER.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    text = COMMENT.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    fence = None
    out = []
    for n, line in enumerate(text.split('\n'), 1):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1) == fence:
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        out.append((n, line))
    return out


def blocks(lines):
    """[(first line number, block text)]: a paragraph or a list item, never a heading, table row or quote."""
    out, cur, first = [], [], 0

    def flush():
        nonlocal cur
        if cur:
            out.append((first, ' '.join(cur)))
        cur = []

    for n, line in lines:
        if not line.strip() or HEADING.match(line) or TABLE_ROW.match(line) or QUOTE_LINE.match(line):
            flush()
            continue
        if LIST_ITEM.match(line):
            flush()
            cur, first = [LIST_ITEM.sub('', line, count=1).strip()], n
            continue
        if not cur:
            first = n
        cur.append(line.strip())
    flush()
    return out


def unquoted(block):
    """A block as the writer's own words: links as their text, code as one word, quotes removed."""
    s = LINK.sub(r'\1', CODE_SPAN.sub('Code', block))
    return QUOTED.sub(' ', s)


def measure(text):
    """(prose words, [(line, participle phrase)]) for a document."""
    lines = prose_lines(text)
    words = sum(len(line.split()) for _n, line in lines)
    found = []
    for n, block in blocks(lines):
        for m in matches(unquoted(block)):
            found.append((n, f'{m.group(0).split()[0]} {m.group(1)}'))
    return words, found


def verdict(text, per_1000=DEFAULT_PER_1000, floor=DEFAULT_FLOOR):
    """(words, passives, allowed, over) for a document."""
    words, found = measure(text)
    allowed = words * per_1000 // 1000
    over = words >= floor and len(found) * 1000 > per_1000 * words
    return words, found, allowed, over


# --- the command ------------------------------------------------------------------------------------

def selftest():
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    def count(text):
        return len(matches(text))

    cases = [
        ('a regular participle', 'The row is checked by lint.', 1),
        ('an irregular participle', 'It was written in July and is built daily.', 2),
        ('any case', 'IS CHECKED and Was Built', 2),
        ('a line break between the two words', 'The gate is\nrefused.', 1),
        ('active voice', 'Lint checks the row. The author wrote it.', 0),
        ('a word between hides it, a known gap', 'It is not used.', 0),
        ('"is" inside a longer word', 'This isolated case was fine.', 0),
        ('a ladder rung', 'That is rung two of the ladder.', 0),
        ('a color', 'The run is red on main.', 0),
        ('an intransitive verb', 'The file is gone.', 0),
        ('every auxiliary', 'am told, are told, were told, being told, is told, been told, '
                            'was told, be told', 8),
    ]
    for label, text, want in cases:
        expect(label, count(text), want)
    # What counts as prose.
    expect('inline code is one word', measure('Run `it is checked` now.')[1], [])
    expect('a fence is not prose', measure('Short.\n```\nit is checked\n```\n')[1], [])
    expect('a comment is not prose', measure('Short.\n<!-- it is checked -->\n')[1], [])
    expect('a quote is removed', measure('He said "it is checked" twice.')[1], [])
    expect('a heading is not a sentence', measure('# It is checked\n\nText.')[1], [])
    expect('a table row is not a sentence', measure('| it is checked |\n')[1], [])
    expect('a passive reports its line', measure('One.\n\nThe row is checked.\n')[1],
           [(3, 'is checked')])
    expect('front matter keeps line numbers', measure('---\na: b\n---\nIt is checked.\n')[1],
           [(4, 'is checked')])
    # The limit: a document under the floor passes whatever it holds; one at the floor is asked.
    small = 'The row is checked. ' * 10
    expect('under the floor passes', verdict(small)[3], False)
    clean = 'The tool checks the row. ' * 250
    expect('a clean document passes', verdict(clean)[3], False)
    two = clean + 'Lint is run. It was built.'
    words = verdict(two)[0]
    expect('2 in about 1,250 words passes', (words >= DEFAULT_FLOOR, verdict(two)[3]), (True, False))
    many = clean + 'Lint is run. It was built. The row is checked. A file is read.'
    expect('4 in about 1,250 words fails', verdict(many)[3], True)
    expect('the allowance rounds down', verdict(many)[2], 2)
    print('passive_voice selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    per_1000, floor, listing, files = DEFAULT_PER_1000, DEFAULT_FLOOR, False, []
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--selftest':
            return selftest()
        if args[i] == '--per-1000':
            per_1000 = int(args[i + 1]); i += 2
        elif args[i] == '--floor':
            floor = int(args[i + 1]); i += 2
        elif args[i] == '--list':
            listing = True; i += 1
        else:
            files.append(args[i]); i += 1
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    bad = False
    for f in files:
        with open(f, encoding='utf-8', errors='replace') as fh:
            words, found, allowed, over = verdict(fh.read(), per_1000, floor)
        print(f'==> {f}: {len(found)} passives in {words} words')
        if listing or over:
            for n, phrase in found:
                print(f'  {f}:{n}: {phrase}', file=sys.stderr if over else sys.stdout)
        if over:
            print(f'passive_voice: {f}: {len(found)} passive constructions in {words:,} words, over '
                  f'{per_1000} per 1,000, which allows {allowed}. Put {len(found) - allowed} into the '
                  f'active voice', file=sys.stderr)
            bad = True
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
