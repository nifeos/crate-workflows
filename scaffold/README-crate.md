# <crate>

[![check](https://github.com/nifeos/<crate>/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nifeos/<crate>/actions/workflows/ci.yml?query=branch%3Amain)
[![proofs](https://github.com/nifeos/<crate>/actions/workflows/proofs.yml/badge.svg?branch=main)](https://github.com/nifeos/<crate>/actions/workflows/proofs.yml?query=branch%3Amain)
[![license](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](https://github.com/nifeos/<crate>#license)
[![minimum Rust version](https://img.shields.io/badge/rust-<rust-version>%2B-blue.svg)](https://github.com/nifeos/<crate>/blob/main/Cargo.toml)

One line: what the crate is for.

The crate is `no_std`-friendly, dual licensed `MIT OR Apache-2.0`, and proven: every property it
claims is a Kani harness in the tree, and every harness carries a falsification patch that shows
what turns it red.

## EXAMPLES

```rust
// The smallest thing a user does with this crate, as real code that compiles.
```

## What is proven

- One line per property, in the words a user would use. Name the harness only where a reader
  needs it to run one.

## Building and testing

```sh
cargo build
cargo test   # add --features <name> for any feature a test target requires
rustup target add <bare-metal target>
cargo build --lib --target <bare-metal target>
```

Name every command a reader needs, with the feature flags. A test target that needs a feature
(`required-features` in `Cargo.toml`) does not run under a plain `cargo test`, and Cargo says
nothing about it, so say which flag runs it. Say to run `rustup target add` before the first bare-metal build, and list the
targets the crate's `ci.yml` builds. Delete the bare-metal lines for a host-only crate.

### Running the proofs

Install Kani here, before any other mention of `cargo kani`: `cargo install --locked
kani-verifier --version <the version in the template's .kani-version>`, then `cargo kani setup`.
The setup step downloads a model checker, so say that it needs network access.

Then say how long `cargo kani` takes and its peak memory, as you measured them (`/usr/bin/time -v
cargo kani`), and how to run one harness: `cargo kani --harness <module>::<name> --exact`, with the
full path, since `--exact` refuses a bare name. If the crate's `proofs.yml` passes `kani-args`
(for example `--jobs 2 --output-format=terse`), give those flags and why.

Say what a passing run prints that looks alarming and means nothing: the `use of an unstable feature`
warning, the `Found the following unsupported constructs` warning, the `aborting path on
assume(false)` lines, checks described as unreachable code, and the future-compatibility warnings
Kani's toolchain raises. Point the reader to the last line (`Complete - N successfully verified
harnesses, 0 failures, N total.`) as the answer.

### Running one falsification patch

```sh
patch -p1 --no-backup-if-mismatch < falsifications/<module>.<harness>.patch
cargo kani --harness <module>::<harness> --exact   # ends VERIFICATION:- FAILED
git checkout -- src
```

Give one real example from the crate in place of these placeholders, and say what the failing run
prints.

## BUGS

- The starting shape carries none. A limit you know of lands here, beside the feature it limits, the
  day you learn of it.

## Minimum Rust version

The `rust-version` in `Cargo.toml`, as `Rust 1.xx`. The badge under the title says the same
number, and `check / standalone` fails when the two disagree. Say how to check it:
`rustup toolchain install 1.xx --profile minimal`, then `cargo +1.xx test`, and the bare-metal
build with the same `+1.xx`.

## License

Licensed under either of the MIT license (`LICENSE-MIT`) or the Apache License,
Version 2.0 (`LICENSE-APACHE`), at your option.
