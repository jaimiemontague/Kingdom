"""
Small synchronous screenshot helper for standalone Ursina tools.

Unlike ShowBase.screenshot(), this writes the framebuffer immediately so tools can
save a PNG and quit in the same frame for visual review loops.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_tool_screenshot_path(
    *,
    subdir: str | None,
    stem: str | None,
) -> str:
    from tools.ursina_screenshot import next_auto_screenshot_path_for

    return next_auto_screenshot_path_for(
        subdir=(subdir or None),
        stem=(stem or None),
    )


def save_window_screenshot_sync(base: Any, out_path: str) -> bool:
    try:
        from panda3d.core import Filename, PNMImage

        if base is None or getattr(base, "win", None) is None:
            print("[tool-screenshot] No Ursina window available")
            return False
        try:
            base.graphicsEngine.renderFrame()
            base.graphicsEngine.renderFrame()
        except Exception:
            pass

        out_abs = os.path.abspath(out_path)
        out_dir = os.path.dirname(out_abs)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        tex = base.win.getScreenshot()
        if tex is None:
            print("[tool-screenshot] getScreenshot returned None")
            return False
        img = PNMImage()
        if not tex.store(img):
            print("[tool-screenshot] Texture.store failed")
            return False
        ok = bool(img.write(Filename.fromOsSpecific(out_abs)))
        if ok:
            print(f"[tool-screenshot] Saved: {out_abs}")
        return ok
    except Exception as exc:
        print(f"[tool-screenshot] Failed: {exc}")
        return False


def install_auto_capture(
    *,
    app: Any,
    seconds: float,
    out_path: str | None,
    quit_after: bool = True,
) -> None:
    if seconds <= 0:
        return

    def _capture(task):
        from ursina import application

        if out_path:
            save_window_screenshot_sync(application.base, out_path)
        if quit_after:
            try:
                application.quit()
            except Exception:
                pass
        return task.done

    try:
        app.taskMgr.doMethodLater(float(seconds), _capture, "kingdom_tool_auto_capture")
    except Exception as exc:
        print(f"[tool-screenshot] Could not install auto capture: {exc}")
