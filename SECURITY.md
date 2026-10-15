# Security policy

This repository holds CI workflows, not shipped code. A security problem here is a way to run
untrusted code in every crate repository that calls the workflows, or a way to publish a crate
nobody reviewed. Report those through GitHub's private vulnerability reporting; the apply script
turns it on for every crate repository too.

What shapes the design: every third-party action is pinned to a commit SHA, the default
`GITHUB_TOKEN` is read-only everywhere except the release's tag and publish jobs, and publishing
goes through the `crates-io` environment, which requires a person's approval. A change that weakens
any of the three is the thing to report on, not a leak of secrets nobody stores here.

Like nife, most of this was written by AI agents working in parallel lanes, with one human
reviewing architecture and outcomes. That is disclosed rather than hidden; it is also why the
workflows say what each gate is for instead of trusting institutional memory.

## Supported versions

One line: the newest release tag. A crate repository calling an older release is failed by the lag
check, not supported by a patch to the old one.
