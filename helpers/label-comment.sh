#!/bin/sh
# shellcheck shell=sh
#
# helpers/label-comment.sh: post label.yml's one finding comment, marker-guarded so a pull request
# gets it once, ever. Ported from nife's helpers/architect-label-comment.sh, with the crate
# repository's two rules in place of nife's five and the drain references dropped (a crate
# repository has no merge drain; the hold check itself keeps the label live).
#
# Out of the workflow file for the reason its nife original records: a YAML block literal breaks on
# a multi-line comment body written the way a human would write it. A plain script has no such
# constraint.
#
# Usage: helpers/label-comment.sh <pr-number> <owner/repo> <report>
#   <report>  the rule engine's output, one "rule: file: detail" line per match
#
# Needs `gh` (GH_TOKEN) and `jq`. Never exits non-zero: a failed comment is logged and swallowed.
# No correction of error should ever be blocked from existing because a comment API call failed.

set -eu

pr_number="$1"
repo="$2"
report="$3"
marker="crate-architect-rules-finding"

existing="$(gh pr view "$pr_number" --repo "$repo" --json comments 2>/dev/null |
	jq -r --arg m "$marker" '[.comments[] | select(.body | contains($m))] | length' 2>/dev/null || echo 0)"

if [ "${existing:-0}" != "0" ]; then
	echo "label-comment: marker already on PR #$pr_number; not posting again"
	exit 0
fi

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT

cat >"$body_file" <<BODY
\`needs-architect\` was added because this diff matched a rule in \`.crate-workflows/helpers/architect-label-rules.py\`. The two rules this repository keeps from nife's labeler:

- a dependency new to the crate's graph;
- a breaking change \`cargo-semver-checks\` reports against the last published version.

What each finding means is in that file's docstring. A ruling is recorded with \`script/record-ruling $pr_number --text '<the ruling>'\`, which swaps the label for \`architect-ruled\`; removing \`needs-architect\` by hand does not stick, because the labeler re-fires on the next push while a rule still fires. "False positive, nothing like that moved" is a ruling like any other.

<!-- $marker -->
BODY

if gh pr comment "$pr_number" --repo "$repo" --body-file "$body_file" >/dev/null 2>&1; then
	echo "label-comment: posted the finding on PR #$pr_number"
else
	echo "label-comment: could not post the finding comment on PR #$pr_number." >&2
	echo "label-comment: not fatal. The label itself is still on the pull request." >&2
fi
exit 0
