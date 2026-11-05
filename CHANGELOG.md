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
- `check` gains three gates from nife, with no baseline files. Passive voice stays at 2 per 1,000
  prose words in the README, CHANGELOG and `docs/`. History phrases stay out of the README and
  `docs/`; the CHANGELOG is exempt. Functions stay within 100 code lines. Ruled 2026-10-31 (UTC).
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

## BUGS

- Nothing here is on crates.io yet, so no release row exists. The first release line lands with
  the `v1` tag.
