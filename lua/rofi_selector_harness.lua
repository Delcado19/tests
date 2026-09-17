-- luautils/selector/rofi.lua estimates the rendered window size (for the
-- follow-cursor overflow clamp) from the resolved theme's own .rasi file,
-- falling back to the shared dropdown themes' 23em x 30em window when that
-- file is missing or doesn't declare width/height. It used to hardcode
-- 23em x 30em regardless of which theme was actually rendered, so a caller
-- using a differently-sized theme (without an explicit min_width_em/
-- min_height_em override) got a wrong overflow estimate.
--
-- REPO_ROOT selects the tree to check.

local repo_root = assert(os.getenv("REPO_ROOT"), "REPO_ROOT is not set")
local lib_root = repo_root .. "/Configs/.local/lib/hyde"
package.path = lib_root .. "/?.lua;" .. lib_root .. "/?/init.lua;" .. package.path

local root = os.tmpname()
os.remove(root)
os.execute(string.format("mkdir -p '%s/hyde/rofi/themes'", root))

package.loaded["luautils.xdg"] = {data = root}
package.loaded["luautils.hypr.hyprctl"] = {
    get_option_value = function() return "0" end
}

local captured_pos_opts
package.loaded["luautils.rofi.pos"] = {
    get_rofi_pos = function(opts)
        captured_pos_opts = opts
        return {x = 0, y = 0, str = ""}
    end
}

-- The final command still runs through io.popen; stub it so the harness
-- never depends on the `rofi`/`printf` binaries actually being installed.
io.popen = function()
    return {
        read = function() return "" end,
        close = function() return true, "exit", 0 end
    }
end

local rofi = require("luautils.selector.rofi")

local failures = 0
local function check(condition, message)
    if not condition then
        failures = failures + 1
        print("    fail: " .. message)
    end
end

local function close(a, b)
    return math.abs(a - b) < 1e-6
end

local function write(path, contents)
    local f = assert(io.open(path, "w"))
    assert(f:write(contents))
    f:close()
end

local PX_PER_EM = 10 * (4 / 3) -- default scale is 10

local function select_with(theme, opts)
    opts = opts or {}
    opts.theme = theme
    captured_pos_opts = nil
    rofi.select({{name = "one", icon = ""}}, opts)
    return captured_pos_opts
end

-- A theme with a non-default window size must drive the estimate.
write(root .. "/hyde/rofi/themes/wide.rasi", "window {\n    width: 60em;\n    height: 12em;\n}\n")
local wide = select_with("wide")
check(wide ~= nil, "rofi.select did not reach the position estimate for an existing theme")
check(wide and close(wide.min_width, 60 * PX_PER_EM), "a theme's own width was not used for the overflow estimate")
check(wide and close(wide.min_height, 12 * PX_PER_EM), "a theme's own height was not used for the overflow estimate")

-- A theme file that exists but declares no window size falls back to 23x30em.
write(root .. "/hyde/rofi/themes/bare.rasi", 'configuration { modi: "drun"; }\n')
local bare = select_with("bare")
check(bare and close(bare.min_width, 23 * PX_PER_EM), "a theme without a window block must fall back to the 23em default width")
check(bare and close(bare.min_height, 30 * PX_PER_EM), "a theme without a window block must fall back to the 30em default height")

-- A theme name with no matching file on disk must not error, and must also fall back.
local ok, missing = pcall(select_with, "does-not-exist")
check(ok, "a theme with no .rasi file on disk must not raise an error: " .. tostring(missing))
check(missing and close(missing.min_width, 23 * PX_PER_EM), "a missing theme file must fall back to the 23em default width")

-- An empty theme name (falsy in every other language, truthy in Lua) must not
-- be treated as a real path and must also fall back.
local ok_empty, empty = pcall(select_with, "")
check(ok_empty, "an empty theme name must not raise an error: " .. tostring(empty))
check(empty and close(empty.min_height, 30 * PX_PER_EM), "an empty theme name must fall back to the 30em default height")

-- Malformed/partial content (e.g. a unitless or missing dimension) must fall
-- back per-axis instead of failing the whole lookup.
write(root .. "/hyde/rofi/themes/partial.rasi", "window {\n    width: 60em;\n    height: 12px;\n}\n")
local partial = select_with("partial")
check(partial and close(partial.min_width, 60 * PX_PER_EM), "a parseable width must still be honored even if height is not")
check(partial and close(partial.min_height, 30 * PX_PER_EM), "a height with the wrong unit must fall back to the 30em default rather than erroring")

-- An explicit min_width_em/min_height_em override always wins over the theme.
local overridden = select_with("wide", {min_width_em = 5, min_height_em = 6})
check(overridden and close(overridden.min_width, 5 * PX_PER_EM), "an explicit min_width_em override must take priority over the theme")
check(overridden and close(overridden.min_height, 6 * PX_PER_EM), "an explicit min_height_em override must take priority over the theme")

os.execute(string.format("rm -rf '%s'", root))
os.exit(failures == 0 and 0 or 1)
