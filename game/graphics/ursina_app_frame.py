"""WK118: the per-frame update() loop extracted from ursina_app.py's run() (owner-arg
pure-move). UrsinaApp.run() keeps a thin update() shim that calls run_frame(self, time.dt).
Byte-faithful move — no behavior change."""
from __future__ import annotations

import os
import time as pytime
from typing import TYPE_CHECKING

import config
from ursina import Vec3, camera, held_keys, mouse

from game.graphics.ursina_input_debug import is_ursina_debug_input_enabled, print_wk20_input_line
from game.input_manager import InputEvent

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in the shim)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


def _ensure_igloop_bracket(owner) -> None:
    """Mythos S0 (`gate-measurement-harness`): bracket Panda's ``igLoop`` task with two
    tiny taskMgr tasks at sort 49/51. ``igLoop`` (stock ShowBase sort 50) is the C++
    cull + draw + buffer-swap + vsync/present wait — the whole "dt minus run_frame CPU"
    block the slowlog could never attribute. The post task (sort 51) stores the elapsed
    ms on ``owner._igloop_last_ms`` (read by run_frame's [frameavg]/[slowframe2] lines —
    one frame stale there, since this frame's igLoop runs AFTER run_frame returns) and
    appends an ``igloop`` stage sample for the KINGDOM_URSINA_FPS_PROBE summary/soak CSV.

    Installed lazily on the first instrumented frame; dead-by-default — run_frame only
    calls this when KINGDOM_FPS_SLOWLOG or KINGDOM_URSINA_FPS_PROBE is set. One-time
    sanity check: if igLoop is not found at sort 50 (non-stock taskMgr), the bracket is
    NOT installed (a misplaced bracket would attribute the wrong tasks).
    """
    if getattr(owner, "_igloop_bracket_installed", False):
        return
    owner._igloop_bracket_installed = True
    owner._igloop_last_ms = 0.0
    try:
        from direct.task.TaskManagerGlobal import taskMgr
        from direct.task import Task

        ig_tasks = taskMgr.getTasksNamed("igLoop")
        ig_sort = ig_tasks[0].getSort() if ig_tasks else None
        if ig_sort != 50:
            print(
                f"[mythos] igloop bracket NOT installed (igLoop sort={ig_sort!r}, expected 50)",
                flush=True,
            )
            return

        state = {"t0": 0.0}

        def _igloop_pre(task):
            state["t0"] = pytime.perf_counter()
            return Task.cont

        def _igloop_post(task):
            t0 = state["t0"]
            if t0 > 0.0:
                owner._igloop_last_ms = (pytime.perf_counter() - t0) * 1000.0
                try:
                    owner._record_fps_probe_stage_ms("igloop", t0)
                except Exception:
                    pass
            return Task.cont

        taskMgr.add(_igloop_pre, "kingdom-igloop-pre", sort=49)
        taskMgr.add(_igloop_post, "kingdom-igloop-post", sort=51)
        print("[mythos] igloop bracket installed (sorts 49/51 around igLoop@50)", flush=True)
    except Exception as exc:
        print(f"[mythos] igloop bracket install failed: {exc}", flush=True)


def run_frame(owner: "UrsinaApp", dt) -> None:
    pan_speed = 55.0

    # WK122 perf: one-time gc.freeze() after the static scene is built. The terrain mesh
    # + ~2083 tree objects + initial buildings build lazily on the first renderer.update,
    # so wait ~90 frames (a few seconds) before freezing — comfortably after the one-time
    # build but while few transient objects exist. freeze() moves the long-lived static
    # heap into the permanent generation, excluding it from every subsequent gen2 scan.
    # Behavior-preserving: new per-frame DTOs are created AFTER the freeze and still collect.
    if not owner._gc_frozen:
        owner._gc_frame_count += 1
        if owner._gc_frame_count >= 90:
            import gc
            gc.collect()
            gc.freeze()  # move the static terrain/tree/startup heap to the permanent gen — excluded from future gen2 scans
            owner._gc_frozen = True

    # WK122 (diagnostic, env-gated, dead-by-default): per-frame timing logger.
    # NO-OP unless KINGDOM_FPS_SLOWLOG is set — changes NO behavior.
    _slowlog = os.environ.get("KINGDOM_FPS_SLOWLOG", "") not in ("", "0")
    _slow_t0 = pytime.perf_counter() if _slowlog else 0.0
    _d_tick = 0.0
    _d_renderer = 0.0
    _d_hudrender = 0.0
    _d_hudupload = 0.0
    # Mythos S0 (`gate-measurement-harness`): time the previously-untracked blocks.
    # ``_d_cam`` sums the three camera/fog/pointer CPU sub-blocks inside run_frame
    # (canvas-sync + pointer-motion pre-tick; zoom/FOV mid-block; pan/terrain-clamp/
    # auto-follow/zone-fog post-HUD) and the igLoop bracket (installed below) covers
    # the Panda cull/draw/swap/present wait OUTSIDE run_frame. Both are dead-by-default
    # behind the SAME existing env flags (KINGDOM_FPS_SLOWLOG / KINGDOM_URSINA_FPS_PROBE).
    _timing = _slowlog or bool(getattr(owner, "_fps_probe_enabled", False))
    _d_cam = 0.0
    if _timing and not getattr(owner, "_igloop_bracket_installed", False):
        _ensure_igloop_bracket(owner)
    _cam_t0 = pytime.perf_counter() if _timing else 0.0

    eng = owner.engine

    def _chat_captures_keyboard() -> bool:
        """True while hero chat or command mode is open — block 3D pan/zoom so keys type into input."""
        if getattr(eng, '_command_mode', False):
            return True
        cp = getattr(getattr(eng, "hud", None), "_chat_panel", None)
        return cp is not None and getattr(cp, "is_active", lambda: False)()

    # WK22 R3: dynamic HUD resolution — match pygame surface to Ursina window (no fixed 1080p GPU stretch).
    owner._sync_headless_ui_canvas_to_window()

    # 1) Motion every frame (HUD hover, building preview validity).
    owner._queue_pointer_motion_event()
    # 2) Same-frame click after motion (placement reads preview_valid).
    if owner._pending_lmb:
        owner._pending_lmb = False
        vpos = owner._virtual_screen_pos()
        hud = getattr(eng, "hud", None)
        if hud is not None and hasattr(hud, "handle_sidebar_split_pointer_down"):
            try:
                hud.handle_sidebar_split_pointer_down(vpos, eng.get_game_state())
            except Exception:
                pass
        pos = owner._pointer_event_pos()
        if not owner._sidebar_split_drag_active():
            owner.input_manager.queue_event(
                InputEvent(type="MOUSEDOWN", button=1, pos=pos, key=None)
            )
        if is_ursina_debug_input_enabled():
            from config import TILE_SIZE

            _p, kind, hit, wx_sim, wy_sim = owner._engine_screen_pos_for_pointer()
            tile = None
            if hit is not None:
                tile = (int(wx_sim // TILE_SIZE), int(wy_sim // TILE_SIZE))
            print_wk20_input_line(
                raw_sx=float(mouse.x),
                raw_sy=float(mouse.y),
                pygame_x=owner.input_manager.get_mouse_pos()[0],
                pygame_y=owner.input_manager.get_mouse_pos()[1],
                ui_hit=kind,
                world_xz=hit,
                tile=tile,
            )

    if _timing:  # close cam sub-block 1 (canvas sync + pointer motion + pending click)
        _d_cam += (pytime.perf_counter() - _cam_t0) * 1000.0

    _stage_t0 = pytime.perf_counter()
    owner.engine.tick_simulation(dt)
    owner._record_fps_probe_stage_ms("tick_simulation", _stage_t0)
    if _slowlog:
        _d_tick = (pytime.perf_counter() - _stage_t0) * 1000.0
    owner.engine._last_frame_dt_ms = float(dt or 0.0) * 1000.0

    if getattr(owner, "_worker_scale_shot_reattach", 0) > 0:
        owner._worker_scale_shot_reattach -= 1
        owner._install_worker_scale_comparison_shot()

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
    owner._record_fps_probe_sample(float(dt or 0.0))

    # Pause menu Quit sets engine.running = False; Pygame's engine.run() exits the process —
    # Ursina must stop app.run() explicitly or the window stays open forever.
    if not getattr(owner.engine, "running", True):
        try:
            from ursina import application

            application.quit()
        except Exception:
            import sys

            sys.exit(0)
        return

    # WK30 debug: auto-screenshot + auto-exit for prefab iteration.
    if (
        not owner._auto_exit_triggered
        and owner._auto_exit_deadline_sec > 0.0
    ):
        owner._auto_exit_elapsed += float(dt or 0.0)
        if owner._auto_exit_elapsed >= owner._auto_exit_deadline_sec:
            owner._auto_exit_triggered = True
            owner._maybe_auto_screenshot_then_quit()
            return

    if _timing:  # open cam sub-block 2 (zoom keys + FOV sync + dolly align)
        _cam_t0 = pytime.perf_counter()

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

    owner._sync_ursina_camera_fov_from_zoom()
    # Keep EditorCamera dolly target aligned — zoom is FOV-driven from engine.zoom, not trackball dolly.
    ecam = getattr(owner, "_editor_camera", None)
    if ecam is not None:
        ecam.target_z = camera.z

    if _timing:  # close cam sub-block 2
        _d_cam += (pytime.perf_counter() - _cam_t0) * 1000.0

    _stage_t0 = pytime.perf_counter()
    snapshot = owner.engine.build_snapshot()
    # WK67 Move 4 / L6: presentation timing/camera/selection are no longer on
    # the sim snapshot — build the per-frame presentation state and pass both.
    frame = owner.engine.build_presentation_frame()
    owner.renderer.update(snapshot, frame)
    owner._record_fps_probe_stage_ms("ursina_renderer", _stage_t0)
    if _slowlog:
        _d_renderer = (pytime.perf_counter() - _stage_t0) * 1000.0

    # WK58 Agent 10 (cross-domain, scoped): auto-reveal hook for perf_render_benchmark
    # and tools/run_ursina_capture_once.py --reveal-map. Fires once when env flag is set.
    if (
        not getattr(owner, "_auto_reveal_done", False)
        and os.environ.get("KINGDOM_URSINA_REVEAL_ON_START", "").strip() == "1"
    ):
        owner._auto_reveal_done = True
        owner.engine.process_command("/revealmap")

    _stage_t0 = pytime.perf_counter()
    owner.engine.render_pygame()
    owner._record_fps_probe_stage_ms("pygame_hud_render", _stage_t0)
    if _slowlog:
        _d_hudrender = (pytime.perf_counter() - _stage_t0) * 1000.0
    _stage_t0 = pytime.perf_counter()
    owner._refresh_ui_overlay_texture()
    owner._record_fps_probe_stage_ms("hud_texture_upload", _stage_t0)
    if _slowlog:
        _d_hudupload = (pytime.perf_counter() - _stage_t0) * 1000.0
    # Fullscreen ↔ windowed toggles with a static HUD skip texture upload; still resync filter.
    owner._sync_hud_texture_filter_mode(owner._hud_composite_texture)

    if _timing:  # open cam sub-block 3 (pan + layer lerp + terrain clamp + follow + zone fog)
        _cam_t0 = pytime.perf_counter()

    # Pan parallel to X/Z floor (world units / sec). Skip while typing in hero chat.
    if not _chat_captures_keyboard():
        ecam = getattr(owner, "_editor_camera", None)
        try:
            orbiting = bool(getattr(mouse, "right", False)) and not getattr(owner, '_camera_orbit_locked', False)
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
    if owner._camera_transitioning and owner._camera_transition_target_y is not None:
        dy = owner._camera_transition_target_y - camera.y
        if abs(dy) < 0.5:
            camera.y = owner._camera_transition_target_y
            owner._camera_transitioning = False
            owner._camera_transition_target_y = None
        else:
            step = owner._camera_transition_speed * dt
            camera.y += step if dy > 0 else -step

    # WK53 R3: Camera terrain clamp — prevent camera from clipping below the
    # terrain surface when orbiting/panning. Sample terrain height at the
    # camera's world XZ position and enforce a minimum Y offset above ground.
    # WK57 Wave 3: Skip terrain clamp when camera is underground or transitioning.
    if not owner._camera_transitioning and owner._camera_active_layer == 0:
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
    if not owner._camera_transitioning:
        try:
            _hud = getattr(eng, 'hud', None)
            _ps = getattr(_hud, '_pin_slot', None) if _hud else None
            _ph_id = getattr(_ps, 'hero_id', None) if _ps else None
            if _ph_id is not None:
                _ph = eng._find_hero_by_id(_ph_id)
                _ph_layer = getattr(_ph, 'layer', 0) if _ph is not None else 0
                _prev_layer = owner._hero_follow_last_layer
                if _prev_layer is not None and _ph_layer != _prev_layer:
                    if _ph_layer == -1 and owner._camera_active_layer == 0:
                        # Hero entered underground — follow
                        from config import UNDERGROUND_DEPTH
                        owner.begin_camera_underground_transition(-(UNDERGROUND_DEPTH - 3.0))
                        print("Camera: Auto-follow underground", flush=True)
                        if _hud:
                            _hud.add_message("Camera: Following hero underground", (100, 200, 255))
                    elif _ph_layer == 0 and owner._camera_active_layer == -1:
                        # Hero returned to surface — follow
                        owner.begin_camera_surface_transition()
                        print("Camera: Auto-follow surface", flush=True)
                        if _hud:
                            _hud.add_message("Camera: Following hero to surface", (100, 200, 255))
                owner._hero_follow_last_layer = _ph_layer
            else:
                owner._hero_follow_last_layer = None
        except Exception:
            pass

    # WK57 Wave 3: Pass camera active layer to renderer for entity visibility
    _renderer = getattr(owner, 'renderer', None)
    if _renderer is not None:
        _renderer._camera_active_layer = owner._camera_active_layer

    # WK57/58: Zone-specific fog color based on camera position
    try:
        owner.update_zone_fog_color(
            float(camera.world_position.x),
            float(camera.world_position.z),
        )
    except Exception:
        pass

    if _timing:
        # Close cam sub-block 3 and record the per-frame ``cam`` stage sample for the
        # FPS probe (synthetic started_at because the stage is the SUM of three
        # non-contiguous sub-blocks; the recorder computes now - started_at).
        _d_cam += (pytime.perf_counter() - _cam_t0) * 1000.0
        owner._record_fps_probe_stage_ms("cam", pytime.perf_counter() - _d_cam / 1000.0)

    # WK122 (diagnostic, env-gated, dead-by-default): per-frame timing summary.
    if _slowlog:
        _total_ms = (pytime.perf_counter() - _slow_t0) * 1000.0
        _dt_ms = float(dt or 0.0) * 1000.0
        _cpu_sum = _d_tick + _d_renderer + _d_hudrender + _d_hudupload
        _untracked = _total_ms - _cpu_sum
        # Mythos S0: igLoop time is measured by the sort-49/51 bracket AROUND the base
        # frame step, so the freshest completed value is the PREVIOUS frame's (this
        # frame's igLoop runs after run_frame returns). Negligible drift over the
        # 120-frame [frameavg] window.
        _igl_prev = float(getattr(owner, "_igloop_last_ms", 0.0) or 0.0)
        eng = owner.engine
        try:
            _ne = len([e for e in getattr(eng, "enemies", []) if getattr(e, "is_alive", True)])
        except Exception:
            _ne = -1
        _nb = len(getattr(eng, "buildings", []) or [])
        _nh = len(getattr(eng, "heroes", []) or [])
        # rolling accumulators for a periodic summary
        owner._slowlog_frames = getattr(owner, "_slowlog_frames", 0) + 1
        owner._slowlog_accum = getattr(owner, "_slowlog_accum", None) or {"dt":0.0,"tick":0.0,"rend":0.0,"hudr":0.0,"hudu":0.0,"untr":0.0,"cam":0.0,"igl":0.0}
        a = owner._slowlog_accum
        a["dt"] += _dt_ms; a["tick"] += _d_tick; a["rend"] += _d_renderer
        a["hudr"] += _d_hudrender; a["hudu"] += _d_hudupload; a["untr"] += _untracked
        a["cam"] = a.get("cam", 0.0) + _d_cam; a["igl"] = a.get("igl", 0.0) + _igl_prev
        # Per-slow-frame line (frames slower than ~40ms = sub-25fps)
        if _dt_ms > 40.0:
            print(f"[slowframe] dt={_dt_ms:.1f}ms run_frame_cpu={_total_ms:.1f} tick={_d_tick:.1f} rend={_d_renderer:.1f} hudR={_d_hudrender:.1f} hudU={_d_hudupload:.1f} cam={_d_cam:.1f} untracked={_untracked:.1f} | enemies={_ne} buildings={_nb} heroes={_nh}", flush=True)
            print(f"[slowframe2] gpu_or_ursina={_dt_ms - _total_ms:.1f}ms (dt - run_frame_cpu) igl_prev={_igl_prev:.1f}ms", flush=True)
        # Periodic rolling summary every 120 frames
        if owner._slowlog_frames % 120 == 0:
            n = 120.0
            print(f"[frameavg] over {int(n)}f: dt={a['dt']/n:.1f}ms (=~{1000.0*n/max(a['dt'],1e-6):.1f}fps) | tick={a['tick']/n:.1f} rend={a['rend']/n:.1f} hudR={a['hudr']/n:.1f} hudU={a['hudu']/n:.1f} cam={a.get('cam',0.0)/n:.1f} igl={a.get('igl',0.0)/n:.1f} untracked={a['untr']/n:.1f} | E={_ne} B={_nb}", flush=True)
            for k in a: a[k] = 0.0
