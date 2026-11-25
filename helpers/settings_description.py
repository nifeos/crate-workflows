#!/usr/bin/env python3
"""The description a crate repository carries, from settings/repository-settings.json.

    python3 settings_description.py --selftest

script/apply-settings writes `description(settings, repo, crate)` and script/check-settings reads
it back, so a description changed by hand is drift. A repository carries the file's
`metadata.description` with `{crate}` filled in, unless the file's `descriptions` table holds its own
text under the repository's name (the name without the owner, so an entry survives a transfer). Any
other description, one written in the web interface included, is replaced at the next apply.

A crate repository stands alone, so a description that names nife (nife, nifeos, nifefs) is refused,
as is one longer than GitHub's limit of 350 characters. The selftest also reads the real settings
file, so a refused entry fails `script/lint` before it reaches a repository.
"""

import json
import re
import sys
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / 'settings' / 'repository-settings.json'
GITHUB_LIMIT = 350
NAMES_NIFE = re.compile(r'\bnife', re.IGNORECASE)


def refusal(text):
    """Why `text` may not be a crate repository's description, or None."""
    if NAMES_NIFE.search(text):
        return 'names nife; a crate repository stands alone'
    if len(text) > GITHUB_LIMIT:
        return f'is {len(text)} characters, over GitHub\'s limit of {GITHUB_LIMIT}'
    if not text.strip():
        return 'is empty'
    return None


def description(settings, repo, crate):
    """The description for `repo` (owner/name or name) holding `crate`; ValueError when refused."""
    name = repo.split('/')[-1]
    own = (settings.get('descriptions') or {}).get(name)
    text = own if own is not None else settings['metadata']['description'].replace('{crate}', crate)
    why = refusal(text)
    if why:
        raise ValueError(f'description of {name} {why}: {text!r}')
    return text


def file_findings(settings):
    """Every refused description the file can produce: the template and each own entry."""
    out = []
    template = settings['metadata']['description']
    if '{crate}' not in template:
        out.append('metadata.description: the template has no {crate} to fill')
    texts = [('metadata.description', template.replace('{crate}', 'example_crate'))]
    texts += [(f'descriptions.{k}', v) for k, v in (settings.get('descriptions') or {}).items()
              if not k.startswith('_')]
    for where, text in texts:
        why = refusal(text)
        if why:
            out.append(f'{where} {why}')
    return out


def selftest():
    settings = {'metadata': {'description': '{crate}: a standalone Rust crate'},
                'descriptions': {'own': 'A crate with its own words'}}
    ok = True

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {name}: expected {want!r}, got {got!r}')

    def refused(name, s, repo, crate):
        nonlocal ok
        try:
            description(s, repo, crate)
            ok = False
            print(f'FAIL {name}: accepted')
        except ValueError:
            pass

    expect('the template fills the crate', description(settings, 'org/some', 'some'),
           'some: a standalone Rust crate')
    expect('--crate fills, not the repository name', description(settings, 'org/repo', 'other'),
           'other: a standalone Rust crate')
    expect('an own entry wins', description(settings, 'org/own', 'own'), 'A crate with its own words')
    expect('an own entry is keyed without the owner', description(settings, 'own', 'own'),
           'A crate with its own words')
    for word in ('nife', 'nifeos', 'Nifeos', 'NIFEFS'):
        refused(f'a template naming {word}', {'metadata': {'description': f'{{crate}}: a {word} crate'}},
                'org/x', 'x')
        refused(f'an own entry naming {word}',
                {'metadata': {'description': '{crate}'}, 'descriptions': {'x': f'from {word}'}}, 'org/x', 'x')
    expect('knife is not nife', refusal('a knife'), None)
    refused('over the limit', {'metadata': {'description': 'x' * (GITHUB_LIMIT + 1)}}, 'org/x', 'x')
    refused('empty own entry', {'metadata': {'description': '{crate}'}, 'descriptions': {'x': ' '}},
            'org/x', 'x')
    expect('a template without {crate} is a finding',
           file_findings({'metadata': {'description': 'a crate'}}),
           ['metadata.description: the template has no {crate} to fill'])
    real = file_findings(json.loads(SETTINGS.read_text()))
    expect('the real settings file', real, [])
    print('settings_description selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(selftest() if sys.argv[1:] == ['--selftest'] else 2)
