"""theme.import.py's fzf list marks already-installed themes with a leading,
colored checkmark (INSTALLED_PREFIX) so "More Themes" shows what's already
there without repeating a text label on every row.

fzf's --ansi (needed to render that color at all) STRIPS the SGR escape
codes out of every value it hands back via `{}` -- both the live preview
substitution and the final selected-line output on stdout -- keeping only
the glyph. A first version of this marker stripped the wrong thing: it
matched the *colored* prefix, which fzf's `{}` never actually contains, so
every installed theme's JSON lookup silently failed and its preview (and
its confirm-time selection) broke while not-installed themes -- whose
prefix is plain spaces with nothing for --ansi to strip -- kept working.
That's the actual shape of the bug this file exists to catch: it must
assert the JSON lookup *succeeds* with fzf's real, already-stripped output,
not just that the script doesn't crash on it.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", "."))
SCRIPT_PATH = REPO_ROOT / "Configs/.local/lib/hyde/theme.import.py"
INSTALLED_GLYPH = "✓ "  # what fzf's {} substitution actually contains
INSTALLED_PREFIX = f"\033[32m{INSTALLED_GLYPH}\033[0m"  # what's fed to fzf for display
NOT_INSTALLED_PREFIX = "  "

failures = 0


def check(condition: bool, message: str) -> None:
    global failures
    if not condition:
        failures += 1
        print(f"    fail: {message}")


def run_preview(cache_home: pathlib.Path, theme_arg: str):
    env = dict(os.environ)
    env["XDG_CACHE_HOME"] = str(cache_home)
    env["LOG_LEVEL"] = "debug"  # so the resolved theme name shows up on stderr
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--skip-clone", "--preview", theme_arg],
        capture_output=True,
        text=True,
        env=env,
    )


def check_resolves(cache_home: pathlib.Path, theme_arg: str, label: str) -> None:
    result = run_preview(cache_home, theme_arg)
    check(
        "AttributeError" not in result.stderr,
        f"--preview with {label} crashed: {result.stderr}",
    )
    check(
        "Theme: Vesper" in result.stderr,
        f"--preview with {label} did not resolve to the fixture theme "
        f"(the JSON lookup used an unstripped/mangled name): stderr={result.stderr!r}",
    )
    check(
        "Theme not found in gallery data" not in result.stderr,
        f"--preview with {label} hit the not-found path instead of matching Vesper: "
        f"stderr={result.stderr!r}",
    )


def main() -> int:
    with __import__("tempfile").TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        # Matches theme.import.py's own CLONE_DIR: os.path.join(XDG_CACHE_HOME, "hyde/gallery-database")
        clone_dir = tmp_path / "hyde" / "gallery-database"
        clone_dir.mkdir(parents=True)
        (clone_dir / "hyde-themes.json").write_text(
            json.dumps(
                [
                    {
                        "THEME": "Vesper",
                        "LINK": "https://example.invalid/vesper",
                        "OWNER": "someone",
                        "DESCRIPTION": "test fixture",
                        "COLORSCHEME": ["#111111", "#222222"],
                    }
                ]
            )
        )

        # The real case: fzf's --ansi already stripped the color codes, so
        # only the bare glyph reaches the script. This is what broke.
        check_resolves(tmp_path, INSTALLED_GLYPH + "Vesper", "the ansi-stripped glyph (real fzf output)")

        # Defensive: also handle the colored form if it's ever passed directly.
        check_resolves(tmp_path, INSTALLED_PREFIX + "Vesper", "the still-colored prefix")

        # A not-installed theme carries the blank alignment prefix instead.
        check_resolves(tmp_path, NOT_INSTALLED_PREFIX + "Vesper", "the not-installed prefix")

        # Sanity check: a genuinely unknown theme is the actual not-found
        # path, not a crash -- distinguishes "the lookup works" above from
        # "the script never crashes on anything".
        result_unknown = run_preview(tmp_path, "DoesNotExist")
        check(
            "AttributeError" not in result_unknown.stderr,
            f"an unknown theme name should print 'not found', not crash: {result_unknown.stderr}",
        )
        check(
            "Theme not found in gallery data" in result_unknown.stderr,
            f"an unknown theme name should hit the not-found path: stderr={result_unknown.stderr!r}",
        )
        # The whole point of the not-found path: fzf's preview pane shows
        # get_theme_preview()'s return value, not just a debug log the user
        # never sees. main() used to discard it, leaving the pane blank.
        check(
            "Image preview not found for DoesNotExist" in result_unknown.stdout,
            f"an unknown theme name should say so on stdout (what the fzf "
            f"preview pane actually shows), not just in the debug log: "
            f"stdout={result_unknown.stdout!r}",
        )

    # Gallery data unavailable entirely (no hyde-themes.json -- a fresh
    # machine with --skip-clone, or a failed clone): JSON_DATA stays None,
    # and iterating it directly raises TypeError before the not-found
    # fallback ever runs.
    with __import__("tempfile").TemporaryDirectory() as tmp_no_json:
        tmp_no_json_path = pathlib.Path(tmp_no_json)
        (tmp_no_json_path / "hyde" / "gallery-database").mkdir(parents=True)
        result_no_data = run_preview(tmp_no_json_path, "Anything")
        check(
            "TypeError" not in result_no_data.stderr,
            f"--preview with no gallery data crashed instead of reporting not-found: "
            f"{result_no_data.stderr}",
        )
        check(
            result_no_data.returncode == 0,
            f"--preview with no gallery data exited {result_no_data.returncode}: {result_no_data.stderr}",
        )
        check(
            "Image preview not found for Anything" in result_no_data.stdout,
            f"missing gallery data should say so on stdout, not just avoid crashing: "
            f"stdout={result_no_data.stdout!r}",
        )

    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
