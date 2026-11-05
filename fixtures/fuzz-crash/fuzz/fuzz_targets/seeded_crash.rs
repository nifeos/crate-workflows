#![no_main]

use libfuzzer_sys::fuzz_target;

// Any non-empty input panics, so the fuzzer finds the crash in its first moments.
fuzz_target!(|data: &[u8]| {
    let _ = fuzz_crash::checksum(data);
    assert!(data.is_empty(), "seeded crash");
});
