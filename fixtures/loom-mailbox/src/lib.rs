//! A fixture for the loom selftest: a mailbox of one slot, written once by one thread and read by
//! another. The flag's Release store and Acquire load order the slot's write before its read, and
//! the loom model below checks every interleaving of the two threads.

#[cfg(loom)]
use loom::{
    cell::UnsafeCell,
    sync::atomic::{AtomicBool, Ordering},
};
#[cfg(not(loom))]
use std::sync::atomic::{AtomicBool, Ordering};

/// The standard cell with the closure interface loom's cell has, so one body serves both builds.
#[cfg(not(loom))]
struct UnsafeCell<T>(std::cell::UnsafeCell<T>);

#[cfg(not(loom))]
impl<T> UnsafeCell<T> {
    fn new(value: T) -> Self {
        Self(std::cell::UnsafeCell::new(value))
    }

    fn with<R>(&self, f: impl FnOnce(*const T) -> R) -> R {
        f(self.0.get())
    }

    fn with_mut<R>(&self, f: impl FnOnce(*mut T) -> R) -> R {
        f(self.0.get())
    }
}

/// One slot and the flag that says it is full.
pub struct Mailbox {
    full: AtomicBool,
    slot: UnsafeCell<u32>,
}

// SAFETY: the slot is written only before `full` is set and read only after it is seen set.
unsafe impl Sync for Mailbox {}

impl Default for Mailbox {
    fn default() -> Self {
        Self::new()
    }
}

impl Mailbox {
    /// An empty mailbox.
    pub fn new() -> Self {
        Self {
            full: AtomicBool::new(false),
            slot: UnsafeCell::new(0),
        }
    }

    /// Puts `value` in the slot and marks it full.
    ///
    /// # Safety
    ///
    /// The caller puts at most once, from one thread.
    pub unsafe fn put(&self, value: u32) {
        // SAFETY: the one writer writes before it sets the flag, and no reader reads before it.
        self.slot.with_mut(|slot| unsafe { *slot = value });
        self.full.store(true, Ordering::Release);
    }

    /// The value in the slot, once it is full.
    pub fn take(&self) -> Option<u32> {
        if !self.full.load(Ordering::Acquire) {
            return None;
        }
        // SAFETY: the Acquire load saw the writer's Release store, so the write is complete.
        Some(self.slot.with(|slot| unsafe { *slot }))
    }
}

#[cfg(all(test, not(loom)))]
mod tests {
    use super::Mailbox;

    #[test]
    fn a_full_mailbox_gives_its_value() {
        let mailbox = Mailbox::new();
        assert_eq!(mailbox.take(), None);
        // SAFETY: one put, from this thread.
        unsafe { mailbox.put(7) };
        assert_eq!(mailbox.take(), Some(7));
    }
}

#[cfg(all(test, loom))]
mod interleavings {
    use super::Mailbox;
    use loom::{sync::Arc, thread};

    #[test]
    fn a_reader_sees_the_value_or_nothing() {
        loom::model(|| {
            let mailbox = Arc::new(Mailbox::new());
            let writer = Arc::clone(&mailbox);
            // SAFETY: the one put of this mailbox, from the one writer thread.
            let handle = thread::spawn(move || unsafe { writer.put(7) });
            if let Some(value) = mailbox.take() {
                assert_eq!(value, 7);
            }
            handle.join().unwrap();
        });
    }
}
