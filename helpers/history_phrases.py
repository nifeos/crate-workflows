#!/usr/bin/env python3
"""A document states what is in force now, so phrases that only a history uses stay at zero (nife's rule on history).

    python3 history_phrases.py FILE...
    python3 history_phrases.py --selftest

Nife's rule: a document says what is true and in force now, and how it got there goes in commit
messages and pull request bodies. Nife's gate cannot see every way to narrate history, so it counts
the phrases that almost never mean anything else, in Markdown outside fenced code, inline code,
HTML comments, front matter and `>` quotation lines. The phrase list is nife's, unchanged:

- `supersede` in any form, and `supersession`, unless a modal or `to` precedes it ("a later
  release can supersede this" is about the future). An all-capitals `SUPERSEDED` is a status value.
- `used to` followed by `be`, `say`, `read`, `live`, `hold`, `carry`, `mean`, `sit`, `name`,
  `call`, `count`, `list`, `state` or `claim`.
- `was` or `were`, then within the sentence `until` and a milestone, a section, a pull request
  number or a date: "The job was named `clippy` until 2026-10-08."
- `renamed from`, `was renamed`, `formerly`.
- `moved from` (or `moved here from`, `moved whole from`) naming a document: a link, a `.md` path,
  a milestone, a section, or "its section".
- A heading that names a history: `Timeline`, `Status history`, `BUGS history`, `How it got
  here`, `The history`, `Its history`.
- A file whose name ends in `history.md` or `timeline.md`.

**No baseline, and where the template differs from nife.** Nife holds a ceiling (its tree's count
when the gate landed) and fails a branch that adds any hit against its merge base. A new crate
repository starts at zero, so the ceiling here is zero and any hit fails. Nife has no equivalent
of the three differences below, each because a crate repository keeps a file nife does not:

- `CHANGELOG.md` is not read. A changelog is the place history goes, and the rule exists to send
  history there; the workflow does not pass it, and this script skips a file with that name.
- Nife skips a file whose path carries a date (`measured-2026-08-16.md`, a record of one event).
  This script does the same.
- A document may carry `<!-- history: exception. Reason: ... -->` to say out loud that it is a
  record of an event. Nife's exception is the same marker.

**What it does not read.** Markdown only, as nife's gate. Rust doc comments and `//` comments carry
history too, and nife holds them by length (its comment-block rule, `comment_blocks.py` here), not
by phrasing. A reviewer owns the rest, and a hit count is a floor.

**Which files.** The workflow passes the crate's `README*` and `docs/*.md`.

Name: provisional, from the gates lane. Nife's name for the helper is `history_ratchet.py`; this
one has no ratchet, so it takes the shorter and truer name.
"""

import os
import re
import sys

DATED = re.compile(r'\d{4}-\d\d-\d\d')
EXCEPTION = re.compile(r'<!--\s*history:\s*exception\b[^>]*\bReason:', re.S)
EXEMPT_NAMES = ('CHANGELOG.md',)


def in_scope(path):
    base = os.path.basename(path)
    return (path.endswith('.md') and base not in EXEMPT_NAMES and not DATED.search(path)
            and not path.startswith(('vendor/', 'target/')))


PHRASES = {
    'supersede': re.compile(r'(?i)\bsupersed(?:e|ed|es|ing)\b|\bsupersession\b'),
    'used to': re.compile(r'(?i)\bused to (?:be|say|read|live|hold|carry|mean|sit|name|call|count|'
                          r'list|state|claim)\b'),
    'was until': re.compile(r'(?i)\b(?:was|were)\b[^.]{0,80}?\buntil (?:milestone \d|§\d|#\d|'
                            r'\d{4}-\d\d-\d\d)'),
    'renamed': re.compile(r'(?i)\brenamed from\b|\bwas renamed\b|\bformerly\b'),
    'moved from': re.compile(r'(?i)\bmoved (?:whole |here )?from (?:its (?:section|BUGS)|\[|'
                             r'milestone \d|§\d|\S+\.md\b)'),
}
MODAL = re.compile(r'(?i)\b(?:could|would|can|may|might|will|to)\s+$')
HEADING = re.compile(r'^#{1,6} .*\b(?i:timeline|status history|bugs history|'
                     r'how (?:it|this|we) got here|the history|its history)\b')
HISTORY_FILE = re.compile(r'(?:^|-)(?:history|timeline)\.md$')
CODE = re.compile(r'`[^`\n]*`')
COMMENT = re.compile(r'<!--.*?-->', re.S)


def line_hits(line):
    """[(kind, phrase)] in one line of prose."""
    if re.match(r'\s*>', line):
        return []
    if HEADING.match(line):
        return [('heading', line.strip())]
    text = CODE.sub('``', line)
    out = []
    for kind, pattern in PHRASES.items():
        for m in pattern.finditer(text):
            if m.group(0).isupper():
                continue
            if kind == 'supersede' and MODAL.search(text[:m.start()]):
                continue
            out.append((kind, m.group(0)))
    return out


def file_hits(text, path=''):
    """[(line, kind, phrase)] for a Markdown document."""
    if EXCEPTION.search(text):
        return []
    hits = []
    if path and HISTORY_FILE.search(os.path.basename(path)):
        hits.append((0, 'history file', os.path.basename(path)))
    # Comments go, keeping their newlines, so a line number still points at the line.
    text = COMMENT.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    lines = text.split('\n')
    start = 0
    if lines and lines[0] == '---':
        for i in range(1, len(lines)):
            if lines[i] == '---':
                start = i + 1
                break
    fence = None
    for n in range(start, len(lines)):
        line = lines[n]
        mark = re.match(r'\s*(```|~~~)', line)
        if mark:
            fence = None if fence == mark.group(1) else (fence or mark.group(1))
            continue
        if fence:
            continue
        hits += [(n + 1, kind, phrase) for kind, phrase in line_hits(line)]
    return hits


def selftest():
    cases = [
        ('This supersedes the 2026-09-19 ruling.', ['supersede']),
        ('Section 105 is superseded. It was superseded on a second pass.', ['supersede', 'supersede']),
        ('This bullet used to say the row was missing.', ['used to']),
        ('It was called init until #1500.', ['was until']),
        ('The lint job was named `clippy` until 2026-10-08 (UTC).', ['was until']),
        ('`rank::GIC` (renamed from `rank::X`); the crate, formerly old-name.', ['renamed', 'renamed']),
        ('An appendix of [x](../x.md), moved from its section "Y" on 2026-10-12.', ['moved from']),
        ('Moved whole from [`notes/a.md`](../a.md).', ['moved from']),
        ('## Timeline', ['heading']),
        ('### The status history', ['heading']),
        # What is not history.
        ('status: SUPERSEDED, and `superseded_by: 148`.', []),
        ('A later release can supersede this, and one may supersede it.', []),
        ('> "It supersedes the old one," he said.', []),
        ('The tool is used to build the image. It was slow until warmed.', []),
        ('`PHYS_START` moved from 1 MiB to 32 MiB; the choice moved from the wait site.', []),
        ('```\nThis supersedes the 2026-09-19 ruling.\n```', []),
        ('<!-- This supersedes it. -->', []),
        ('---\nstatus: DECIDED\nnote: superseded\n---\nBody.', []),
        ('<!-- history: exception. Reason: a dated run. -->\nThis supersedes it.', []),
    ]
    failed = 0
    for src, want in cases:
        got = [k for _, k, _ in file_hits(src)]
        if got != want:
            failed += 1
            print(f'FAIL {src!r} counted {got}, wanted {want}', file=sys.stderr)
    for path, want in [('docs/history.md', ['history file']), ('docs/bugs-timeline.md', ['history file']),
                       ('docs/histogram.md', [])]:
        got = [k for _, k, _ in file_hits('Nothing here.', path)]
        if got != want:
            failed += 1
            print(f'FAIL {path} counted {got}, wanted {want}', file=sys.stderr)
    for path, want in [('CHANGELOG.md', False), ('docs/CHANGELOG.md', False),
                       ('docs/measured-2026-08-16.md', False), ('README.md', True),
                       ('src/lib.rs', False)]:
        if in_scope(path) != want:
            failed += 1
            print(f'FAIL in_scope({path}) is {not want}, wanted {want}', file=sys.stderr)
    lines = [n for n, _, _ in file_hits('A\n\n<!-- a\nb -->\nIt was renamed.')]
    if lines != [5]:
        failed += 1
        print(f'FAIL line numbers {lines}, wanted [5]', file=sys.stderr)
    print('history_phrases selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


def main(argv):
    args = argv[1:]
    if '--selftest' in args:
        return selftest()
    files = args
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    bad = False
    judged = 0
    for f in files:
        if not in_scope(f):
            continue
        try:
            text = open(f, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        judged += 1
        for line, kind, phrase in file_hits(text, f):
            print(f'history_phrases: {f}:{line}: {kind}: {phrase}', file=sys.stderr)
            bad = True
    if bad:
        print('history_phrases: a document states what is in force now. Say the current fact and put '
              'how it got there in the commit message, the pull request or the CHANGELOG.',
              file=sys.stderr)
    else:
        print(f'==> history phrases: none in {judged} documents')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
