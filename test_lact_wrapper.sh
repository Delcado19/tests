#!/usr/bin/env sh
# Checks lact.lua's standalone formatting/parsing logic: malformed, missing,
# negative, and out-of-range LACT daemon values must all degrade to valid
# Waybar JSON instead of crashing the module.

. "$(dirname -- "$0")/lib/common.sh"

if ! command -v lua >/dev/null 2>&1; then
    skip "lua is not installed"
    finish
fi

# lact.lua only exists on HyDE-Project/HyDE#2096, not yet merged to dev, so a
# checkout of dev has no module for this spec to load (HyDE-Project/tests#5).
# Same gap test_shader_default.sh already guards against for its own module.
lact_module="$REPO_ROOT/Configs/.local/lib/hyde/lact.lua"
[ -f "$lact_module" ] || {
    skip "lact.lua is not in this checkout yet (HyDE-Project/HyDE#2096)"
    finish
}

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

# Isolates lact.lua's state file (the --emoji preference) from the real
# machine, same approach test_gpuinfo_lua_e2e.sh uses for gpuinfo.lua.
mkdir -p "$work_dir/runtime"
LACT_TEST_WORK_DIR="$work_dir" XDG_RUNTIME_DIR="$work_dir/runtime" \
    lua "$TESTS_DIR/lua/lact_spec.lua" || fail "lact_spec reported defects"

finish
