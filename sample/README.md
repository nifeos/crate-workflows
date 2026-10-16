# <crate-workflows-sample>

The template's fixture crate: one function, two tests, one proof, and a falsification patch. The
selftest workflow runs every reusable workflow against this crate, so a gate that cannot pass
here is broken before any real crate meets it. It carries `publish = false` on purpose, and the
selftest tells the standalone gate so.

## EXAMPLES

```rust
assert_eq!(crate_workflows_sample::saturating_add_percent(30, 40), 70);
assert_eq!(crate_workflows_sample::saturating_add_percent(60, 60), 100);
```

## BUGS

- The fixture proves the workflows, not the function. Nothing here is a claim about percentage
  arithmetic worth depending on.
