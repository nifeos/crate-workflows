#!/bin/sh
# shellcheck shell=sh
#
# helpers/lag-check-selftest.sh: proves helpers/lag-check.sh against a stand-in `gh`, so no network
# and no release are needed. Each case sets the releases, the compare status against the newest and
# the previous release, and the clock, then names the verdict the check must reach. Run it from
# the repository root: sh helpers/lag-check-selftest.sh

set -eu

cd "$(dirname "$0")/.."
check="$PWD/helpers/lag-check.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/bin"

# The stand-in gh answers the three calls the check makes. FAKE_RELEASES is the release list as
# JSON, newest first; FAKE_VS_NEWEST and FAKE_VS_PREVIOUS are the compare statuses.
cat >"$work/bin/gh" <<'STUB'
#!/bin/sh
path="$2"
shift 2
jq_filter=""
[ "${1:-}" = "--jq" ] && jq_filter="$2"
case "$path" in
*/releases?per_page=2)
	[ -n "$FAKE_RELEASES" ] || exit 1
	json="$FAKE_RELEASES"
	;;
*/commits/*)
	json="{\"sha\": \"sha-of-${path##*/}\"}"
	;;
*/compare/sha-of-"$FAKE_NEWEST_TAG"...*)
	json="{\"status\": \"$FAKE_VS_NEWEST\"}"
	;;
*/compare/sha-of-*)
	json="{\"status\": \"$FAKE_VS_PREVIOUS\"}"
	;;
*)
	exit 1
	;;
esac
printf '%s' "$json" | jq -r "$jq_filter"
STUB
chmod +x "$work/bin/gh"

two='[{"tag_name":"v9","published_at":"2026-11-23T00:00:00Z"},{"tag_name":"v8","published_at":"2026-11-16T00:00:00Z"}]'
one='[{"tag_name":"v1","published_at":"2026-11-23T00:00:00Z"}]'
day=86400
tag_time=1795392000 # 2026-11-23T00:00:00Z

failures=0
# expect <pass|fail> <name> <releases> <vs newest> <vs previous> <days after the newest release>
expect() {
	verdict="$1" name="$2"
	set +e
	PATH="$work/bin:$PATH" TEMPLATE_REPO=o/r GITHUB_REPOSITORY=x/y JOB_WORKFLOW_SHA=pin \
		FAKE_RELEASES="$3" FAKE_NEWEST_TAG="${FAKE_NEWEST_TAG:-v9}" FAKE_VS_NEWEST="$4" FAKE_VS_PREVIOUS="$5" \
		LAG_NOW=$((tag_time + $6 * day)) sh "$check" >"$work/out" 2>&1
	code=$?
	set -e
	if { [ "$verdict" = pass ] && [ "$code" -eq 0 ]; } || { [ "$verdict" = fail ] && [ "$code" -ne 0 ]; }; then
		echo "ok: $name"
	else
		echo "FAILED: $name (wanted $verdict, exit $code)" >&2
		cat "$work/out" >&2
		failures=$((failures + 1))
	fi
}

expect pass "pinned at the newest release" "$two" identical behind 3
expect pass "pinned ahead of the newest release" "$two" ahead identical 30
expect pass "one release behind, newest is 3 days old" "$two" behind identical 3
expect pass "one release behind, newest is exactly 7 days old" "$two" behind identical 7
expect pass "between the previous and the newest release" "$two" behind ahead 3
expect fail "one release behind, newest is 8 days old" "$two" behind identical 8
expect fail "two releases behind, newest is 1 day old" "$two" behind behind 1
expect fail "diverged from the release line" "$two" diverged diverged 1
expect pass "behind the only release, inside the grace" "$one" behind behind 2
expect fail "behind the only release, past the grace" "$one" behind behind 9
expect fail "no release at all" "" identical identical 0

# A call in the template's own repository stands down; an empty pin fails closed.
if ! PATH="$work/bin:$PATH" TEMPLATE_REPO=o/r GITHUB_REPOSITORY=o/r JOB_WORKFLOW_SHA='' sh "$check" >/dev/null 2>&1; then
	echo "FAILED: same-repository call must pass" >&2
	failures=$((failures + 1))
else
	echo "ok: same-repository call"
fi
if PATH="$work/bin:$PATH" TEMPLATE_REPO=o/r GITHUB_REPOSITORY=x/y JOB_WORKFLOW_SHA='' sh "$check" >/dev/null 2>&1; then
	echo "FAILED: empty pin must fail" >&2
	failures=$((failures + 1))
else
	echo "ok: empty pin fails closed"
fi

[ "$failures" -eq 0 ] || exit 1
echo "lag-check-selftest: all cases behaved"
