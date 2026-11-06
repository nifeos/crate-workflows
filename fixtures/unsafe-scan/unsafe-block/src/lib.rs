//! A crate with an unsafe block.

/// Reads the first byte.
pub fn first(data: &[u8]) -> u8 {
    unsafe { *data.as_ptr() }
}
