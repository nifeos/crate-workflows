//! An unsafe fn that follows a test module with braces in a string.

#[cfg(test)]
mod tests {
    const BRACE: &str = "}";
}

/// Not safe to call.
pub unsafe fn raw(pointer: *const u8) -> u8 {
    *pointer
}
