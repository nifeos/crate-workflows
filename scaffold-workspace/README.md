# Callers for a repository of several crates

These replace `scaffold/caller-workflows/` when the repository is a Cargo workspace of several crates, a
virtual root over `first_crate/` and `second_crate/`. They show two crates; rename them, and
copy a job block for each further crate. `first_crate` may be published; `second_crate` carries
`publish = false`. Fill the placeholders as the single-crate callers do (`@PINS@`,
`@MUTATION_CRON@`), and take `label.yml`, `hold.yml` and `ruled.yml` from `scaffold/caller-workflows/`
unchanged: the labeler checks every publishable crate by itself.

What differs from a repository of one crate:

- **One call for each crate.** Every workflow takes `manifest-path`, and a job names its crate:
  `check-first_crate`, `proofs-second_crate`. The required status checks follow the job ids, so
  run `script/apply-settings <owner/name> --member first_crate --member second_crate`; the same
  `--member` flags go to `script/check-settings`, and the weekly settings-drift job passes them
  itself.
- **A crate is a directory.** Each crate carries its own `README.md`, `LICENSE-MIT`,
  `LICENSE-APACHE`, `_typos.toml`, `rustfmt.toml` and `docs/`, and its manifest states its own
  `version`, `rust-version`, `license` and `[lints]` (the standalone gate refuses `lints.workspace`).
  The repository root keeps `deny.toml`, `.github/` and `Cargo.lock`.
- **Exemption lists.** `.github/mutants-exempts` stays one file for the repository. Each entry is
  named from the workspace root, the way cargo-mutants prints a mutant: `first_crate/src/lib.rs:16`.
  A crate's full run calls only the entries under its own directory stale. Keep the proof modules
  out of the mutants in a `.cargo/mutants.toml` at the workspace root (`exclude_globs`).
- **Tags name the crate.** A release is tagged `first_crate-v0.1.0`, and the semver baseline is
  that crate's own previous tag. A crate carrying `publish = false` is never published, never
  compared with a release and owes no stranger-test record; the releases of the others are
  unchanged.
- **Settings drift once.** Only one call of `weekly.yml` keeps `settings-drift` on; every
  publishable crate keeps its own `stranger-cadence`.
- **Converting a repository of one crate.** Its tag prefix changes from `v` to `<crate>-v`, so the
  old `v*` tags are no longer semver baselines (the first release after the change has none), and
  the tags ruleset needs `apply-settings --member` run again. A workspace whose root is itself a
  crate (a `[package]` and a `[workspace]` in one `Cargo.toml`) is not supported: the root of a
  repository of several crates is virtual.
