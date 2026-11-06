//! A fixture for the fuzz selftest.

/// Adds the bytes with wrapping arithmetic.
pub fn checksum(data: &[u8]) -> u8 {
    data.iter().fold(0, |sum, byte| sum.wrapping_add(*byte))
}
