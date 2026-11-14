#!/usr/bin/env python3
"""Print a manifest's version, for the release gate.

    python3 read_version.py <Cargo.toml>

The version is the one cargo resolves, so `version.workspace = true` prints the workspace's.
"""

import sys

import crate_info


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        pkg, _ = crate_info.own(argv[1])
    except (RuntimeError, OSError) as e:
        print(f'read_version: {e}', file=sys.stderr)
        return 1
    print(pkg['version'], end='')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
