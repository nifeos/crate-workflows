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
| `.github/workflows/weekly.yml` | a weekly schedule, no pull request open | `lag`, `drift`, `msrv`, `semver`, `miri`, `mutation-plan`, `mutation` (one per shard), `mutation-verdict` (named `mutation`), `settings-drift`, `stranger` |
| `.github/workflows/fuzz.yml` | a weekly schedule, no pull request open | `lag`, `fuzz` |
| `.github/workflows/release.yml` | a dispatch naming a version | `gate`, `tag`, `publish` |
| `.github/workflows/label.yml` | every pull request push | `label` |
| `.github/workflows/hold.yml` | pull request and label events | `hold` |
| `.github/workflows/ruled.yml` | label events | `clear`, `rerun` |

Inputs every workflow takes (all optional unless named): `manifest-path` (default `Cargo.toml`),
`targets` (space-separated bare-metal targets to build and lint for, default none), `toolchain`
(default `stable`), `coverage-floor` (default 85). `check.yml` takes `allow-unpublished` for
fixture crates that carry `publish = false` on purpose. `proofs.yml` takes `kani-args`.
`weekly.yml` takes `caller-checks` (the settings-drift and stranger jobs, off for this template's
own selftest) and `mutants-per-shard` (default 200; see below). `fuzz.yml` takes `public-crash-inputs` (the opt-in, default false), `seconds-per-target` (default 300) and `total-seconds` (default
1,200). `release.yml` takes `version` (required, e.g. `0.1.0`) and `dry-run`
(default true).

## The weekly mutation run

`weekly.yml` splits cargo-mutants over a matrix, since one hosted job cannot test a large crate's
mutants inside its 60-minute timeout. `mutation-plan` counts the mutants with `cargo mutants --list`
and makes ceil(mutants / `mutants-per-shard`) shards, at least one. Each `mutation` job tests one
shard (`--shard k/n --sharding round-robin`) and uploads its `mutants.out` as `mutants-shard-k`.
`mutation-verdict` judges every shard's outcomes together against `.github/mutants-exempts`, and
carries the name `mutation`, so `weekly / mutation` stays the one status to read or require.

The default of 200 mutants a shard fits a crate whose mutants take about 15 seconds each, two at a
time: 25 minutes a shard. A crate under 200 mutants runs as one shard. A crate with slower tests
lowers `mutants-per-shard` in its caller; the plan refuses a count over 256 shards, the most a
matrix holds.

## The weekly fuzz run

Every crate repository carries the `fuzz.yml` caller, and a repository created from the scaffold
fuzzes nothing until someone opts it in. The caller passes `public-crash-inputs: false`; a repository
that has not opted in passes with a short note and runs no fuzz step.

What is public: a crash input is written to the run log and uploaded as the `fuzz-artifacts`
artifact, and both are readable by any signed-in GitHub user.

Why only safe-Rust crates opt in: in a crate with no `unsafe` code, a crash is a panic or a hang, a
denial of service at worst. In a crate with `unsafe` code, a crash may be a memory-safety flaw, and
the input that triggers it would be published before anyone could fix it. So an opt-in is refused,
and the job is red, when the crate's shipped source (`src/**/*.rs`, outside `#[cfg(test)]`) contains
an `unsafe` block, fn, impl, trait or attribute. The message names the file and line. The check
(`helpers/unsafe_scan.py`) ignores comments, strings and character literals, and passes a crate whose
every root carries `#![forbid(unsafe_code)]`. It does not look at fuzz targets or dependencies. It
is a scan of the standard library rather than `cargo geiger` so that it costs no install and
`script/lint` can prove it against the fixtures in `fixtures/unsafe-scan`.

A suspected security flaw goes to the private channel in the repository's `SECURITY.md`, never to
an issue or a comment. A person who suspects one in a run deletes the run and its artifact.

To opt in, set `public-crash-inputs: true` in the repository's `.github/workflows/fuzz.yml`. To opt
out again, set it back to `false` (or remove the line), and delete earlier runs and artifacts if
they hold inputs that should not stay public.

A crate with a `fuzz/Cargo.toml` that has opted in runs every target it lists for a bounded time
each, on a hosted runner, on a Tuesday cron and on dispatch. A crate without one passes with a note.
Each target runs for the smaller of `seconds-per-target` and an even share of `total-seconds`, and
never under 10 seconds, so a crate with many targets still ends inside the job's budget.

The run files nothing. It opens no issue, creates no advisory and posts no comment. A crash, a
timeout, an out-of-memory or a leak turns the run red, and the run uploads `fuzz/artifacts` for 14
days. A person reads the run and decides what the crash is.

The job never runs on a pull request: the caller has no `pull_request` trigger, the job refuses a
pull request from a fork, and it never uses a self-hosted runner. `script/lint` holds those rules
(`helpers/fuzz-ci-selftest.sh`), proves the script red on a seeded crash and green on a clean target
against a stand-in cargo, and proves the scan on the unsafe fixtures. The selftest workflow proves the rest with cargo-fuzz itself. `fixtures/fuzz-clean` goes through the
live workflow with the opt-in and must pass. `fixtures/fuzz-crash` goes through it without the
opt-in and must pass having run nothing, and through the script, where it must fail and leave its
input behind. A crate with an `unsafe` block must be refused.

## The lag check

Every reusable workflow's first job is `lag`. It compares the commit the caller pinned
(`job.workflow_sha`, the SHA of this template's file the call resolved to) with this repository's
newest release, and fails when the pin is behind it or on a diverged line. A call at an older
template release is red, Dependabot's `github-actions` ecosystem opens the bump, and the weekly
schedule runs the same check with no pull request open so a repository nobody touches still finds
out. When no release exists yet, the check fails closed: an unreleased template has nothing a crate
repository may pin.

## The release path

`release.yml` runs on a dispatch naming a version. `gate` refuses while `docs/stranger-test.md`
reads `Last run: none`, because a stranger-test run must be on record before the first release. It
also refuses unless the check and proof runs for that exact commit are green, so a tag whose proof
job is red never gets made. `tag` creates
`v<version>` on that commit, refusing a version that does not match the manifest or a tag that
already exists. `publish` runs last, in the `crates-io` environment (a person approves), gets
`id-token: write` and nothing else, and exchanges the OpenID Connect (OIDC) token for a temporary crates.io token
through trusted publishing. `dry-run` defaults to true, so a rehearsal publishes nothing and needs
no approval.

crates.io binds a trusted publisher only to a crate that already exists, so a crate's first publish
uses a token instead. `helpers/publish_mode.py` picks the door by whether the crate is on crates.io:
absent means the `crates-io` environment secret `CRATES_IO_FIRST_PUBLISH_TOKEN`. Its name is
provisional. The maintainer creates it as a `publish-new` token limited to the crate name, with a
short expiry. Present means trusted publishing only, even if the secret is still set. A failed lookup or a
missing secret is a red job; nothing falls back. The first publish passes the same gate and the
same environment approval as every later one, and a dry run reports which door it would use.
`helpers/publish-rehearsal.sh <manifest> [--token-present]` runs the same two steps by hand, with
no credential: `cargo publish --dry-run`, then the door. It publishes nothing.

## What each nife gate became

| nife gate | here | where |
|---|---|---|
| `script/fmt` (rustfmt) | `cargo fmt --check` on stable; nife's two unstable rustfmt options are refused | `check / fmt`, and `standalone` refuses them in `rustfmt.toml` |
| clippy `-D warnings` | host, each listed target, and a `--cfg kani` pass over a shipped Kani shim | `check / clippy` |
| rustdoc broken links | `-D rustdoc::broken_intra_doc_links -D rustdoc::invalid_html_tags` | `check / standalone` |
| cargo-machete | `cargo machete` on the manifest | `check / supply-chain` |
| host tests | `cargo test` | `check / tests` |
| coverage, 85% per file | cargo-llvm-cov, per-file floor | `check / coverage` |
| fuzz (cargo-fuzz) | nightly, weekly, a bounded time per target, only when the caller opts in; see below | `fuzz / fuzz` |
| Miri, weekly | `cargo +nightly miri test` | `weekly / miri` |
| mutation, weekly | cargo-mutants in shards; a survivor or a timeout fails unless `.github/mutants-exempts` lists it with a reason | `weekly / mutation` |
| `script/verify` (Kani) | `cargo kani` at the version in `.kani-version`, on every pull request | `proofs / kani` |
| falsification sweep | every patch applied with `-p1` must turn its harness red at its own assertion; the form check (every harness carries a patch or a reason) runs beside it | `proofs / falsify` |
| kani-reach | dropped: a dispatch-only measurement of nife's reach | |
| loom interleavings | dropped: none of the first crates uses loom | |
| cargo-deny | nife's policy without its exceptions | `check / supply-chain` |
| vendor-verify, vendor-watch | dropped: no vendored code | |
| toolchain drift and bump | weekly build on newest stable and beta | `weekly / drift` |
| MSRV build | the manifest's `rust-version` builds and tests | `weekly / msrv` |
| semver check | cargo-semver-checks against the previous release tag (`--baseline-rev`), weekly, as a report | `weekly / semver`; the labeler runs it per pull request (below) |
| `script/crate-standalone` | the file, license, vocabulary and lint checks run in the repository itself | `check / standalone` |
| file-length ratchet, 2,000 lines | same limit, no baseline file (a new repository starts under the cap) | `check / standalone` |
| comment-block ratchet, 40 lines | same rule | `check / standalone` |
| workspace lints | `unsafe_op_in_unsafe_fn`, `missing_docs`, and `unexpected_cfgs` naming `cfg(kani)` required in the crate's own `[lints]` | `check / standalone` |
| orphan Rust files | every `.rs` file sits in the module tree | `check / standalone` |
| prose ratchet | README and CHANGELOG at nife's caps (3,000 words, median 20, longest 40) | `check / standalone` |
| passive-voice ratchet | README, CHANGELOG and `docs/*.md` at nife's limit of 2 passives per 1,000 prose words; no baseline | `check / standalone` |
| history ratchet | README and `docs/*.md` carry no phrase that only a history uses (`supersede`, `renamed from`, `moved from` a document, a Timeline heading); the CHANGELOG is exempt; no baseline | `check / standalone` |
| acronym gate | every acronym (two or more capitals, `FSInfo` included) is expanded at its first use, as `Extensible Firmware Interface (EFI)` or `EFI (Extensible Firmware Interface)`, or is listed in `helpers/prose_acronyms.toml`. The README, CHANGELOG and each `docs/*.md` are judged per file; Rust doc comments are judged once per crate (the README's expansions and the first use in the crate root count for every source file). A width (`FAT32` once `FAT` is expanded) is covered. Code spans, code blocks, headings, document names, labels such as `SAFETY:` and capitals whose lowercase form the file also uses (`THIS`) are exempt; ceiling 0, no baseline | `check / standalone` |
| banned-figures gate | the same files carry none of the phrases in `helpers/prose_figures.toml` (`oracle`, `battle-tested`, `under the hood` and similar), and the failure shows each plain replacement; ceiling 0, no baseline | `check / standalone` |
| function-length ratchet, 100 code lines | the count clippy's `too_many_lines` makes, read from source; no baseline | `check / standalone` |
| house style, typos | `typos` 1.51.1 with the en-us locale over the tree, through `helpers/typos_gate.sh`; the crate carries its own `_typos.toml` (copied from `scaffold/`), and the gate refuses a missing file or another locale | `check / standalone` |
| markdown links resolve | every relative link resolves | `check / standalone` |
| `EXAMPLES` and `BUGS` | the README must carry both headings | `check / standalone` |
| actions pinned to a SHA | the same grep nife runs, over the caller's workflows | `check / supply-chain` |
| a swallowed failure says where it goes | the template's own `script/lint`; callers inherit the workflows' behavior | template selftest |
| shellcheck, `sh -n` | over the caller's `script/` and the template's helpers | `check / standalone` |
| tracked-but-ignored files | same check | `check / standalone` |
| job budgets | a budgets file and a warn-at-85%, fail-over check on the heavy jobs | `.github/ci-job-budgets` in the caller, `helpers/job_budget.py` |
| CodeQL | same job, advanced setup, `build-mode: none` | `check / supply-chain` |
| `Co-Authored-By` commit hook | documented in the scaffold's `.githooks`; a crate repository copies nife's hook file | scaffold |
| empty diff | a merge that changes no file is refused | `check / supply-chain` |
| architect label | the dependency rule, plus a semver rule: a major break against the previous release tag that the merge base did not already carry, run only when the diff touches a `.rs` file or a `Cargo.toml` (`helpers/semver-rule.sh`) | `label / label` |
| architect hold | red while `needs-architect` or `held-by-lane` is on, green on `architect-ruled`; a required check | `hold / architect hold` |
| `script/record-ruling` | a ruling swaps `needs-architect` for `architect-ruled` | `script/record-ruling` |
| spelled-out words, unit symbols | every name the crate defines spells out the ruled words (`receive`, not `rx`) and its unit (`_MILLISECONDS`, not `_MS`); the words are `helpers/naming_words.toml`, ceiling 0, no baseline. A name kept from a datasheet, a specification or the standard library opens its doc comment with `(<name>, <source>)` and carries `#[doc(alias)]`; an integer constant (a register, bit, field or command) is never kept and takes the spelled-out name, with the source spelling as its alias; a package or program keeps its name by opening the crate root docs with `(<name>, <source>)` | `check / standalone` |
| register names | a register offset ends `_REGISTER`, in an inline `mod registers` or a file such as `src/registers.rs`; a mask of several bits ends `_MASK`; a register, field or bit constant is spelled out, with the source's spelling in `#[doc(alias)]`; an address in memory is `_VIRTUAL_ADDRESS` or `_PHYSICAL_ADDRESS` (a relative, logical or block address is not one); a size, length or limit carries its unit (`helpers/register_names.py`); ceiling 0, no baseline | `check / standalone` |
| American spelling | no name the crate defines holds a British form (an `our` ending for `or`, an `ise` ending for `ize`, a doubled `l` before `ed`); the forms are `[british]` and the three stem families in `helpers/naming_words.toml`; ceiling 0 | `check / standalone` |
| no Unix service model | no name holds `daemon` or ends in a lone `d` component; a crate or program name of four or more characters does not end in `d`; the word `daemon` appears in no tracked text; ceiling 0 | `check / standalone` |
| contract crates | a package or program name does not end in `proto` or `protocol` (spell it `_contract`) nor glue `contract` on (`fscontract`); ceiling 0 | `check / standalone` |
| question-shaped functions | a function returning `bool` and taking no `&mut` is named `is_`, `has_`, `can_`, `was_`, `will_`, `all_`, `any_` or with a finite verb; ceiling 0 | `check / standalone` |
| name provenance blocks, citations, roadmap, branch names, merge drain | dropped: another project's process. A crate carries no `Name:` block, and a TODO in a crate cites an issue there | |
| audit and stranger cadence | a stranger builds and proves the crate from its README alone; the job fails when the recorded run is overdue | `weekly / stranger` |
| kernel and image gates | dropped: a library crate has none | |

## The abbreviations report

A name spells out what it holds. `helpers/spelled_out.py` refuses the abbreviations it lists;
`helpers/abbreviations.py` finds the ones nobody listed. It reads the same names and splits each
into components the same way. It reports every component that is not one of these:

- an English word (`helpers/english_words.txt`, from Spell Checker Oriented Word Lists (SCOWL);
  its source and license are in its header and `helpers/english_words.LICENSE`);
- a technical word (`helpers/technical_words.txt`);
- a short word in `[accepted]` in `helpers/naming_words.toml`, each with its reason (`id`, `pci`,
  `len`);
- a word in the crate's own `.github/accepted-words`, one per line followed by its reason.

`[abbreviations]` in the same file names dictionary words that a name still spells out (`err`,
`info`). The check skips a name kept from a datasheet, a specification or the standard library in
the form `helpers/rust_names.py` describes; it never skips an integer constant, which is never kept. Each finding reads
`file:line: name: component 'val' is not a word (did you mean 'value'?)`, followed by a count per
file and a total.

The check is report only. `check / standalone` runs it as its own step and writes the findings to
the job summary; it never fails on a finding. It fails only on a malformed configuration, such as an
accepted word without a reason. The check reads `.github/abbreviations-ceiling`, one number, and
compares the total with it; nothing enforces it yet.

## The README reports

Three checks read a crate's two front pages, the README and the crate root's `//!` doc comment
(`helpers/readme_documents.py`). Each writes its findings to the job summary and never fails on one:

- `helpers/readme_acronyms.py`: an acronym used before the page defines it, in parentheses, in the
  same sentence or in Title Case earlier, unless an accepted word allows it. It reads headings and
  forms the acronym gate skips (`exFAT`).
- `helpers/inflated_wording.py`: the phrases in `helpers/inflated_wording.toml`, each with its plain
  replacement. An entry no crate uses any more can move to `helpers/prose_figures.toml`, which fails.
- `helpers/readme_sections.py`: the README's sections in the one order its header states, which
  `scaffold/README-crate.md` and `sample/README.md` follow.

Each reports against its own ceiling file under `.github/`, named in its header.

## How Kani moves

`.kani-version` holds the one exact kani-verifier version that `proofs.yml` installs. Every
Wednesday `.github/workflows/kani-bump.yml` compares it with the newest release on crates.io and,
when that is newer, opens or updates a single pull request that changes only that file. This
repository's own `selftest (proofs)` run is the verification, and the default is to merge. A crate
repository receives the new Kani when it next bumps its pin of this template (Dependabot, weekly),
so the lag is the bump merge plus a template release plus that weekly pin bump. The job authenticates
as nife-smelter (`NIFE_SMELTER_APP_ID`, `NIFE_SMELTER_PRIVATE_KEY`, with contents and pull requests
write here) and fails naming the secret when one is missing.

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
breaking change cargo-semver-checks reports against the previous release tag. The semver rule holds
only a break the pull request introduces. It checks the merge base against the same tag, and a
break already on the base branch was ruled in its own pull request, so it does not hold a later
one. A diff that touches no `.rs` file (build scripts included) and no `Cargo.toml` does not run
the tool. `Cargo.lock` is not in that filter: a dependent resolves its own lockfile, and the tool
reads only the crate's own items. Everything else
nife's labeler watched (the application binary interface (ABI) surface, the spawn protocol, the syscall errors, the decisions
tree) lives in nife and stays there.

## Required checks

The ruleset on `main` requires nine checks, with branches up to date: the six `check /` jobs (fmt,
clippy, tests, coverage, standalone, supply-chain), the two `proofs /` jobs (kani, falsify), and
the hold. The names are the caller's job id, a slash, and the reusable workflow's job name;
`scaffold/` fixes the caller job ids so the two ends cannot drift.

```
check / fmt, check / clippy, check / tests, check / coverage, check / standalone, check / supply-chain,
proofs / kani, proofs / falsify, hold / architect hold
```

## Adopting it for a crate

Copy `scaffold/` into a new crate repository, and replace the pins in the six workflow files. The
pin is the commit SHA of the release you are adopting: run `git rev-parse v1^{commit}` in a
checkout of this repository. Then run `script/apply-settings <owner/name>` once, from a checkout,
as somebody with repository administration rights. `.github/ci-job-budgets` is optional; without
it every heavy job assumes 20 minutes. `.github/mutants-exempts` is optional; without it one survivor
fails `weekly / mutation`.

Before the first release, run the stranger test and record its date as `Last run: YYYY-MM-DD` in
`docs/stranger-test.md` (ruled 2026-11-01 UTC). The scaffold starts at `Last run: none`, and
`release / gate` and the weekly `stranger cadence` job both fail on it.

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

## Release secrets

`release / tag` creates the tag as the nife-smelter app, because the tags ruleset refuses every
other actor. Two organization secrets, visible to every crate repository, feed it:

| secret | holds |
|---|---|
| `NIFE_SMELTER_APP_ID` | the nife-smelter app's ID |
| `NIFE_SMELTER_PRIVATE_KEY` | a private key generated for the app (the whole Privacy-Enhanced Mail (PEM) file) |

The caller passes both (`scaffold/caller-workflows/release.yml` does). If either is missing the
job fails naming it; it never falls back to `github.token`. The app must also be installed on the
repository, with contents write.

## Testing a release

The canary repository `nifeos/crate-workflows-test` adopts every release before anything depends
on one. The ritual after cutting a tag: open a pull request there that moves every caller's pin
to the new release's commit, expect the nine required checks green, and merge it. A release is
not depended on until the canary has adopted it, and a canary pin behind the newest release is
the lag check's red, by design. The canary is also the configured repository `apply-settings` and
`check-settings` run against, so the drift check always has a real repository to read.

`.github/workflows/canary-adopt.yml` opens that pull request when a release is published (or on a
dispatch naming a tag). It copies the release's `scaffold/caller-workflows` into the canary with
the pin filled in, on the branch `adopt-<tag>`, and a re-run updates the same pull request. It
authenticates as nife-smelter (`NIFE_SMELTER_APP_ID`, `NIFE_SMELTER_PRIVATE_KEY`), which needs
contents, pull requests and workflows write on the canary, and fails naming a missing secret. It
never merges: a person reads the checks, and a release that renames a required check also needs
`apply-settings` run from it first.

## BUGS

- Names are provisional: this repository's name, the workflow names, and the release cadence
  wait for calef's naming pass; the team slug is ruled (`crate-maintainers`).
- The required-check names above describe what GitHub shows for cross-repository reusable workflow
  calls. The canary repository's runs are the evidence; if GitHub names the checks
  differently, this section and the ruleset in the settings file are both wrong until they match.
- The coverage floor here is 85, matching nife's current floor. The roadmap block still says 80
  because it predates the raise.
- The semver baseline is the newest `v<x>.<y>.<z>` tag before the commit (`helpers/semver_baseline.py`),
  passed by revision, so a crate not yet on crates.io has one. With no tag the tool falls back to the
  last published version, and a crate with neither has no baseline, which counts as nothing major.
- `weekly / semver` and `weekly / stranger` are reports: a semver break between releases is
  deliberate waiting, and the stranger run needs a person, so neither fails a release. The release gate refuses only a record that still reads `none`. The
  per-pull-request semver rule in the labeler is the one that holds a merge.
- `weekly / settings-drift` reads the rulesets and environments APIs, which need repository
  Administration read-only. The GITHUB_TOKEN cannot carry that scope: GitHub's parser refuses
  `administration` in any `permissions` block, at the workflow level as well as the job level
  (this repository's first selftest runs are the evidence). The check authenticates as the
  caller's `SETTINGS_TOKEN` secret instead, a fine-grained personal access token (PAT) with that scope, stored once as an
  organization secret. Until it exists, the job is red on its 403 with instructions. The merge
  settings (`allow_merge_commit` and the other five) are returned only to a caller with push
  access, so the PAT also needs Contents read and write; without it each one is an "unreadable"
  finding naming that scope, not a mismatch.
- Publishing for real needs the trusted publisher configured on crates.io for the crate and
  repository pair, which needs calef's crates.io account. Until then only `dry-run` rehearsals
  run.
- The repository's Actions allowlist is `patterns_allowed` in the settings file, and each pattern
  needs the `@*` suffix: `taiki-e/install-action` alone matches no reference. Every caller
  workflow using a third-party action then ends in `startup_failure` with empty `referenced_workflows`
  (measured on the canary; the same patterns with `@*` run). The file must name every third-party
  action the template itself uses: `taiki-e/install-action`. `check-settings` compares the list
  exactly.
- Kani is installed with `cargo install --locked kani-verifier` at the version in `.kani-version`.
  The version is read from the template's own pinned checkout, so a crate inherits it through its
  pin. The `model-checking/kani-github-action` is not used: it calls `dtolnay/rust-toolchain@stable` and
  `actions/checkout@v3` unpinned, which a repository requiring SHA pinning refuses.
- The fork pull request approval policy is organization state, and nothing here can set or read
  it. The org Actions endpoints answer 403 to a non-admin token; the fork-policy path answers
  Not Found (measured 2026-10-16). Set it once in the org's Actions settings. A public
  repository's default is approval for first-time outside contributors only.
- Tag rules: the tags ruleset is a tag-target ruleset (`refs/tags/v*`: creation, update,
  deletion), because a push-target ruleset refuses ref_name conditions ("Target ref_name is not
  supported for push rulesets"). Its only bypass actor is the nife-smelter app, which the release
  workflow's `tag` job authenticates as. The GitHub Actions integration is refused as a bypass
  actor ("must be part of the ruleset source or owner organization"), so `github.token` cannot
  tag. The app is accepted as a bypass actor only once it is installed on the repository. Measured
  on the canary 2026-10-17: a repository-level tag ruleset is accepted, a hand-made `v*` tag is
  refused (422), and a tag that does not match `v*` is allowed.