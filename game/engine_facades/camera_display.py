"""Camera, zoom, display mode, and screenshot — mechanical facade over :class:`game.engine.GameEngine`."""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

import pygame

from config import (
    MAP_HEIGHT,
    MAP_WIDTH,
    TILE_SIZE,
    CAMERA_SPEED_PX_PER_SEC,
    CAMERA_EDGE_MARGIN_PX,
    ZOOM_MIN,
    ZOOM_MAX,
)
from game.display_manager import DisplayManager

if TYPE_CHECKING:
    from game.engine import GameEngine


class EngineCameraDisplay:
    """Presentation-only: camera movement, zoom, display apply, screenshot."""

    __slots__ = ("_e",)

    def __init__(self, engine: GameEngine) -> None:
        self._e = engine

    def apply_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        e = self._e
        if getattr(e, "headless_ui", False) and getattr(e, "_ursina_viewer", False):
            DisplayManager.apply_ursina_window(e, display_mode, window_size)
            return
        if e.display_manager is None:
            return
        e.display_manager.apply_settings(display_mode, window_size)

    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        e = self._e
        z = e.zoom if e.zoom else 1.0
        return e.camera_x + (screen_x / z), e.camera_y + (screen_y / z)

    def clamp_camera(self):
        e = self._e
        win_w = int(e.window_width)
        win_h = int(e.window_height)
        view_w = max(1, int(win_w / (e.zoom if e.zoom else 1.0)))
        view_h = max(1, int(win_h / (e.zoom if e.zoom else 1.0)))
        world_w = MAP_WIDTH * TILE_SIZE
        world_h = MAP_HEIGHT * TILE_SIZE

        max_x = max(0, world_w - view_w)
        max_y = max(0, world_h - view_h)

        e.camera_x = max(0, min(max_x, e.camera_x))
        e.camera_y = max(0, min(max_y, e.camera_y))

    def center_on_castle(self, reset_zoom: bool = True, castle=None):
        e = self._e
        if reset_zoom:
            e.zoom = float(getattr(e, "default_zoom", 1.0))

        if castle is None:
            castle = next(
                (
                    b
                    for b in e.buildings
                    if getattr(b, "building_type", None) == "castle" and getattr(b, "hp", 0) > 0
                ),
                None,
            )
        if not castle:
            return

        win_w = int(e.window_width)
        win_h = int(e.window_height)
        e.camera_x = castle.center_x - win_w // 2
        e.camera_y = castle.center_y - win_h // 2
        self.clamp_camera()

    def capture_screenshot(self):
        e = self._e
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs", "screenshots", "manual")
        os.makedirs(screenshot_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        try:
            pygame.image.save(e.screen, filepath)
            e.hud.add_message(f"Screenshot saved: {filename}", (100, 200, 255))
            print(f"[screenshot] Saved: {filepath}")
        except Exception as ex:
            e.hud.add_message(f"Screenshot failed: {ex}", (255, 100, 100))
            print(f"[screenshot] Failed: {ex}")

    def set_zoom(self, new_zoom: float):
        e = self._e
        e.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(new_zoom)))
        self.clamp_camera()

    def zoom_by(self, factor: float):
        if factor is None:
            return
        factor = float(factor)
        if factor <= 0:
            return

        e = self._e
        mouse_x, mouse_y = (
            e.input_manager.get_mouse_pos()
            if getattr(e, "input_manager", None)
            else pygame.mouse.get_pos()
        )
        before_x, before_y = self.screen_to_world(mouse_x, mouse_y)

        self.set_zoom(e.zoom * factor)

        after_zoom = e.zoom if e.zoom else 1.0
        e.camera_x = before_x - (mouse_x / after_zoom)
        e.camera_y = before_y - (mouse_y / after_zoom)
        self.clamp_camera()

    def update_camera(self, dt: float):
        e = self._e
        if hasattr(e, "hud"):
            chat_panel = getattr(e.hud, "_chat_panel", None)
            if chat_panel is not None and getattr(chat_panel, "is_active", lambda: False)():
                return

        speed = float(CAMERA_SPEED_PX_PER_SEC) * float(dt)

        dx = 0.0
        dy = 0.0

        if getattr(e, "input_manager", None):
            if e.input_manager.is_key_pressed("a"):
                dx -= speed
            if e.input_manager.is_key_pressed("d"):
                dx += speed
            if e.input_manager.is_key_pressed("w"):
                dy -= speed
            if e.input_manager.is_key_pressed("s"):
                dy += speed
        else:
            pg_keys = pygame.key.get_pressed()
            if pg_keys[pygame.K_a]:
                dx -= speed
            if pg_keys[pygame.K_d]:
                dx += speed
            if pg_keys[pygame.K_w]:
                dy -= speed
            if pg_keys[pygame.K_s]:
                dy += speed

        has_focus = (
            e.input_manager.is_mouse_focused()
            if getattr(e, "input_manager", None)
            else pygame.mouse.get_focused()
        )
        if has_focus:
            mx, my = (
                e.input_manager.get_mouse_pos()
                if getattr(e, "input_manager", None)
                else pygame.mouse.get_pos()
            )
            if mx < CAMERA_EDGE_MARGIN_PX:
                dx -= speed
            elif mx > int(e.window_width) - CAMERA_EDGE_MARGIN_PX:
                dx += speed

            if my < CAMERA_EDGE_MARGIN_PX:
                dy -= speed
            elif my > int(e.window_height) - CAMERA_EDGE_MARGIN_PX:
                dy += speed

        if dx or dy:
            e.camera_x += dx
            e.camera_y += dy
            self.clamp_camera()
