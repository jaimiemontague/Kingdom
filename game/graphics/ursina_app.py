"""
Basic 3D Viewer application using Ursina.
Wraps the core headless simulation and visualizes it with a perspective camera
on the X/Z floor plane; Pygame UI is composited on camera.ui (separate UI camera).
"""
from __future__ import annotations

import gc
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

        # Mythos S1 (`vsync-off`): Panda's default ``sync-video`` is TRUE and quantizes
        # every frame up to a vblank multiple (16.7/33.3ms at 60Hz) — measured ~10-16ms
        # of pure present-wait per frame at exactly the 30fps gate. Ursina 8.3.0's
        # ``Ursina(vsync=...)`` kwarg is dead code (window._ready never consumes it, and
        # ``apply_settings`` re-sets vsync=True post-open; runtime disable is
        # unimplemented — window.py:497-508), so the ONLY working lever is the prc store
        # BEFORE the window opens. Env hatch ``KINGDOM_VSYNC=1`` restores stock vsync
        # for A/B soaks. With vsync off, light scenes (menus) would spin uncapped, so we
        # also set a sleep-based frame cap (``clock-mode limited`` — caps without
        # quantizing: a frame slower than the cap interval is never rounded up).
        # ``KINGDOM_FPS_CAP`` overrides the cap (default 60; 0 = uncapped).
        self._vsync_enabled = os.environ.get("KINGDOM_VSYNC", "").strip() == "1"
        if not self._vsync_enabled:
            from panda3d.core import loadPrcFileData
            loadPrcFileData("kingdom-perf", "sync-video false")
            try:
                _fps_cap = float(os.environ.get("KINGDOM_FPS_CAP", "").strip() or 60.0)
            except ValueError:
                _fps_cap = 60.0
            if _fps_cap > 0:
                loadPrcFileData("kingdom-perf", "clock-mode limited")
                loadPrcFileData("kingdom-perf", f"clock-frame-rate {_fps_cap:g}")

        # Mythos S2 (text-font-cache-patch): patch ursina.Text's font/resolution
        # class properties BEFORE the first Text exists (Ursina() itself creates the
        # window fps-counter Text). Stock Text() re-runs FontPool.load_font AND
        # appends a duplicate directory to Panda's global model-path on EVERY label
        # (5-21 ms each, degrading over the session as the path grows) — the unit
        # spawn micro-hitch root cause. The patch memoizes the shared font object
        # once; rendering is pixel-identical (FontPool already shares one font
        # object per name — see game/graphics/ursina_text_font_cache.py).
        try:
            from game.graphics.ursina_text_font_cache import apply_text_font_cache_patch
            _font_patched = apply_text_font_cache_patch()
            print(f"[prewarm] ursina Text font-cache patch applied: {_font_patched}")
        except Exception as _e:
            print(f"[prewarm] ursina Text font-cache patch skipped: {_e}")

        self.app = Ursina(
            title='Kingdom Sim - Ursina 3D Viewer',
            borderless=False,
            fullscreen=False,
            # WK22 R3: dev mode runs extra bookkeeping that can hitch the main thread
            # (and audiostream / music) on a steady cadence.
            development_mode=False,
        )
        # Mythos S1 (`vsync-off`): re-assert AFTER Ursina() returns — ursina's
        # ``window.apply_settings`` (window.py:82) writes ``sync-video true`` back into
        # the prc store during init, which would silently re-enable vsync on any GL
        # context rebuild (e.g. a fullscreen toggle). The already-open window keeps the
        # boot-time setting; this keeps the store consistent for rebuilds.
        if not self._vsync_enabled:
            from panda3d.core import loadPrcFileData
            loadPrcFileData("kingdom-perf", "sync-video false")
        # One-line boot state for soak logs (A/B forensics).
        try:
            from panda3d.core import ConfigVariableBool
            _sv = bool(ConfigVariableBool("sync-video"))
        except Exception:
            _sv = self._vsync_enabled  # best-effort fallback: report the requested state
        from game.graphics.ursina_scene_ignore import mark_scene_ignore, scene_ignore_enabled
        print(
            f"[mythos] vsync={'on' if _sv else 'off'} "
            f"(KINGDOM_VSYNC={os.environ.get('KINGDOM_VSYNC', '') or 'unset'}) "
            f"scene_ignore={'on' if scene_ignore_enabled() else 'off'} "
            f"(KINGDOM_SCENE_IGNORE={os.environ.get('KINGDOM_SCENE_IGNORE', '') or 'unset'})",
            flush=True,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True
        # Mythos S1 (`scene-entities-ignore`): Kingdom has ZERO world colliders (picking
        # is analytic — ursina_pick.py), yet ursina's mouse.update runs two
        # CollisionTraverser passes + an unhover scan per frame. ``traverse_target=None``
        # is the escape hatch ursina documents (mouse.py:39). Same env gate as the
        # entity-ignore marks.
        if scene_ignore_enabled():
            try:
                mouse.traverse_target = None
            except Exception:
                pass

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
        # WK121: per-frame zone-fog caches (avoid buildings scan + get_zone each frame).
        # _zone_fog_castle_xy assumes a static castle center (grid_x/grid_y are set
        # once in Building.__init__ and never reassigned); _zone_fog_last_tile gates
        # the get_zone() recompute to integer camera-tile changes.
        self._zone_fog_castle_xy: tuple[int, int] | None = None
        self._zone_fog_last_tile: tuple[int, int] | None = None

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
        # Mythos S1 (`scene-entities-ignore`): the HUD quad has no update/input — skip
        # it in ursina's per-frame entity walk (texture refresh is explicit in run_frame).
        mark_scene_ignore(self.ui_overlay)

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
        # Stationary-pointer/camera cache for _engine_screen_pos_for_pointer (per-frame perf).
        # Key captures raw pointer + camera/zoom + 3D camera transform + paused/menu flags;
        # when unchanged the floor raycast / HUD layout / game-state build are skipped.
        self._pointer_cache_key = None
        self._pointer_cache_result = None
        self._pointer_cache_world_sim = None
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
        # Mythos S0 (`gate-measurement-harness`): optional wall-clock acceptance window.
        # KINGDOM_URSINA_FPS_WINDOW_SEC="900:1200" -> on exit, the probe summary emits a
        # single greppable "[fps-probe-window 900:1200] ..." line with avg/p10/p50/min
        # fps computed ONLY from frames inside that window (whole-run percentiles
        # overstate the minute-15..20 gate 2-3x on a 20-min soak). Dead unless both this
        # env and KINGDOM_URSINA_FPS_PROBE are set.
        self._fps_probe_window_sec = self._parse_fps_probe_window_env()
        self._fps_probe_window_samples: list[float] = []
        # Mythos S0: igLoop bracket state (sort-49/51 tasks around Panda's igLoop@50);
        # installed lazily by run_frame only when slowlog/probe instrumentation is on.
        self._igloop_bracket_installed = False
        self._igloop_last_ms = 0.0

        # WK122 perf: the per-frame loop allocates ~130 DTOs + profile snapshots; the
        # default gen0 threshold (700) triggers very frequent collections → periodic
        # frame-time stutter. Raise thresholds so collections are far rarer. A one-time
        # gc.freeze() (in run_frame, after the static scene is built) excludes the permanent
        # terrain/tree heap from gen2 scans. Behavior-preserving (garbage is still collected).
        gc.set_threshold(50000, 500, 1000)
        self._gc_frozen = False
        self._gc_frame_count = 0

        # WK122 perf: prewarm the Panda3D model cache for every building-prefab piece mesh.
        # Neutral buildings spawn during gameplay (~every 6s) and cross construction bands
        # (plot -> build_20 -> build_50 -> final), each swapping a prefab JSON whose first
        # Entity(model=...) would cold-parse its .glb on the render thread (a single-frame
        # FPS dip). Loading each unique piece model once here (Ursina app + model-path are
        # ready above) moves those cold parses off the gameplay hot path. Behavior-preserving
        # (identical models, just cached earlier). Wrapped so a prewarm failure never blocks startup.
        try:
            from game.graphics.ursina_prefabs import prewarm_building_prefab_models
            _warmed = prewarm_building_prefab_models()
            print(f"[prewarm] building prefab models warmed: {_warmed}")
        except Exception as _e:
            print(f"[prewarm] building prefab model prewarm skipped: {_e}")

        # Mythos S2 (unit-prewarm-extension): warm the remaining cold first-spawn
        # assets so the FIRST hero/arrow/label of a session doesn't hitch — the
        # 2048x2048 unit atlas (measured 269ms CPU + ~16MB GPU upload on the first
        # unit render), the three projectile/magic/heal billboard textures (first
        # volley), the Text font + glyph pages + overlay quad render states (first
        # label), and — when KINGDOM_URSINA_INSTANCING=1 — the instanced unit
        # renderer's shaders/buffer textures. Uses NodePath.prepare_scene (no frame
        # rendered, nothing can flash). Behavior-preserving: identical assets, just
        # created at load time; bounded (~0.3-0.5s). Never blocks startup.
        try:
            from game.graphics.ursina_prewarm import prewarm_unit_spawn_assets
            _warm_stats = prewarm_unit_spawn_assets(renderer=self.renderer, base=self.app)
            print(f"[prewarm] unit spawn assets warmed: {_warm_stats}")
        except Exception as _e:
            print(f"[prewarm] unit spawn asset prewarm skipped: {_e}")

    @staticmethod
    def _parse_fps_probe_window_env() -> tuple[float, float] | None:
        """Parse KINGDOM_URSINA_FPS_WINDOW_SEC="<lo>:<hi>" (seconds) -> (lo, hi) | None."""
        raw = os.environ.get("KINGDOM_URSINA_FPS_WINDOW_SEC", "").strip()
        if not raw or ":" not in raw:
            return None
        try:
            lo_s, hi_s = raw.split(":", 1)
            lo, hi = float(lo_s), float(hi_s)
        except ValueError:
            return None
        if hi <= lo or lo < 0.0:
            return None
        return (lo, hi)

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
        def update():
            from game.graphics import ursina_app_frame
            ursina_app_frame.run_frame(self, time.dt)

        import __main__

        __main__.update = update
        self.app.run()
