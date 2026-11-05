"""An acronym is expanded at its first use in a file, or it is on the allowlist.

    python3 prose_acronyms.py FILE...
    python3 prose_acronyms.py --selftest

A reader meets EFI, MMIO or LBA cold unless the prose says what the letters stand for. In a crate's
README, CHANGELOG, `docs/*.md` and Rust doc comments (`///` and `//!`), a run of two or more capital
letters (mixed forms such as `FSInfo`, `PCIe` and `IPv4` included) must be expanded where the file
first uses it, or be listed in `prose_acronyms.toml`. Ceiling 0, no baseline.

**What is a token.** Two or more capitals, then any letters or digits, as a whole word; a trailing
lowercase `s` after capitals is a plural (`LBAs` is `LBA`). A constant (`MAX_SIZE`), a hex literal
(`0xFF`), a bare byte (`FF`) and a hex word with a digit (`AA55`) are not tokens.

**What is not read.** Inline code, fenced code, addresses, HTML comments, front matter and
headings. Rust is read only in doc comments; a `//` comment and code are not prose here.

**The expansion pattern the gate accepts.** The first use of the token is one of

- `Extensible Firmware Interface (EFI)`: the words, then the token in parentheses; or
- `EFI (Extensible Firmware Interface)`: the token, then the words in parentheses.

The initials of the words must spell the token, in order. Small words (of, the, and, for, to, in, on,
or, a, an, with, by) do not count, a hyphenated word counts as two (`Non-Volatile Memory Express`
is `NVMe`), a word that is itself an acronym gives all its letters (`PCI Express` is `PCIe`), and a CamelCase word gives each capital (`OpenID Connect` is `OIDC`), and
the words may be a prefix of the token (`File System Information (FSInfo)`). A line break inside
the words is fine. Expanding a token later in the file does not excuse an earlier bare use.

**Allowlist.** `prose_acronyms.toml` beside this file, key `allow`: words every reader of a Rust
crate knows. A name that is not on it is expanded, not added.

Name: provisional, from the prose gates lane.
"""
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prose_text import prose_lines  # noqa: E402

TOKEN = re.compile(r'\b[A-Z]{2,}[A-Za-z0-9]*\b')
STOP = {'of', 'the', 'and', 'for', 'to', 'in', 'on', 'or', 'a', 'an', 'with', 'by'}
WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
HEX = re.compile(r'^[0-9A-F]+$')


def normal(token):
    """The token without a plural s."""
    if token.endswith('s') and token[:-1].isupper() and len(token) > 3:
        return token[:-1]
    return token


def is_hex(token):
    return bool(HEX.match(token)) and (len(token) == 2 or any(c.isdigit() for c in token))


def initials(words):
    out = ''
    for w in words:
        if w.lower() in STOP:
            continue
        if w.isupper() and len(w) >= 2:
            out += w.lower()
        else:
            # A CamelCase word gives each capital (`OpenID` is O, I, D).
            out += w[0].lower() + ''.join(c.lower() for c in w[1:] if c.isupper())
    return out


def spells(token, words):
    """Do the words' initials spell the token (or its leading part)?"""
    want = re.sub(r'[0-9]', '', token).lower()
    got = initials(words)
    return len(got) >= 2 and want.startswith(got)


def expanded(stream, start, end, token):
    """Is the use at stream[start:end] in an accepted expansion pattern?"""
    before = stream[:start].rstrip()
    if before.endswith('(') and stream[end:].startswith(')'):
        words = WORD.findall(before[:-1])[-8:]
        return any(spells(token, words[-k:]) for k in range(2, len(words) + 1))
    after = re.match(r'\s*\(([^)]*)\)', stream[end:])
    if after:
        return spells(token, WORD.findall(after.group(1)))
    return False


def violations(path, text, allow):
    """[(line, token)] for each acronym whose first use in the file is not expanded."""
    stream, marks = '', []
    for n, line, heading in prose_lines(path, text):
        if heading:
            continue
        marks.append((len(stream), n))
        stream += line + ' '
    out, seen = [], set()
    for m in TOKEN.finditer(stream):
        token = normal(m.group(0))
        if token in seen:
            continue
        seen.add(token)
        if token in allow or is_hex(token):
            continue
        if expanded(stream, m.start(), m.end(), token):
            continue
        line = [n for off, n in marks if off <= m.start()][-1]
        out.append((line, m.group(0)))
    return out


def load_allow():
    path = Path(__file__).resolve().with_name('prose_acronyms.toml')
    return set(tomllib.loads(path.read_text(encoding='utf-8'))['allow'])



ALLOW = {'API', 'CPU'}


def selftest():
    cases = [
        # (source, wanted tokens)
        ('The EFI loads the image.\n', ['EFI']),
        ('Extensible Firmware Interface (EFI) loads the image. Later EFI again.\n', []),
        ('EFI (Extensible Firmware Interface) loads the image. Later EFI again.\n', []),
        ('The Logical Block Addressing (LBA) rules. The LBAs are 512 bytes.\n', []),
        ('Later EFI use. Then Extensible Firmware Interface (EFI) after the first use.\n', ['EFI']),
        ('Read the FSInfo sector, then the FSInfo sector again.\n', ['FSInfo']),
        ('File System Information (FSInfo) sector. The FSInfo again.\n', []),
        ('The API and the CPU are allowed.\n', []),
        ('The `EFI` code span and `MMIO` are exempt.\n', []),
        ('```\nEFI MMIO\n```\n', []),
        ('# EFI heading\nPlain text.\n', []),
        ('The PRP list and the CNS value.\n', ['PRP', 'CNS']),
        ('A byte 0xFF, then FF and AA55 and MAX_SIZE.\n', []),
        ('Controller or Namespace Structure (CNS) value. A Wrong Words (CNS) twist.\n', []),
        ('Some Wrong Words (EFI) pair.\n', ['EFI']),
        ('OpenID Connect (OIDC) and PCI Express (PCIe) and Non-Volatile Memory Express (NVMe).\n', ['PCI']),
    ]
    failed = 0
    for src, want in cases:
        got = [t for _, t in violations('a.md', src, ALLOW)]
        if got != want:
            failed += 1
            print(f'FAIL {src!r} gave {got}, wanted {want}', file=sys.stderr)
    rs = '/// The EFI table.\nfn f() {} // EFI in code\n'
    got = [t for _, t in violations('a.rs', rs, ALLOW)]
    if got != ['EFI']:
        failed += 1
        print(f'FAIL rust doc gave {got}', file=sys.stderr)
    good = '/// Extensible Firmware Interface (EFI) table.\nfn f() {} // MMIO here\n'
    if violations('a.rs', good, ALLOW):
        failed += 1
        print('FAIL rust good fixture failed', file=sys.stderr)
    print('prose_acronyms selftest: %s' % ('FAILED' if failed else 'ok'))
    return 1 if failed else 0


def main(argv):
    if '--selftest' in argv:
        return selftest()
    files = argv[1:]
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    allow = load_allow()
    bad = 0
    for f in files:
        try:
            text = open(f, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for line, token in violations(f, text, allow):
            print(f'prose_acronyms: {f}:{line}: {token} is not expanded at its first use', file=sys.stderr)
            bad += 1
    if bad:
        print("prose_acronyms: write the words first, then the acronym in parentheses "
              "('Extensible Firmware Interface (EFI)'), or the acronym first with the words in "
              "parentheses. Words every reader knows go in helpers/prose_acronyms.toml.",
              file=sys.stderr)
    else:
        print(f'==> acronyms: all expanded in {len(files)} files')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
