#!/usr/bin/env python3
"""Print the cargo feature flags for the all-features lint pass.

usage: feature_args.py MANIFEST [EXCLUDED_FEATURE ...]

With no exclusions the output is `--all-features`, the strict form. With exclusions it is
`--no-default-features --features a,b,c`, where the list is every feature the crate declares
(implicit features of optional dependencies included) minus the excluded ones, so a set of
features that cannot be combined is linted without them. An excluded name the crate does not
declare is an error: a stale exclusion must not linger.
"""
import json
import os
import subprocess
import sys


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    manifest, excluded = argv[1], set(argv[2:])
    if not excluded:
        print("--all-features")
        return 0
    meta = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--no-deps", "--format-version", "1", "--manifest-path", manifest]))
    want = os.path.realpath(manifest)
    package = next(p for p in meta["packages"] if os.path.realpath(p["manifest_path"]) == want)
    declared = set(package["features"]) - {"default"}
    unknown = excluded - declared
    if unknown:
        print("error: excluded features not declared by the crate: " + " ".join(sorted(unknown)),
              file=sys.stderr)
        return 1
    print("--no-default-features --features " + ",".join(sorted(declared - excluded)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
