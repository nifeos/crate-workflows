#!/usr/bin/env python3
"""Fit the shared settings to the organization that owns a crate repository.

    python3 settings_owner.py --selftest

script/apply-settings and script/check-settings call `for_owner(settings, owner)` after reading
settings/repository-settings.json and before helpers/settings_members.py, so a repository is
applied and read back against the values of the organization that owns it. With no entry for the
owner, the settings are returned as they are.

The file's `owners` table maps an organization to the values that differ there. While the crate
repositories move from one organization to another, the two hold different values for the team's
organization, the release app and its bypass actor id, and the Actions allowlist. A dictionary
merges key by key, `rulesets` merges by ruleset name, and any other value, a list included,
replaces the shared one. An override for a ruleset the file does not name is an error, never
silently dropped.
"""

import copy
import sys


def merge(base, over, path='settings'):
    """`over` merged into a deep copy of `base`."""
    if not isinstance(base, dict) or not isinstance(over, dict):
        return copy.deepcopy(over)
    out = copy.deepcopy(base)
    for key, value in over.items():
        if key == 'rulesets':
            out[key] = merge_rulesets(base.get(key) or [], value, f'{path}.{key}')
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = merge(base[key], value, f'{path}.{key}')
        else:
            out[key] = copy.deepcopy(value)
    return out


def merge_rulesets(base, over, path):
    by_name = {rs['name']: i for i, rs in enumerate(base)}
    out = copy.deepcopy(base)
    for entry in over:
        name = entry.get('name')
        if name not in by_name:
            raise ValueError(f'{path}: an override names ruleset {name!r}, which the file does not hold')
        out[by_name[name]] = merge(base[by_name[name]], entry, f'{path}[{name}]')
    return out


def for_owner(settings, owner):
    """The settings as they hold for a repository owned by `owner`, without the `owners` table."""
    owners = settings.get('owners') or {}
    shared = {k: v for k, v in settings.items() if k != 'owners'}
    if owner not in owners:
        return shared
    over = {k: v for k, v in owners[owner].items() if not k.startswith('_')}
    return merge(shared, over)


def selftest():
    base = {
        'team': {'org': 'old', 'slug': 'maintainers'},
        'actions': {'patterns_allowed': ['a@*'], 'enabled': True},
        'rulesets': [{'name': 'branch', 'bypass_actors': []},
                     {'name': 'tags', 'bypass_actors': [{'actor_id': 1}], 'rules': {'creation': True}}],
        'owners': {'new': {
            '_readme': 'ignored',
            'team': {'org': 'new'},
            'actions': {'patterns_allowed': ['a@*', 'b@*']},
            'rulesets': [{'name': 'tags', 'bypass_actors': [{'actor_id': 2}]}]}},
    }
    ok = True

    def expect(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f'FAIL {name}: expected {want!r}, got {got!r}')

    old = for_owner(base, 'old')
    expect('an owner with no entry keeps the shared values', old['team']['org'], 'old')
    expect('the owners table never reaches the caller', 'owners' in old, False)
    new = for_owner(base, 'new')
    expect('a dictionary merges key by key', new['team'], {'org': 'new', 'slug': 'maintainers'})
    expect('a list replaces', new['actions']['patterns_allowed'], ['a@*', 'b@*'])
    expect('a key the override leaves out stays', new['actions']['enabled'], True)
    expect('a ruleset merges by name', new['rulesets'][1],
           {'name': 'tags', 'bypass_actors': [{'actor_id': 2}], 'rules': {'creation': True}})
    expect('another ruleset is untouched', new['rulesets'][0], base['rulesets'][0])
    expect('a key starting with _ is a comment', '_readme' in new, False)
    expect('the input is unchanged', base['team']['org'], 'old')
    expect('the input ruleset is unchanged', base['rulesets'][1]['bypass_actors'], [{'actor_id': 1}])
    bad = copy.deepcopy(base)
    bad['owners']['new']['rulesets'] = [{'name': 'missing'}]
    try:
        for_owner(bad, 'new')
        ok = False
        print('FAIL an override of a ruleset the file does not hold was accepted')
    except ValueError:
        pass
    print('settings_owner selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(selftest() if sys.argv[1:] == ['--selftest'] else 2)
