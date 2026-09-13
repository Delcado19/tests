#!/usr/bin/env sh
# "More Themes" (theme.import.py's fzf list) marks already-installed themes
# with a suffix so the user can tell them apart. The marker must be stripped
# back off before the raw theme name is looked up in the gallery JSON, or
# get_theme_preview() crashes on every already-installed theme.

. "$(dirname -- "$0")/lib/common.sh"

if ! command -v python3 >/dev/null 2>&1; then
    skip "python3 is not installed"
    finish
fi

python3 "$TESTS_DIR/python/check_theme_import_installed_marker.py" ||
    fail "check_theme_import_installed_marker reported defects"

finish
