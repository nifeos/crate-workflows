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

## BUGS

- The starting shape carries none. A known limit lands here, beside the feature it limits, the
  day it is known.

## Minimum Rust version

The `rust-version` in `Cargo.toml`, as `Rust 1.xx`. The badge under the title says the same
number, and `check / standalone` fails when the two disagree.

## License

Licensed under either of the MIT license (`LICENSE-MIT`) or the Apache License,
Version 2.0 (`LICENSE-APACHE`), at your option.
