#!/usr/bin/env sh
# An icon-only Waybar module format must end in a space, or its glyph's ink
# overflow bleeds into the next module in the bar (#2206).

. "$(dirname -- "$0")/lib/common.sh"

if ! command -v python3 >/dev/null 2>&1; then
    skip "python3 is not installed"
    finish
fi

python3 "$TESTS_DIR/python/check_icon_trailing_space.py" ||
    fail "an icon-only module format lost its trailing space"

finish
