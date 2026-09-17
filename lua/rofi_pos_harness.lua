-- Exercise the public positioning API without a running compositor.
local lib = assert(os.getenv('REPO_ROOT'), 'REPO_ROOT is not set') .. '/Configs/.local/lib/hyde/'
package.path = lib .. '?.lua;' .. package.path
local cursor, monitor
package.loaded['luautils.hypr.hyprctl'] = {
    cursorpos = function() return cursor end,
    get_active_monitor = function() return monitor end
}
local pos = require('luautils.rofi.pos')
local function check(x, y, size, expected_x, expected_y, anchor)
    cursor = {x=x, y=y}
    local result = pos.get_rofi_pos(size)
    assert(math.abs(result.x-expected_x)<1e-6, 'unexpected x offset: '..result.x)
    assert(math.abs(result.y-expected_y)<1e-6, 'unexpected y offset: '..result.y)
    assert(result.str:find('anchor:'..anchor..';',1,true), result.str)
end
monitor = {width=1000, height=1000}
check(100,100,nil,100,100,'west north')
check(100,100,{min_width=200,min_height=200},100,100,'west north')
check(100,100,{min_width=900,min_height=900},100,100,'west north')
check(100,100,{min_width=950,min_height=950},50,50,'west north')
check(900,900,{min_width=950,min_height=950},-50,-50,'east south')
check(500,500,{min_width=0,min_height=0},-500,-500,'east south')
check(100,100,{min_width=1200,min_height=1200},-200,-200,'west north')
check(900,900,{min_width=1200,min_height=1200},200,200,'east south')

-- Reserved areas and configured margins contribute to both safe boundaries.
monitor.reserved = {10,20,30,40}
hyde = {config={monitor={edge_margin={0.01,0.02,0.03,0.04}}}}
check(100,100,{min_width=900,min_height=900},0,0,'west north')
check(900,900,{min_width=900,min_height=900},0,0,'east south')
hyde.config.monitor.edge_margin = {0.01,0.02}
check(100,100,nil,70,70,'west north')
hyde.config.monitor.edge_margin = {0.01}
check(100,100,nil,80,70,'west north')
hyde = nil

monitor = {width=2000,height=1000,scale=2,x=-1000,y=100,transform=1}
check(-900,200,{min_width=450,min_height=950},50,50,'west north')
cursor = nil
local result = pos.get_rofi_pos()
assert(result.x==0 and result.y==0 and result.str=='', 'missing cursor must use default placement')
cursor, monitor = {x=0,y=0}, nil
result = pos.get_rofi_pos()
assert(result.x==0 and result.y==0 and result.str=='', 'missing monitor must use default placement')
print('PASS: rofi fit/overflow boundaries, both axes, margins, scaling, rotation and missing compositor data')
