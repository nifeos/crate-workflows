//! One harness for each function. Each record names the patch that must turn it red.

use crate::{even, half, larger};

/// Falsification: replayable `falsifications/proofs.larger_is_at_least_both.patch`
#[kani::proof]
fn larger_is_at_least_both() {
    let a: u8 = kani::any();
    let b: u8 = kani::any();
    let m = larger(a, b);
    assert!(m >= a && m >= b);
}

/// Falsification: replayable `falsifications/proofs.half_never_grows.patch`
#[kani::proof]
fn half_never_grows() {
    let a: u8 = kani::any();
    assert!(half(a) <= a);
}

/// Falsification: replayable `falsifications/proofs.even_is_even.patch`
#[kani::proof]
fn even_is_even() {
    let a: u8 = kani::any();
    assert!(even(a) % 2 == 0);
}
