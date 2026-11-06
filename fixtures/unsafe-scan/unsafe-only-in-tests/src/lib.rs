//! Unsafe code only under cfg(test).

/// Adds one.
pub fn add_one(value: u8) -> u8 {
    value.wrapping_add(1)
}

#[cfg(test)]
mod tests {
    #[test]
    fn reads() {
        let x = 1u8;
        let _ = unsafe { *(&x as *const u8) };
    }
}
