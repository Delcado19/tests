#!/usr/bin/env bash
# app2unit reports launch errors (e.g. "Executable not found: 'br]'" after a
# typo in the rofi launcher) with `notify-send -u critical -a app2unit`.
# HyDE's dunstrc sets `[urgency_critical] timeout = 0`, so those errors stayed
# on screen until logout (#2246). The fix is a dunst rule that expires
# critical app2unit notifications; dunst applies sections in file order, so
# it only works when it comes after [urgency_critical].
#
# This checks the dunstrc that wallbash/scripts/dunst.sh generates, and the
# pre-generated dunstrc shipped in Configs (active until wallbash first runs),
# and that ordinary critical notifications keep `timeout = 0`.

. "$(dirname -- "$0")/lib/common.sh"

script="$REPO_ROOT/Configs/.local/share/wallbash/scripts/dunst.sh"
shipped="$REPO_ROOT/Configs/.config/dunst/dunstrc"
[ -f "$script" ] || {
    fail "dunst.sh not found at $script"
    finish
}

# Prints "<key>=<value>" for every line of section $2 in dunstrc $1, and the
# line number the section starts on as "@line=<n>" (first occurrence only).
section() {
    awk -v want="[$2]" '
        /^\[/ { inside = ($0 == want) && !seen; if (inside) { seen = 1; print "@line=" NR } next }
        inside && /=/ {
            key = $0; sub(/[ \t]*=.*/, "", key)
            val = $0; sub(/^[^=]*=[ \t]*/, "", val)
            print key "=" val
        }
    ' "$1"
}

check() {
    local file=$1 label=$2 crit rule crit_line rule_line
    [ -s "$file" ] || {
        fail "$label: dunstrc is missing or empty"
        return
    }
    crit=$(section "$file" urgency_critical)
    rule=$(section "$file" app2unit_error)
    [ -n "$rule" ] || {
        fail "$label: no [app2unit_error] section, app2unit errors never expire"
        return
    }
    crit_line=$(sed -n 's/^@line=//p' <<<"$crit")
    rule_line=$(sed -n 's/^@line=//p' <<<"$rule")
    [ -n "$crit_line" ] && [ "$rule_line" -gt "$crit_line" ] ||
        fail "$label: [app2unit_error] must come after [urgency_critical] to override its timeout"
    grep -qxF 'appname="^app2unit$"' <<<"$rule" ||
        fail "$label: [app2unit_error] does not match appname exactly '^app2unit\$' (got: $(grep '^appname=' <<<"$rule"))"
    grep -qxF 'msg_urgency=critical' <<<"$rule" ||
        fail "$label: [app2unit_error] is not limited to critical notifications"
    timeout=$(sed -n 's/^timeout=//p' <<<"$rule")
    [[ "$timeout" =~ ^[1-9][0-9]*$ ]] ||
        fail "$label: [app2unit_error] timeout must be a positive number of seconds (got: '$timeout')"
    grep -qxF 'timeout=0' <<<"$crit" ||
        fail "$label: other critical notifications must stay sticky (timeout = 0)"
}

# The shipped file needs no tooling, so it is always checked.
check "$shipped" "shipped Configs/.config/dunst/dunstrc"

if ! command -v envsubst >/dev/null 2>&1; then
    skip "envsubst is not installed, generated dunstrc not checked"
    finish
fi

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

# Stubs: dunst.sh sources hyde-shell for get_hyprConf and restarts dunst at
# the end; neither may touch the real session.
bin="$work_dir/bin"
mkdir -p "$bin" "$work_dir/config/dunst" "$work_dir/cache/wallbash" "$work_dir/data/icons"
cat >"$bin/hyde-shell" <<'EOF'
get_hyprConf() { :; }
EOF
printf '#!/bin/sh\nexit 0\n' >"$bin/killall"
printf '#!/bin/sh\nexit 0\n' >"$bin/dunst"
chmod +x "$bin/hyde-shell" "$bin/killall" "$bin/dunst"
cp "$REPO_ROOT/Configs/.config/dunst/dunst.conf" "$work_dir/config/dunst/dunst.conf"
: >"$work_dir/cache/wallbash/dunst.conf"

PATH="$bin:$PATH" HOME="$work_dir" confDir="$work_dir/config" \
    cacheDir="$work_dir/cache" XDG_DATA_HOME="$work_dir/data" \
    iconsDir="$work_dir/data/icons" WALLBASH_SCRIPTS="$work_dir" \
    bash "$script" >"$work_dir/out.log" 2>&1 ||
    fail "dunst.sh exited non-zero: $(cat "$work_dir/out.log")"

check "$work_dir/config/dunst/dunstrc" "generated dunstrc"

finish
