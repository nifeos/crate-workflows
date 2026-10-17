# What a crate repository copies

A crate repository carries none of this template's code. It carries thin callers, one configuration
file set, and the pins. Copy this directory's contents into the new repository's root:

    cp -R ../crate-workflows/scaffold/. .

then replace `@PINS@` in the six workflow files with the commit SHA of the template release you are
adopting (`git rev-parse v1^{commit}` in the template checkout), and commit. Dependabot's
github-actions ecosystem opens the bumps afterward; the lag check fails closed in the meantime.

| file | what it is |
|---|---|
| caller-workflows/ci.yml | calls check.yml on pull requests; the runs land at the merge commit's SHA, which is what the release gate reads |
| caller-workflows/proofs.yml | calls proofs.yml on pull requests, same |
| caller-workflows/weekly.yml | calls weekly.yml on a Monday cron and on dispatch |
| caller-workflows/release.yml | calls release.yml on dispatch |
| caller-workflows/label.yml | calls label.yml on pull request pushes |
| caller-workflows/hold.yml | calls hold.yml on pull request and label events |
| caller-workflows/ruled.yml | calls ruled.yml on label events |
| .github/ci-job-budgets | the template's budgets, with reasons; raise one with a reason of your own |
| .github/mutants-exempts | empty; a survivor goes here with a reason, or the weekly run goes red |
| .github/coverage-exemptions | empty; a file that cannot run on the host goes here with a reason |
| .github/dependabot.yml | cargo and github-actions ecosystems, both weekly |
| .github/pull_request_template.md | the disclosure line first, then what changed |
| .github/ISSUE_TEMPLATE/ | bug report and feature request forms, blank issues off |
| CODEOWNERS | the crate-maintainers team owns every path |
| caller `weekly.yml` | forwards the `SETTINGS_TOKEN` secret to the template's weekly workflow |
| CONTRIBUTING.md | disclosure of agent-written work, and how outside contributions are reviewed |
| SECURITY.md | what a security report means here, and private reporting |
| CHANGELOG.md | one line per release; the release gate reads nothing from it, people do |
| README-crate.md | the crate README's starting shape, with EXAMPLES and BUGS headings already in it |
| deny.toml | nife's cargo-deny policy without its exceptions |
| rustfmt.toml | the stable subset; nife's two unstable options would be refused |
| .githooks/commit-msg | the Co-Authored-By trailer, required of every agent's commit |
| docs/stranger-test.md | the stranger cadence record; the first run is overdue until it exists |

The caller workflow files fix the job ids (`check`, `proofs`, `weekly`, `release`, `label`, `hold`),
which is what makes the required-check names in the settings file stable: GitHub shows a called
reusable workflow's jobs as `<caller job id> / <job name>`, so `check / fmt` and friends resolve
exactly when the caller ids are these.
