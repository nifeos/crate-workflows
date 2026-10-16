# crate-workflows

One CI template for every crate repository under `nifeos`. A crate repository's own workflow files
are a few lines each that call the reusable workflows here, pinned by commit SHA, the way nife pins
every action it runs. The name is provisional, for calef's naming pass, as are the workflow names
and the release cadence.

The ruling behind it: 857's Fork 1 put one repository per crate under `nifeos` and said every one
of them uses one shared CI template (Kani, lint, release) through reusable workflows. Fork 4 ruled
the proof job and that a release refuses to publish while it is red. Fork 6 ruled trusted
publishing from a `nifeos` workflow. This repository is where all three land.

## The reusable workflows

| workflow | called on | jobs |
|---|---|---|
| `.github/workflows/check.yml` | every pull request | `lag`, `fmt`, `clippy`, `tests`, `coverage`, `standalone`, `supply-chain` |
| `.github/workflows/proofs.yml` | every pull request | `lag`, `kani`, `falsify` |
| `.github/workflows/weekly.yml` | a weekly schedule, no pull request open | `lag`, `drift`, `msrv`, `semver`, `miri`, `mutation`, `fuzz`, `settings-drift`, `stranger` |
| `.github/workflows/release.yml` | a dispatch naming a version | `gate`, `tag`, `publish` |
| `.github/workflows/label.yml` | every pull request push | `label` |
| `.github/workflows/hold.yml` | pull request and label events | `hold` |
| `.github/workflows/ruled.yml` | label events | `clear`, `rerun` |

Inputs every workflow takes (all optional unless named): `manifest-path` (default `Cargo.toml`),
`targets` (space-separated bare-metal targets to build and lint for, default none), `toolchain`
(default `stable`), `coverage-floor` (default 85). `check.yml` takes `allow-unpublished` for
fixture crates that carry `publish = false` on purpose. `proofs.yml` takes `kani-args`.
`weekly.yml` takes `fuzz` (a boolean, default false, since cargo-fuzz needs nightly and only
parsing crates want it) and `caller-checks` (the settings-drift and stranger jobs, off for this
template's own selftest). `release.yml` takes `version` (required, e.g. `0.1.0`) and `dry-run`
(default true).

## The lag check

Every reusable workflow's first job is `lag`. It compares the commit the caller pinned
(`job.workflow_sha`, the SHA of this template's file the call resolved to) with this repository's
newest release, and fails when the pin is behind it or on a diverged line. A call at an older
template release is red, Dependabot's `github-actions` ecosystem opens the bump, and the weekly
schedule runs the same check with no pull request open so a repository nobody touches still finds
out. When no release exists yet, the check fails closed: an unreleased template has nothing a crate
repository may pin.

## The release path

`release.yml` runs on a dispatch naming a version. `gate` refuses unless the check and proof runs
for that exact commit are green, so a tag whose proof job is red never gets made. `tag` creates
`v<version>` on that commit, refusing a version that does not match the manifest or a tag that
already exists. `publish` runs last, in the `crates-io` environment (a person approves), gets
`id-token: write` and nothing else, and exchanges the OIDC token for a temporary crates.io token
through trusted publishing. `dry-run` defaults to true, so a rehearsal publishes nothing and needs
no approval.

## What each nife gate became

| nife gate | here | where |
|---|---|---|
| `script/fmt` (rustfmt) | `cargo fmt --check` on stable; nife's two unstable rustfmt options are refused | `check / fmt`, and `standalone` refuses them in `rustfmt.toml` |
| clippy `-D warnings` | host, each listed target, and a `--cfg kani` pass over a shipped Kani shim | `check / clippy` |
| rustdoc broken links | `-D rustdoc::broken_intra_doc_links -D rustdoc::invalid_html_tags` | `check / standalone` |
| cargo-machete | `cargo machete` on the manifest | `check / supply-chain` |
| host tests | `cargo test` | `check / tests` |
| coverage, 85% per file | cargo-llvm-cov, per-file floor | `check / coverage` |
| fuzz (cargo-fuzz) | nightly, weekly, only when the caller asks | `weekly / fuzz` |
| Miri, weekly | `cargo +nightly miri test` | `weekly / miri` |
| mutation, weekly | cargo-mutants; new survivors fail against `mutants-baseline.txt` | `weekly / mutation` |
| `script/verify` (Kani) | `model-checking/kani-github-action` on every pull request | `proofs / kani` |
| falsification sweep | every patch applied with `-p1` must turn its harness red at its own assertion; the form check (every harness carries a patch or a reason) runs beside it | `proofs / falsify` |
| kani-reach | dropped: a dispatch-only measurement of nife's reach | |
| loom interleavings | dropped: none of the first crates uses loom | |
| cargo-deny | nife's policy without its exceptions | `check / supply-chain` |
| vendor-verify, vendor-watch | dropped: no vendored code | |
| toolchain drift and bump | weekly build on newest stable and beta | `weekly / drift` |
| MSRV build | the manifest's `rust-version` builds and tests | `weekly / msrv` |
| semver check | cargo-semver-checks against the last release, weekly, as a report | `weekly / semver`; the labeler runs it per pull request (below) |
| `script/crate-standalone` | the file, license, vocabulary and lint checks run in the repository itself | `check / standalone` |
| file-length ratchet, 2,000 lines | same limit, no baseline file (a new repository starts under the cap) | `check / standalone` |
| comment-block ratchet, 40 lines | same rule | `check / standalone` |
| workspace lints | `unsafe_op_in_unsafe_fn`, `missing_docs`, and `unexpected_cfgs` naming `cfg(kani)` required in the crate's own `[lints]` | `check / standalone` |
| orphan Rust files | every `.rs` file sits in the module tree | `check / standalone` |
| prose ratchet | README and CHANGELOG at nife's caps (3,000 words, median 20, longest 40) | `check / standalone` |
| house style, typos | `typos` over the tree | `check / standalone` |
| markdown links resolve | every relative link resolves | `check / standalone` |
| EXAMPLES and BUGS | the README must carry both headings | `check / standalone` |
| actions pinned to a SHA | the same grep nife runs, over the caller's workflows | `check / supply-chain` |
| a swallowed failure says where it goes | the template's own `script/lint`; callers inherit the workflows' behavior | template selftest |
| shellcheck, `sh -n` | over the caller's `script/` and the template's helpers | `check / standalone` |
| tracked-but-ignored files | same check | `check / standalone` |
| job budgets | a budgets file and a warn-at-85%, fail-over check on the heavy jobs | `.github/ci-job-budgets` in the caller, `helpers/job_budget.py` |
| CodeQL | same job, advanced setup, `build-mode: none` | `check / supply-chain` |
| `Co-Authored-By` commit hook | documented in the scaffold's `.githooks`; a crate repository copies nife's hook file | scaffold |
| empty diff | a merge that changes no file is refused | `check / supply-chain` |
| architect label | the dependency rule, plus a semver rule (cargo-semver-checks against the last release) | `label / label` |
| architect hold | red while `needs-architect` or `held-by-lane` is on, green on `architect-ruled`; a required check | `hold / architect hold (needs-architect label)` |
| `script/record-ruling` | a ruling swaps `needs-architect` for `architect-ruled` | `script/record-ruling` |
| naming checks, name provenance, citations, roadmap, branch names, merge drain | dropped: nife's own process. A TODO in a crate cites an issue there | |
| audit and stranger cadence | a stranger builds and proves the crate from its README alone; the job fails when the recorded run is overdue | `weekly / stranger` |
| kernel and image gates | dropped: a library crate has none | |

## Repository configuration

`settings/repository-settings.json` is the one description of what a crate repository is
configured to be. It covers the features (issues on with forms, everything else off) and the merge
behavior (merge commits, strict up-to-date branches, auto-merge, delete on merge). It covers the
two rulesets, the `crates-io` environment with a person as required reviewer, and the security
features. It covers the Actions permissions, the team and app access, the metadata, and the label
set. `script/apply-settings` applies it to a repository with `gh api`; a setting the API refuses
is reported and failed, never skipped silently. `script/check-settings` reads the live settings
back and fails on any difference. The weekly `settings-drift` job runs it, so a setting changed by
hand in the web interface is a red run, not a surprise.

The architect rules a crate repository keeps: a dependency new to the crate's graph, and a
breaking change cargo-semver-checks reports against the last published version. Everything else
nife's labeler watched (the ABI surface, the spawn protocol, the syscall errors, the decisions
tree) lives in nife and stays there.

## Required checks

The ruleset on `main` requires nine checks, with branches up to date: the six `check /` jobs (fmt,
clippy, tests, coverage, standalone, supply-chain), the two `proofs /` jobs (kani, falsify), and
the hold. The names are the caller's job id, a slash, and the reusable workflow's job name;
`scaffold/` fixes the caller job ids so the two ends cannot drift.

```
ci / fmt, ci / clippy, ci / tests, ci / coverage, ci / standalone, ci / supply-chain,
proofs / kani, proofs / falsify, hold / architect hold (needs-architect label)
```

## Adopting it for a crate

Copy `scaffold/` into a new crate repository, and replace the pins in the six workflow files. The
pin is the commit SHA of the release you are adopting: run `git rev-parse v1^{commit}` in a
checkout of this repository. Then run `script/apply-settings <owner/name>` once, from a checkout,
as somebody with repository administration rights. `.github/ci-job-budgets` is optional; without
it every heavy job assumes 20 minutes. `mutants-baseline.txt` is optional; without it one survivor
fails `weekly / mutation`.

## EXAMPLES

Adopt the template for a crate called `example_thing`:

```sh
gh repo create nifeos/example_thing --public --clone
cd example_thing
cp -R ../crate-workflows/scaffold/. .
sed -i 's/@PINS@/<release SHA>/g' .github/workflows/*.yml
# put the crate under src/, its proofs under src/ with #[kani::proof],
# its falsification patches under falsifications/
git add -A && git commit -m "adopt the shared crate workflows"
gh workflow run release.yml -f version=0.1.0 -f dry-run=true   # rehearse
gh workflow run release.yml -f version=0.1.0 -f dry-run=false  # publish, after approval
```

Run the settings drift check by hand:

```sh
script/check-settings nifeos/example_thing
```

Record an architect ruling on a pull request:

```sh
script/record-ruling 12 --text "The new dependency is fine: it is no_std and proven."
```

## BUGS

- Names are provisional: this repository's name, the workflow names, the team slug (`crates-io`)
  and the release cadence all wait for calef's naming pass.
- The required-check names above describe what GitHub shows for cross-repository reusable workflow
  calls. The throwaway test repository's runs are the evidence; if GitHub names the checks
  differently, this section and the ruleset in the settings file are both wrong until they match.
- The coverage floor here is 85, matching nife's current floor. The roadmap block still says 80
  because it predates the raise.
- `weekly / semver` and `weekly / stranger` are reports: a semver break between releases is
  deliberate waiting, and the stranger run needs a person, so neither fails a release. The
  per-pull-request semver rule in the labeler is the one that holds a merge.
- `weekly / settings-drift` reads the rulesets and environments APIs, which need repository
  Administration read-only. The GITHUB_TOKEN cannot carry that scope: GitHub's parser refuses
  `administration` in any `permissions` block, at the workflow level as well as the job level
  (this repository's first selftest runs are the evidence). The check authenticates as the
  caller's `SETTINGS_TOKEN` secret instead, a fine-grained PAT with that scope, stored once as an
  organization secret. Until it exists, the job is red on its 403 with instructions.
- Publishing for real needs the trusted publisher configured on crates.io for the crate and
  repository pair, which needs calef's crates.io account. Until then only `dry-run` rehearsals
  run.
- The org-level Actions allowlist (SHA-pinned only, verified creators, `kani-github-action`
  named) is organization state, not repository state; `script/apply-settings` attempts it and
  reports the refusal when the token lacks the scope.
- The fork pull request approval policy ("require approval for all outside contributors") is
  organization state too, and nothing here can set or read it: the org Actions endpoints answer
  403 to a non-admin token and the fork-policy path answers Not Found (measured 2026-10-16). Set
  it once in the org's Actions settings. A public repository's default is approval for
  first-time outside contributors only.
- Tag rules: the repository rulesets API refuses ref_name conditions on push-target rulesets
  ("Target ref_name is not supported for push rulesets", measured live on the throwaway
  repository), so `apply-settings` reports the tags ruleset as refused and the release workflow's
  own gate is what keeps a stray tag from mattering. The durable fix is an organization-level
  push ruleset scoped by repository and ref, which needs an org-scoped token.
