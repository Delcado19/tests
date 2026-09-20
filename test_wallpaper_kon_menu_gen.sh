#!/usr/bin/env sh
# wallpaper.kon.sh regenerates its own hydewallpaper.desktop at runtime
# (the "Refresh List" action, and every per-theme "Set As Wallpaper" action
# it writes into the [Desktop Action ...] blocks). #2121 fixed the *shipped*
# hydewallpaper.desktop's Exec= line to route through hyde-shell, but missed
# that wallpaper.kon.sh writes the same file itself, using its own bare
# $scrName -- undoing the fix the first time a user clicks "Refresh List",
# and never routing the per-theme click actions through hyde-shell at all.
# Static-check the generator's templates directly, since the actual output
# only exists at runtime in $HOME/.local/share/kio/servicemenus, not in this
# checkout (see #2118, #2121).

. "$(dirname -- "$0")/lib/common.sh"

wallpaper_kon="$REPO_ROOT/Configs/.local/lib/hyde/wallpaper.kon.sh"
if [ ! -f "$wallpaper_kon" ]; then
    skip "wallpaper.kon.sh not shipped in this checkout"
    finish
fi

exec_lines=$(grep 'Exec=' "$wallpaper_kon")
if [ -z "$exec_lines" ]; then
    skip "no Exec= templates found in wallpaper.kon.sh"
    finish
fi

checked=0
while IFS= read -r line; do
    [ -n "$line" ] || continue
    checked=$((checked + 1))
    case "$line" in
    *'Exec=hyde-shell '*)
        continue
        ;;
    esac
    fail "wallpaper.kon.sh writes: $line -- an Exec= line for the generated \
hydewallpaper.desktop without routing through hyde-shell. A GUI-launched KIO \
action doesn't have \$HOME/.local/lib/hyde on PATH (only \$HOME/.local/bin, \
see Configs/.config/uwsm/env.d/00-hyde.sh), so the bare script name fails \
with 'could not find the program' -- exactly the #2118 regression #2121 was \
meant to close, reintroduced the moment this generator runs."
done <<EOF
$exec_lines
EOF

printf '    %d generated Exec= template(s) checked for the session-PATH gap\n' "$checked"

finish
