#!/bin/sh
# Keep logic coverage available on machines without a graphical test stack.
set -eu
root=${REPO_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 "$root/tests/settings_test.py"
if command -v xvfb-run >/dev/null 2>&1 && /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "3.0")' 2>/dev/null; then
    GDK_BACKEND=x11 xvfb-run -a /usr/bin/python3 "$root/tests/settings_test.py" --gtk
elif [ "${CI:-}" = true ]; then
    echo 'GTK and Xvfb are required in CI' >&2
    exit 1
else
    echo 'SKIP: GTK integration tests require GTK 3, PyGObject and xvfb-run'
fi
