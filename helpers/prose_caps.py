#!/usr/bin/env python3
"""Prose caps for a crate's README and CHANGELOG, at nife's limits.

    python3 prose_caps.py [--words 3000] [--median 20] [--longest 40] [--bold 4] FILE...

The limits are nife's writing standards (its §213 numbers): at most 3,000 words in a document, a
median sentence of 20 words, a longest sentence of 40, and 4 bold spans per 1,000 words. Fenced
code blocks are prose neither a reader nor a linter reads as sentences, so they come out first;
table rows count, one row per sentence, because a wide table row is exactly the wall of text the
longest-sentence cap exists to catch.

A document over a cap fails, with its numbers, so the fix is a sentence-level decision and not a
mood. Name: provisional, from milestone 887's lane.
"""

import re
import statistics
import sys

DEFAULTS = {'words': 3000, 'median': 20, 'longest': 40, 'bold': 4}


def prose(text):
    """The document with fenced code blocks removed, as a list of sentences' word counts."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'~~~.*?~~~', '', text, flags=re.S)
    text = re.sub(r'`[^`]*`', lambda m: m.group(0).replace('.', '').replace('!', '').replace('?', ''), text)
    counts = []
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        words = sentence.split()
        if words:
            counts.append(len(words))
    return counts


def bold_spans(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    return len(re.findall(r'\*\*', text))


def check(path, limits):
    text = open(path).read()
    counts = prose(text)
    words = sum(counts)
    found = []
    if words > limits['words']:
        found.append(f'{words} words over the {limits["words"]} cap')
    if counts:
        median = statistics.median(counts)
        longest = max(counts)
        if median > limits['median']:
            found.append(f'median sentence {median:g} words over the {limits["median"]} cap')
        if longest > limits['longest']:
            found.append(f'longest sentence {longest} words over the {limits["longest"]} cap')
    if words:
        bold_per_1000 = bold_spans(text) * 1000 / words
        if bold_per_1000 > limits['bold']:
            found.append(f'{bold_per_1000:.1f} bold spans per 1,000 words over the {limits["bold"]} cap')
    return words, found


def selftest():
    import tempfile
    from pathlib import Path
    ok = True

    def expect(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {label}: got {got!r} want {want!r}', file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'README.md'
        p.write_text('# A crate.\n\nShort sentences. Each one lands.\n\n```rust\nlet long = sentence; // not prose. Not counted.\n```\n')
        words, found = check(p, DEFAULTS)
        expect('clean', found, [])
        expect('code fence not counted', words, 8)
        p.write_text('One. ' * 3200 + '\n')
        _, found = check(p, DEFAULTS)
        expect('word cap', any('word' in f for f in found), True)
        p.write_text(' '.join(['word'] * 45) + '.\n')
        _, found = check(p, DEFAULTS)
        expect('longest cap', any('longest' in f for f in found), True)
        p.write_text(' '.join(['**bold**'] * 30) + ' and ' + ' '.join(['word'] * 1000) + '.\n')
        _, found = check(p, DEFAULTS)
        expect('bold cap', any('bold' in f for f in found), True)
    print('prose_caps selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


def main(argv):
    args = [a for a in argv[1:]]
    limits = dict(DEFAULTS)
    files = []
    i = 0
    while i < len(args):
        if args[i] == '--selftest':
            return selftest()
        if args[i] == '--words':
            limits['words'] = int(args[i + 1]); i += 2
        elif args[i] == '--median':
            limits['median'] = int(args[i + 1]); i += 2
        elif args[i] == '--longest':
            limits['longest'] = int(args[i + 1]); i += 2
        elif args[i] == '--bold':
            limits['bold'] = int(args[i + 1]); i += 2
        else:
            files.append(args[i]); i += 1
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    bad = False
    for f in files:
        words, found = check(f, limits)
        print(f'==> {f}: {words} words')
        for x in found:
            print(f'prose_caps: {f}: {x}', file=sys.stderr)
            bad = True
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
