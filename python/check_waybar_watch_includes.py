"""--watch must generate the CSS includes that defaults.css imports.

Session autostart runs `waybar.py --watch` and nothing else. On a clean
install ~/.config/waybar/includes held no border-radius.css or global.css, so
the @imports in defaults.css failed, waybar exited 1 and systemd stopped
restarting it (HyDE-Project/HyDE#2160).
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", ".")).resolve()
LIB = REPO_ROOT / "Configs/.local/lib/hyde"

failures = 0


def fail(msg: str) -> None:
    global failures
    failures += 1
    print(f"FAIL: {msg}", file=sys.stderr)


work = pathlib.Path(tempfile.mkdtemp(prefix="waybar_watch_"))
atexit.register(shutil.rmtree, work, ignore_errors=True)
for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state"),
                 ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "run"), ("HOME", "home")):
    (work / sub).mkdir()
    os.environ[var] = str(work / sub)
os.environ.pop("WAYBAR_BORDER_RADIUS", None)
sys.path.insert(0, str(LIB))

spec = importlib.util.spec_from_file_location("waybar_under_test", LIB / "waybar.py")
wb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wb)

wb.is_waybar_running_for_current_user = lambda: False
launched = []
wb.subprocess.run = lambda cmd, *a, **k: launched.append(cmd)
wb.HAS_SYSTEMD = True

# The templates a deployed install has under $XDG_DATA_HOME.
template_dir = work / "data/waybar/includes"
template_dir.mkdir(parents=True)
shutil.copy(REPO_ROOT / "Configs/.local/share/waybar/includes/border-radius.css", template_dir)

includes = work / "config/waybar/includes"
css = (includes / "border-radius.css", includes / "global.css")


def reset(preexisting: bool = False) -> None:
    shutil.rmtree(includes, ignore_errors=True)
    launched.clear()
    if preexisting:
        includes.mkdir(parents=True)
        for f in css:
            f.write_text("/* user */\n")


# 1. clean install: both imported files exist before waybar is launched
reset()
wb.watch_waybar()
for f in css:
    if not f.is_file():
        fail(f"watch_waybar() left {f.name} missing")
if not launched:
    fail("watch_waybar() did not launch waybar")

# 2. waybar already running: nothing is touched and nothing is launched
reset()
wb.is_waybar_running_for_current_user = lambda: True
wb.watch_waybar()
if includes.exists() or launched:
    fail("watch_waybar() acted although waybar is already running")
wb.is_waybar_running_for_current_user = lambda: False

# 3. repeated start keeps working and keeps existing files valid
reset(preexisting=True)
wb.watch_waybar()
wb.watch_waybar()
for f in css:
    if not f.is_file() or not f.read_text().strip():
        fail(f"{f.name} empty or missing after repeated watch_waybar()")

# 4. garbage radius from the environment must not stop the launch
reset()
os.environ["WAYBAR_BORDER_RADIUS"] = "not-a-number"
try:
    wb.watch_waybar()
except Exception as e:  # noqa: BLE001
    fail(f"watch_waybar() raised on a malformed border radius: {e!r}")
if not launched:
    fail("watch_waybar() skipped the launch on a malformed border radius")

sys.exit(1 if failures else 0)
