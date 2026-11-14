#!/usr/bin/env python3
"""Fit the shared settings to a repository of several crates.

    python3 settings_members.py --selftest

script/apply-settings and script/check-settings call `expand(settings, members)` after reading
settings/repository-settings.json, so a repository of several crates is applied and read back by
one rule. With no members (a repository of one crate) the settings are returned as they are.

A repository of several crates calls `check` and `proofs` once for each crate, and a required
status is named for the caller's job, so each crate has its own: the caller's job ids are
`check-<crate>` and `proofs-<crate>`, and the one `check / fmt` becomes `check-<crate> / fmt` for
each. The release workflow tags `<crate>-v<version>` there, so the tags ruleset also covers
`refs/tags/*-v*`; a tag that the ruleset does not name is a tag anybody may make.
"""

import copy
import sys

PER_CRATE = ('check', 'proofs')
CRATE_TAGS = 'refs/tags/*-v*'


def expand(settings, members):
    if not members:
        return settings
    out = copy.deepcopy(settings)
    for rs in out['rulesets']:
        checks = rs['rules'].get('required_status_checks')
        if checks:
            wanted = []
            for entry in checks['required_status_checks']:
                job, _, rest = entry['context'].partition(' / ')
                if job in PER_CRATE:
                    wanted += [{**entry, 'context': f'{job}-{m} / {rest}'} for m in sorted(members)]
                else:
                    wanted.append(entry)
            checks['required_status_checks'] = wanted
        include = rs['conditions'].get('ref_name', {}).get('include', [])
        if rs['target'] == 'tag' and 'refs/tags/v*' in include and CRATE_TAGS not in include:
            include.append(CRATE_TAGS)
    return out


def selftest():
    base = {'rulesets': [
        {'target': 'branch', 'conditions': {'ref_name': {'include': ['~DEFAULT_BRANCH']}},
         'rules': {'required_status_checks': {'strict': True, 'required_status_checks': [
             {'context': 'check / fmt'}, {'context': 'proofs / kani'},
             {'context': 'hold / architect hold'}]}}},
        {'target': 'tag', 'conditions': {'ref_name': {'include': ['refs/tags/v*']}}, 'rules': {}}]}
    ok = True
    if expand(base, []) is not base:
        ok = False
        print('FAIL: no members changes nothing')
    got = expand(base, ['b', 'a'])
    contexts = [c['context'] for c in got['rulesets'][0]['rules']['required_status_checks']['required_status_checks']]
    if contexts != ['check-a / fmt', 'check-b / fmt', 'proofs-a / kani', 'proofs-b / kani',
                    'hold / architect hold']:
        ok = False
        print(f'FAIL: contexts {contexts}')
    if got['rulesets'][1]['conditions']['ref_name']['include'] != ['refs/tags/v*', CRATE_TAGS]:
        ok = False
        print('FAIL: tag patterns')
    if base['rulesets'][1]['conditions']['ref_name']['include'] != ['refs/tags/v*']:
        ok = False
        print('FAIL: the input was changed')
    print('settings_members selftest: %s' % ('ok' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(selftest() if sys.argv[1:] == ['--selftest'] else 2)
