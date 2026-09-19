#!/usr/bin/env sh
. "$(dirname -- "$0")/lib/common.sh"

if ! command -v lua >/dev/null 2>&1; then
    skip "lua is not installed"
    finish
fi

# shaders.lua (and this harness, via luautils.init) requires lfs (LuaFileSystem).
# HyDE builds that into its own bootstrapped lua_env with luarocks rather than
# installing it as a system package (see pyutils/lua_env.py), so a checkout
# that never ran that bootstrap -- a fresh CI runner, most sandboxes -- has no
# lfs.so to find. Same gap test_shader_default.sh already guards against.
lua_env="$HOME/.local/state/hyde/lua_env"
lua_lib=$(find "$lua_env/lib/lua" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -n 1)
if [ -z "$lua_lib" ]; then
    skip "the lua environment is not built, lfs (LuaFileSystem) is unavailable"
    finish
fi

lua "$TESTS_DIR/lua/shaders_harness.lua" || fail "shaders_harness reported defects"
finish
