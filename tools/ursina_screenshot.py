"""
WK21 — Capture the full Ursina/Panda3D window (3D scene + camera.ui overlay) to PNG.

WK67 Round A-2 (L9): the screenshot helpers moved verbatim into
``game.graphics.ursina_screenshot`` (sever the ``game/graphics -> tools`` runtime
import). This module is now a thin **re-export** so existing tools consumers
(``ursina_capture``, ``run_ursina_capture_once``, ``run_worker_scale_ursina_shot``, …)
keep importing these symbols from ``tools.ursina_screenshot`` unchanged. ``tools`` ->
``game`` is the allowed (non-circular) import direction. The game module's
``docs_screenshots_dir`` walks one directory deeper but resolves to the same repo
``docs/screenshots`` root.

Used by F12 in the Ursina viewer. Default: ``docs/screenshots/ursina_<timestamp>.png``.

Optional environment (PowerShell examples)::

    $env:KINGDOM_SCREENSHOT_SUBDIR = "wk32_nature"
    python main.py
    # (default renderer is Ursina) F12 → docs/screenshots/wk32_nature/ursina_<timestamp>.png

    $env:KINGDOM_SCREENSHOT_STEM = "meadow"
    # F12 → .../meadow_<timestamp>.png

Subdir is constrained under ``docs/screenshots/`` (``..`` and absolute paths rejected).
"""

from __future__ import annotations

from game.graphics.ursina_screenshot import (  # noqa: F401
    _screenshot_filename_stem,
    build_screenshot_filepath,
    docs_screenshots_dir,
    next_auto_screenshot_path,
    next_auto_screenshot_path_for,
    save_ursina_window_screenshot,
    screenshot_output_dir,
)


if __name__ == "__main__":
    root = docs_screenshots_dir()
    resolved = screenshot_output_dir()
    stem = _screenshot_filename_stem()
    print("Ursina screenshot helper - used in-game when you press F12 (see game/graphics/ursina_app.py).")
    print()
    print("Environment variables:")
    print("  KINGDOM_SCREENSHOT_SUBDIR   Subfolder under docs/screenshots/ (e.g. wk32_nature)")
    print("  KINGDOM_SCREENSHOT_STEM     Filename prefix (default: ursina)")
    print()
    print(f"docs/screenshots root: {root}")
    print(f"Resolved output dir:   {resolved}")
    print(f"Resolved filename stem:  {stem}_<timestamp>.png")
