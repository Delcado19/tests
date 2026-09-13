#!/usr/bin/env sh
# Every shipped Lua file has to parse.

. "$(dirname -- "$0")/lib/common.sh"

if ! command -v luac >/dev/null 2>&1; then
    skip "luac is not installed"
    finish
fi

files_list=$(mktemp) || exit 1
trap 'rm -f "$files_list"' EXIT

find "$REPO_ROOT/Configs" -name '*.lua' -type f | sort > "$files_list"

count=0
while IFS= read -r file; do
    count=$((count + 1))
    luac -p "$file" >/dev/null 2>&1 || fail "${file#"$REPO_ROOT"/} does not parse"
done < "$files_list"

printf '    %d file(s) checked\n' "$count"
finish
