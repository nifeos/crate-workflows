# crate-workflows-sample

[![check](https://github.com/nifeos/crate-workflows/actions/workflows/selftest.yml/badge.svg?branch=main)](https://github.com/nifeos/crate-workflows/actions/workflows/selftest.yml?query=branch%3Amain)
[![proofs](https://github.com/nifeos/crate-workflows/actions/workflows/selftest.yml/badge.svg?branch=main)](https://github.com/nifeos/crate-workflows/actions/workflows/selftest.yml?query=branch%3Amain)
[![license](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](https://github.com/nifeos/crate-workflows#license)
[![minimum Rust version](https://img.shields.io/badge/rust-1.85%2B-blue.svg)](https://github.com/nifeos/crate-workflows/blob/main/sample/Cargo.toml)

The template's fixture crate: one function, two tests, one proof, and a falsification patch. The
selftest workflow runs every reusable workflow against this crate, so a gate that cannot pass
here is broken before any real crate meets it. It carries `publish = false` on purpose, and the
selftest tells the standalone gate so.

## EXAMPLES

```rust
assert_eq!(crate_workflows_sample::saturating_add_percent(30, 40), 70);
assert_eq!(crate_workflows_sample::saturating_add_percent(60, 60), 100);
```

## What is proven

- The sum never exceeds 100, for every first percentage up to 100 and every second byte. The
  falsification patch in `falsifications/` turns the harness red.

## BUGS

- The fixture proves the workflows, not the function. Nothing here is a claim about percentage
  arithmetic worth depending on.

## Minimum Rust version

Rust 1.85.

## License

Licensed under either of the MIT license ([LICENSE-MIT](LICENSE-MIT)) or the Apache License,
Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE)), at your option.
