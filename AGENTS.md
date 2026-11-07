# Working on crate-workflows

This repository holds the CI that every nifeos crate repository shares: four reusable workflows
(`check`, `proofs`, `weekly`, `release`) plus the label and hold workflows, one settings file, and
the scripts that apply and re-check it. It exists because milestone 857's forks ruled one
repository per crate, and milestone 887 ruled that they share one template adapted gate by gate
from nife's own CI.

## Rules

- nife's `AGENTS.md` governs style and conduct here by adoption: UTC dates, no em-dashes, one
  purpose per commit with a `Co-Authored-By:` trailer, agent-written pull requests say so in their
  first line. This file is the local summary, not a replacement.
- Names here are provisional until calef's naming pass rules on them. The repository's own name is
  provisional. Say so beside anything you mint.
- A crate repository that calls these workflows must never carry nife's vocabulary: no roadmap
  citations, no `design/` paths and no `Name:` provenance block (see "Comments and names").
  `sample/` is the template's own fixture and may name nife; `scaffold/`
  is copied into every crate repository and may not (`helpers/scaffold_alone.sh` refuses it, and
  `script/lint` runs the typos gate over `scaffold/`).
- Every third-party action is pinned to a full commit SHA, with the tag in a trailing comment.
  `script/lint` refuses anything else.
- A workflow that swallows a failure says where the failure goes.

## What gates this repository itself

`script/lint` runs in `.github/workflows/selftest.yml` beside a live call of every reusable
workflow against `sample/`, a fixture crate. The selftest is the proof that a change here still
runs; a change that only edits YAML and never sees a green selftest is not done.

## Comments and names

Crate repositories follow nife's comment standard (ruled 2026-11-01 UTC), which is
[section 267 of nifeos/nife](https://github.com/nifeos/nife/blob/main/design/decisions/0267-a-comment-states-the-constraint-as-it-is-now.md)
(a comment states the constraint as it is now).

Two prose gates run in `check / standalone` beside the passive-voice and history gates, with a
ceiling of 0 and no baseline. `helpers/prose_acronyms.py` wants every acronym expanded at its first
use (per file for documents, once per crate for doc comments), in `Extensible Firmware Interface (EFI)` or `EFI (Extensible Firmware Interface)`
form, unless `helpers/prose_acronyms.toml` allows it; keep that allowlist short.
`helpers/prose_figures.py` refuses the phrases in `helpers/prose_figures.toml`, and every entry
there needs a plain replacement, which the failure prints. Both read doc comments through
`helpers/prose_text.py`. A new gate of this kind gets a selftest with a bad and a good fixture.

A crate carries no `Name:` provenance block; git holds a name's history, and `standalone.py`
refuses a block. The naming rules still hold after a crate moves: `check / standalone` runs
`helpers/spelled_out.py`, `unit_symbols.py`, `register_names.py`, `british_spelling.py`, `service_model.py`,
`contract_names.py` and `question_shape.py` over every name the crate defines, with the words in
`helpers/naming_words.toml`, a ceiling of 0 and no baseline. A name that mirrors a
datasheet, a specification or the standard library keeps its spelling by saying so at the item: its
doc comment's first paragraph names it and its source as `(<name>, <source>)`, and a
`#[doc(alias)]` carries the plain-English name. A package or program name, which has no item, is kept
by opening the crate root docs with `(<name>, <source>)`. `helpers/rust_names.py` holds the form, and
a kept name that lacks either part fails. An integer constant (a register, bit, field or command) is
never kept: it takes the spelled-out name, and the source spelling goes in `#[doc(alias)]`.
`register_names.py` holds the register rules, which take no kept form: a register offset ends
`_REGISTER` (in an inline `mod registers` or a file such as `src/registers.rs`), a mask ends `_MASK`,
an integer constant that states its own name as its source is renamed with the source spelling in
`#[doc(alias)]`; an address in memory is virtual or physical, and a size, length or limit carries
its unit.
`helpers/abbreviations.py` runs beside them as a report, never a failure: it lists each component
of a name that is not an English, technical or accepted word. A word joins
`helpers/technical_words.txt` when engineers say it whole, and `[accepted]` when nobody says its
expansion; either change keeps its selftest green.

Three README reports run beside it, also never a failure: `helpers/readme_acronyms.py` (an acronym
used before the README or the crate root's doc comment defines it), `helpers/inflated_wording.py`
(the phrases in `helpers/inflated_wording.toml`) and `helpers/readme_sections.py` (the section order
its header states). A change to the order changes
`scaffold/README-crate.md` and `sample/README.md` with it; `script/lint` fails when the sample has a
finding.

Prose and comments are spell-checked by `helpers/typos_gate.sh` (typos, en-us locale), which
`check / standalone` runs over the crate with the crate's own `_typos.toml`. The tool version is
pinned in `check.yml` and `selftest.yml` together; a bump changes both. The template's own
`_typos.toml` excludes the files that list British spellings on purpose.
