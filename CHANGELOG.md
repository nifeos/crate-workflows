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
