#!/usr/bin/env python3
"""An acronym is expanded at its first use in a file, or it is on the allowlist.

    python3 prose_acronyms.py FILE...
    python3 prose_acronyms.py --selftest

STUB: the implementation follows the selftest.
"""
import sys


def violations(path, text, allow):
    """[(line, token)] for each acronym whose first use in the file is not expanded."""
    raise NotImplementedError


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


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else 2)
