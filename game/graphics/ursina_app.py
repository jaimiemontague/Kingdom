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
from tools.ursina_input_debug import is_ursina_debug_input_enabled, print_wk20_input_line
from tools.ursina_screenshot import save_ursina_window_screenshot


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
        #   KINGDOM_URSINA_AUTO_SCREENSHOT=1           — if PATH empty, use tools.ursina_screenshot
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
            from tools.ursina_screenshot import next_auto_screenshot_path

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
        """~0.5–0.8 ms @ 1080p: sample every 8th row plus top/bottom chrome rows.

        Stride 16 missed thin HUD deltas (~12px building bars; WK22). WK51 r6: stride 8 so
        header/footer chrome (pin, recall) cannot fall entirely between sampled rows.
        """
        w, h = surf.get_size()
        mv = memoryview(surf.get_view("1"))
        row = w * 4
        acc = zlib.crc32(b"")
        rows: set[int] = set(range(0, h, 8))
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
        """Frame castle + surrounding tiles (PM WK20); do not sync 2D engine camera when 3D pans.

        WK32: **EditorCamera** (orbit/pan) is default-on for model viewer parity.
        ``KINGDOM_URSINA_EDITORCAMERA=0`` keeps the legacy world-space camera as a fallback.
        The EditorCamera pivot sits on the castle floor point, while the starting world pose is
        derived from the known-good legacy ``look_at`` framing.
        """
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
        # WK30 debug: when the prefab-test layout is active, frame the castle + prefab
        # row. Optional ``KINGDOM_URSINA_CAM_TOPDOWN=1`` to switch to a top-down shot.
        if os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1":
            cx += 10.5  # midpoint between castle center and east end of test row
            span = 32.0

        # WK32 debug: allow deterministic close oblique captures by focusing a single building.
        # Apply *after* the prefab-test layout default framing so focus can override it.
        focus_type = os.environ.get("KINGDOM_URSINA_CAM_FOCUS_BUILDING_TYPE", "").strip().lower()
        if focus_type:
            def _matches_focus(bt) -> bool:
                raw = bt
                try:
                    s = str(raw or "").strip().lower()
                except Exception:
                    s = ""
                if s == focus_type:
                    return True
                # Accept enum-ish strings like "BuildingType.INN" or "inn_v2".
                if s.endswith(f".{focus_type}") or s.endswith(f"_{focus_type}") or s.endswith(focus_type):
                    return True
                try:
                    name = str(getattr(raw, "name", "") or "").strip().lower()
                    if name == focus_type:
                        return True
                except Exception:
                    pass
                return False

            target_b = next(
                (
                    b
                    for b in getattr(self.engine, "buildings", [])
                    if _matches_focus(getattr(b, "building_type", ""))
                    and getattr(b, "hp", 1) > 0
                ),
                None,
            )
            if target_b is not None:
                cx, cz = sim_px_to_world_xz(float(target_b.center_x), float(target_b.center_y))
                try:
                    span = float(os.environ.get("KINGDOM_URSINA_CAM_FOCUS_SPAN", "") or span)
                except Exception:
                    pass
                print(
                    f"[ursina-camera] focus={focus_type} cx={cx:.2f} cz={cz:.2f} span={span:.2f}",
                    flush=True,
                )

        hfov = math.radians(float(camera.fov))
        d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
        elev = d * 0.8
        back = d

        # Perspective FOV that matches engine.zoom==default_zoom (single source of truth: engine.zoom).
        self._ursina_reference_fov = float(camera.fov)

        editor_camera_env = os.environ.get("KINGDOM_URSINA_EDITORCAMERA", "").strip().lower()
        use_editor_camera = editor_camera_env not in ("0", "false", "no", "off")
        if not use_editor_camera:
            self._editor_camera = None
            if os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1":
                if os.environ.get("KINGDOM_URSINA_CAM_TOPDOWN") == "1":
                    camera.position = Vec3(cx, d * 1.6, cz)
                    camera.look_at(Vec3(cx, 0, cz))
                else:
                    # Deterministic oblique shot with optional yaw/pitch overrides.
                    try:
                        yaw_deg = float(os.environ.get("KINGDOM_URSINA_CAM_YAW", "") or 0.0)
                    except Exception:
                        yaw_deg = 0.0
                    try:
                        pitch_mul = float(os.environ.get("KINGDOM_URSINA_CAM_PITCH_MUL", "") or 1.0)
                    except Exception:
                        pitch_mul = 1.0
                    try:
                        height_mul = float(os.environ.get("KINGDOM_URSINA_CAM_HEIGHT_MUL", "") or 0.85)
                    except Exception:
                        height_mul = 0.85
                    yaw_rad = math.radians(yaw_deg)
                    back_mul = 0.7
                    by = d * height_mul * max(0.0, pitch_mul)
                    bx = math.sin(yaw_rad) * d * back_mul
                    bz = math.cos(yaw_rad) * d * back_mul
                    camera.position = Vec3(cx + bx, by, cz - bz)
                    camera.look_at(Vec3(cx, 0, cz))
            else:
                camera.position = Vec3(cx, elev, cz - back)
                camera.look_at(Vec3(cx, 0, cz))
            self._default_cam_state = {
                'cam_position': Vec3(camera.position),
                'cam_rotation': Vec3(camera.rotation),
                'cam_world_position': Vec3(camera.world_position),
            }
            self._camera_orbit_locked = False
            return

        target = Vec3(cx, 0.0, cz)
        debug_layout = os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1"
        rig_rotation: Vec3 | None = None
        rig_world_position = Vec3(cx, elev, cz - back)
        if not debug_layout:
            # Derive the initial rig rotation from the known-good legacy framing, then parent the
            # camera under EditorCamera for mouse orbit/pan. This avoids sign/axis drift between
            # Ursina's camera look_at and EditorCamera's pivot transform.
            camera.position = rig_world_position
            camera.look_at(target)
            rig_rotation = Vec3(camera.rotation)

        # EditorCamera: pivot on the castle floor point; the camera keeps the centered legacy
        # world position after the rig rotation is applied.
        ec = EditorCamera(
            zoom_speed=0.0,
            rotation_speed=200.0,
            pan_speed=Vec2(5, 5),
            ignore_scroll_on_ui=True,
        )
        ec.position = target
        if debug_layout:
            # Debug layout: fixed rig pitch (no look_at — avoids fighting ec.rotation for prefab shots).
            if os.environ.get("KINGDOM_URSINA_CAM_TOPDOWN") == "1":
                camera.position = Vec3(0.0, d * 1.6, -d * 0.02)
                ec.rotation = Vec3(89.0, 0.0, 0.0)
            else:
                cam_dist = d
                try:
                    cam_dist = float(os.environ.get("KINGDOM_URSINA_CAM_DIST", "") or cam_dist)
                except Exception:
                    cam_dist = d
                camera.position = Vec3(0.0, cam_dist * 0.85, -cam_dist * 0.7)
                try:
                    pitch = float(os.environ.get("KINGDOM_URSINA_CAM_PITCH", "") or 40.0)
                except Exception:
                    pitch = 40.0
                try:
                    yaw = float(os.environ.get("KINGDOM_URSINA_CAM_YAW", "") or 0.0)
                except Exception:
                    yaw = 0.0
                ec.rotation = Vec3(pitch, yaw, 0.0)
        else:
            camera.rotation = Vec3(0.0, 0.0, 0.0)
            if rig_rotation is not None:
                ec.rotation = rig_rotation
            camera.world_position = rig_world_position
        # EditorCamera.__init__ snapshots camera.editor_position before parenting; on_enable can
        # leave stale state. Sync so orbit/pivot matches castle framing.
        try:
            camera.editor_position = camera.position
        except Exception:
            pass
        ec.target_z = camera.z
        self._editor_camera = ec
        self._default_cam_state = {
            'ec_position': Vec3(ec.position),
            'ec_rotation': Vec3(ec.rotation),
            'cam_position': Vec3(camera.position),
            'cam_world_position': Vec3(camera.world_position),
            'target_z': ec.target_z,
        }
        self._camera_orbit_locked = False

    def _recenter_editor_camera_to_sim_xy(self, sim_x: float, sim_y: float) -> None:
        """WK51: move EditorCamera pivot to follow recall / camera snap (sim pixel coords)."""
        wx, wz = sim_px_to_world_xz(float(sim_x), float(sim_y))
        ec = getattr(self, "_editor_camera", None)
        if ec is not None:
            ec.position = Vec3(wx, 0.0, wz)

    def _is_chat_active(self) -> bool:
        if getattr(self.engine, '_command_mode', False):
            return True
        cp = getattr(getattr(self.engine, "hud", None), "_chat_panel", None)
        return cp is not None and getattr(cp, "is_active", lambda: False)()

    def _reset_camera_to_default(self) -> None:
        state = getattr(self, '_default_cam_state', None)
        if state is None:
            return

        if self._camera_orbit_locked:
            self._camera_orbit_locked = False
            ec = getattr(self, '_editor_camera', None)
            if ec is not None:
                ec.rotation_speed = 200.0

        ec = getattr(self, '_editor_camera', None)
        if ec is not None and state.get('ec_position') is not None:
            ec.position = Vec3(state['ec_position'])
            ec.rotation = Vec3(state['ec_rotation'])
            camera.position = Vec3(state['cam_position'])
            camera.world_position = Vec3(state['cam_world_position'])
            ec.target_z = state['target_z']
            try:
                camera.editor_position = camera.position
            except Exception:
                pass
        else:
            camera.position = Vec3(state['cam_position'])
            camera.world_position = Vec3(state['cam_world_position'])
            rot = state.get('cam_rotation')
            if rot is not None:
                camera.rotation = Vec3(rot)

        self.engine.zoom = float(getattr(self.engine, 'default_zoom', 1.0))
        self._sync_ursina_camera_fov_from_zoom()

        hud = getattr(self.engine, 'hud', None)
        if hud:
            hud.add_message("Camera reset", (100, 200, 255))

    def _toggle_camera_lock(self) -> None:
        self._camera_orbit_locked = not getattr(self, '_camera_orbit_locked', False)
        ec = getattr(self, '_editor_camera', None)
        if ec is not None:
            ec.rotation_speed = 0.0 if self._camera_orbit_locked else 200.0
        hud = getattr(self.engine, 'hud', None)
        if hud:
            label = "Camera Lock: ON" if self._camera_orbit_locked else "Camera Lock: OFF"
            hud.add_message(label, (100, 200, 255))

    def _sync_ursina_camera_fov_from_zoom(self) -> None:
        """Keep perspective FOV tied to engine.zoom so wheel, +/-, and Q/E match HUD/world mapping."""
        eng = self.engine
        z = float(eng.zoom if eng.zoom else 1.0) / float(
            eng.default_zoom if getattr(eng, "default_zoom", None) else 1.0
        )
        z = max(z, 1e-6)
        ref = float(self._ursina_reference_fov)
        camera.fov = max(8.0, min(95.0, ref / z))

    # WK57/58: Zone-specific fog color hints
    _ZONE_FOG_COLORS: dict[str, tuple[float, float, float]] = {
        "darkwood": (0.35, 0.55, 0.35),       # Greenish forest mist
        "mountains": (0.60, 0.70, 0.85),       # Cool blue mountain haze
        "canyon_land": (0.75, 0.60, 0.50),      # Warm reddish canyon dust
        "castle_town": (0.53, 0.72, 0.88),     # Default sky blue
    }
    _DEFAULT_FOG_COLOR: tuple[float, float, float] = (0.53, 0.72, 0.88)

    def update_zone_fog_color(self, camera_world_x: float, camera_world_z: float) -> None:
        """Lerp atmospheric fog color toward the zone under the camera."""
        fog = self._atmo_fog
        if fog is None:
            return
        try:
            from game.world_zones import get_zone
        except Exception:
            return

        # Convert camera world position to tile coords
        tile_x = int(camera_world_x * SCALE / float(config.TILE_SIZE))
        tile_z = int(-camera_world_z * SCALE / float(config.TILE_SIZE))

        # Castle center in tile coords for zone lookup
        castle_cx = int(config.MAP_WIDTH) // 2
        castle_cy = int(config.MAP_HEIGHT) // 2
        try:
            castle = next(
                (b for b in self.engine.buildings
                 if getattr(b, "building_type", "") == "castle" and getattr(b, "hp", 1) > 0),
                None,
            )
            if castle is not None:
                castle_cx = int(getattr(castle, "grid_x", castle_cx)) + int(getattr(castle, "size", (1, 1))[0]) // 2
                castle_cy = int(getattr(castle, "grid_y", castle_cy)) + int(getattr(castle, "size", (1, 1))[1]) // 2
        except Exception:
            pass

        zone = get_zone(tile_x, tile_z, castle_cx, castle_cy)
        zone_id = getattr(zone, "zone_id", None) if zone is not None else None
        target = self._ZONE_FOG_COLORS.get(zone_id, self._DEFAULT_FOG_COLOR) if zone_id else self._DEFAULT_FOG_COLOR
        self._zone_fog_target = target

        # Lerp current color toward target for smooth transition
        cr, cg, cb = self._zone_fog_current
        tr, tg, tb = self._zone_fog_target
        lerp_speed = 0.02  # per-frame lerp factor — gradual over ~50 frames
        nr = cr + (tr - cr) * lerp_speed
        ng = cg + (tg - cg) * lerp_speed
        nb = cb + (tb - cb) * lerp_speed
        self._zone_fog_current = (nr, ng, nb)

        # Apply only when the delta is perceptible (avoid per-frame setColor thrash)
        if abs(nr - cr) > 0.001 or abs(ng - cg) > 0.001 or abs(nb - cb) > 0.001:
            try:
                fog.setColor(nr, ng, nb, 1.0)
            except Exception:
                pass

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
        eng._ursina_pointer_world_sim = None
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
                eng._ursina_pointer_world_sim = (wx_sim, wy_sim)
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
        _ks = str(key).strip().lower()
        if not self._is_chat_active():
            if _ks == 'home':
                self._reset_camera_to_default()
                return
            if _ks == 'l':
                self._toggle_camera_lock()
                return
        # WK52 R12: Route wheel to left menus before queuing — MOUSEMOTION may map pointer to
        # world-relative coords while building/hero menus use virtual framebuffer pixels only.
        if _ks in ("scroll up", "scroll down"):
            _wy = 1 if _ks == "scroll up" else -1
            _eng = self.engine
            _hud = getattr(_eng, "hud", None)
            if _hud is not None:
                try:
                    _mx = self.input_manager.get_mouse_pos()
                except Exception:
                    _mx = (0, 0)
                if _hud.handle_menu_scroll(tuple(_mx), int(_wy), _eng.get_game_state(), getattr(_eng, "building_panel", None)):
                    return
        # WK22 SPRINT-BUG-004: forward keyboard / wheel to engine (was dropped by early return).
        evt = ursina_key_to_input_event(key)
        if evt is not None:
            self.input_manager.queue_event(evt)

    def _refresh_ui_overlay_texture(self) -> None:
        """Upload pygame HUD to GPU — zero-copy Y-inversion via GPU texture coords (R5 round 3.5).

        Previous path: pygame.tobytes -> _flip_surface_bytes_vertical (8MB memcpy) -> setRamImageAs
        New path:      pygame.tobytes -> setRamImageAs (raw, un-flipped)
        GPU handles the Pygame-vs-Panda3D Y-axis difference via texture_scale=(1,-1) + texture_offset=(0,1)
        on the ui_overlay entity, which is free (just different UV interpolation during rasterization).
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

        try:
            self._hud_quick_sig = self._hud_quick_fingerprint(surf)
        except Exception:
            self._hud_quick_sig = zlib.crc32(raw_data) & 0xFFFFFFFF

        # Skip Python-side byte flip; GPU handles Y-inversion via texture_scale=(1,-1).
        # This eliminates an 8MB memoryview reversal (~15-30ms at 1080p RGBA).

        from panda3d.core import Texture as PandaTexture

        if self._hud_composite_texture is None or self._hud_composite_size != sz:
            panda_tex = PandaTexture()
            panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
            panda_tex.setRamImageAs(raw_data, "RGBA")
            self._hud_composite_texture = Texture(panda_tex)
            self._hud_composite_size = sz
            self.ui_overlay.texture = self._hud_composite_texture
            # GPU-side Y-inversion: flip V coord so Pygame's top-down rows render correctly
            # in Panda3D's bottom-up coordinate system. Must be set AFTER texture assignment
            # since Ursina may reset texture properties during assignment.
            self.ui_overlay.texture_scale = (1, -1)
            self.ui_overlay.texture_offset = (0, 1)
            self._sync_hud_texture_filter_mode(self._hud_composite_texture)
            self._hud_prev_raw = raw_data
        else:
            panda_tex = self._hud_composite_texture._texture
            if int(panda_tex.getXSize()) != int(sz[0]) or int(panda_tex.getYSize()) != int(sz[1]):
                panda_tex = PandaTexture()
                panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
                panda_tex.setRamImageAs(raw_data, "RGBA")
                self._hud_composite_texture = Texture(panda_tex)
                self._hud_composite_size = sz
                self.ui_overlay.texture = self._hud_composite_texture
                # Re-apply GPU-side Y-inversion after texture reassignment
                self.ui_overlay.texture_scale = (1, -1)
                self.ui_overlay.texture_offset = (0, 1)
                self._sync_hud_texture_filter_mode(self._hud_composite_texture)
                self._hud_prev_raw = raw_data
            else:
                # R5 phase 3: dirty-region upload — only upload changed rows to GPU.
                if self._hud_prev_raw is not None and len(self._hud_prev_raw) == len(raw_data):
                    row_stride = sz[0] * 4
                    dirty_min = sz[1]
                    dirty_max = -1

                    # Scan from top to find first dirty row
                    for y in range(sz[1]):
                        offset = y * row_stride
                        if raw_data[offset:offset + row_stride] != self._hud_prev_raw[offset:offset + row_stride]:
                            dirty_min = y
                            break

                    if dirty_min < sz[1]:
                        # Scan from bottom to find last dirty row
                        for y in range(sz[1] - 1, dirty_min - 1, -1):
                            offset = y * row_stride
                            if raw_data[offset:offset + row_stride] != self._hud_prev_raw[offset:offset + row_stride]:
                                dirty_max = y
                                break

                    if dirty_max >= dirty_min:
                        sub_h = dirty_max - dirty_min + 1
                        sub_offset = dirty_min * row_stride
                        sub_bytes = raw_data[sub_offset:sub_offset + sub_h * row_stride]

                        try:
                            from panda3d.core import PNMImage as _PNMImage

                            # Create temp texture holding only the dirty rows
                            temp_tex = PandaTexture()
                            temp_tex.setup2dTexture(sz[0], sub_h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
                            temp_tex.setRamImageAs(sub_bytes, "RGBA")

                            # Convert to PNMImage for load_sub_image
                            sub_pnm = _PNMImage()
                            temp_tex.store(sub_pnm)

                            # Panda3D texture y=0 is at BOTTOM. Our RAM is un-flipped (pygame top-down),
                            # so RAM row 0 maps to panda_y = height-1. The sub-image's top edge
                            # (dirty_min) maps to panda_y = height - dirty_min - sub_h.
                            panda_y = sz[1] - dirty_min - sub_h
                            self._hud_composite_texture._texture.load_sub_image(sub_pnm, 0, panda_y)
                        except Exception:
                            # Fallback: full upload if load_sub_image fails
                            panda_tex.setRamImageAs(raw_data, "RGBA")
                    # else: no dirty rows (fingerprint false positive) — skip upload
                else:
                    # No previous data or size changed — full upload
                    panda_tex.setRamImageAs(raw_data, "RGBA")

                self._hud_prev_raw = raw_data

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
            self._hud_prev_raw = None

    def _add_wk30_debug_prefab_layout(self) -> None:
        """WK30 debug: place one of each prefab-backed building near the castle.

        Used by Agent 03 + Jaimie for prefab-fit iteration. Places castle + warrior /
        ranger / rogue / wizard guilds + inn + a house fully constructed in a row east of the
        castle so a single default-framed screenshot shows every prefab against the tile
        grid. Uses ``engine.building_factory`` so any future building-subclass wiring
        (occupancy, researchers, etc.) is consistent with the player-placed path.
        """
        engine = self.engine
        castle = next(
            (
                b
                for b in engine.buildings
                if getattr(b, "building_type", None) == "castle"
            ),
            None,
        )
        if castle is None:
            print("[wk30-debug-layout] no castle in engine; skipping prefab row")
            return

        factory = getattr(engine, "building_factory", None)
        if factory is None:
            print("[wk30-debug-layout] engine.building_factory missing; skipping")
            return

        # Anchor the row 2 tiles east of the castle's east edge, aligned with its north row.
        base_x = int(castle.grid_x) + int(castle.size[0]) + 2
        base_y = int(castle.grid_y)

        # (building_type, dx) — dx chosen to leave one tile of gap between footprints
        # (2x2 guilds at +0/+3/+6/+9, 3x2 inn at +12, 1x1 house at +16). House is not in BuildingFactory
        # (it's spawned by peasants, not the build menu), so build it via the base class.
        layout = [
            ("warrior_guild", 0),
            ("ranger_guild", 3),
            ("rogue_guild", 6),
            ("wizard_guild", 9),
            ("inn", 12),
            ("house", 16),
        ]
        only = os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT_ONLY", "").strip().lower()
        if only:
            layout = [(bts, dx) for (bts, dx) in layout if bts == only]
        from game.entities.buildings.base import Building
        from game.entities.buildings.types import BuildingType

        for bts, dx in layout:
            try:
                if bts == "house":
                    b = Building(base_x + dx, base_y, BuildingType.HOUSE)
                else:
                    b = factory.create(bts, base_x + dx, base_y)
                if b is None:
                    print(f"[wk30-debug-layout] factory returned None for {bts}")
                    continue
                if hasattr(b, "is_constructed"):
                    b.is_constructed = True
                if hasattr(b, "construction_started"):
                    b.construction_started = True
                engine.buildings.append(b)
                if hasattr(b, "set_event_bus") and getattr(engine, "event_bus", None):
                    b.set_event_bus(engine.event_bus)
            except Exception as exc:
                print(f"[wk30-debug-layout] skipped {bts}: {exc}")

        # Reveal the entire map so fog-of-war does not hide the test row.
        try:
            from game.world import Visibility

            world = engine.world
            for ty in range(int(world.height)):
                for tx in range(int(world.width)):
                    world.visibility[ty][tx] = Visibility.VISIBLE
            engine._fog_revision = int(getattr(engine, "_fog_revision", 0)) + 1
        except Exception as exc:
            print(f"[wk30-debug-layout] fog reveal failed: {exc}")

    def _install_worker_scale_comparison_shot(self) -> None:
        """Place one warrior + one peasant beside the castle for Ursina scale QA (see tools/run_worker_scale_ursina_shot.py)."""
        from config import TILE_SIZE

        from game.entities.hero import Hero
        from game.entities.peasant import Peasant

        eng = self.engine
        castle = next((b for b in eng.buildings if getattr(b, "building_type", "") == "castle"), None)
        if castle is None:
            print("[worker-scale-shot] no castle; skipping")
            return
        cx = float(getattr(castle, "center_x", 0.0))
        cy = float(getattr(castle, "center_y", 0.0))
        wx = cx + TILE_SIZE * 2.5
        wy = cy
        px = wx + TILE_SIZE * 1.0
        py = wy
        # Isolate one warrior vs one peasant (default match spawns many heroes + tax collector).
        eng.heroes.clear()
        eng.heroes.append(Hero(wx, wy, hero_class="warrior"))
        eng.peasants.clear()
        eng.peasants.append(Peasant(px, py))
        eng.tax_collector = None
        eng.enemies.clear()
        eng.guards.clear()
        setattr(eng.sim, "_worker_scale_shot_hold", True)
        if hasattr(eng, "screenshot_hide_ui"):
            eng.screenshot_hide_ui = True
        try:
            z = float(getattr(eng, "zoom", 1.0) or 1.0)
            eng.zoom = max(z, 2.25)
        except Exception:
            pass

    def _add_hero_fps_probe_layout(self, hero_count: int) -> None:
        """WK32 r5 debug: deterministic warrior guild + N warriors for renderer FPS probes."""
        engine = self.engine
        castle = next(
            (
                b
                for b in engine.buildings
                if getattr(b, "building_type", None) == "castle"
            ),
            None,
        )
        if castle is None:
            print("[hero-fps-probe] no castle in engine; skipping scenario")
            return

        try:
            from game.entities import WarriorGuild
            from game.entities.hero import Hero

            guild = WarriorGuild(int(castle.grid_x) - 4, int(castle.grid_y) + 2)
            guild.is_constructed = True
            guild.construction_started = True
            if hasattr(guild, "set_event_bus"):
                guild.set_event_bus(engine.event_bus)
            engine.buildings.append(guild)
            if os.environ.get("KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            ):
                neutral = getattr(engine, "neutral_building_system", None)
                if neutral is not None:
                    neutral.spawn_interval_sec = 999999.0

            for idx in range(max(0, int(hero_count))):
                hero = Hero(
                    guild.center_x + config.TILE_SIZE + (idx % 3) * 10,
                    guild.center_y + (idx // 3) * 10,
                    hero_class="warrior",
                )
                hero.home_building = guild
                engine.heroes.append(hero)

            # Keep the probe view deterministic without revealing the whole map; full-map
            # visibility would benchmark terrain draw count instead of hero-spawn cost.
            try:
                from game.world import Visibility

                world = engine.world
                cx = int(getattr(castle, "grid_x", 0))
                cy = int(getattr(castle, "grid_y", 0))
                radius = 14
                for ty in range(max(0, cy - radius), min(int(world.height), cy + radius + 1)):
                    for tx in range(max(0, cx - radius), min(int(world.width), cx + radius + 1)):
                        world.visibility[ty][tx] = Visibility.VISIBLE
                engine._fog_revision = int(getattr(engine, "_fog_revision", 0)) + 1
            except Exception:
                pass

            print(f"[hero-fps-probe] spawned warrior_guild heroes={len(engine.heroes)}")
        except Exception as exc:
            print(f"[hero-fps-probe] setup failed: {exc}")

    def _record_fps_probe_sample(self, dt: float) -> None:
        if not self._fps_probe_enabled:
            return
        self._fps_probe_elapsed += float(dt or 0.0)
        if self._fps_probe_elapsed < self._fps_probe_warmup_sec:
            return
        if dt > 1e-9:
            self._fps_probe_samples.append(1.0 / float(dt))

    def _record_fps_probe_stage_ms(self, name: str, started_at: float) -> None:
        if not self._fps_probe_enabled or self._fps_probe_elapsed < self._fps_probe_warmup_sec:
            return
        self._fps_probe_stage_samples.setdefault(name, []).append((pytime.perf_counter() - started_at) * 1000.0)

    def _print_fps_probe_summary(self) -> None:
        if not self._fps_probe_enabled:
            return
        samples = list(self._fps_probe_samples)
        if not samples:
            print("[fps-probe] no samples collected")
            return
        samples.sort()
        avg = sum(samples) / len(samples)
        p10 = samples[max(0, int(len(samples) * 0.10) - 1)]
        p50 = samples[max(0, int(len(samples) * 0.50) - 1)]
        p90 = samples[max(0, int(len(samples) * 0.90) - 1)]
        print(
            "[fps-probe] "
            f"heroes={len(getattr(self.engine, 'heroes', []))} "
            f"frames={len(samples)} "
            f"avg_fps={avg:.1f} "
            f"min_fps={samples[0]:.1f} "
            f"p10_fps={p10:.1f} "
            f"p50_fps={p50:.1f} "
            f"p90_fps={p90:.1f} "
            f"max_fps={samples[-1]:.1f}"
        )
        for name, values in sorted(self._fps_probe_stage_samples.items()):
            vals = sorted(values)
            if not vals:
                continue
            avg_ms = sum(vals) / len(vals)
            p90_ms = vals[max(0, int(len(vals) * 0.90) - 1)]
            print(
                "[fps-probe-stage] "
                f"{name} frames={len(vals)} avg_ms={avg_ms:.3f} "
                f"p90_ms={p90_ms:.3f} max_ms={vals[-1]:.3f}"
            )

    def _maybe_auto_screenshot_then_quit(self) -> None:
        """WK30 debug: save one screenshot (if a path was requested) and quit Ursina.

        Uses the **synchronous** ``base.win.getScreenshot()`` + ``PNMImage.write()`` path
        rather than ``base.screenshot(...)`` which queues the write for a later frame
        (the async queue never drains before ``application.quit()`` exits the process).
        """
        try:
            from ursina import application

            base = getattr(application, "base", None)
            if base is not None:
                try:
                    base.graphicsEngine.renderFrame()
                    base.graphicsEngine.renderFrame()
                except Exception:
                    pass
            self._print_fps_probe_summary()
            if self._auto_screenshot_path and base is not None:
                out_path = os.path.abspath(self._auto_screenshot_path)
                out_dir = os.path.dirname(out_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                ok = self._save_window_screenshot_sync(base, out_path)
                if ok and os.path.isfile(out_path):
                    print(f"[auto-screenshot] Saved: {out_path}")
                else:
                    print(f"[auto-screenshot] Failed to write: {out_path}")
            try:
                application.quit()
            except Exception:
                import sys

                sys.exit(0)
        except Exception as exc:
            print(f"[auto-exit] Aborted: {exc}")

    @staticmethod
    def _save_window_screenshot_sync(base, out_path: str) -> bool:
        """Grab the main GraphicsWindow framebuffer into a PNMImage and write it now.

        Unlike ``base.screenshot()`` this does not schedule a future write — the image
        bytes are pulled synchronously and written in the same call. Works from a
        shutdown path where we are about to ``application.quit()``.
        """
        try:
            from panda3d.core import Filename, PNMImage

            tex = base.win.getScreenshot()
            if tex is None:
                print("[auto-screenshot] getScreenshot returned None")
                return False
            img = PNMImage()
            if not tex.store(img):
                print("[auto-screenshot] Texture.store failed")
                return False
            fn = Filename.fromOsSpecific(out_path)
            return bool(img.write(fn))
        except Exception as exc:
            print(f"[auto-screenshot] Sync capture failed: {exc}")
            return False

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
            self.renderer.update(snapshot)
            self._record_fps_probe_stage_ms("ursina_renderer", _stage_t0)

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

            # WK53 R3: Camera terrain clamp — prevent camera from clipping below the
            # terrain surface when orbiting/panning. Sample terrain height at the
            # camera's world XZ position and enforce a minimum Y offset above ground.
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
