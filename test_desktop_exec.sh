#!/usr/bin/env sh
# HyDE's own shipped session-wide PATH (Configs/.config/uwsm/env.d/00-hyde.sh)
# only prepends $HOME/.local/bin -- never $HOME/.local/lib/hyde, which is only
# added by the interactive shell's rc file (.zshrc). A GUI app started by the
# session (a file manager launching a KIO service menu action, for example)
# inherits the session's PATH, not a login shell's, so a `.desktop` Exec= line
# naming a bare Configs/.local/lib/hyde/*.sh script by its bare name resolves
# fine from a terminal and fails with "could not find the program" from the
# GUI -- exactly what happened with hydewallpaper.desktop's `wallpaper.kon.sh`
# (issue #2118). Routing through `hyde-shell <script>` fixes it, since
# hyde-shell itself lives in the always-present $HOME/.local/bin.
#
# This is a static check (does the Exec= command name a lib/hyde script by
# its bare name, unrouted) rather than an actual PATH lookup, so it holds on
# any checkout -- including CI, which never has HyDE actually deployed to
# $HOME -- not only a machine with a live install to run `command -v` against.

. "$(dirname -- "$0")/lib/common.sh"

desktop_files=$(find -H "$REPO_ROOT" -name "*.desktop" -not -path "*/tests/*" -not -path "*/.claude/*" -not -path "*/.git/*")
if [ -z "$desktop_files" ]; then
    skip "no .desktop files shipped in this checkout"
    finish
fi

lib_hyde="$REPO_ROOT/Configs/.local/lib/hyde"
checked=0
while IFS= read -r desktop_file; do
    [ -n "$desktop_file" ] || continue
    while IFS= read -r exec_line; do
        [ -n "$exec_line" ] || continue
        checked=$((checked + 1))
        cmd=$(printf '%s' "$exec_line" | sed 's/^Exec=//' | awk '{print $1}')
        case "$cmd" in
        "" | /* | hyde-shell)
            # Empty, an already-absolute path, or already routed through
            # hyde-shell: none of these hit the session-PATH gap.
            continue
            ;;
        esac
        if [ -f "$lib_hyde/$cmd" ]; then
            fail "$(basename "$desktop_file"): Exec='$exec_line' names $cmd by its bare name. \
$cmd lives in \$HOME/.local/lib/hyde, which is on PATH for an interactive shell (.zshrc) but not \
for the session-wide PATH a GUI-launched app like this actually runs under (only \$HOME/.local/bin \
is prepended there, see Configs/.config/uwsm/env.d/00-hyde.sh) -- a terminal test would miss this, \
a real click in a file manager would fail with \"could not find the program\". Route through \
'hyde-shell $cmd' instead."
        fi
    done <<EOF
$(grep "^Exec=" "$desktop_file")
EOF
done <<EOF
$desktop_files
EOF

[ "$checked" -gt 0 ] || {
    skip "no Exec= lines found in the shipped .desktop file(s)"
    finish
}

printf '    %d desktop Exec command(s) checked for the session-PATH gap\n' "$checked"

finish
