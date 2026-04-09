"""
Basic 3D Viewer application using Ursina.
Wraps the core headless simulation and visualizes it with a perspective camera
on the X/Z floor plane; Pygame UI is composited on camera.ui (separate UI camera).
"""
from __future__ import annotations

import math
import os
import time as pytime
import zlib

import config
import pygame
from PIL import Image
from ursina import Ursina, Vec2, window, camera, time, Entity, Texture, Vec3, scene, mouse, held_keys
from ursina.lights import AmbientLight, DirectionalLight
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.display_manager import DisplayManager
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
            # WK22 R3: dev mode runs extra bookkeeping that can hitch the main thread
            # (and audiostream / music) on a steady cadence.
            development_mode=False,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True

        # Default shader: lit+shadows only when directional shadows are enabled (otherwise unlit = much cheaper).
        _ursina_shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        Entity.default_shader = lit_with_shadows_shader if _ursina_shadows else unlit_shader
        # SPRINT-BUG-008: Ursina attaches linear Fog to the scene by default. Combined with
        # lit_with_shadows_shader's own fog mix + a forest-green clear color, drivers often show
        # thick horizontal banding in the upper view. Fog-of-war is handled by a floor quad in
        # UrsinaRenderer — we do not need Panda scene fog here.
        scene.clearFog()

        from ursina import color as ucolor

        from panda3d.core import LVecBase4f
        base = self.app
        # Neutral sky/clear color (was forest green; green bands read as "broken terrain").
        base.setBackgroundColor(LVecBase4f(0.06, 0.07, 0.09, 1))
        try:
            window.color = ucolor.rgb(0.06, 0.07, 0.09)
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
        # InputHandler: 'e' selects elven bungalow — in Ursina we use E/Q as continuous zoom (held_keys).
        self.engine._ursina_viewer = True
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
        # SPRINT-BUG-008: HUD is RGBA over the 3D layer — need proper alpha blend and no depth
        # fighting with ui_render's depth buffer (otherwise half-screen black / garbage).
        from panda3d.core import TransparencyAttrib

        self.ui_overlay.setTransparency(TransparencyAttrib.M_alpha)
        self.ui_overlay.set_depth_test(False)
        self.ui_overlay.set_depth_write(False)

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
        self._last_ui_overlay_scale: tuple[float, float] | None = None
        # Row-sampled CRC — skip GPU re-upload when pygame HUD likely unchanged (WK22 R3).
        self._hud_quick_sig: int | None = None

    @staticmethod
    def _hud_quick_fingerprint(surf: pygame.Surface) -> int:
        """~0.3–0.5 ms @ 1080p: sample every 16th row plus top/bottom chrome rows."""
        w, h = surf.get_size()
        mv = memoryview(surf.get_view("1"))
        row = w * 4
        acc = zlib.crc32(b"")
        rows: set[int] = set(range(0, h, 16))
        for y in (0, 1, 2, h - 3, h - 2, h - 1):
            if 0 <= y < h:
                rows.add(y)
        for y in sorted(rows):
            a = y * row
            acc = zlib.crc32(mv[a : a + row], acc)
        return acc & 0xFFFFFFFF

    @staticmethod
    def _hud_prefers_nearest_pixel_filter() -> bool:
        """WK22 R3: Pygame HUD is sized to the Ursina window — 1:1 texels; nearest keeps UI text sharp."""
        return True

    @staticmethod
    def _sync_hud_texture_filter_mode(tex: Texture | None) -> None:
        if tex is None:
            return
        nearest = UrsinaApp._hud_prefers_nearest_pixel_filter()
        try:
            # Panda/Ursina: None → nearest; True → linear (smoother when window is scaled).
            tex.filtering = None if nearest else True
        except Exception:
            try:
                tex.filtering = False if nearest else True
            except Exception:
                pass

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

        # Perspective FOV that matches engine.zoom==default_zoom (single source of truth: engine.zoom).
        self._ursina_reference_fov = float(camera.fov)

    def _sync_ursina_camera_fov_from_zoom(self) -> None:
        """Keep perspective FOV tied to engine.zoom so wheel, +/-, and Q/E match HUD/world mapping."""
        eng = self.engine
        z = float(eng.zoom if eng.zoom else 1.0) / float(
            eng.default_zoom if getattr(eng, "default_zoom", None) else 1.0
        )
        z = max(z, 1e-6)
        ref = float(self._ursina_reference_fov)
        camera.fov = max(18.0, min(95.0, ref / z))

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

        # Paused / ESC menu: the center of the screen is pygame HUD (often semi-transparent
        # backdrop). get_at() can be <24 alpha or stale → world-mapping breaks hover/clicks.
        # Input is consumed by the menu while open; when paused, world clicks are blocked too.
        if getattr(eng, "_ursina_viewer", False) and (
            getattr(eng, "paused", False)
            or (
                getattr(eng, "pause_menu", None) is not None
                and getattr(eng.pause_menu, "visible", False)
            )
        ):
            return (px, py), "ui", None, 0.0, 0.0

        gs = eng.get_game_state()
        if self._pixel_hits_opaque_ui(px, py) or eng.hud.virtual_pointer_in_hud_chrome(
            (px, py), eng.screen, gs
        ):
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
        # Ursina: expose left-button hold state so UI sliders only drag while LMB is down.
        try:
            lmb = 1 if bool(mouse.left) else 0
        except Exception:
            lmb = 0
        buttons = (lmb, 1 if bool(getattr(mouse, "right", False)) else 0, 0)
        self.input_manager.queue_event(
            InputEvent(type="MOUSEMOTION", pos=pos, key=None, buttons=buttons)
        )

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
        if key == "left mouse up":
            pos = self._last_engine_screen_pos
            self.input_manager.queue_event(InputEvent(type="MOUSEUP", button=1, pos=pos, key=None))
            return
        # WK22 SPRINT-BUG-004: forward keyboard / wheel to engine (was dropped by early return).
        evt = ursina_key_to_input_event(key)
        if evt is not None:
            self.input_manager.queue_event(evt)

    def _refresh_ui_overlay_texture(self) -> None:
        """Upload pygame HUD to GPU only when pixel data changes (WK22 R3 jitter fix).

        Full-window ``tobytes`` + PIL + ``Texture.apply`` was running on a timer every
        100ms even when the HUD was static, which produced periodic main-thread hitches
        (audible as music glitches). A CRC32 of the packed framebuffer skips that work
        entirely when nothing drew into ``engine.screen`` since the last upload.
        """
        scale = (camera.aspect_ratio, 1)
        if self._last_ui_overlay_scale != scale:
            self.ui_overlay.scale = scale
            self._last_ui_overlay_scale = scale

        surf = self.engine.screen
        sz = surf.get_size()

        try:
            quick = self._hud_quick_fingerprint(surf)
        except Exception:
            quick = None

        # Building panel research bars are ~12px tall; row-sampled CRC often misses them → stale GPU texture.
        force_upload = bool(getattr(self.engine, "_ursina_hud_force_upload", False))
        if force_upload:
            setattr(self.engine, "_ursina_hud_force_upload", False)

        if (
            not force_upload
            and quick is not None
            and self._hud_composite_texture is not None
            and self._hud_composite_size == sz
            and self._hud_quick_sig is not None
            and quick == self._hud_quick_sig
        ):
            return

        raw_data = pygame.image.tobytes(surf, "RGBA")
        img = Image.frombytes("RGBA", sz, raw_data)
        try:
            self._hud_quick_sig = self._hud_quick_fingerprint(surf)
        except Exception:
            self._hud_quick_sig = zlib.crc32(raw_data) & 0xFFFFFFFF

        if self._hud_composite_texture is None or self._hud_composite_size != sz:
            self._hud_composite_texture = Texture(img, filtering=False)
            self._sync_hud_texture_filter_mode(self._hud_composite_texture)
            self._hud_composite_size = sz
            self.ui_overlay.texture = self._hud_composite_texture
        else:
            # If GPU texture size ever diverges, recreating avoids row-stride corruption (stripes).
            tex = self._hud_composite_texture
            if int(tex.width) != int(sz[0]) or int(tex.height) != int(sz[1]):
                self._hud_composite_texture = Texture(img, filtering=False)
                self._sync_hud_texture_filter_mode(self._hud_composite_texture)
                self._hud_composite_size = sz
                self.ui_overlay.texture = self._hud_composite_texture
            else:
                tex._cached_image = img
                tex.apply()
                self._sync_hud_texture_filter_mode(tex)

    def _sync_headless_ui_canvas_to_window(self) -> None:
        """Poll Ursina ``window.size`` and resize ``engine.screen`` to match — fonts/layout rasterize at native pixels."""
        try:
            W, H = int(window.size[0]), int(window.size[1])
        except Exception:
            return
        if W < 32 or H < 32:
            return
        eng = self.engine
        prev = (int(getattr(eng, "window_width", 0)), int(getattr(eng, "window_height", 0)))
        DisplayManager.apply_headless_ui_canvas_size(eng, W, H)
        cur = (int(eng.window_width), int(eng.window_height))
        self.input_manager.set_virtual_screen_size(cur)
        if prev != cur:
            self._hud_quick_sig = None
            self._hud_composite_texture = None
            self._hud_composite_size = None

    def run(self):
        pan_speed = 55.0

        def update():
            dt = time.dt

            eng = self.engine

            def _chat_captures_keyboard() -> bool:
                """True while hero chat is open — block 3D pan/zoom so WASD/EQ type into chat."""
                cp = getattr(getattr(eng, "hud", None), "_chat_panel", None)
                return cp is not None and getattr(cp, "is_active", lambda: False)()

            # WK22 R3: dynamic HUD resolution — match pygame surface to Ursina window (no fixed 1080p GPU stretch).
            self._sync_headless_ui_canvas_to_window()

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

            # Pause menu Quit sets engine.running = False; Pygame's engine.run() exits the process —
            # Ursina must stop app.run() explicitly or the window stays open forever.
            if not getattr(self.engine, "running", True):
                try:
                    from ursina import application

                    application.quit()
                except Exception:
                    import sys

                    sys.exit(0)
                return

            # WK22 R3: Wheel / +/- already adjust engine.zoom in InputHandler — drive 3D FOV from that.
            # Held Q/E apply the same multiplicative zoom (cursor-anchored via zoom_by) so coords stay consistent.
            hk = held_keys
            zstep = float(config.ZOOM_STEP)
            # ~3 "UI zoom steps" per second while held (matches old ~35°/s FOV tweak feel).
            rate = 3.0 * dt
            _allow_zoom = (
                not eng.paused
                and not getattr(eng.pause_menu, "visible", False)
                and not _chat_captures_keyboard()
            )
            if _allow_zoom:
                if hk.get("e", 0):
                    eng.zoom_by(zstep**rate)
                if hk.get("q", 0):
                    eng.zoom_by(zstep ** (-rate))

            self._sync_ursina_camera_fov_from_zoom()

            self.renderer.update()

            if not self._shadow_bounds_initialized:
                try:
                    self._directional_light.update_bounds(scene)
                except Exception:
                    pass
                self._shadow_bounds_initialized = True

            self.engine.render_pygame()
            self._refresh_ui_overlay_texture()
            # Fullscreen ↔ windowed toggles with a static HUD skip texture upload; still resync filter.
            self._sync_hud_texture_filter_mode(self._hud_composite_texture)

            # Pan parallel to X/Z floor (world units / sec). Skip while typing in hero chat.
            if not _chat_captures_keyboard():
                if hk["a"]:
                    camera.x -= pan_speed * dt
                if hk["d"]:
                    camera.x += pan_speed * dt
                # WK23 R1: W = pan north (up-screen / +world Z); S = south — matches player expectation.
                if hk["w"]:
                    camera.z += pan_speed * dt
                if hk["s"]:
                    camera.z -= pan_speed * dt

        import __main__

        __main__.update = update

        self.app.run()
