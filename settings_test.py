"""Behaviour checks for settings; temporary data only, no real tools launched."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
                      XDG_CURRENT_DESKTOP="Hyprland")
    s.APP_ID += ".Tests"
    s.load_gtk()
    assert s.Gtk.init_check()[0], "Xvfb display is unavailable"


class Logic(unittest.TestCase):
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
        for entry in s.ENTRIES:
            self.assertIn(entry.category, s.CATEGORIES)
            self.assertTrue(entry.target)
            if not entry.desktop:
                self.assertEqual(s.hyde_command(entry)[:6], ["hyde-shell", "app", "-t", "scope", "--", "hyde-shell"])
                candidates = [ROOT / "Configs/.local/lib/hyde" / (entry.target[0] + ext) for ext in (".sh", ".lua", ".py")]
                self.assertTrue(any(p.exists() for p in candidates), entry.target)

    def test_xdg(self):
        for value in ("", "relative/path"):
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": value}):
                self.assertEqual(s.xdg_path("XDG_CONFIG_HOME", ".config"), Path.home() / ".config")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/a b"}):
            self.assertEqual(s.xdg_path("XDG_CONFIG_HOME", ".config"), Path("/tmp/a b"))

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
        self.path.write_text('@import "palette.css";\n@define-color main-fg alpha(@wb-act-fg, 0.8);')
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
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nHidden=true\n')
        self.assertIsNone(resolved(False))
        path.write_text('[Desktop Entry]\nType=Application\nName=Test Tool\nExec=/bin/true\nTryExec=/does/not/exist\n')
        self.assertIsNone(s.desktop_info(entry))
        path.write_text('not a desktop entry')
        self.assertIsNone(s.desktop_info(entry))

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
