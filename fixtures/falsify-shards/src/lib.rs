//! A fixture for the falsify shard selftest: three small functions, each with one Kani harness
//! and one falsification patch, so a call of proofs.yml with two harnesses a shard replays them in
//! two shards of unequal size.

/// The larger of two bytes.
pub fn larger(a: u8, b: u8) -> u8 {
    if a > b { a } else { b }
}

/// A byte halved, rounding down.
pub fn half(a: u8) -> u8 {
    a / 2
}

/// A byte with its lowest bit cleared.
pub fn even(a: u8) -> u8 {
    a & !1
}

#[cfg(kani)]
mod proofs;
