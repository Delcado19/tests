#!/usr/bin/env sh
. "$(dirname -- "$0")/lib/common.sh"

if ! command -v lua >/dev/null 2>&1; then
    skip "lua is not installed"
    finish
fi

lua "$TESTS_DIR/lua/rofi_pos_harness.lua" || fail "rofi_pos_harness reported defects"
finish
