//! A fixture crate: enough crate to run every gate against, and nothing more.
//!
//! One function with two visible behaviors (clamped, exact), tests that pin both, and one Kani
//! harness whose falsification patch shows what breaks the property. The selftest workflow runs
//! every reusable workflow against this crate; if a gate cannot pass here, it is broken, and no
//! crate repository should be finding that out.

/// Adds two percentages, saturating at 100.
///
/// ```
/// assert_eq!(crate_workflows_sample::saturating_add_percent(60, 60), 100);
/// assert_eq!(crate_workflows_sample::saturating_add_percent(30, 40), 70);
/// ```
pub fn saturating_add_percent(a: u8, b: u8) -> u8 {
    let sum = a.saturating_add(b);
    if sum > 100 { 100 } else { sum }
}

#[cfg(kani)]
mod proofs;

#[cfg(test)]
mod tests {
    use crate::saturating_add_percent;

    #[test]
    fn caps_at_100() {
        assert_eq!(saturating_add_percent(60, 60), 100);
        // The saturating add, not only the clamp: 200 + 100 overflows u8 first.
        assert_eq!(saturating_add_percent(200, 100), 100);
    }

    #[test]
    fn exact_sum_passes_through() {
        assert_eq!(saturating_add_percent(30, 40), 70);
        assert_eq!(saturating_add_percent(0, 0), 0);
    }
}
