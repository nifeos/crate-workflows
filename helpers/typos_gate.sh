#!/bin/sh
#
# helpers/typos_gate.sh DIR: spell-check the tree under DIR with the _typos.toml that sits in DIR.
#
# The gate exists because house style is American spelling and typos is the tool that knows both
# the misspellings and the locale. It refuses two things before it runs the tool: a DIR without a
# _typos.toml (the gate would otherwise run with typos' default locale and accept British spellings), and a
# _typos.toml whose locale is not en-us. Run as `check / standalone`'s typos step and by
# script/lint's selftest. Exit 0 clean, 1 on a finding or a refused config, 2 on bad usage or a
# missing typos binary.

set -eu

[ $# -eq 1 ] || { echo "usage: typos_gate.sh DIR" >&2; exit 2; }
dir=$1
config="$dir/_typos.toml"

command -v typos >/dev/null 2>&1 || { echo "typos_gate: typos is not installed" >&2; exit 2; }
[ -f "$config" ] || {
	echo "typos_gate: $config is missing; copy _typos.toml from the template's scaffold/" >&2
	exit 1
}
grep -Eq '^locale[[:space:]]*=[[:space:]]*"en-us"[[:space:]]*(#.*)?$' "$config" || {
	echo "typos_gate: $config must set locale = \"en-us\" under [default]" >&2
	exit 1
}
exec typos --config "$config" "$dir"
