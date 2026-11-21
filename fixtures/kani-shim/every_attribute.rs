//! Uses every attribute the lint shim supplies, in the forms real harnesses write them.
//! `script/lint` compiles this against the shim, so an attribute the shim lacks fails there.

#![allow(dead_code)]

#[kani::proof]
#[kani::unwind(4)]
fn unwound() {
    let a: u8 = kani::any();
    kani::assume(a < 4);
}

#[kani::proof]
#[kani::should_panic]
fn panics() {
    let a: u8 = kani::any();
    assert!(a < 3);
}

#[kani::proof]
#[kani::solver(minisat)]
fn solved() {}

fn real() -> u8 {
    1
}

fn replacement() -> u8 {
    2
}

#[kani::proof]
#[kani::stub(real, replacement)]
fn stubbed() {
    let _ = real();
}
