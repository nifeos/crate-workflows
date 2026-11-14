//! The proof the crate's one property holds: the result never passes 100.
//!
//! The lint pass (`clippy --cfg kani`) compiles this module against the template's shim, and the
//! real proof runs in proofs.yml. The record below is the falsification gate's form: the named
//! patch must apply, and must turn this harness red at its own assertion.

use crate::saturating_add_percent;

/// Falsification: replayable `falsifications/src.proofs.saturating_add_percent_capped.patch`
#[kani::proof]
fn saturating_add_percent_capped() {
    let a: u8 = kani::any();
    kani::assume(a <= 100);
    let b: u8 = kani::any();
    assert!(saturating_add_percent(a, b) <= 100);
}
