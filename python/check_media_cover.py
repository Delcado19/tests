"""mediacover.py: the album-art popup behind "Show Cover" (HyDE-Project/HyDE#2153).

Waybar tooltips cannot show images, so the mediaplayer/spotify right-click
menus open a small GTK layer-shell window instead. Everything that decides
*what* that window shows and *where* is plain Python and checked here without
a display: resolving mpris:artUrl to a local file (file:// directly, http(s)
downloaded once into a per-URL cache), picking the player, placing the popup
under the cursor, and the one-popup-at-a-time toggle. The menu wiring in both
module configs is checked as well.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", ".")).resolve()
LIB = REPO_ROOT / "Configs/.local/lib/hyde"
MODULES = REPO_ROOT / "Configs/.local/share/waybar/modules"
MENUS = REPO_ROOT / "Configs/.local/share/waybar/menus"

failures = 0


def fail(msg: str) -> None:
    global failures
    failures += 1
    print(f"FAIL: {msg}", file=sys.stderr)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def load_module():
    path = LIB / "mediacover.py"
    if not path.is_file():
        sys.exit(f"FAIL: {path} does not exist")
    sys.path.insert(0, str(LIB))
    spec = importlib.util.spec_from_file_location("mediacover", path)
    module = importlib.util.module_from_spec(spec)
    # Importing must not need gi or a display: the GTK part loads in main().
    spec.loader.exec_module(module)
    return module


class _Handler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):  # noqa: N802
        _Handler.hits.append(self.path)
        if urllib.parse.urlparse(self.path).path == "/cover.png":
            body = b"\x89PNG fake cover"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def check_art_path(mc) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cache = tmp / "cache"

        # file:// is used as-is, including percent-encoded names.
        local = tmp / "my cover (1).jpg"
        local.write_bytes(b"jpg")
        url = "file://" + urllib.parse.quote(str(local))
        check(mc.art_path(url, cache) == local, "file:// art URL does not resolve to the local file")
        check(mc.art_path("file:///nonexistent/cover.jpg", cache) is None, "missing file:// art should give None")

        # Empty, missing and unsupported schemes have no art.
        for bad in ("", None, "ftp://example.com/a.jpg", "data:image/png;base64,AAAA", "not a url"):
            check(mc.art_path(bad, cache) is None, f"art URL {bad!r} should give None")

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            got = mc.art_path(base + "/cover.png", cache)
            check(got is not None and got.is_file(), "http art URL was not downloaded")
            if got is not None:
                check(got.read_bytes() == b"\x89PNG fake cover", "downloaded art has the wrong content")
                check(cache in got.parents, "downloaded art is not stored in the cache dir")
            hits = len(_Handler.hits)
            again = mc.art_path(base + "/cover.png", cache)
            check(again == got, "same art URL resolved to a different cache file")
            check(len(_Handler.hits) == hits, "cached art URL was downloaded a second time")

            other = mc.art_path(base + "/cover.png?v=2", cache)
            check(other is not None and other != got, "different art URLs share one cache file")

            check(mc.art_path(base + "/missing.png", cache) is None, "HTTP 404 art should give None")
            leftovers = [p.name for p in cache.iterdir() if p not in (got, other)]
            check(not leftovers, f"failed download left files in the cache: {leftovers}")

            # Nothing listens on port 9 (discard); must fail fast, not raise.
            check(mc.art_path("http://127.0.0.1:9/x.png", cache) is None, "unreachable art host should give None")
        finally:
            server.shutdown()


def check_pick_player(mc) -> None:
    players = [("firefox", "Paused"), ("spotify", "Playing"), ("vlc", "Stopped")]
    check(mc.pick_player(players, None) == "spotify", "the playing player should win without --player")
    check(mc.pick_player(players, "vlc") == "vlc", "--player should pick that player even when it is not playing")
    check(mc.pick_player(players, "mpv") is None, "--player naming an absent player should give None")
    check(mc.pick_player([("a", "Paused"), ("b", "Paused")], None) == "a", "no playing player should fall back to the first")
    check(mc.pick_player([], None) is None, "no players should give None")
    # Instance names (spotify.instance123) match their base name.
    check(mc.pick_player([("chromium.instance42", "Playing")], "chromium") == "chromium.instance42",
          "--player should match an instance-suffixed player name")


def check_popup_margin(mc) -> None:
    # Centred on the cursor, relative to the monitor.
    check(mc.popup_margin(4472, 3840, 1280, 300) == 632 - 150, "popup is not centred on the cursor")
    # Clamped to the monitor edges with a gap.
    check(mc.popup_margin(3845, 3840, 1280, 300) == mc.EDGE_GAP, "popup runs off the left edge")
    check(mc.popup_margin(3840 + 1278, 3840, 1280, 300) == 1280 - 300 - mc.EDGE_GAP, "popup runs off the right edge")
    # A monitor narrower than the popup still gives a non-negative margin.
    check(mc.popup_margin(100, 0, 200, 300) == 0, "too-narrow monitor should give margin 0")


def check_toggle(mc) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = pathlib.Path(tmp) / "mediacover.pid"
        check(mc.close_running(pidfile) is False, "no pidfile should mean nothing to close")

        pidfile.write_text("not a pid")
        check(mc.close_running(pidfile) is False and not pidfile.exists(), "garbage pidfile should be removed")

        # A live process that is not mediacover (reused pid) must survive.
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            pidfile.write_text(str(other.pid))
            check(mc.close_running(pidfile) is False, "a pid reused by another program must not count as a running popup")
            check(other.poll() is None, "close_running killed a process that is not mediacover")
        finally:
            other.kill()
            other.wait()

        dead = subprocess.Popen([sys.executable, "-c", "pass", "mediacover"])
        dead.wait()
        pidfile.write_text(str(dead.pid))
        check(mc.close_running(pidfile) is False and not pidfile.exists(), "stale pidfile should be removed")

        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "mediacover.py"])
        try:
            pidfile.write_text(str(live.pid))
            check(mc.close_running(pidfile) is True, "a running popup should be closed")
            try:
                live.wait(timeout=3)
            except subprocess.TimeoutExpired:
                fail("running popup did not exit after close_running")
            check(not pidfile.exists(), "pidfile should be removed after closing the popup")
        finally:
            if live.poll() is None:
                live.send_signal(signal.SIGKILL)
                live.wait()


def jsonc(path: pathlib.Path) -> dict:
    text = re.sub(r"^\s*//.*$", "", path.read_text(encoding="utf-8"), flags=re.M)
    return json.loads(text)


def check_menus() -> None:
    for module, menu, player_arg in (
        ("custom-mediaplayer.jsonc", "mediaplayer.xml", None),
        ("custom-spotify.jsonc", "spotify.xml", "spotify"),
    ):
        name, cfg = next(iter(jsonc(MODULES / module).items()))
        action = cfg.get("menu-actions", {}).get("cover", "")
        check("mediacover" in action, f"{name}: no 'cover' menu action running mediacover")
        if player_arg:
            check(f"--player {player_arg}" in action, f"{name}: cover action does not pass --player {player_arg}")
        else:
            check("--player" not in action, f"{name}: cover action should follow the active player")
        xml = (MENUS / menu).read_text(encoding="utf-8")
        check('id="cover"' in xml, f"{menu}: no menu item with id 'cover'")


def main() -> int:
    mc = load_module()
    check_art_path(mc)
    check_pick_player(mc)
    check_popup_margin(mc)
    check_toggle(mc)
    check_menus()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
