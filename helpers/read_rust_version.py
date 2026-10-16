#!/usr/bin/env python3
"""Print a manifest's `rust-version`, for the weekly MSRV job.

    python3 read_rust_version.py <Cargo.toml>

Empty output means the manifest states no MSRV, which the standalone gate refuses; the job fails
on it rather than skipping, because a missing MSRV here means the gate and the manifest disagree.
"""

import sys
import tomllib


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], 'rb') as f:
        print(tomllib.load(f).get('package', {}).get('rust-version', ''), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
