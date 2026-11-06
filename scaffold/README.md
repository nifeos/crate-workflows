# What a crate repository copies

A crate repository carries none of this template's code. It carries thin callers, one configuration
file set, and the pins. Copy this directory's contents into the new repository's root:

    cp -R ../crate-workflows/scaffold/. .

then replace `@PINS@` in every caller workflow file with the commit SHA of the template release you are
adopting (`git rev-parse v1^{commit}` in the template checkout), and commit. Dependabot's
github-actions ecosystem opens the bumps afterward; the lag check fails closed in the meantime.

| file | what it is |
|---|---|
| caller-workflows/ci.yml | calls check.yml on pull requests and on each push to main; the push run is at the merge commit's SHA, which is what the release gate reads |
| caller-workflows/proofs.yml | calls proofs.yml on pull requests and on each push to main, same |
| caller-workflows/weekly.yml | calls weekly.yml on a Monday cron and on dispatch |
| caller-workflows/fuzz.yml | calls fuzz.yml on a Tuesday cron and on dispatch; fuzzes nothing until the caller sets `public-crash-inputs: true`, which only a crate with no `unsafe` code does (crash inputs are public); see the template README |
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
| `CODEOWNERS` | the crate-maintainers team owns every path |
| caller `weekly.yml` | forwards the `SETTINGS_TOKEN` secret to the template's weekly workflow |
| `CONTRIBUTING.md` | disclosure of agent-written work, and how outside contributions are reviewed |
| `SECURITY.md` | what a security report means here, and private reporting |
| CHANGELOG.md | one line per release; the release gate reads nothing from it, people do |
| README-crate.md | the crate README's starting shape, with `EXAMPLES` and `BUGS` headings already in it |
| deny.toml | the cargo-deny policy: no skipped crate, no ignored advisory |
| _typos.toml | the en-us locale for the typos step; add a word only with its reason, never to hide a misspelling |
| rustfmt.toml | the stable subset; the two unstable options are refused |
| .githooks/commit-msg | the Co-Authored-By trailer, required of every agent's commit |
| docs/stranger-test.md | the stranger cadence record; starts at `Last run: none`, which the release gate refuses |

The caller workflow files fix the job ids (`check`, `proofs`, `weekly`, `release`, `label`, `hold`),
which is what makes the required-check names in the settings file stable: GitHub shows a called
reusable workflow's jobs as `<caller job id> / <job name>`, so `check / fmt` and friends resolve
exactly when the caller ids are these.
