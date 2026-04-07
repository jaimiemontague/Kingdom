"""
Display mode management for GameEngine.
"""
import os
from typing import TYPE_CHECKING

import pygame

from config import WINDOW_WIDTH, WINDOW_HEIGHT, GAME_TITLE

if TYPE_CHECKING:
    from game.engine import GameEngine


class DisplayManager:
    """Apply and coordinate runtime display mode changes."""

    def __init__(self, engine: "GameEngine"):
        self.engine = engine

    @staticmethod
    def apply_headless_ui_canvas_size(engine: "GameEngine", width: int, height: int) -> None:
        """Ursina viewer: resize the offscreen pygame HUD to match the Ursina window (1:1, no fixed 1080p stretch).

        ``engine.display_manager`` is normally None in this mode; this mirrors the surface/HUD
        updates from ``apply_settings`` without calling ``pygame.display.set_mode`` (SDL dummy).
        """
        if not getattr(engine, "headless_ui", False):
            return
        w = max(320, min(int(width), 7680))
        h = max(240, min(int(height), 4320))
        if w == int(getattr(engine, "window_width", 0)) and h == int(getattr(engine, "window_height", 0)):
            try:
                if engine.screen is not None and engine.screen.get_size() == (w, h):
                    return
            except Exception:
                pass

        engine.window_width = w
        engine.window_height = h
        engine.window_size = (w, h)

        engine.screen = pygame.Surface((w, h), pygame.SRCALPHA)
        engine._scaled_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        engine._pause_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        engine._pause_overlay.fill((0, 0, 0, 128))
        engine._view_surface = None
        engine._view_surface_size = (0, 0)

        if hasattr(engine, "hud"):
            engine.hud.screen_width = w
            engine.hud.screen_height = h
            if hasattr(engine.hud, "on_resize"):
                try:
                    engine.hud.on_resize(w, h)
                except Exception:
                    pass
        if hasattr(engine, "pause_menu") and hasattr(engine.pause_menu, "on_resize"):
            try:
                engine.pause_menu.on_resize(w, h)
            except Exception:
                pass
        if hasattr(engine, "build_catalog_panel") and hasattr(engine.build_catalog_panel, "on_resize"):
            try:
                engine.build_catalog_panel.on_resize(w, h)
            except Exception:
                pass
        if hasattr(engine, "building_list_panel") and hasattr(engine.building_list_panel, "on_resize"):
            try:
                engine.building_list_panel.on_resize(w, h)
            except Exception:
                pass
        if hasattr(engine, "dev_tools_panel") and hasattr(engine.dev_tools_panel, "on_resize"):
            try:
                engine.dev_tools_panel.on_resize(w, h)
            except Exception:
                pass
        if hasattr(engine, "building_panel"):
            try:
                engine.building_panel.screen_width = w
                engine.building_panel.screen_height = h
            except Exception:
                pass
        if hasattr(engine, "debug_panel"):
            try:
                engine.debug_panel.screen_width = w
                engine.debug_panel.screen_height = h
            except Exception:
                pass
        if hasattr(engine, "clamp_camera"):
            try:
                engine.clamp_camera()
            except Exception:
                pass

    def apply_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """
        Apply display mode settings (fullscreen/borderless/windowed).

        Args:
            display_mode: "fullscreen" | "borderless" | "windowed"
            window_size: (width, height) tuple for windowed mode. If None, uses current window_size.
        """
        engine = self.engine

        # Update state
        engine.display_mode = str(display_mode)
        if window_size is not None:
            engine.window_size = (int(window_size[0]), int(window_size[1]))

        # Skip event processing for a few frames after mode switches to avoid
        # rare SDL crash inside pygame.event.get() on Windows.
        try:
            engine._skip_event_processing_frames = 10
        except Exception:
            pass

        # Check for headless/dummy driver (safe fallback)
        # NOTE: Even with SDL_VIDEODRIVER=dummy, pygame.display.set_mode can return a Surface.
        # We must still set window_width/window_height (and preferably screen) so the engine can boot.
        driver = str(os.environ.get("SDL_VIDEODRIVER", "")).lower()

        # Get display info (dummy driver may report 0; fall back to configured defaults)
        info = pygame.display.Info()
        disp_w = int(getattr(info, "current_w", WINDOW_WIDTH) or WINDOW_WIDTH)
        disp_h = int(getattr(info, "current_h", WINDOW_HEIGHT) or WINDOW_HEIGHT)
        # Use desktop sizes when possible (avoids fullscreen staying at old window size)
        try:
            desktop_sizes = pygame.display.get_desktop_sizes()
            if desktop_sizes:
                disp_w, disp_h = int(desktop_sizes[0][0]), int(desktop_sizes[0][1])
        except Exception:
            pass

        # Clear forced window position when leaving borderless
        if display_mode != "borderless":
            os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            os.environ.pop("SDL_VIDEO_CENTERED", None)

        # Determine size and flags based on mode
        flags = 0
        desired_w = engine.window_size[0]
        desired_h = engine.window_size[1]

        if driver == "dummy":
            # Headless mode: keep it simple and deterministic-safe.
            # We still create a display surface so downstream code can query sizes.
            flags = 0
            display_mode = "windowed"

        if display_mode == "fullscreen":
            flags |= pygame.FULLSCREEN
            desired_w = disp_w
            desired_h = disp_h
        elif display_mode == "borderless":
            flags |= pygame.NOFRAME
            # Borderless uses desktop resolution
            desired_w = disp_w
            desired_h = disp_h
            # Center on larger displays; pin to origin when matching display resolution
            if desired_w == disp_w and desired_h == disp_h:
                os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
            else:
                os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        elif display_mode == "windowed":
            flags |= pygame.RESIZABLE
            # Use saved window_size
            desired_w = max(1, min(desired_w, disp_w))
            desired_h = max(1, min(desired_h, disp_h))
            # Center once to avoid pinned top-left on mode switch
            os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        else:
            # Unknown mode: default to windowed
            flags |= pygame.RESIZABLE

        # Apply display mode
        engine.window_width = int(desired_w)
        engine.window_height = int(desired_h)
        engine.screen = pygame.display.set_mode((engine.window_width, engine.window_height), flags)
        # Ensure dimensions reflect the actual mode applied by SDL
        engine.window_width = int(engine.screen.get_width())
        engine.window_height = int(engine.screen.get_height())
        pygame.display.set_caption(GAME_TITLE)

        # Recreate cached surfaces sized to window
        engine._scaled_surface = pygame.Surface((engine.window_width, engine.window_height))
        engine._pause_overlay = pygame.Surface((engine.window_width, engine.window_height), pygame.SRCALPHA)
        engine._pause_overlay.fill((0, 0, 0, 128))
        # Reset view surface so it gets resized on demand
        engine._view_surface = None
        engine._view_surface_size = (0, 0)

        # Update HUD size
        if hasattr(engine, "hud"):
            engine.hud.screen_width = engine.window_width
            engine.hud.screen_height = engine.window_height
            if hasattr(engine.hud, "on_resize"):
                try:
                    engine.hud.on_resize(engine.window_width, engine.window_height)
                except Exception:
                    pass
        # Resize modal panels if they expose on_resize (WK7 mid-sprint hitbox fix)
        if hasattr(engine, "pause_menu") and hasattr(engine.pause_menu, "on_resize"):
            try:
                engine.pause_menu.on_resize(engine.window_width, engine.window_height)
            except Exception:
                pass
        if hasattr(engine, "build_catalog_panel") and hasattr(engine.build_catalog_panel, "on_resize"):
            try:
                engine.build_catalog_panel.on_resize(engine.window_width, engine.window_height)
            except Exception:
                pass
        if hasattr(engine, "building_list_panel") and hasattr(engine.building_list_panel, "on_resize"):
            try:
                engine.building_list_panel.on_resize(engine.window_width, engine.window_height)
            except Exception:
                pass
        if hasattr(engine, "dev_tools_panel") and hasattr(engine.dev_tools_panel, "on_resize"):
            try:
                engine.dev_tools_panel.on_resize(engine.window_width, engine.window_height)
            except Exception:
                pass
        # Clamp camera to new view bounds after mode change
        if hasattr(engine, "clamp_camera"):
            try:
                engine.clamp_camera()
            except Exception:
                pass

        # After a mode switch on some Windows/SDL builds, the *first* event poll can crash in SDL.
        # Best-effort mitigation: pump once + clear the queue now (outside the main event loop).
        try:
            pygame.event.pump()
            pygame.event.clear()
        except Exception:
            pass
