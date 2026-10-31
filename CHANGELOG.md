# Changelog

Dates are UTC. The template's releases are tags on one commit each (`v1`, `v2`, ...); a crate
repository pins a release by its commit SHA and Dependabot opens the bump. The lag check fails a
call that sits behind the newest release.

## Unreleased

- First version, from milestone 887 (crate repositories share one CI template). Four reusable
  workflows (`check`, `proofs`, `weekly`, `release`), plus the architect label and hold workflows.
  One settings file, with an apply script and a drift check. The lag check sits in every reusable
  workflow's first job. `sample/` is the fixture crate the selftest runs everything against.
- `check` lints each bare-metal target with `--lib --bins`, not `--all-targets`: the `test` crate
  does not exist on those targets, so a crate with unit tests could never pass. The host run keeps
  `--all-targets`, so tests are still linted once.
- The Disclosure section of CONTRIBUTING.md, in the repository and in `scaffold/`, now says a person
  outside the project may use any tools they like and need not say which. The first-line rule for
  agent-written pull requests is unchanged. Ruled 2026-10-31 (UTC).

## BUGS

- Nothing here is on crates.io yet, so no release row exists. The first release line lands with
  the `v1` tag.
