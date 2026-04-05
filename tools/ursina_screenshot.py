"""
WK21 — Capture the full Ursina/Panda3D window (3D scene + camera.ui overlay) to PNG.

Used by F12 in the Ursina viewer. Saves under docs/screenshots/ with a timestamp filename.
"""

from __future__ import annotations

import os
from datetime import datetime


def docs_screenshots_dir() -> str:
    """Absolute path to repo ``docs/screenshots/``."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "docs", "screenshots")


def save_ursina_window_screenshot(base) -> str | None:
    """
    Capture the main GraphicsWindow via ShowBase.screenshot (full composite view).

    :param base: ``ursina.application.base`` (Ursina / ShowBase instance)
    :returns: Path written as string, or None on failure
    """
    if base is None:
        print("[screenshot] Ursina ShowBase not available")
        return None

    out_dir = docs_screenshots_dir()
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"ursina_{ts}.png"
    filepath = os.path.join(out_dir, filename)

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
