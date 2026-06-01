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
from ursina import (
    EditorCamera,
    Entity,
    Texture,
    Ursina,
    Vec2,
    Vec3,
    camera,
    held_keys,
    mouse,
    scene,
    time,
    window,
)
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.display_manager import DisplayManager
from game.engine import GameEngine
from game.graphics.ursina_pick import pick_world_xz_on_floor_y0
from game.paths import ASSETS_DIR
from game.graphics.ursina_renderer import UrsinaRenderer, SCALE, sim_px_to_world_xz
from game.input_manager import InputEvent
from game.ursina_input_manager import UrsinaInputManager, ursina_key_to_input_event
from game.graphics.ursina_input_debug import is_ursina_debug_input_enabled, print_wk20_input_line
from game.graphics.ursina_screenshot import save_ursina_window_screenshot


def _flip_surface_bytes_vertical(raw_rgba: bytes, width: int, height: int) -> bytes:
    """Flip RGBA pixel data vertically (reverse row order).

    Pygame's Y-axis points down; Panda3D's points up. PIL.Image.transpose(FLIP_TOP_BOTTOM)
    does this, but PIL adds ~15-30ms of Python overhead for the 8MB allocation + object
    construction. This function does the same operation directly on the byte buffer.
    """
    row_stride = width * 4
    # Build reversed row list — each slice is a memoryview into the original buffer,
    # so this allocates only the final joined result, not N intermediate copies.
    mv = memoryview(raw_rgba)
    return b"".join(mv[i * row_stride : (i + 1) * row_stride] for i in range(height - 1, -1, -1))


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

        # PyInstaller / frozen-bundle: register asset directories on Panda3D's model-path
        # so that Entity(model=...) and loader.loadModel() resolve correctly from _MEIPASS.
        from panda3d.core import getModelPath
        getModelPath().appendDirectory(str(ASSETS_DIR.resolve()))
        getModelPath().appendDirectory(str((ASSETS_DIR / "models").resolve()))

        # Default shader: lit+shadows only when directional shadows are enabled (otherwise unlit = much cheaper).
        _ursina_shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        Entity.default_shader = lit_with_shadows_shader if _ursina_shadows else unlit_shader
        # WK53: clear Ursina's default linear fog first, then re-apply as exponential.
        # SPRINT-BUG-008 history: linear fog + lit_with_shadows_shader caused horizontal
        # banding; exponential fog avoids the banding artifact while giving atmospheric
        # depth perspective.
        scene.clearFog()

        from ursina import color as ucolor

        from panda3d.core import LVecBase4f
        base = self.app
        # WK53 R1: sky-blue clear color (was 0.06, 0.07, 0.09 — near-black void).
        _sky_r, _sky_g, _sky_b = 0.53, 0.72, 0.88
        base.setBackgroundColor(LVecBase4f(_sky_r, _sky_g, _sky_b, 1))
        try:
            window.color = ucolor.rgb(_sky_r, _sky_g, _sky_b)
        except Exception:
            pass

        # WK53 R1: atmospheric distance fog — exponential mode.
        # Exponential fog avoids the horizontal banding that linear fog caused with
        # lit_with_shadows_shader (SPRINT-BUG-008). Fog color matches the sky clear
        # color so distant objects fade naturally into the horizon.
        # WK54: Density reduced from 0.008 to 0.005 for the 250x250 map expansion
        # (proportional to 150/250 scale change). Keeps distant terrain visible so
        # the larger world feels expansive rather than claustrophobic.
        self._atmo_fog = None
        try:
            from panda3d.core import Fog as PandaFog
            _atmo_fog = PandaFog("atmospheric_distance_fog")
            _atmo_fog.setColor(_sky_r, _sky_g, _sky_b, 1.0)
            _atmo_fog.setExpDensity(0.005)
            base.render.setFog(_atmo_fog)
            self._atmo_fog = _atmo_fog
        except Exception:
            # If exponential fog setup fails (driver/API issue), fall back to no fog.
            # The sky clear color alone still eliminates the dark void.
            scene.clearFog()

        # WK57/58: Zone-specific fog color — current lerp target and state
        self._zone_fog_current = (_sky_r, _sky_g, _sky_b)
        self._zone_fog_target = (_sky_r, _sky_g, _sky_b)

        # WK57 Wave 3: Camera layer awareness (0 = surface, -1 = underground)
        self._camera_active_layer: int = 0
        self._camera_transitioning: bool = False
        self._camera_transition_target_y: float | None = None
        self._camera_transition_speed: float = 0.0
        self._camera_surface_y: float | None = None  # stored when descending

        # WK57 Wave 4: Track pinned hero's last known layer for auto-follow
        self._hero_follow_last_layer: int | None = None

        tiles_w = config.MAP_WIDTH
        tiles_h = config.MAP_HEIGHT

        # Map center in world X/Z (pixels -> sim_px_to_world_xz)
        cx_px = tiles_w * SCALE * 0.5
        cy_px = tiles_h * SCALE * 0.5
        self._map_center_xz = sim_px_to_world_xz(cx_px, cy_px)

        camera.orthographic = False
        camera.clip_plane_near = 0.1
        camera.clip_plane_far = 10000

        # v1.5 Sprint 1.2: Ambient + Directional lights live in UrsinaRenderer._setup_scene_lighting().

        self.input_manager = UrsinaInputManager()
        _playtest = os.environ.get("KINGDOM_PLAYTEST_START", "").strip() == "1"
        self.engine = GameEngine(
            input_manager=self.input_manager,
            headless=False,
            headless_ui=True,
            playtest_start=_playtest,
        )
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

        self.renderer = UrsinaRenderer(self.engine.world)

        # WK30 debug: optional deterministic layout for prefab-fit iteration.
        if os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1":
            self._add_wk30_debug_prefab_layout()
        self._hero_fps_probe_count = self._read_int_env(
            "KINGDOM_URSINA_HERO_FPS_PROBE_COUNT", 0, min_value=0, max_value=20
        )
        if self._hero_fps_probe_count > 0:
            self._add_hero_fps_probe_layout(self._hero_fps_probe_count)

        self._setup_ursina_camera_for_castle()
        self.engine._ursina_recenter_fn = self._recenter_editor_camera_to_sim_xy

        self._worker_scale_shot_reattach = 0
        if os.environ.get("KINGDOM_URSINA_WORKER_SCALE_SHOT", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            self._install_worker_scale_comparison_shot()
            # Sim ticks spawn peasants; re-apply for several seconds so the auto-screenshot sees exactly one.
            self._worker_scale_shot_reattach = 420
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
        # Dirty-region tracking: previous frame's raw bytes for row-level diff (R5 phase 3).
        self._hud_prev_raw: bytes | None = None

        # WK32: ``_editor_camera`` is set by ``_setup_ursina_camera_for_castle()``. EditorCamera is
        # default-on; ``KINGDOM_URSINA_EDITORCAMERA=0`` is the legacy fallback. Do not reassign here
        # — a duplicate ``self._editor_camera = None`` after setup broke framing (WK32).

        # WK30 debug: auto-screenshot-then-exit for prefab fit iteration.
        # Env vars:
        #   KINGDOM_URSINA_AUTO_EXIT_SEC=<float>       — seconds after first update before exit.
        #   KINGDOM_URSINA_AUTO_SCREENSHOT_PATH=<path> — if set, save screenshot to this path
        #                                                just before quitting (overrides F12 dir).
        #   KINGDOM_URSINA_AUTO_SCREENSHOT=1           — if PATH empty, use game.graphics.ursina_screenshot
        #                                                naming (KINGDOM_SCREENSHOT_SUBDIR / STEM).
        # CLI: python tools/run_ursina_capture_once.py
        try:
            self._auto_exit_deadline_sec = float(
                os.environ.get("KINGDOM_URSINA_AUTO_EXIT_SEC", "") or 0.0
            )
        except ValueError:
            self._auto_exit_deadline_sec = 0.0
        self._auto_screenshot_path = (
            os.environ.get("KINGDOM_URSINA_AUTO_SCREENSHOT_PATH") or ""
        ).strip()
        # If auto-exit is set and caller asked for a capture but did not precompute a path,
        # use the same naming as F12 (KINGDOM_SCREENSHOT_SUBDIR / KINGDOM_SCREENSHOT_STEM).
        if (
            self._auto_exit_deadline_sec > 0.0
            and not self._auto_screenshot_path
            and os.environ.get("KINGDOM_URSINA_AUTO_SCREENSHOT", "").strip().lower()
            in ("1", "true", "yes", "on")
        ):
            from game.graphics.ursina_screenshot import next_auto_screenshot_path

            self._auto_screenshot_path = next_auto_screenshot_path()
        self._auto_exit_elapsed = 0.0
        self._auto_exit_triggered = False
        self._fps_probe_enabled = os.environ.get("KINGDOM_URSINA_FPS_PROBE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._fps_probe_warmup_sec = float(
            os.environ.get("KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC", "") or 2.0
        )
        self._fps_probe_elapsed = 0.0
        self._fps_probe_samples: list[float] = []
        self._fps_probe_stage_samples: dict[str, list[float]] = {}

    @staticmethod
    def _read_int_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return int(default)
        try:
            value = int(raw)
        except ValueError:
            return int(default)
        return max(int(min_value), min(int(max_value), value))

    @staticmethod
    def _hud_quick_fingerprint(surf: pygame.Surface) -> int:
        from game.graphics import ursina_app_ui_overlay
        return ursina_app_ui_overlay._hud_quick_fingerprint(surf)

    @staticmethod
    def _hud_prefers_nearest_pixel_filter() -> bool:
        from game.graphics import ursina_app_ui_overlay
        return ursina_app_ui_overlay._hud_prefers_nearest_pixel_filter()

    @staticmethod
    def _sync_hud_texture_filter_mode(tex: Texture | None) -> None:
        from game.graphics import ursina_app_ui_overlay
        return ursina_app_ui_overlay._sync_hud_texture_filter_mode(tex)

    def _setup_ursina_camera_for_castle(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._setup_ursina_camera_for_castle(self)

    def _recenter_editor_camera_to_sim_xy(self, sim_x: float, sim_y: float) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._recenter_editor_camera_to_sim_xy(self, sim_x, sim_y)

    def _is_chat_active(self) -> bool:
        from game.graphics import ursina_app_input
        return ursina_app_input._is_chat_active(self)

    def _reset_camera_to_default(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._reset_camera_to_default(self)

    def _toggle_camera_lock(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._toggle_camera_lock(self)

    def _toggle_underground_camera(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._toggle_underground_camera(self)

    def _sync_ursina_camera_fov_from_zoom(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera._sync_ursina_camera_fov_from_zoom(self)

    def update_zone_fog_color(self, camera_world_x: float, camera_world_z: float) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera.update_zone_fog_color(self, camera_world_x, camera_world_z)

    # ------------------------------------------------------------------
    # WK57 Wave 3: Camera layer transition API
    # ------------------------------------------------------------------

    @property
    def camera_active_layer(self) -> int:
        """Current camera layer: 0 = surface, -1 = underground."""
        return self._camera_active_layer

    def begin_camera_underground_transition(self, target_y: float) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera.begin_camera_underground_transition(self, target_y)

    def begin_camera_surface_transition(self) -> None:
        from game.graphics import ursina_app_camera
        return ursina_app_camera.begin_camera_surface_transition(self)

    def _install_ursina_input_hook(self) -> None:
        from game.graphics import ursina_app_input
        return ursina_app_input._install_ursina_input_hook(self)

    def _pixel_hits_opaque_ui(self, px: int, py: int) -> bool:
        from game.graphics import ursina_app_input
        return ursina_app_input._pixel_hits_opaque_ui(self, px, py)

    def _engine_screen_pos_for_pointer(self) -> tuple[tuple[int, int], str, tuple[float, float] | None, float, float]:
        from game.graphics import ursina_app_input
        return ursina_app_input._engine_screen_pos_for_pointer(self)

    def _sidebar_split_drag_active(self) -> bool:
        from game.graphics import ursina_app_input
        return ursina_app_input._sidebar_split_drag_active(self)

    def _virtual_screen_pos(self) -> tuple[int, int]:
        from game.graphics import ursina_app_input
        return ursina_app_input._virtual_screen_pos(self)

    def _pointer_event_pos(self) -> tuple[int, int]:
        from game.graphics import ursina_app_input
        return ursina_app_input._pointer_event_pos(self)

    def _queue_pointer_motion_event(self) -> None:
        from game.graphics import ursina_app_input
        return ursina_app_input._queue_pointer_motion_event(self)

    def _handle_ursina_input(self, key: str) -> None:
        from game.graphics import ursina_app_input
        return ursina_app_input._handle_ursina_input(self, key)

    def _refresh_ui_overlay_texture(self) -> None:
        from game.graphics import ursina_app_ui_overlay
        return ursina_app_ui_overlay._refresh_ui_overlay_texture(self)

    def _sync_headless_ui_canvas_to_window(self) -> None:
        from game.graphics import ursina_app_ui_overlay
        return ursina_app_ui_overlay._sync_headless_ui_canvas_to_window(self)

    def _add_wk30_debug_prefab_layout(self) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._add_wk30_debug_prefab_layout(self)

    def _install_worker_scale_comparison_shot(self) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._install_worker_scale_comparison_shot(self)

    def _add_hero_fps_probe_layout(self, hero_count: int) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._add_hero_fps_probe_layout(self, hero_count)

    def _record_fps_probe_sample(self, dt: float) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._record_fps_probe_sample(self, dt)

    def _record_fps_probe_stage_ms(self, name: str, started_at: float) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._record_fps_probe_stage_ms(self, name, started_at)

    def _print_fps_probe_summary(self) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._print_fps_probe_summary(self)

    def _maybe_auto_screenshot_then_quit(self) -> None:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._maybe_auto_screenshot_then_quit(self)

    @staticmethod
    def _save_window_screenshot_sync(base, out_path: str) -> bool:
        from game.graphics import ursina_app_debug_probe
        return ursina_app_debug_probe._save_window_screenshot_sync(base, out_path)

    def run(self):
        pan_speed = 55.0

        def update():
            dt = time.dt

            eng = self.engine

            def _chat_captures_keyboard() -> bool:
                """True while hero chat or command mode is open — block 3D pan/zoom so keys type into input."""
                if getattr(eng, '_command_mode', False):
                    return True
                cp = getattr(getattr(eng, "hud", None), "_chat_panel", None)
                return cp is not None and getattr(cp, "is_active", lambda: False)()

            # WK22 R3: dynamic HUD resolution — match pygame surface to Ursina window (no fixed 1080p GPU stretch).
            self._sync_headless_ui_canvas_to_window()

            # 1) Motion every frame (HUD hover, building preview validity).
            self._queue_pointer_motion_event()
            # 2) Same-frame click after motion (placement reads preview_valid).
            if self._pending_lmb:
                self._pending_lmb = False
                vpos = self._virtual_screen_pos()
                hud = getattr(eng, "hud", None)
                if hud is not None and hasattr(hud, "handle_sidebar_split_pointer_down"):
                    try:
                        hud.handle_sidebar_split_pointer_down(vpos, eng.get_game_state())
                    except Exception:
                        pass
                pos = self._pointer_event_pos()
                if not self._sidebar_split_drag_active():
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

            _stage_t0 = pytime.perf_counter()
            self.engine.tick_simulation(dt)
            self._record_fps_probe_stage_ms("tick_simulation", _stage_t0)
            self.engine._last_frame_dt_ms = float(dt or 0.0) * 1000.0

            if getattr(self, "_worker_scale_shot_reattach", 0) > 0:
                self._worker_scale_shot_reattach -= 1
                self._install_worker_scale_comparison_shot()

            # WK31: EMA of 1/dt for F2 overlay — pygame clock FPS is not Panda3D/GPU FPS in this mode.
            try:
                d = float(dt or 0.0)
                if d > 1e-9:
                    inst = 1.0 / d
                    prev = getattr(eng, "_ursina_window_fps_ema", None)
                    if prev is None:
                        eng._ursina_window_fps_ema = inst
                    else:
                        eng._ursina_window_fps_ema = prev * 0.92 + inst * 0.08
            except Exception:
                pass
            self._record_fps_probe_sample(float(dt or 0.0))

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

            # WK30 debug: auto-screenshot + auto-exit for prefab iteration.
            if (
                not self._auto_exit_triggered
                and self._auto_exit_deadline_sec > 0.0
            ):
                self._auto_exit_elapsed += float(dt or 0.0)
                if self._auto_exit_elapsed >= self._auto_exit_deadline_sec:
                    self._auto_exit_triggered = True
                    self._maybe_auto_screenshot_then_quit()
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
            # Keep EditorCamera dolly target aligned — zoom is FOV-driven from engine.zoom, not trackball dolly.
            ecam = getattr(self, "_editor_camera", None)
            if ecam is not None:
                ecam.target_z = camera.z

            _stage_t0 = pytime.perf_counter()
            snapshot = self.engine.build_snapshot()
            # WK67 Move 4 / L6: presentation timing/camera/selection are no longer on
            # the sim snapshot — build the per-frame presentation state and pass both.
            frame = self.engine.build_presentation_frame()
            self.renderer.update(snapshot, frame)
            self._record_fps_probe_stage_ms("ursina_renderer", _stage_t0)

            # WK58 Agent 10 (cross-domain, scoped): auto-reveal hook for perf_render_benchmark
            # and tools/run_ursina_capture_once.py --reveal-map. Fires once when env flag is set.
            if (
                not getattr(self, "_auto_reveal_done", False)
                and os.environ.get("KINGDOM_URSINA_REVEAL_ON_START", "").strip() == "1"
            ):
                self._auto_reveal_done = True
                self.engine.process_command("/revealmap")

            _stage_t0 = pytime.perf_counter()
            self.engine.render_pygame()
            self._record_fps_probe_stage_ms("pygame_hud_render", _stage_t0)
            _stage_t0 = pytime.perf_counter()
            self._refresh_ui_overlay_texture()
            self._record_fps_probe_stage_ms("hud_texture_upload", _stage_t0)
            # Fullscreen ↔ windowed toggles with a static HUD skip texture upload; still resync filter.
            self._sync_hud_texture_filter_mode(self._hud_composite_texture)

            # Pan parallel to X/Z floor (world units / sec). Skip while typing in hero chat.
            if not _chat_captures_keyboard():
                ecam = getattr(self, "_editor_camera", None)
                try:
                    orbiting = bool(getattr(mouse, "right", False)) and not getattr(self, '_camera_orbit_locked', False)
                except Exception:
                    orbiting = False
                if ecam is not None and not orbiting:
                    if hk["a"]:
                        ecam.x -= pan_speed * dt
                    if hk["d"]:
                        ecam.x += pan_speed * dt
                    if hk["w"]:
                        ecam.z += pan_speed * dt
                    if hk["s"]:
                        ecam.z -= pan_speed * dt
                elif ecam is None:
                    if hk["a"]:
                        camera.x -= pan_speed * dt
                    if hk["d"]:
                        camera.x += pan_speed * dt
                    # WK23 R1: W = pan north (up-screen / +world Z); S = south — matches player expectation.
                    if hk["w"]:
                        camera.z += pan_speed * dt
                    if hk["s"]:
                        camera.z -= pan_speed * dt

            # WK57 Wave 3: Camera layer transition lerp — smooth descent/ascent
            # between surface and underground. Runs before terrain clamp so we can
            # override the clamp during underground transitions.
            if self._camera_transitioning and self._camera_transition_target_y is not None:
                dy = self._camera_transition_target_y - camera.y
                if abs(dy) < 0.5:
                    camera.y = self._camera_transition_target_y
                    self._camera_transitioning = False
                    self._camera_transition_target_y = None
                else:
                    step = self._camera_transition_speed * dt
                    camera.y += step if dy > 0 else -step

            # WK53 R3: Camera terrain clamp — prevent camera from clipping below the
            # terrain surface when orbiting/panning. Sample terrain height at the
            # camera's world XZ position and enforce a minimum Y offset above ground.
            # WK57 Wave 3: Skip terrain clamp when camera is underground or transitioning.
            if not self._camera_transitioning and self._camera_active_layer == 0:
                try:
                    from game.graphics.terrain_height import get_terrain_height, is_initialized as _terrain_ok
                    if _terrain_ok():
                        cam_wx = float(camera.world_position.x)
                        cam_wz = float(camera.world_position.z)
                        ground_y = get_terrain_height(cam_wx, cam_wz)
                        min_cam_y = ground_y + 1.0  # offset above ground for comfortable feel
                        if float(camera.world_position.y) < min_cam_y:
                            camera.world_position = Vec3(cam_wx, min_cam_y, cam_wz)
                except Exception:
                    pass

            # WK57 Wave 4: Auto-follow pinned hero underground/surface transitions.
            # If the pinned hero's layer changes, automatically move the camera to match.
            if not self._camera_transitioning:
                try:
                    _hud = getattr(eng, 'hud', None)
                    _ps = getattr(_hud, '_pin_slot', None) if _hud else None
                    _ph_id = getattr(_ps, 'hero_id', None) if _ps else None
                    if _ph_id is not None:
                        _ph = eng._find_hero_by_id(_ph_id)
                        _ph_layer = getattr(_ph, 'layer', 0) if _ph is not None else 0
                        _prev_layer = self._hero_follow_last_layer
                        if _prev_layer is not None and _ph_layer != _prev_layer:
                            if _ph_layer == -1 and self._camera_active_layer == 0:
                                # Hero entered underground — follow
                                from config import UNDERGROUND_DEPTH
                                self.begin_camera_underground_transition(-(UNDERGROUND_DEPTH - 3.0))
                                print("Camera: Auto-follow underground", flush=True)
                                if _hud:
                                    _hud.add_message("Camera: Following hero underground", (100, 200, 255))
                            elif _ph_layer == 0 and self._camera_active_layer == -1:
                                # Hero returned to surface — follow
                                self.begin_camera_surface_transition()
                                print("Camera: Auto-follow surface", flush=True)
                                if _hud:
                                    _hud.add_message("Camera: Following hero to surface", (100, 200, 255))
                        self._hero_follow_last_layer = _ph_layer
                    else:
                        self._hero_follow_last_layer = None
                except Exception:
                    pass

            # WK57 Wave 3: Pass camera active layer to renderer for entity visibility
            _renderer = getattr(self, 'renderer', None)
            if _renderer is not None:
                _renderer._camera_active_layer = self._camera_active_layer

            # WK57/58: Zone-specific fog color based on camera position
            try:
                self.update_zone_fog_color(
                    float(camera.world_position.x),
                    float(camera.world_position.z),
                )
            except Exception:
                pass

        import __main__

        __main__.update = update

        self.app.run()
