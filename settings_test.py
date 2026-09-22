"""Behaviour checks for settings; temporary data only, no real tools launched."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="gi.events")
from unittest.mock import patch, Mock

ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[1]))
SCRIPT = ROOT / "Configs/.local/lib/hyde/settings.py"
spec = importlib.util.spec_from_file_location("hyde_settings", SCRIPT)
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)
GTK = "--gtk" in sys.argv
if GTK:
    sys.argv.remove("--gtk")
    # Set before importing GIO: it caches the XDG directories for the process.
    temp_home = tempfile.TemporaryDirectory()
    os.environ.update(HOME=temp_home.name, XDG_CONFIG_HOME=temp_home.name + "/config",
                      XDG_DATA_HOME=temp_home.name + "/data", XDG_DATA_DIRS=temp_home.name + "/system:/usr/share",
                      XDG_CURRENT_DESKTOP="Hyprland",
                      # xdg_path() falls back to a set XDG_STATE_HOME verbatim (never
                      # to $HOME); an ambient real value here would make tests read
                      # and write the real user's ~/.local/state/hyde/config (#found
                      # via test_window_and_live_reload writing a real category).
                      XDG_STATE_HOME=temp_home.name + "/state")
    s.APP_ID += ".Tests"
    s.load_gtk()
    assert s.Gtk.init_check()[0], "Xvfb display is unavailable"


class Logic(unittest.TestCase):
    def test_readable_foreground(self):
        # Real Waybar theme values that prompted this (main-fg on main-bg,
        # both translucent): 4.44:1 against a light desktop background,
        # below the 4.5:1 body-text floor -- despite 7.15:1 against a dark one.
        main_bg = (21 / 255, 10 / 255, 9 / 255, 0.8)
        main_fg = (240 / 255, 176 / 255, 170 / 255, 0.8)
        fixed = s.readable_foreground(main_fg, main_bg)
        self.assertEqual(fixed[3], 1.0)
        self.assertEqual(fixed[:3], main_fg[:3])
        for backdrop in ((0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)):
            bg_over = s._composite(main_bg, backdrop)
            fg_over = s._composite(fixed, (*bg_over, 1.0))
            self.assertGreaterEqual(s._contrast_ratio(fg_over, bg_over), 4.5)

        # already-safe pair: untouched, not just "still passes"
        safe_fg, safe_bg = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)
        self.assertEqual(s.readable_foreground(safe_fg, safe_bg), safe_fg)

        # boundary: exactly opaque black-on-white must not be altered or crash
        self.assertEqual(s.readable_foreground((0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)), (0.0, 0.0, 0.0, 1.0))

        # degenerate: fully transparent background (alpha 0) must not divide by zero
        result = s.readable_foreground((0.5, 0.5, 0.5, 0.5), (0.1, 0.1, 0.1, 0.0))
        self.assertEqual(len(result), 4)

        # known limit: even opaque, this theme's hover hues can't reach 4.5:1 --
        # readable_foreground only removes alpha as a variable, it never invents
        # a new hue (this app deliberately never overrides a theme's own colours).
        hvr_fg, hvr_bg = (240 / 255, 176 / 255, 170 / 255, 0.8), (125 / 255, 80 / 255, 75 / 255, 0.4)
        fixed_hvr = s.readable_foreground(hvr_fg, hvr_bg)
        self.assertEqual(fixed_hvr[:3], hvr_fg[:3])
        self.assertLess(s._contrast_ratio(fixed_hvr[:3], hvr_bg[:3]), 4.5)

    def test_search(self):
        display = s.ENTRIES[1]
        for query in ("", "  ", "MONITOR", "Ｂｉｌｄｓｃｈｉｒｍ", "display scaling", "\tmonitor\n"):
            with self.subTest(query=query):
                self.assertTrue(s.matches(display, query))
        for query in ("scanner", "monitor scanner", "'$(touch /tmp/never)'", "x" * 100000, "\x00", "🦄"):
            with self.subTest(query=query):
                self.assertFalse(s.matches(display, query))
        self.assertTrue(s.matches(s.ENTRIES[0], "lautstärke"))

    def test_catalog(self):
        self.assertEqual(len(s.ENTRIES), len({(e.category, e.title) for e in s.ENTRIES}))
        shipped_desktop_dir = ROOT / "Configs/.local/share/applications"
        with (ROOT / "Scripts/dots/hyde.toml").open("rb") as f:
            dots = tomllib.load(f)
        deployed_paths = set()
        for block in dots.get("hyde", {}).get("files", []):
            paths = block.get("paths", [])
            deployed_paths.update([paths] if isinstance(paths, str) else paths)
        for entry in s.ENTRIES:
            self.assertIn(entry.category, s.CATEGORIES)
            self.assertTrue(entry.target)
            if not entry.desktop:
                self.assertEqual(s.hyde_command(entry)[:6], ["hyde-shell", "app", "-t", "scope", "--", "hyde-shell"])
                candidates = [ROOT / "Configs/.local/lib/hyde" / (entry.target[0] + ext) for ext in (".sh", ".lua", ".py")]
                self.assertTrue(any(p.exists() for p in candidates), entry.target)
            elif (shipped_desktop_dir / entry.target[0]).exists():
                # HyDE ships this desktop file itself instead of relying on a
                # system package's -- keep it in sync with its Entry target.
                content = (shipped_desktop_dir / entry.target[0]).read_text()
                self.assertIn("Type=Application", content)
                self.assertRegex(content, r"(?m)^Exec=\S")
                # Shipping the file in the repo isn't enough -- the installer
                # has to actually deploy it, or it never reaches a real install.
                self.assertIn(f"applications/{entry.target[0]}", deployed_paths,
                              f"{entry.target[0]} is shipped but not deployed by Scripts/dots/hyde.toml")

    def test_default_apps_targets_a_standalone_tool(self):
        # org.kde.keditfiletype.desktop's Exec=keditfiletype needs a mimetype
        # argv it never gets from a bare launch -- it just prints --help and
        # exits without opening anything. kcmshell6 filetypes is the actual
        # standalone GUI, so the entry ships its own shim pointing at that.
        entry = next(e for e in s.ENTRIES if e.title == "Default apps")
        self.assertEqual(entry.target, ("hyde-default-apps.desktop",))
        path = ROOT / "Configs/.local/share/applications" / entry.target[0]
        content = path.read_text()
        self.assertIn("Exec=hyde-shell app -t scope -- kcmshell6 filetypes", content)
        # Without TryExec, GIO only checks that hyde-shell (the outer command)
        # resolves -- kcmshell6 itself (kde-cli-tools) could be missing and
        # this entry would still show as available, then silently do nothing.
        self.assertIn("TryExec=kcmshell6", content)

    def test_font_manager_desktop_id(self):
        # font-manager ships its .desktop under a reverse-DNS id; the plain
        # "font-manager.desktop" name resolves to nothing on any system.
        entry = next(e for e in s.ENTRIES if e.title == "Font manager")
        self.assertEqual(entry.target, ("com.github.FontManager.FontManager.desktop",))

    def test_firewall_targets_a_wayland_safe_tool(self):
        # gufw's Exec=gufw re-execs its whole GTK GUI as root via pkexec,
        # which loses WAYLAND_DISPLAY/XAUTHORITY and never opens a window on
        # Wayland/XWayland, even after a successful polkit auth. plasma-
        # firewall's KCM authorizes individual ufw actions via KAuth/Polkit
        # instead, so the entry ships its own shim pointing at that.
        entry = next(e for e in s.ENTRIES if e.title == "Firewall")
        self.assertEqual(entry.target, ("hyde-firewall.desktop",))
        path = ROOT / "Configs/.local/share/applications" / entry.target[0]
        content = path.read_text()
        self.assertIn("Exec=hyde-shell app -t scope -- kcmshell6 firewall", content)
        # Without TryExec, GIO only checks that hyde-shell (the outer command)
        # resolves -- kcmshell6 itself (kde-cli-tools) could be missing and
        # this entry would still show as available, then silently do nothing.
        self.assertIn("TryExec=kcmshell6", content)
        self.assertEqual(s.PACKAGES["Firewall"], "plasma-firewall")

    def test_xdg(self):
        for value in ("", "relative/path"):
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": value}):
                self.assertEqual(s.xdg_path("XDG_CONFIG_HOME", ".config"), Path.home() / ".config")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/a b"}):
            self.assertEqual(s.xdg_path("XDG_CONFIG_HOME", ".config"), Path("/tmp/a b"))

    def test_user_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_STATE_HOME": tmp}):
            # missing input
            self.assertEqual(s.read_user_state("NOPE"), "")

            s.write_user_state("PLAIN", "Bielefeld")
            self.assertEqual(s.read_user_state("PLAIN"), "Bielefeld")

            # malformed/out-of-spec values a geocoding API could plausibly send:
            # quotes, an apostrophe, backticks, a command substitution, a
            # backslash. The regression this guards: these used to go straight
            # into export KEY="value" unescaped, so sourcing the file executed
            # them.
            for value in (
                'Bielefeld, "Germany"',
                "O'Brien's Town",
                "$(touch /tmp/hyde-settings-test-pwned)",
                "`id`",
                "back\\slash",
            ):
                s.write_user_state("PLACE", value)
                self.assertEqual(s.read_user_state("PLACE"), value)

                result = subprocess.run(
                    ["bash", "-c", f'source "{s.user_state_path()}" && printf %s "$PLACE"'],
                    capture_output=True, text=True, timeout=3, check=True,
                )
                self.assertEqual(result.stdout, value)
            self.assertFalse(Path("/tmp/hyde-settings-test-pwned").exists())

            # boundary: empty string
            s.write_user_state("EMPTY", "")
            self.assertEqual(s.read_user_state("EMPTY"), "")

            # a newline can't survive the line-based reader; collapsed, not corrupted
            s.write_user_state("MULTILINE", "line one\nline two")
            self.assertEqual(s.read_user_state("MULTILINE"), "line one line two")

            # overwrite replaces, doesn't duplicate, and leaves sibling keys alone
            s.write_user_state("PLAIN", "Rewritten")
            self.assertEqual(s.read_user_state("PLAIN"), "Rewritten")
            contents = s.user_state_path().read_text()
            self.assertEqual(contents.count("PLAIN="), 1)
            self.assertEqual(s.read_user_state("EMPTY"), "")

    def test_user_state_survives_config_regeneration(self):
        # The bug this guards: settings.py used to persist into
        # $XDG_STATE_HOME/hyde/config, the exact file config.lua fully
        # rewrites from config.toml on every change/restart -- silently
        # dropping the saved category and weather location. staterc is
        # never touched by that regeneration.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_STATE_HOME": tmp}):
            s.write_user_state("HYDE_SETTINGS_LAST_CATEGORY", "Displays")
            generated_config = Path(tmp) / "hyde/config"
            generated_config.parent.mkdir(parents=True, exist_ok=True)
            generated_config.write_text("export SOME_OTHER_VAR=1\n")  # config.lua's full rewrite
            self.assertEqual(s.read_user_state("HYDE_SETTINGS_LAST_CATEGORY"), "Displays")
            self.assertNotEqual(s.user_state_path(), generated_config)

    def test_weather_location_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            # missing file entirely
            self.assertEqual(s.read_weather_location(), "")

            # no [weather] section yet -- must create one, not crash
            (Path(tmp) / "hyde").mkdir(parents=True)
            config_path = s.config_toml_path()
            config_path.write_text('"$schema" = "https://example/schema.json"\n\n[desktop.app]\nbrowser = "brave"\n')
            s.write_weather_location("52.0302,8.5325")
            self.assertEqual(s.read_weather_location(), "52.0302,8.5325")
            # sibling section untouched
            self.assertIn('browser = "brave"', config_path.read_text())

            # existing key gets replaced in place, not duplicated
            s.write_weather_location("1.0,2.0")
            self.assertEqual(s.read_weather_location(), "1.0,2.0")
            self.assertEqual(config_path.read_text().count("location ="), 1)

            # a section AFTER [weather] must survive the in-place edit
            config_path.write_text(config_path.read_text() + "\n[gaming]\nfoo = 1\n")
            s.write_weather_location("3.0,4.0")
            self.assertEqual(s.read_weather_location(), "3.0,4.0")
            self.assertIn("[gaming]", config_path.read_text())
            self.assertIn("foo = 1", config_path.read_text())

            # boundary/malformed: quote and backslash in the value round-trip
            s.write_weather_location('weird",$(echo hi)')
            self.assertEqual(s.read_weather_location(), 'weird",$(echo hi)')
            # and never as live, unescaped TOML/shell content
            self.assertNotIn('weird",$(echo hi)"', config_path.read_text())

            # unreadable/empty config.toml: fail soft, don't crash
            config_path.write_text("")
            self.assertEqual(s.read_weather_location(), "")
            s.write_weather_location("5.0,6.0")
            self.assertEqual(s.read_weather_location(), "5.0,6.0")

    def test_failed_probes(self):
        for error in (FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("probe", 3), UnicodeError()):
            with patch.object(s.subprocess, "run", side_effect=error):
                self.assertEqual(s.command_output(["probe"]), "")
        with patch.object(s.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "invalid", "")):
            self.assertEqual(s.command_output(["probe"]), "")

    def test_missing_system_data(self):
        with patch.object(s, "read_text", return_value="garbage"), patch.object(s, "command_output", return_value="[]"), patch.object(s.shutil, "disk_usage", side_effect=PermissionError()):
            info = s.system_information()
        values = {name: value for _, name, value in info}
        self.assertEqual(values["RAM"], s.UNAVAILABLE)
        self.assertEqual(values["GPU"], s.UNAVAILABLE)
        self.assertEqual(values["Hyprland"], s.UNAVAILABLE)
        self.assertTrue(all(isinstance(v, str) and v for _, _, v in info))

    def test_system_parsing(self):
        def read(path):
            return {"/proc/meminfo": "MemTotal:       8388608 kB", "/proc/cpuinfo": "model name : Test CPU\n"}.get(path, "")
        def command(argv):
            return '00:02.0 VGA compatible controller: Intel Test\n01:00.0 3D controller: NVIDIA Test' if argv[0] == "lspci" else '{"version": "0.test"}'
        with patch.object(s, "read_text", side_effect=read), patch.object(s, "command_output", side_effect=command):
            info = s.system_information()
        values = {name: value for _, name, value in info}
        self.assertEqual(values["RAM"], "8.0 GiB")
        self.assertEqual(values["CPU"], "Test CPU")
        self.assertEqual(values["GPU"], "Intel Test\nNVIDIA Test")
        self.assertEqual(values["Hyprland"], "0.test")
        self.assertNotIn("Serial", s.information_text(info))
        self.assertEqual(s.size_text(-1), s.UNAVAILABLE)
        self.assertEqual(s.size_text(0), "0.0 GiB")

    def test_account_overview(self):
        def record(name="alice", gecos="Alice Example,,,", uid=1000, gid=100, home="/home/alice", shell="/bin/bash"):
            return type("Record", (), {"pw_name": name, "pw_gecos": gecos, "pw_uid": uid, "pw_gid": gid, "pw_dir": home, "pw_shell": shell})()

        def group(name, members):
            return type("Group", (), {"gr_name": name, "gr_mem": members})()

        with patch.object(s.pwd, "getpwuid", return_value=record()), \
             patch.object(s.grp, "getgrgid", return_value=group("users", [])), \
             patch.object(s.grp, "getgrall", return_value=[group("wheel", ["alice"]), group("users", [])]):
            rows = dict(s.account_overview())
        self.assertEqual(rows["Username"], "alice")
        self.assertEqual(rows["Full name"], "Alice Example")
        self.assertEqual(rows["Groups"], "users, wheel")

        # missing: UID has no passwd entry (e.g. a container/sandbox with a bare UID)
        with patch.object(s.pwd, "getpwuid", side_effect=KeyError()):
            self.assertEqual(s.account_overview(), [])

        # malformed: empty gecos field falls back to the username
        with patch.object(s.pwd, "getpwuid", return_value=record(gecos="")), \
             patch.object(s.grp, "getgrgid", return_value=group("users", [])), \
             patch.object(s.grp, "getgrall", return_value=[]):
            rows = dict(s.account_overview())
        self.assertEqual(rows["Full name"], "alice")

        # boundary: primary group id does not resolve (stale/broken NSS)
        with patch.object(s.pwd, "getpwuid", return_value=record(gid=31337)), \
             patch.object(s.grp, "getgrgid", side_effect=KeyError()), \
             patch.object(s.grp, "getgrall", return_value=[]):
            rows = dict(s.account_overview())
        self.assertEqual(rows["Primary group"], "31337")
        self.assertEqual(rows["Groups"], "31337")

        # boundary: no supplementary groups at all still lists the primary group
        with patch.object(s.pwd, "getpwuid", return_value=record()), \
             patch.object(s.grp, "getgrgid", return_value=group("users", [])), \
             patch.object(s.grp, "getgrall", return_value=[]):
            rows = dict(s.account_overview())
        self.assertEqual(rows["Groups"], "users")

    def test_set_hostname(self):
        with patch.object(s.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assertEqual(s.set_hostname("laptop"), (True, ""))
        with patch.object(s.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "Failed to set hostname: Invalid hostname 'a b'")):
            ok, detail = s.set_hostname("a b")
            self.assertFalse(ok)
            self.assertIn("Invalid hostname", detail)
        for error in (FileNotFoundError(2, "No such file or directory"), subprocess.TimeoutExpired("hostnamectl", 120)):
            with self.subTest(error=error), patch.object(s.subprocess, "run", side_effect=error):
                ok, detail = s.set_hostname("x")
                self.assertFalse(ok)
                self.assertTrue(detail)
        # boundary: empty name -- hostnamectl itself rejects it, we just relay that
        with patch.object(s.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "Failed to set hostname: Invalid hostname ''")):
            ok, detail = s.set_hostname("")
            self.assertFalse(ok)

    def test_unreadable_and_oversized_data(self):
        with patch.object(Path, "open", side_effect=PermissionError()):
            self.assertEqual(s.read_text("/denied"), "")
        for value in ("-1", "abc", "9" * 5000):
            with patch.object(s, "read_text", return_value=f"MemTotal: {value} kB"), patch.object(s, "command_output", return_value=""):
                values = {name: data for _, name, data in s.system_information()}
                self.assertEqual(values["RAM"], s.UNAVAILABLE)

    def test_version_cache_is_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "executed"
            malicious = f"HYDE_VERSION='$(touch {marker})'"
            with patch.object(s, "read_text", return_value=malicious), patch.object(s, "command_output", return_value=""):
                values = {name: data for _, name, data in s.system_information()}
            self.assertEqual(values["HyDE"], f"$(touch {marker})")
            self.assertFalse(marker.exists())

    def test_cli(self):
        for args, status in ((["--help"], 0), (["--bad"], 2), (["unexpected"], 2), (["--system-info=bad"], 2)):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, status)
                self.assertNotIn("Traceback", result.stderr)
        env = dict(os.environ, DISPLAY="", WAYLAND_DISPLAY="", GDK_BACKEND="x11")
        result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


@unittest.skipUnless(GTK, "separate GTK integration run")
class GtkBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "theme.css"
        self.good = "\n".join(f"@define-color {role} #234567;" for role in s.COLORS)
        self.path.write_text(self.good)

    def tearDown(self):
        self.tmp.cleanup()

    def test_palette(self):
        self.assertIsNotNone(s.palette_provider(self.path))
        for css in ("", "@define-color main-bg red;", self.good + " invalid {", self.good.replace("#234567", "nonsense")):
            with self.subTest(css=css):
                self.path.write_text(css)
                with self.assertRaises((ValueError, s.GLib.Error)):
                    s.palette_provider(self.path)
        self.path.unlink()
        with self.assertRaises((ValueError, s.GLib.Error)):
            s.palette_provider(self.path)

    def test_imports_and_symbolic_colors(self):
        (self.path.parent / "palette.css").write_text(self.good)
        # wb-act-fg is overridden to white first: main-fg (same hue as main-bg in
        # `self.good`) would otherwise get its alpha rounded up to 1.0 by the
        # contrast safety net, which would swallow the "0.8" this test checks for.
        self.path.write_text('@import "palette.css";\n@define-color wb-act-fg #ffffff;\n@define-color main-fg alpha(@wb-act-fg, 0.8);')
        provider = s.palette_provider(self.path)
        self.assertIn("0.8", provider.to_string())
        (self.path.parent / "palette.css").unlink()
        with self.assertRaises((ValueError, s.GLib.Error)):
            s.palette_provider(self.path)

    def test_desktop_resolution(self):
        apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        path = apps / "hyde-test.desktop"
        entry = s.Entry("Test", "Test", "Test", "", (path.name,))
        self.assertIsNone(s.desktop_info(entry))
        def resolved(available):
            # GIO invalidates its desktop directory cache asynchronously.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                while s.GLib.MainContext.default().iteration(False):
                    pass
                app = s.desktop_info(entry)
                if bool(app) == available:
                    return app
                time.sleep(0.01)
            self.fail("Desktop cache did not converge after a filesystem change")
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true "two words"\n')
        self.assertEqual(resolved(True).get_display_name(), "Test Tool")
        # NoDisplay/OnlyShowIn gate a generic desktop menu, not whether a tool
        # this hub deliberately picked cross-desktop can be launched (#xfce4-power-manager
        # silently reporting "not installed" despite OnlyShowIn=XFCE on Hyprland).
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nNoDisplay=true\n')
        self.assertEqual(resolved(True).get_display_name(), "Test Tool")
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nOnlyShowIn=SomeOtherDesktop;\n')
        self.assertEqual(resolved(True).get_display_name(), "Test Tool")
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nHidden=true\n')
        self.assertIsNone(resolved(False))
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nTryExec=/does/not/exist\n')
        self.assertIsNone(s.desktop_info(entry))
        path.write_text('not a desktop entry')
        self.assertIsNone(s.desktop_info(entry))

    def test_entry_detail_ignores_session_locale(self):
        # get_display_name() honours the session locale (e.g. LANG=de_DE
        # returning a desktop file's Name[de]), which would leak non-English
        # text into this hub's otherwise all-English detail line.
        apps = Path(os.environ["XDG_DATA_HOME"]) / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        path = apps / "hyde-locale-test.desktop"
        path.write_text('[Desktop Entry]\nType=Application\nName=Right Name\nExec=/bin/true\n')
        entry = s.Entry("Test", "Locale Test", "Test", "computer-symbolic", (path.name,))
        deadline = time.monotonic() + 2
        app = None
        while time.monotonic() < deadline:
            while s.GLib.MainContext.default().iteration(False):
                pass
            app = s.desktop_info(entry)
            if app:
                break
            time.sleep(0.01)
        self.assertIsNotNone(app)
        gtk_app = s.create_application()
        gtk_app.content = s.Gtk.Box()
        with patch.object(type(app), "get_display_name", return_value="Wrong Localized Name"):
            gtk_app.add_entry(entry)
        button = gtk_app.content.get_children()[0].get_children()[0]
        accessible_name = button.get_accessible().get_name()
        self.assertIn("Opens Right Name", accessible_name)
        self.assertNotIn("Wrong Localized Name", accessible_name)

    def test_launch_failures(self):
        app = s.create_application()
        button, message = s.Gtk.Button(), s.Gtk.Label()
        with patch.object(s, "desktop_info", return_value=None):
            app.launch(button, s.ENTRIES[0], message)
        self.assertIn("no longer available", message.get_text())
        self.assertTrue(message.get_visible())
        with patch.object(s.Gio.Subprocess, "new", side_effect=s.GLib.Error("missing executable")):
            app.launch(button, next(e for e in s.ENTRIES if not e.desktop), message)
        self.assertIn("Could not open", message.get_text())
        failed = Mock()
        failed.wait_check_finish.side_effect = s.GLib.Error("exit 1")
        app.launch_finished(failed, None, (button, message))
        self.assertTrue(button.get_sensitive())
        self.assertIn("exited with an error", message.get_text())
        success = Mock()
        app.launch_finished(success, None, (button, message))
        self.assertTrue(button.get_sensitive())

    def test_palette_permission_failure(self):
        with patch.object(s.Gtk.CssProvider, "load_from_path", side_effect=s.GLib.Error("Permission denied")):
            with self.assertRaises(s.GLib.Error):
                s.palette_provider(self.path)

    def test_last_category_restored_on_cold_start(self):
        # A saved category is honoured...
        with patch.object(s, "read_user_state", return_value="Displays"):
            app = s.create_application()
        self.assertEqual(app.category, "Displays")
        # ...but a stale/unknown one (renamed/removed category) falls back safely
        # instead of crashing on nav.get_row_at_index() during do_activate().
        with patch.object(s, "read_user_state", return_value="Not A Real Category"):
            app = s.create_application()
        self.assertEqual(app.category, s.CATEGORIES[0])
        written = {}
        with patch.object(s, "read_user_state", return_value=""), \
             patch.object(s, "write_user_state", side_effect=written.__setitem__):
            app = s.create_application()
            app.theme_path = self.path
            # do_activate() only, not register()+activate(): this test doesn't need
            # real D-Bus registration, and a second GApplication on the session bus
            # in the same process broke test_window_and_live_reload's own register().
            app.do_activate()
            try:
                app.nav.select_row(app.nav.get_row_at_index(1))
            finally:
                app.window.destroy()
        self.assertEqual(written.get("HYDE_SETTINGS_LAST_CATEGORY"), "Displays")

    def test_category_switch_survives_unwritable_state(self):
        # The bug this guards: write_user_state() used to raise straight out
        # of category_changed() on a full disk/unwritable state dir, which
        # ran between updating self.category and calling render() -- so the
        # sidebar selection changed but the content pane never caught up
        # (stayed on the old category, or blank on first activation).
        app = s.create_application()
        app.theme_path = self.path
        # A genuinely unwritable state path (not a mocked stand-in for one):
        # staterc's parent directory already exists as a plain file, so
        # mkdir(parents=True) raises a real OSError.
        blocked_state_home = Path(tempfile.mkdtemp())
        (blocked_state_home / "hyde").write_text("not a directory")
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(blocked_state_home)}):
            app.do_activate()
            try:
                target_index = next(i for i, c in enumerate(s.CATEGORIES) if c != app.category)
                app.nav.select_row(app.nav.get_row_at_index(target_index))
                self.assertEqual(app.category, s.CATEGORIES[target_index])
                headings = [c for c in app.content.get_children() if "heading" in c.get_style_context().list_classes()]
                self.assertTrue(headings, "render() did not run after the persistence failure")
                self.assertEqual(headings[0].get_text(), s.CATEGORIES[target_index])
            finally:
                app.window.destroy()

    def test_window_and_live_reload(self):
        app = s.create_application()
        app.theme_path = self.path
        app.register(None)
        app.activate()
        def drain(seconds=0.1):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while s.GLib.MainContext.default().iteration(False):
                    pass
                time.sleep(0.005)
        try:
            drain()
            self.assertEqual(app.category, "Audio")
            original = app.palette.to_string()
            self.path.write_text("@define-color main-bg red;")
            app.reload_theme()
            self.assertEqual(app.palette.to_string(), original)
            self.path.unlink()
            app.reload_theme()
            self.assertEqual(app.palette.to_string(), original)
            self.path.write_text(self.good)
            app.reload_theme()
            self.assertEqual(app.notice.get_text(), "")
            app.nav.select_row(app.nav.get_row_at_index(1))
            self.assertEqual(app.category, "Displays")
            app.search.set_text("drucker")
            drain(0.25)
            self.assertEqual(app.content.get_children()[0].get_text(), "Search results")
            self.assertEqual(app.content.get_children()[1].get_text(), "1 result")
            self.path.write_text("broken css")
            drain(0.4)
            self.assertEqual(app.palette.to_string(), original)
            self.assertIn("Keeping previous", app.notice.get_text())
            replacement = self.path.with_suffix(".tmp")
            replacement.write_text(self.good.replace("#234567", "#abcdef"))
            replacement.replace(self.path)
            drain(0.4)
            self.assertNotEqual(app.palette.to_string(), original)
            self.assertEqual(app.search.get_text(), "drucker")
            self.assertEqual(app.category, "Displays")
            app.search.set_text("")
            drain(0.25)
            self.assertEqual(app.content.get_children()[0].get_text(), "Displays")
            # Every category can render without executing its associated tool.
            app.info = [("Hardware", "CPU", "<b>literal</b> " + "x" * 400)]
            for index, category in enumerate(s.CATEGORIES):
                app.nav.select_row(app.nav.get_row_at_index(index))
                drain()
                self.assertEqual(app.content.get_children()[0].get_text(), category)
            button = app.content.get_children()[1]
            app.copy_info(button)
            self.assertEqual(s.Gtk.Clipboard.get(s.Gdk.SELECTION_CLIPBOARD).wait_for_text(), s.information_text(app.info))
            app.search.set_text("no-match-" + "x" * 10000)
            drain(0.25)
            self.assertEqual(app.content.get_children()[1].get_text(), "0 results")
            event = Mock(state=s.Gdk.ModifierType.CONTROL_MASK, keyval=s.Gdk.KEY_f)
            self.assertTrue(app.key_press(None, event))
            event = Mock(state=0, keyval=s.Gdk.KEY_Escape)
            self.assertTrue(app.key_press(None, event))
            self.assertEqual(app.search.get_text(), "")
            for index in range(10):
                self.path.write_text(self.good.replace("#234567", f"#{index:06x}"))
                app.reload_theme()
            self.assertIn("rgb(0,0,9)", app.palette.to_string())
            app.window.resize(650, 420)
            drain()
            self.assertLessEqual(app.window.get_size()[0], 650)
            app.window.resize(960, 680)
            app.activate()
            self.assertEqual(len(app.get_windows()), 1)
            # Distinct semantic colours make the visual artifact reviewable.
            self.path.write_text("\n".join(f"@define-color {role} {value};" for role, value in zip(s.COLORS, ("#12211b", "#d5ebdf", "#285640", "#e1ffeb", "#244534", "#ffffff"))))
            app.reload_theme()
            app.nav.select_row(app.nav.get_row_at_index(4))
            drain(0.3)
            # Capture only the isolated test window, never the user's desktop.
            screenshot = s.Gdk.pixbuf_get_from_window(app.window.get_window(), 0, 0, *app.window.get_size())
            screenshot.savev("/tmp/hyde-settings-test.png", "png", [], [])
        finally:
            app.window.destroy()
            drain()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(GtkBehaviour if GTK else Logic)
    result = unittest.TextTestRunner(verbosity=2, warnings="ignore").run(suite)
    sys.exit(not result.wasSuccessful())
