//! The word unsafe appears here, and in /* unsafe */ comments, strings and raw strings only.

// unsafe { nothing }
/* a /* nested unsafe */ comment */

/// Says the word.
pub fn word() -> &'static str {
    let _quote = '"';
    let _raw = r#"unsafe " still a string"#;
    let _byte = b"unsafe";
    let _identifier = r#unsafe_not_a_keyword();
    "unsafe { }"
}

fn r#unsafe_not_a_keyword() {}

/// A lifetime is not a character literal.
pub fn pick<'a>(left: &'a str, _right: &'a str) -> &'a str {
    left
}
