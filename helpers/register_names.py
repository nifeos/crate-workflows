#!/usr/bin/env python3
"""Register, mask, address and size names: the naming rules that read a constant's shape.

    python3 register_names.py [--manifest Cargo.toml] [--report] FILE...
    python3 register_names.py --selftest

Four rules, each judged on the names the crate defines (helpers/rust_names.py says which):

1. **A register offset ends `_REGISTER`.** A constant with a plain integer literal for its value
   that either has `offset` in its name or sits in a module named for registers or offsets
   (`registers`, `register_offsets`, `offsets`) ends `_REGISTER`, and says which register:
   `CONTROL_REGISTER`, never `CTRL` or `CONTROL_OFFSET`. A name that ends `_MASK`, `_SHIFT`,
   `_VALUE`, `_BYTES` or `_BITS` is a different quantity and is not read as an offset.
2. **A mask of several bits ends `_MASK`.** A constant with `mask` anywhere but last in its name
   fails: `STATUS_MASK`, never `MASK_STATUS`.
3. **An address is virtual or physical.** A name with `address` (or `addr`) in it has `virtual` or
   `physical` straight before it (`FRAME_PHYSICAL_ADDRESS`), or a word from `[address_qualifiers]`
   that says it is not a location in memory (`MAC_ADDRESS`).
4. **A size carries its unit.** A constant, static or field with `size`, `len` or `length` in its
   name also holds a word from `[size_units]` (`BUFFER_SIZE_BYTES`, never `BUFFER_SIZE`). A count
   of things names the things (`MAXIMUM_COLUMNS`).

5. **A register constant is spelled out, and the source spelling is the alias.** An integer
   constant whose doc comment opens with a source for its own name, `(CAP, <source>)`, mirrors a
   datasheet's identifier and fails: rename it to say what it is and keep the source's spelling in
   `#[doc(alias = "CAP")]`. A constant that states a source for a different spelling carries that
   spelling as an alias, or it fails.

Rules 1, 2 and 5 have no exception: an offset, a mask and a register constant are renamed. Rules 3
and 4 take the kept form rust_names.py describes (a name that mirrors a specification or the
standard library opens its doc comment with `(<name>, <source>)` and carries `#[doc(alias)]`).
There is no baseline: the ceiling is 0, and every finding fails.

The rules are the naming rules page's "Registers and constants" and "Units" sections in the
operating system project this template serves (design/naming.md there). The file's name is
provisional.

BUGS:
- A lexer, not a parser. Whether a constant is a register offset is read from its module and its
  value, so an offset written as an expression (`BASE + 0x10`) in a module with another name is
  missed.
- A mask is recognized by the word `mask` in its name. A multi-bit constant that never says so
  (`0xFF00`) is not read; a reviewer reads those.
- Whether a name spells out what a register is stays a reader's judgment: this check refuses the
  spec's own abbreviation only where the doc comment states it as the source.
"""

import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rust_names  # noqa: E402

INTEGERS = {'u8', 'u16', 'u32', 'u64', 'u128', 'usize', 'i8', 'i16', 'i32', 'i64', 'i128', 'isize'}
REGISTER_MODULES = {'register', 'registers', 'offset', 'offsets'}
OTHER_QUANTITIES = {'mask', 'shift', 'value', 'bytes', 'bits'}
NUMBER = re.compile(r'0[xXbBoO][0-9A-Fa-f_]+|[0-9][0-9_]*')


def _words(table, words):
    return set(words.get(table, {}).get('words', ()))


def is_plain_literal(definition):
    """Whether the initializer is one integer literal (an offset), not a shift or a mask."""
    value = definition.value
    return len(value) == 1 and bool(NUMBER.fullmatch(value[0]))


def in_register_module(definition):
    return any(c in REGISTER_MODULES for m in definition.module for c in rust_names.components(m))


def stated_source(definition):
    """The spelling the doc comment's first paragraph states as the source, or None."""
    paragraph = '\n'.join(definition.docs).split('\n\n')[0].replace('\n', ' ')
    m = re.search(r'\(\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*,\s*[^)]*[A-Za-z][^)]*\)', paragraph)
    return m.group(1) if m else None


def findings(definition, words):
    """`[(message, keepable)]` for each rule `definition` breaks."""
    out = []
    parts = rust_names.components(definition.name)
    kind = definition.kind
    constant = kind in ('const', 'static')
    integer = definition.type_name in INTEGERS
    if constant and integer and is_plain_literal(definition) \
            and not set(parts[-1:]) & OTHER_QUANTITIES and parts[-1:] != ['register']:
        if 'offset' in parts or 'offsets' in parts or in_register_module(definition):
            out.append(('a register offset ends `_REGISTER` and names the register, as '
                        '`CONTROL_REGISTER`', False))
    if constant and ('mask' in parts or 'masks' in parts) and parts[-1] not in ('mask', 'masks'):
        out.append(('a mask of several bits ends `_MASK`', False))
    qualifiers = _words('address_qualifiers', words)
    for k, part in enumerate(parts):
        if part in ('address', 'addresses', 'addr', 'addrs'):
            if k and parts[k - 1] in qualifiers:
                continue
            spelled = 'address' if part.startswith('addr') and not part.startswith('address') \
                else part
            out.append((f'an address is `_VIRTUAL_ADDRESS` or `_PHYSICAL_ADDRESS` in every '
                        f'location; write the {spelled} as one of them', True))
            break
    sized = ('size', 'sizes', 'len', 'length', 'lengths')
    if kind in ('const', 'static', 'field') and any(p in sized for p in parts) \
            and not set(parts) & _words('size_units', words):
        out.append(('a size, a length or a limit carries its unit: end it `_BYTES`, `_BITS`, '
                    '`_WORDS` or another unit from `[size_units]`', True))
    if constant and integer:
        source = stated_source(definition)
        aliases = [a.strip().lower() for a in definition.aliases]
        if source == definition.name:
            out.append((f'a register, field or bit constant is spelled out: name what it is and '
                        f'carry the source spelling `{source}` in #[doc(alias = "{source}")]',
                        False))
        elif source and source.lower() not in aliases:
            out.append((f'its doc comment states the source spelling `{source}`, so it carries '
                        f'#[doc(alias = "{source}")]', False))
    return out


def judge(path, found, words):
    bad = []
    for d in found:
        for message, keepable in findings(d, words):
            if keepable and rust_names.kept(d)[0]:
                continue
            tail = ''
            if keepable and d.kind not in ('parameter', 'binding'):
                tail = (f' If it mirrors a specification or the standard library, keep it and say '
                        f'so at the item: open its doc comment with `({d.name}, <source>)` and add '
                        f'#[doc(alias = "<plain-English name>")].')
            bad.append(f'{path}:{d.line}: {d.kind} {d.name}: {message}.{tail}')
    return bad


def run(argv):
    import argparse
    parser = argparse.ArgumentParser(prog='register_names.py')
    parser.add_argument('files', nargs='*')
    parser.add_argument('--manifest', help='accepted for symmetry with the other naming checks')
    parser.add_argument('--words', default=str(rust_names.WORDS))
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    words = rust_names.load_words(args.words)
    bad, judged = [], 0
    for path in args.files:
        if not path.endswith('.rs'):
            continue
        found = rust_names.file_definitions(path, Path(path).read_text(encoding='utf-8',
                                                                       errors='replace'))
        judged += len(found)
        bad += judge(path, found, words)
    for line in bad:
        print(line, file=sys.stdout if args.report else sys.stderr)
    if args.report or len(bad) <= rust_names.CEILING:
        print(f'register_names: {judged} names judged, {len(bad)} refused '
              f'(ceiling {rust_names.CEILING})')
        return 0
    print(f'\nregister_names: {len(bad)} names break the register naming rules, over the ceiling '
          f'of {rust_names.CEILING}.', file=sys.stderr)
    return 1


def selftest():
    words = rust_names.load_words()
    src = '''
pub mod registers {
    pub const CONTROL_REGISTER: u64 = 0x00;
    pub const STATUS: u64 = 0x04;
    pub const STATUS_MASK: u32 = 0xF0;
    pub const RESET_VALUE: u32 = 0;
}
pub const DATA_OFFSET: usize = 8;
pub const IDENTIFIER_REGISTER: usize = 0x30;
pub const MASK_STATUS: u32 = 0x3;
pub const STATUS_MASK_BITS: u32 = 0x3;
pub const FRAME_PHYSICAL_ADDRESS: u64 = 0;
pub const BASE_ADDRESS: u64 = 0;
pub const GATEWAY_IP_ADDRESS: u32 = 0;
pub const BUFFER_SIZE: usize = 4096;
pub const BUFFER_SIZE_BYTES: usize = 4096;
pub const PAGE_SIZE_SHIFT: u32 = 12;
pub struct Header { pub len: u16, pub payload_length_bytes: u16, pub dest_addr: u32 }
/// **Controller Capabilities** (CAP, NVM Express Base Specification 2.0, section 3.1.1).
#[doc(alias = "controller capabilities")]
pub const CAP: u32 = 0;
/// **Controller Capabilities** (CAP, NVM Express Base Specification 2.0, section 3.1.1).
#[doc(alias = "CAP")]
pub const CONTROLLER_CAPABILITIES_REGISTER: u64 = 0;
/// **Controller Capabilities** (CAP, NVM Express Base Specification 2.0, section 3.1.1).
pub const CONTROLLER_CAPABILITIES_MASK: u32 = 0xFF;
/// **Page size** (PAGE_SIZE, a datasheet).
#[doc(alias = "page size")]
pub const PAGE_SIZE: usize = 4096;
pub fn count(len: usize) -> usize { let size = len; size }
'''
    found = rust_names.definitions(src)
    bad = judge('x.rs', found, words)
    got = sorted({line.split(': ')[1] for line in bad})
    want = sorted(['const STATUS', 'const DATA_OFFSET', 'const MASK_STATUS', 'const STATUS_MASK_BITS',
                   'const BASE_ADDRESS', 'const BUFFER_SIZE', 'field len', 'field dest_addr',
                   'const CAP', 'const CONTROLLER_CAPABILITIES_MASK', 'const PAGE_SIZE'])
    failed = 0
    if got != want:
        failed += 1
        print(f'register_names selftest: refused {got}, wanted {want}', file=sys.stderr)
    text = '\n'.join(bad)
    for needle in ('a register offset ends `_REGISTER`', 'a mask of several bits ends `_MASK`',
                   'is `_VIRTUAL_ADDRESS` or `_PHYSICAL_ADDRESS`', 'carries its unit',
                   'is spelled out', 'carries #[doc(alias = "CAP")]'):
        if needle.replace('carries ', 'so it carries ') not in text and needle not in text:
            failed += 1
            print(f'register_names selftest: no message holds {needle!r}', file=sys.stderr)
    if failed:
        return 1
    print('register_names selftest: ok')
    return 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
