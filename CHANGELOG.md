# Changelog

Dates are UTC. The template's releases are tags on one commit each (`v1`, `v2`, ...); a crate
repository pins a release by its commit SHA and Dependabot opens the bump. The lag check fails a
call that sits behind the newest release.

## Unreleased

- The full mutation run moves out of `weekly.yml` into its own reusable workflow,
  `.github/workflows/mutation.yml`, with the `mutants-per-shard` input. `mutation-plan`, the
  `mutation` shards and `mutation-verdict` (named `mutation`) are unchanged, except that at most two
  shards run at once (`max-parallel: 2`); the workflow opens with the `lag` job like the others.
  `weekly.yml` loses the three jobs and the input. A caller reads `mutation / mutation` where it read
  `weekly / mutation`.
- `helpers/mutants_gate.py --diff` judges a run over changed lines (`cargo mutants --in-diff`): an
  exemption that names no survivor in it is out of the run's reach, not stale, so the stale check
  is skipped. A survivor or timeout that is not exempted still fails.
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
