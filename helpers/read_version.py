#!/usr/bin/env python3
"""Print a manifest's version, for the release gate."""

import sys
import tomllib


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], 'rb') as f:
        print(tomllib.load(f).get('package', {}).get('version', ''), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
