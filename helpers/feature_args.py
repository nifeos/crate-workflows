#!/usr/bin/env python3
"""Print the cargo feature flags for the all-features lint pass.

usage: feature_args.py MANIFEST [EXCLUDED_FEATURE ...]
       feature_args.py --selftest

With no exclusions the output is `--all-features`, the strict form. With exclusions it is
`--no-default-features --features a,b,c`, where the list is every feature the crate declares
(implicit features of optional dependencies included) minus the excluded ones, so a set of
features that cannot be combined is linted without them. An excluded name the crate does not
declare is an error: a stale exclusion must not linger. When the exclusions leave no feature, the
output is `--no-default-features` alone, because `--features` with an empty list is a cargo usage
error.
"""
import json
import os
import subprocess
import sys
import tempfile


def flags(declared, excluded):
    left = sorted(declared - excluded)
    if not left:
        return "--no-default-features"
    return "--no-default-features --features " + ",".join(left)


def selftest():
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print(f"FAIL {label}: expected {want!r}, got {got!r}")

    check("some left", flags({"a", "b", "c"}, {"b"}), "--no-default-features --features a,c")
    check("none left", flags({"simulator"}, {"simulator"}), "--no-default-features")
    check("none excluded", flags({"a"}, set()), "--no-default-features --features a")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "src"))
        open(os.path.join(d, "src", "lib.rs"), "w").close()
        manifest = os.path.join(d, "Cargo.toml")
        with open(manifest, "w") as f:
            f.write('[package]\nname = "only_feature"\nversion = "0.1.0"\nedition = "2024"\n'
                    '[features]\nsimulator = []\n')
        out = subprocess.run([sys.executable, __file__, manifest, "simulator"],
                             capture_output=True, text=True)
        check("only feature excluded", out.stdout.strip(), "--no-default-features")
    print("feature_args selftest: %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
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
    print(flags(declared, excluded))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
