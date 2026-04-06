"""
Basic 3D Viewer application using Ursina.
Wraps the core headless simulation and visualizes it with a perspective camera
on the X/Z floor plane; Pygame UI is composited on camera.ui (separate UI camera).
"""
from __future__ import annotations

import math
import os
import time as pytime

import config
import pygame
from PIL import Image
from ursina import Ursina, Vec2, window, camera, time, Entity, Texture, Vec3, scene, mouse
from ursina.lights import AmbientLight, DirectionalLight
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.engine import GameEngine
from game.graphics.ursina_pick import pick_world_xz_on_floor_y0
from game.graphics.ursina_renderer import UrsinaRenderer, SCALE, sim_px_to_world_xz
from game.input_manager import InputEvent
from game.ursina_input_manager import UrsinaInputManager, ursina_key_to_input_event
from tools.ursina_input_debug import is_ursina_debug_input_enabled, print_wk20_input_line
from tools.ursina_screenshot import save_ursina_window_screenshot


class UrsinaApp:
    def __init__(self, ai_controller_factory):
        # Pygame hidden — engine may expect SDL/font/audio
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()

        self.app = Ursina(
            title='Kingdom Sim - Ursina 3D Viewer',
            borderless=False,
            fullscreen=False,
            development_mode=True,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True

        # Default shader: lit+shadows only when directional shadows are enabled (otherwise unlit = much cheaper).
        _ursina_shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        Entity.default_shader = lit_with_shadows_shader if _ursina_shadows else unlit_shader
        scene.fog_density = (0, 1_000_000)
        from ursina import color as ucolor

        scene.fog_color = ucolor.rgba(0, 0, 0, 0)

        from panda3d.core import LVecBase4f
        base = self.app
        base.setBackgroundColor(LVecBase4f(34 / 255, 139 / 255, 34 / 255, 1))
        try:
            window.color = ucolor.rgb(34 / 255, 139 / 255, 34 / 255)
        except Exception:
            pass

        tiles_w = config.MAP_WIDTH
        tiles_h = config.MAP_HEIGHT

        # Map center in world X/Z (pixels -> sim_px_to_world_xz)
        cx_px = tiles_w * SCALE * 0.5
        cy_px = tiles_h * SCALE * 0.5
        self._map_center_xz = sim_px_to_world_xz(cx_px, cy_px)

        camera.orthographic = False
        camera.clip_plane_near = 0.1
        camera.clip_plane_far = 10000

        # WK22 SPRINT-BUG-002: directional sun + shadow caster (bounds fitted to scene after first frame).
        from ursina import color as ucolor2

        AmbientLight(parent=scene, color=ucolor2.rgba(0.42, 0.44, 0.48, 1))
        sm = int(getattr(config, "URSINA_SHADOW_MAP_SIZE", 768))
        sm = max(256, min(2048, sm))
        cx, cz = self._map_center_xz
        self._directional_light = DirectionalLight(
            parent=scene,
            shadows=_ursina_shadows,
            shadow_map_resolution=Vec2(sm, sm),
            color=ucolor2.rgba(0.98, 0.95, 0.88, 1),
        )
        self._directional_light.position = Vec3(cx + 55, 95, cz + 40)
        self._directional_light.look_at(Vec3(cx, 0, cz))
        self._shadow_bounds_initialized = False

        self.input_manager = UrsinaInputManager()
        self.engine = GameEngine(input_manager=self.input_manager, headless=False, headless_ui=True)
        # Let Ursina draw the map; pygame only draws HUD onto a transparent surface (see engine.render).
        self.engine._ursina_skip_world_render = True

        self.ui_overlay = Entity(
            parent=camera.ui,
            model='quad',
            texture=None,
            scale=(camera.aspect_ratio, 1),
            position=(0, 0),
            z=-1,
            shader=unlit_shader,
            collision=False,
        )

        if ai_controller_factory:
            self.engine.ai_controller = ai_controller_factory()

        self.renderer = UrsinaRenderer(self.engine)

        self._setup_ursina_camera_for_castle()
        self._install_ursina_input_hook()
        # Left click deferred to start of update() so MOUSEMOTION is processed first (placement preview).
        self._pending_lmb = False
        self._last_engine_screen_pos: tuple[int, int] = (0, 0)
        # Reuse one Texture for pygame HUD compositing (avoid new GPU alloc every frame; WK22 SPRINT-BUG-006).
        self._hud_composite_texture: Texture | None = None
        self._hud_composite_size: tuple[int, int] | None = None
        self._hud_upload_interval_sec = float(getattr(config, "URSINA_UI_UPLOAD_INTERVAL_SEC", 0.1) or 0.0)
        self._hud_next_upload_at = 0.0
        self._last_ui_overlay_scale: tuple[float, float] | None = None

    def _setup_ursina_camera_for_castle(self) -> None:
        """Frame castle + surrounding tiles (PM WK20); do not sync 2D engine camera when 3D pans."""
        castle = next(
            (
                b
                for b in self.engine.buildings
                if getattr(b, "building_type", "") == "castle" and getattr(b, "hp", 1) > 0
            ),
            None,
        )
        if castle is not None:
            cx, cz = sim_px_to_world_xz(float(castle.center_x), float(castle.center_y))
        else:
            cx, cz = self._map_center_xz

        camera.fov = 42
        span = 58.0
        hfov = math.radians(float(camera.fov))
        d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
        camera.position = Vec3(cx, d * 0.8, cz - d)
        camera.look_at(Vec3(cx, 0, cz))

    def _install_ursina_input_hook(self) -> None:
        app = self

        def ursina_input(key: str) -> None:
            app._handle_ursina_input(key)

        import __main__

        __main__.input = ursina_input

    def _pixel_hits_opaque_ui(self, px: int, py: int) -> bool:
        """True if virtual screen pixel has opaque HUD (alpha high enough to steal the click)."""
        surf = self.engine.screen
        try:
            c = surf.get_at((px, py))
        except Exception:
            return True
        if len(c) < 4:
            return bool(c[0] or c[1] or c[2])
        return c[3] >= 24

    def _engine_screen_pos_for_pointer(self) -> tuple[tuple[int, int], str, tuple[float, float] | None, float, float]:
        """
        Map Ursina pointer → virtual pygame pixel + engine screen coords for handlers.

        Returns:
            (engine_sx, engine_sy), kind, world_xz_or_none, wx_sim, wy_sim
        """
        px, py = self.input_manager.get_mouse_pos()
        eng = self.engine
        z = float(eng.zoom if eng.zoom else 1.0)
        hit: tuple[float, float] | None = None
        wx_sim = wy_sim = 0.0

        if self._pixel_hits_opaque_ui(px, py):
            pos = (px, py)
            kind = "ui"
        else:
            hit = pick_world_xz_on_floor_y0()
            if hit is None:
                pos = (px, py)
                kind = "ui_fallback"
            else:
                wx, wz = hit
                wx_sim = wx * SCALE
                wy_sim = -wz * SCALE
                sx = (wx_sim - eng.camera_x) * z
                sy = (wy_sim - eng.camera_y) * z
                pos = (int(round(sx)), int(round(sy)))
                kind = "world"

        return pos, kind, hit, wx_sim, wy_sim

    def _queue_pointer_motion_event(self) -> None:
        """Building placement needs update_preview() via MOUSEMOTION before MOUSEDOWN sets preview_valid."""
        pos, _kind, _hit, _wx, _wy = self._engine_screen_pos_for_pointer()
        self._last_engine_screen_pos = pos
        self.input_manager.queue_event(InputEvent(type="MOUSEMOTION", pos=pos, key=None))

    def _handle_ursina_input(self, key: str) -> None:
        # WK21: F12 — full Ursina window (3D + UI overlay) → docs/screenshots/
        if str(key).lower() == "f12":
            from ursina import application

            path = save_ursina_window_screenshot(application.base)
            if path and hasattr(self.engine, "hud") and self.engine.hud:
                import os as _os

                self.engine.hud.add_message(
                    f"Screenshot: {_os.path.basename(str(path))}",
                    (100, 200, 255),
                )
            return
        if key == "left mouse down":
            # Process click on next update() after motion, so BuildingMenu.preview_valid is current.
            self._pending_lmb = True
            return
        # WK22 SPRINT-BUG-004: forward keyboard / wheel to engine (was dropped by early return).
        evt = ursina_key_to_input_event(key)
        if evt is not None:
            self.input_manager.queue_event(evt)

    def _refresh_ui_overlay_texture(self) -> None:
        """Upload the pygame HUD texture on a short cadence instead of every frame."""
        scale = (camera.aspect_ratio, 1)
        if self._last_ui_overlay_scale != scale:
            self.ui_overlay.scale = scale
            self._last_ui_overlay_scale = scale

        sz = self.engine.screen.get_size()
        now = pytime.perf_counter()
        if (
            self._hud_composite_texture is not None
            and self._hud_composite_size == sz
            and self._hud_upload_interval_sec > 0.0
            and now < self._hud_next_upload_at
        ):
            return

        raw_data = pygame.image.tostring(self.engine.screen, "RGBA")
        img = Image.frombytes("RGBA", sz, raw_data)
        if self._hud_composite_texture is None or self._hud_composite_size != sz:
            self._hud_composite_texture = Texture(img, filtering=False)
            self._hud_composite_size = sz
            self.ui_overlay.texture = self._hud_composite_texture
        else:
            self._hud_composite_texture._cached_image = img
            self._hud_composite_texture.apply()

        if self._hud_upload_interval_sec > 0.0:
            self._hud_next_upload_at = now + self._hud_upload_interval_sec

    def run(self):
        pan_speed = 55.0

        def update():
            dt = time.dt

            # 1) Motion every frame (HUD hover, building preview validity).
            self._queue_pointer_motion_event()
            # 2) Same-frame click after motion (placement reads preview_valid).
            if self._pending_lmb:
                self._pending_lmb = False
                pos = self._last_engine_screen_pos
                self.input_manager.queue_event(
                    InputEvent(type="MOUSEDOWN", button=1, pos=pos, key=None)
                )
                if is_ursina_debug_input_enabled():
                    from config import TILE_SIZE

                    _p, kind, hit, wx_sim, wy_sim = self._engine_screen_pos_for_pointer()
                    tile = None
                    if hit is not None:
                        tile = (int(wx_sim // TILE_SIZE), int(wy_sim // TILE_SIZE))
                    print_wk20_input_line(
                        raw_sx=float(mouse.x),
                        raw_sy=float(mouse.y),
                        pygame_x=self.input_manager.get_mouse_pos()[0],
                        pygame_y=self.input_manager.get_mouse_pos()[1],
                        ui_hit=kind,
                        world_xz=hit,
                        tile=tile,
                    )

            self.engine.tick_simulation(dt)
            self.renderer.update()

            if not self._shadow_bounds_initialized:
                try:
                    self._directional_light.update_bounds(scene)
                except Exception:
                    pass
                self._shadow_bounds_initialized = True

            self.engine.render_pygame()
            self._refresh_ui_overlay_texture()

            from ursina import held_keys

            # Pan parallel to X/Z floor (world units / sec)
            if held_keys['a']:
                camera.x -= pan_speed * dt
            if held_keys['d']:
                camera.x += pan_speed * dt
            if held_keys['w']:
                camera.z -= pan_speed * dt
            if held_keys['s']:
                camera.z += pan_speed * dt

            # Zoom via perspective FOV (smaller = tighter)
            if held_keys['q']:
                camera.fov += 35 * dt
            if held_keys['e']:
                camera.fov -= 35 * dt
            camera.fov = max(18, min(95, camera.fov))

        import __main__

        __main__.update = update

        self.app.run()
