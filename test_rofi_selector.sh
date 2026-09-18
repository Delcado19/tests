#!/usr/bin/env sh
# The generic rofi dmenu selector's follow-cursor overflow estimate must track
# the resolved theme's own window size, not the "clipboard" dropdown theme's
# fixed 23em x 30em, with safe per-axis fallbacks when the theme file is
# missing, empty, or only partially declares its window size.

. "$(dirname -- "$0")/lib/common.sh"

if ! command -v lua >/dev/null 2>&1; then
    skip "lua is not installed"
    finish
fi

lua "$TESTS_DIR/lua/rofi_selector_harness.lua" || fail "rofi_selector_harness reported defects"

finish
