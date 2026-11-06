//! A crate root that forbids unsafe code.
#![forbid(unsafe_code)]

/// Adds one.
pub fn add_one(value: u8) -> u8 {
    value.wrapping_add(1)
}
