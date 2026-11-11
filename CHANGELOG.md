# Changelog

Dates are UTC. The template's releases are tags on one commit each (`v1`, `v2`, ...); a crate
repository pins a release by its commit SHA and Dependabot opens the bump. The lag check fails a
call that sits behind the newest release.

## Unreleased

- The release workflow's `rehearse` and `publish` jobs tell git to ignore the template checkout
  at `.crate-workflows/`. It lies inside the crate's tree, so a crate without an `include` list
  failed `cargo package` and `cargo publish` with the template's files reported as uncommitted
  changes. Nothing changes for a crate that already packaged.
- The scaffold's README starting shape gains a "Building and testing" section, and the stranger
  cadence page lists what a README must say. The list covers the build and test commands with any
  required feature, and `rustup target add`. It covers the Kani install before the first
  `cargo kani`, and the proofs' time and memory. It covers how to run one harness and one
  falsification patch, what a passing Kani run prints that looks alarming, and how to check the
  minimum Rust version. A new crate inherits it; nothing fails for an existing one.
- The unit check refuses `ppm` as the last part of a name with more than one part (`DRIFT_PPM`),
  and asks for `parts_per_million`. A bare `ppm` and one mid-name stay allowed, because `ppm` is
  also the Portable PixMap format. A crate that names a parts-per-million quantity with the symbol
  now fails `check / standalone`.
- `check / standalone` compares the notices a crate carries with its `license` field. A
  notice opens with a line `SPDX-License-Identifier: <id>`, in a text file or a `LICENSE-<name>`
  file at the root; the set of those ids, minus `MIT` and `Apache-2.0`, must equal the `AND` terms
  of the field. A notice with no term and a term with no notice each fail, naming the file or the
  term. A line that merely quotes the marker inside prose is not a notice. Nothing changes for a
  repository whose notices already carry the line.
- `actionlint` 1.7.12 is a required gate of `script/lint` and so of the selftest's lint job, no
  longer an optional one: a missing or different binary fails with the install command. It lints
  `.github/workflows/` and `scaffold/caller-workflows/` (placeholders filled in a scratch copy).
  The version and its SHA-256 are pinned in `helpers/install_actionlint.sh`, which the selftest
  runs. Two findings fixed (`selftest.yml` empty assignment, `mutation.yml` literal backticks); the
  stale ignore for the `administration` permission scope is gone.
- The `mutation` verdict reads a one-shard run. `actions/download-artifact` extracts a lone artifact
  into the download directory itself, not a subdirectory, so the verdict's `find -mindepth 2` found
  no `outcomes.json` and failed every one-shard repository. `mutants_gate.py --shards N` now counts
  both layouts and refuses any count other than N, zero included; a survivor or timeout still fails.
- `check / mutation-diff` is a required check in `settings/repository-settings.json`, ten in all.
  A repository runs `script/apply-settings` from this release after its pin bump brings the job,
  since a required check that never reports holds every pull request.
- `release / gate` also needs a green full mutation run at the released commit:
  `helpers/release-gate.sh` calls `mutation_plan.py verify`. A green `mutation.yml` run there counts
  when it recorded `full`, or `unchanged <fingerprint> since run N` where run N is a green full run
  of the same workflow and fingerprint. A deferred or repeat run never counts. The cases are in
  `fixtures/mutation/release/`. Dispatch `mutation.yml` on main before a release.
- `check / mutation-diff` mutates each pull request's changed lines (`cargo mutants --in-diff`, the
  diff against the merge's first parent) through `helpers/mutation-diff.sh`. A survivor or timeout
  that `.github/mutants-exempts` does not list fails, through `mutants_gate.py --diff`. The run has
  a 20-minute cap, and reaching it fails. A diff with no Rust passes, saying so. Its budget is 30
  minutes in both budget files. `helpers/mutation-diff-selftest.sh` runs it on the three diffs in
  `fixtures/mutation-diff/`.
- The full mutation run runs weekly on each repository's own weekday and tests nothing when nothing
  changed. `helpers/mutation_plan.py` derives the weekday and minute from the repository's name, and
  the new caller `scaffold/caller-workflows/mutation.yml` tries at 08, 10 and 12 UTC (its
  `@MUTATION_CRON@` line comes from `mutation_plan.py schedule <name>`). A scheduled run that starts
  outside 08:00-13:00 UTC is deferred, and one on another weekday fails naming the right line. A
  later try the same day is a repeat. A tree whose fingerprint (tracked files outside `.github/` and
  `docs/`, the exemptions, the resolved toolchain, cargo-mutants and the template's mutation files)
  matches the newest full run, when that run was green, records `unchanged since run N`. Each of
  these passes in seconds with a notice. Every run names a `mutation-record` job with its record,
  which the next run reads with the default token. The `skip-unchanged` and `stagger` inputs (both
  on) turn the rules off for the template's selftest. Fixtures are in `fixtures/mutation/`.
- The full mutation run moves out of `weekly.yml` into its own reusable workflow,
  `.github/workflows/mutation.yml`, with the `mutants-per-shard` input. `mutation-plan`, the
  `mutation` shards and `mutation-verdict` (named `mutation`) are unchanged, except that at most two
  shards run at once (`max-parallel: 2`); the workflow opens with the `lag` job like the others.
  `weekly.yml` loses the three jobs and the input. A caller reads `mutation / mutation` where it read
  `weekly / mutation`.
- `helpers/mutants_gate.py --diff` judges a run over changed lines (`cargo mutants --in-diff`): an
  exemption that names no survivor in it is out of the run's reach, not stale, so the stale check
  is skipped. A survivor or timeout that is not exempted still fails.
- The step of `mutation / mutation` that runs `mutants_gate.py` is named "judge the survivors
  against the exemptions" and, when the gate refuses, adds an error annotation saying so. A refusal
  no longer shows as an exit code on an unnamed step under the artifact download.
- `bus` joins `[address_qualifiers]`, so a bus address (`SYSTEM_MANAGEMENT_BUS_ADDRESS`) passes the
  address rule of `register_names.py`. Its selftest checks that such a name passes and fails when
  the word is removed.
- A crate README opens with a badge row under its title: check and proofs status, license and
  minimum Rust version. `scaffold/README-crate.md` carries it. The new `helpers/readme_badges.py`
  holds the row in `check / standalone`, and a finding fails it. Each badge takes its one form, with
  images only from the repository's own Actions badges and img.shields.io and links only into the
  repository. The minimum-Rust-version badge equals `rust-version`. The new `weekly / crates.io
  badges` job fails when a published crate lacks the crates.io and docs.rs badges, or an
  unpublished one carries them. `readme_badges.py --add-published` writes the pair after the first
  publish.
- The prose and README checks read a line of nothing but badges as no prose, so a badge's alt text
  is not an acronym, an inflated phrase or the summary paragraph.
- `helpers/falsify.py` asks Kani for a harness inside an inline module by its full path. A
  `#[kani::proof]` in `#[cfg(kani)] mod verification { ... }` is `verification::<name>` after the
  file's own module path, so the replay no longer reports "no Kani verdict line" for it. Braces,
  comments, strings and `mod x;` declarations are read so that only an enclosing `mod name {` counts.
  Which records pass or fail is otherwise unchanged.
- `crc` is an accepted word in `helpers/naming_words.toml`: nobody says cyclic redundancy check
  (CRC) in a name, so `abbreviations.py` passes `has_crc` and `CRC_BYTES`. Prose still expands CRC
  at its first use.
- An integer constant is never kept from its source. `helpers/rust_names.py` no longer exempts a
  `const` or `static` of an integer type whose doc comment opens with `(<name>, <source>)` and that
  carries `#[doc(alias)]`. `helpers/spelled_out.py`, `unit_symbols.py` and `abbreviations.py` now
  judge it. A register, bit or command constant takes the spelled-out name: `SD_SEND_OP_COND` fails,
  and `SD_SEND_OPERATION_CONDITIONS` carries the source spelling as its alias.
- `helpers/register_names.py` reads a file named for registers (`src/registers.rs`,
  `src/registers/mod.rs`, a file under `src/registers/`) as a register module, as it already read an
  inline `mod registers`. A constant there with a plain integer value ends `_REGISTER`; a bit is
  written as a shift (`1 << 0`).
- The address rule reads fewer things that are not memory locations: `relative`, `block` and
  `logical` join `[address_qualifiers]`, a qualifier other than `virtual` or `physical` may stand
  one word back (`RELATIVE_CARD_ADDRESS`), and `address` as a verb (`can_address_blocks`,
  `address_and_select`) is not read. The new tables are `[address_verb_before]` and
  `[address_verb_after]` in `helpers/naming_words.toml`.
- Rule 5's source citation needs a source after the comma: a word from the new `[source_words]`
  table (`OpenBSD`, `databook`, `specification`), a file name or a section number. "(`FBE`, `DU` or
  `CES`)" no longer reads as one.
- Two literal readings no longer fail a correct name. `INTERRUPT_MASK_REGISTER`, a register named
  for the mask it holds, passes the mask rule. An integer constant whose first word is in the new
  `[command_verbs]` table (`SET_BLOCK_LENGTH`, a command) is not read by the size rule.

- Three report-only README checks in `check / standalone`, which write their findings to the job
  summary and fail only on a malformed configuration. `helpers/readme_acronyms.py` lists an acronym
  that the README or the crate root's doc comment uses before the text defines it.
  `helpers/inflated_wording.py` lists the rhetorical or inflated phrases in
  `helpers/inflated_wording.toml`, each with its plain replacement. `helpers/readme_sections.py`
  lists a README whose sections leave the shared order: title and summary, `What it does`,
  `EXAMPLES`, `What is proven`, the crate's own sections, `BUGS`, `How it differs from`,
  `Minimum Rust version`, `License`. Each reads its own ceiling file under `.github/` and reports
  against it without enforcing it. `scaffold/README-crate.md` and `sample/README.md` follow the order.
- `helpers/abbreviations.py`, a report-only check. It lists every component of a name the crate
  defines that is not a word. A word is an English word (Spell Checker Oriented Word Lists (SCOWL),
  bundled as `helpers/english_words.txt`), a technical word (`helpers/technical_words.txt`), an
  `[accepted]` word in `helpers/naming_words.toml` or a word in the crate's `.github/accepted-words`.
  `check / standalone` writes the findings to its job summary and does not fail on them; a malformed
  configuration fails it. The check reads `.github/abbreviations-ceiling` and reports against it
  without enforcing it. The scaffold ships an empty `.github/accepted-words`.
- `label / label` rule 2 no longer dies on `An object with id ... could not be found` when it clones
  the baseline tag. The labeler checks out with `filter: blob:none`, so the release's files were not
  on disk, and cargo-semver-checks clones the checkout locally, where a missing file cannot be
  fetched. `helpers/semver-run.sh` now reads the baseline tag's files first, which fetches them in
  one batch. The semver selftest covers a blobless clone. The rule is not weakened.
- Compiled Python files (`helpers/__pycache__/*.pyc`, built by one interpreter version) are no longer
  tracked, and `.gitignore` now ignores `__pycache__/` and `*.pyc`. Nothing read them; the helpers
  run from their `.py` sources.
- `weekly / mutation` runs in shards, so a crate with thousands of mutants finishes inside the
  60-minute job timeout. `mutation-plan` counts the mutants and makes ceil(mutants /
  `mutants-per-shard`) shards (a new input, default 200). Each `mutation` job tests one shard, and
  `mutation-verdict`, named `mutation`, judges them together against `.github/mutants-exempts`. A
  crate under 200 mutants runs as one shard. A mutant that times out now fails the verdict unless
  exempted, as a survivor does; before, it failed the run only when no mutant survived. One exempt
  line now covers every survivor on that line, not only the first.
- The scaffold's typos gate now passes on the scaffold itself. The release caller's two secret names
  (`NIFE_SMELTER_APP_ID`, `NIFE_SMELTER_PRIVATE_KEY`) tripped the spelling check on their first
  word, so `scaffold/_typos.toml` ignores those two identifiers and nothing else. `script/lint` now
  runs the gate over `scaffold/`, and the stand-alone vocabulary check became
  `helpers/scaffold_alone.sh`, which `script/lint` proves with a bad and a good fixture.
- A weekly fuzz workflow, `fuzz.yml`, with a scaffold caller. Crash inputs are public, since the run
  log and the artifact are readable by any signed-in GitHub user. So it fuzzes only when the caller
  sets `public-crash-inputs: true`. The input defaults to false and the scaffold caller leaves it
  false; without it the run passes with a note.
- An opt-in is refused, naming the file and line, when the crate's shipped source contains `unsafe`
  outside tests (`helpers/unsafe_scan.py`). The run covers every cargo-fuzz target for a bounded time
  on a hosted runner, never on a pull request or a self-hosted runner. It uploads the crashing inputs
  as the `fuzz-artifacts` artifact and files nothing. `weekly.yml` loses its opt-in `fuzz` input and
  job, and the scaffold's weekly caller loses `fuzz: false`. `script/lint` holds the job's safety
  rules and proves the scan and the verdicts; the selftest workflow proves them with cargo-fuzz.
- First version, from milestone 887 (crate repositories share one CI template). Four reusable
  workflows (`check`, `proofs`, `weekly`, `release`), plus the architect label and hold workflows.
  One settings file, with an apply script and a drift check. The lag check sits in every reusable
  workflow's first job. `sample/` is the fixture crate the selftest runs everything against.
- `check` lints each bare-metal target with `--lib --bins`, not `--all-targets`: the `test` crate
  does not exist on those targets, so a crate with unit tests could never pass. The host run keeps
  `--all-targets`, so tests are still linted once.
- The Disclosure section of `CONTRIBUTING.md`, in the repository and in `scaffold/`, now says a person
  outside the project may use any tools they like and need not say which. The first-line rule for
  agent-written pull requests is unchanged. Ruled 2026-10-31 (UTC).
- `check` gains three gates from nife, with no baseline files. Passive voice stays at 2 per 1,000
  prose words in the README, CHANGELOG and `docs/`. History phrases stay out of the README and
  `docs/`; the CHANGELOG is exempt. Functions stay within 100 code lines. Ruled 2026-10-31 (UTC).
- `check / standalone` gains two prose gates, each with a selftest, ceiling 0 and no baseline file,
  over the README, CHANGELOG, `docs/*.md` and Rust doc comments. The acronym gate
  (`helpers/prose_acronyms.py`) requires every acronym of two or more capitals to be expanded at its
  first use, as `Extensible Firmware Interface (EFI)` or `EFI (Extensible Firmware
  Interface)`, or to sit on the short allowlist `helpers/prose_acronyms.toml`. Documents are judged
  per file and Rust doc comments once per crate. Document names, labels and capitalized words are
  not acronyms, and a width such as `FAT32` is covered once `FAT` is expanded. The banned-figures
  gate (`helpers/prose_figures.py`) refuses the figurative or vague phrases in
  `helpers/prose_figures.toml` and shows each plain replacement.
- `check / standalone` gains the naming checks, with no baseline files: every name a crate defines
  spells out the ruled words and its units (`helpers/spelled_out.py`, `helpers/unit_symbols.py`,
  words in `helpers/naming_words.toml`). A name kept from its source says so at the item, in its
  doc comment and a `#[doc(alias)]`, since a crate carries no provenance block.
- `check / standalone` gains the rest of the naming checks. Each has a selftest, no baseline file
  and the same kept form. They are American spelling (`helpers/british_spelling.py`), no Unix
  service model in a name or in tracked text (`helpers/service_model.py`), contract crates spelled
  `_contract` (`helpers/contract_names.py`), and yes-or-no functions named like questions
  (`helpers/question_shape.py`). A package or program has no item to carry an attribute, so it keeps
  a name through the crate root docs: `(<name>, <source>)`.
- `check / standalone` gains the typos step the README always listed: typos 1.51.1, installed at an
  exact version with the release checksum the pinned `install-action` holds, run by
  `helpers/typos_gate.sh` with the en-us locale. A crate repository needs the `_typos.toml` that
  `scaffold/` carries; the gate fails without it or with another locale. `script/lint` proves the
  gate passes a clean tree and refuses a misspelling, a British spelling, a missing config and
  another locale.
- The labeler's semver rule holds only a break the pull request introduces. When the pull request
  carries a major break against the previous release tag, `helpers/semver-rule.sh` checks its
  merge base against the same tag. `helpers/semver_major.py` keeps only the major findings the
  merge base did not have, so a break already on `main` does not hold a later pull request. The
  rule runs only when the diff touches a `.rs` file or a `Cargo.toml`; `Cargo.lock` stays out. The
  `selftest (semver rule)` job proves five cases against a throwaway crate repository.
- The American-spelling name check also refuses the `ise` forms of two more stems
  (`unrecogn` and `plural`). The doubled-`l` forms stay refused, a stricter reading than typos takes.

- `check / standalone` gains the register naming rules (`helpers/register_names.py`), with a
  selftest and no baseline file. A register offset ends `_REGISTER`. A mask of several bits ends
  `_MASK`. An integer constant that states its own name as its datasheet source is renamed, with the
  source spelling in `#[doc(alias)]`. Those three take no kept form. An address is
  `_VIRTUAL_ADDRESS` or `_PHYSICAL_ADDRESS`, and a size, length or limit carries its unit; those
  two take the kept form. The word lists are `[address_qualifiers]` and `[size_units]` in
  `helpers/naming_words.toml`. `rust_names.py` now gives each definition its enclosing modules and,
  for a `const` or `static`, its type and initializer.
- The orphan-module check no longer reports files rustc reaches. A child of a file that is not
  `mod.rs` is read from a directory named for that file. A `src/bin/<name>/main.rs` target is a
  root. Two `mod` lines on one line, and stacked attributes above a `#[path]` module, are read. A
  comment or a string never names a module.
- `scaffold/` and the release workflow's messages no longer name nife, calef or a roadmap fork,
  since a crate repository stands alone. `script/lint` refuses that vocabulary in `scaffold/`. The
  release app's secret names (`NIFE_SMELTER_APP_ID`, `NIFE_SMELTER_PRIVATE_KEY`) stay, because the
  organization secrets carry them.

## BUGS

- Nothing here is on crates.io yet, so no release row exists. The first release line lands with
  the `v1` tag.
