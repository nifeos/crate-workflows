# Contributing

Issues first: the bug report and feature request forms are the front door, and blank issues are
off so a report lands in a shape somebody can act on. A change to the workflows goes through a
pull request, and the selftest (`.github/workflows/selftest.yml`) has to run every reusable
workflow against `sample/` and come back green. A change that only edits YAML and never sees a
green selftest is not done.

## What the workflows may never grow

- nife's vocabulary. The crate repositories this serves are standalone; the template's own
  `sample/` and `scaffold/` are the only places nife's milestones, decisions or tree paths may be
  named, because there they describe where a gate came from. A workflow that cites a nife roadmap
  block in a job step is a bug: the caller cannot resolve it.
- A second way to publish. The `release` workflow is the only thing that tags and the only thing
  that publishes, and it refuses to publish unless the check and proof jobs passed on the same
  commit.
- An unpinned action. Every `uses:` from outside this repository carries a full commit SHA.

## Disclosure

This project's code is written by AI agents working in parallel lanes, with one human reviewing
architecture and outcomes (ruled for nife by 857's Fork 8, and adopted here). Outside
contributions are welcome and reviewed the same way as agent-written ones: by what the diff does
and what the selftest says. A pull request written by an agent opens by saying so. A person outside the project who submits a change may use any tools
they like and does not need to say which.
