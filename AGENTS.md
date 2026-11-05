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
  citations and no `design/` paths (a `Name:` provenance block is the one exception; see
  "Comments and names"). `sample/` and `scaffold/` are the only
  places nife may be named, because they are the template's own voice.
- Every third-party action is pinned to a full commit SHA, with the tag in a trailing comment.
  `script/lint` refuses anything else.
- A workflow that swallows a failure says where the failure goes.

## What gates this repository itself

`script/lint` runs in `.github/workflows/selftest.yml` beside a live call of every reusable
workflow against `sample/`, a fixture crate. The selftest is the proof that a change here still
runs; a change that only edits YAML and never sees a green selftest is not done.

## Comments and names

Crate repositories follow nife's comment standard (ruled 2026-11-01 UTC), including the `Name:`
provenance blocks. The standard is
[section 267 of nifeos/nife](https://github.com/nifeos/nife/blob/main/design/decisions/0267-a-comment-states-the-constraint-as-it-is-now.md)
(a comment states the constraint as it is now) and the "Where a name's provenance lives" part of
[nifeos/nife design/naming.md](https://github.com/nifeos/nife/blob/main/design/naming.md). A `Name:`
block stays where it is, with its refusals and dates, and a crate keeps its blocks when it moves
out of nife. This repository adds no lint for it.
