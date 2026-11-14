#!/usr/bin/env python3
"""Print a manifest's `rust-version`, for the weekly MSRV job.

    python3 read_rust_version.py <Cargo.toml>

The value is the one cargo resolves, so `rust-version.workspace = true` prints the workspace's.
Empty output means the manifest states no MSRV, which the standalone gate refuses; the job fails
on it rather than skipping, because a missing MSRV here means the gate and the manifest disagree.
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
        print(f'read_rust_version: {e}', file=sys.stderr)
        return 1
    print(pkg['rust_version'], end='')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
