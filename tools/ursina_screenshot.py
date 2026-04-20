"""
WK21 — Capture the full Ursina/Panda3D window (3D scene + camera.ui overlay) to PNG.

Used by F12 in the Ursina viewer. Default: ``docs/screenshots/ursina_<timestamp>.png``.

Optional environment (PowerShell examples)::

    $env:KINGDOM_SCREENSHOT_SUBDIR = "wk32_nature"
    python main.py --renderer ursina
    # F12 → docs/screenshots/wk32_nature/ursina_<timestamp>.png

    $env:KINGDOM_SCREENSHOT_STEM = "meadow"
    # F12 → .../meadow_<timestamp>.png

Subdir is constrained under ``docs/screenshots/`` (``..`` and absolute paths rejected).
"""

from __future__ import annotations

import os
from datetime import datetime


def docs_screenshots_dir() -> str:
    """Absolute path to repo ``docs/screenshots/`` (root for all captures)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "docs", "screenshots")


def screenshot_output_dir() -> str:
    """
    Effective output directory for F12 captures.

    If ``KINGDOM_SCREENSHOT_SUBDIR`` is set, files go under
    ``docs/screenshots/<subdir>/`` (nested segments allowed, e.g. ``wk32/nature``).
    Invalid values fall back to ``docs/screenshots/`` with a console warning.
    """
    root = os.path.abspath(docs_screenshots_dir())
    raw = os.environ.get("KINGDOM_SCREENSHOT_SUBDIR", "").strip()
    if not raw:
        return root

    parts: list[str] = []
    for segment in raw.replace("\\", "/").split("/"):
        seg = segment.strip()
        if not seg or seg in (".", ".."):
            continue
        parts.append(seg)
    if not parts:
        return root

    out = os.path.abspath(os.path.join(root, *parts))
    if out != root and not out.startswith(root + os.sep):
        print("[screenshot] KINGDOM_SCREENSHOT_SUBDIR must stay under docs/screenshots; using root")
        return root
    return out


def _screenshot_filename_stem() -> str:
    """Filename prefix from ``KINGDOM_SCREENSHOT_STEM`` or default ``ursina``."""
    stem = os.environ.get("KINGDOM_SCREENSHOT_STEM", "").strip()
    if not stem:
        return "ursina"
    # One path segment only — avoid weird filenames
    safe = stem.replace("\\", "/").split("/")[-1].strip()
    if not safe or safe in (".", ".."):
        return "ursina"
    for ch in '<>:"|?*':
        safe = safe.replace(ch, "_")
    return safe[:120] if len(safe) > 120 else safe


def build_screenshot_filepath() -> str:
    """Full path for the next PNG using current env (same naming rules as F12)."""
    out_dir = screenshot_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    stem = _screenshot_filename_stem()
    return os.path.join(out_dir, f"{stem}_{ts}.png")


def next_auto_screenshot_path() -> str:
    """Absolute path for ``KINGDOM_URSINA_AUTO_SCREENSHOT_PATH`` and CLI wrappers."""
    return os.path.abspath(build_screenshot_filepath())


def next_auto_screenshot_path_for(
    *,
    subdir: str | None = None,
    stem: str | None = None,
) -> str:
    """
    Like ``next_auto_screenshot_path()`` but temporarily applies optional
    ``subdir`` / ``stem`` overrides (restores ``os.environ`` after).
    """
    keys = ("KINGDOM_SCREENSHOT_SUBDIR", "KINGDOM_SCREENSHOT_STEM")
    backup: dict[str, str | None] = {k: os.environ.get(k) for k in keys}
    try:
        if subdir is not None:
            os.environ["KINGDOM_SCREENSHOT_SUBDIR"] = subdir
        if stem is not None:
            if stem.strip():
                os.environ["KINGDOM_SCREENSHOT_STEM"] = stem.strip()
            else:
                os.environ.pop("KINGDOM_SCREENSHOT_STEM", None)
        return next_auto_screenshot_path()
    finally:
        for k in keys:
            v = backup.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def save_ursina_window_screenshot(base) -> str | None:
    """
    Capture the main GraphicsWindow via ShowBase.screenshot (full composite view).

    :param base: ``ursina.application.base`` (Ursina / ShowBase instance)
    :returns: Path written as string, or None on failure
    """
    if base is None:
        print("[screenshot] Ursina ShowBase not available")
        return None

    filepath = build_screenshot_filepath()

    try:
        # defaultFilename=False: namePrefix is the full path including extension
        # defaultFilename=0: namePrefix is the full output path (see ShowBase.screenshot).
        result = base.screenshot(namePrefix=filepath, defaultFilename=0)
        if result:
            out = str(result)
            print(f"[screenshot] Saved: {out}")
            return out
        print(f"[screenshot] Failed (no path returned): {filepath}")
        return None
    except Exception as e:
        print(f"[screenshot] Failed: {e}")
        return None


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
