//! Fixture: an opcode named `SIZE` with no entry in `.github/opcode-names` is refused.

pub mod block {
    /// **Size**, the command that asks the device for its size.
    pub const SIZE: u8 = 3;
}
