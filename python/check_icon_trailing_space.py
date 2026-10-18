"""Guard against icon-only Waybar module formats with no trailing space.

A handful of Nerd Font glyphs HyDE's default modules use (the caffeine cup,
the media player drawer's previous/play-pause/next controls, and the eyecare
drawer's backlight icon) render wider than the logical advance width GTK
allocates them -- Pango reports their ink extent about 1.5x the logical
width at the bar's font size. With nothing after them, that overflow bleeds
into whichever module a layout places right after, which looked like
overlapping icons (#2206). `custom/hyprsunset`'s format already carries a
trailing space for the same reason; this check keeps the others in sync
with it instead of regressing silently on the next edit.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", "."))
MODULES_DIR = REPO_ROOT / "Configs" / ".local" / "share" / "waybar" / "modules"

COMMENT = re.compile(r"//.*")

# (file, module key) -> format must end in whitespace
MUST_END_IN_SPACE = {
    ("custom-caffeine.jsonc", "custom/caffeine"),
    ("group-eyecare.jsonc", "backlight#eyecare"),
    ("group-mediaplayer.jsonc", "custom/mediaplayer-play-pause"),
    ("group-mediaplayer.jsonc", "custom/mediaplayer-next"),
    ("group-mediaplayer.jsonc", "custom/mediaplayer-previous"),
}


def main() -> int:
    if not MODULES_DIR.is_dir():
        print(f"no waybar modules directory under {REPO_ROOT}", file=sys.stderr)
        return 1

    failures = 0
    for filename, module_key in sorted(MUST_END_IN_SPACE):
        path = MODULES_DIR / filename
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            failures += 1
            continue

        data = json.loads(COMMENT.sub("", text))
        fmt = data.get(module_key, {}).get("format", "")
        if not fmt or not fmt[-1].isspace():
            print(
                f"{path}: {module_key!r} format {fmt!r} does not end in a "
                "space, so its icon's ink can bleed into the next module (#2206)",
                file=sys.stderr,
            )
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
