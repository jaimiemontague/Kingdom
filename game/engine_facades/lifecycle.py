"""Per-frame lifecycle (update / sim-tick accumulator) — mechanical facade.

WK78 Round B-2f: these are pure mechanical moves of the GameEngine per-frame
lifecycle methods (WK75/76 pattern). Each function takes the live ``GameEngine``
as ``engine``; the body is the original method body with ``self.`` rewritten to
``engine.``. ``game.engine`` keeps 1-line delegating wrappers, so all call sites
(``run()`` -> ``self.update()``; the ursina/pygame loop -> ``self.tick_simulation()``)
and tests are unchanged. Behavior is byte-identical.

When a moved method calls another moved method, the call routes through
``engine.<name>(...)`` (the wrapper) so the delegation seam stays single and the
frame-step order is preserved exactly.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from game.sim.timebase import get_time_multiplier

if TYPE_CHECKING:
    from game.engine import GameEngine

# Mythos S5 (fast-dt-scaling) — DEFAULT OFF (KINGDOM_FAST_DT_SCALING=1 enables).
# Speed tiers normally multiply ACCUMULATED time, not tick size: FAST (1.0)
# drains 20 fixed 50ms ticks per wall-second vs NORMAL's 10, doubling per-tick
# sim CPU at exactly the player's real condition. With this flag, speeds above
# NORMAL scale the tick dt instead (FAST: 10 ticks/s of dt=0.1, clamped at 0.1s)
# — the same sim seconds per wall second, at half the tick count. The effective
# step is published as an INSTANCE ``_FIXED_SIM_DT`` so the render interpolation
# (engine.build_presentation_frame blend = accumulator / _FIXED_SIM_DT) and the
# backlog clamp stay consistent. OFF by default because it coarsens combat/AI dt
# granularity at FAST (a real-play behavior change needing a balance soak) and
# no headless gate exercises this path (the WK67 digest and observe_sync's
# speed-scaling scenarios drive engine.update / the sim directly, bypassing this
# accumulator) — so green gates could not certify it. Flip the env to A/B it in
# the live soak.
_FAST_DT_SCALING = os.environ.get("KINGDOM_FAST_DT_SCALING", "0") == "1"
_FAST_DT_MAX_STEP = 0.1  # never coarser than 100ms sim steps
try:
    from config import SPEED_NORMAL as _SPEED_NORMAL
except Exception:
    _SPEED_NORMAL = 0.5


def update(engine: "GameEngine", dt: float):
    """Update game state."""
    if not engine._prepare_sim_and_camera(dt):
        engine._flush_event_bus()
        return

    game_state = engine.get_game_state()

    # Stage 2: sim update loop lives in SimEngine.
    engine.sim.update(dt, game_state)

    # WK62 Task B: Redundant _cleanup_destroyed_buildings() call removed.
    # SimEngine.update() already performs authoritative destroyed-building
    # cleanup (rubble creation, reference clearing, event emission).
    # GameEngine._cleanup_destroyed_buildings() remains available for
    # on-demand demolish actions (confirm_demolish, GameCommands).

    # Presentation chores stay here for now.
    engine._update_render_animations(dt)
    engine._finalize_update(dt)
    engine._poll_conversation_response()


def _prepare_sim_and_camera(engine: "GameEngine", dt: float) -> bool:
    """Check pause/menu state and update camera. Returns True if sim should tick.

    WK62 Task A: Sim time advancement removed from here. SimEngine.update()
    is the single authoritative owner of _sim_now_ms. GameEngine decides
    WHETHER to tick the sim, but never mutates sim time.
    """
    # wk12 Chronos: speed-tier pause (multiplier 0) or menu pause → no sim (return False). Camera still pans when paused (not when menu open).
    if get_time_multiplier() == 0.0 or engine.paused:
        if not getattr(engine.pause_menu, "visible", False):
            camera_dt = getattr(engine, "_camera_dt", dt)
            engine.update_camera(camera_dt)
        return False
    # V1.3-EXT-BUG-001: Do not move camera/zoom while menu open.
    if getattr(engine.pause_menu, "visible", False):
        return False
    # Camera uses wall-clock dt for responsiveness; sim uses scaled dt (already passed in as dt).
    camera_dt = getattr(engine, "_camera_dt", dt)
    engine.update_camera(camera_dt)
    return True


def _update_render_animations(engine: "GameEngine", dt: float):
    """Advance render-only entity animation state."""
    if engine.headless:
        return
    # Ursina runs after this call; pygame HeroRenderer/EnemyRenderer clear
    # _render_anim_trigger here. Snapshot one-shots so Ursina billboards can still play attack/hurt.
    if getattr(engine, "_ursina_skip_world_render", False):
        for hero in engine.heroes:
            t = getattr(hero, "_render_anim_trigger", None)
            if t:
                hero._ursina_anim_trigger = str(t)
        for enemy in engine.enemies:
            t = getattr(enemy, "_render_anim_trigger", None)
            if t:
                enemy._ursina_anim_trigger = str(t)
        for guard in engine.guards:
            t = getattr(guard, "_render_anim_trigger", None)
            if t:
                guard._ursina_anim_trigger = str(t)
    engine.renderer_registry.update_animations(
        dt=dt,
        heroes=engine.heroes,
        enemies=engine.enemies,
        peasants=engine.peasants,
        tax_collector=engine.tax_collector,
        guards=engine.guards,
    )


def tick_simulation(engine: "GameEngine", dt: float) -> tuple[float, float]:
    """
    Advance the game simulation using a fixed-rate accumulator loop.
    The sim runs at 20 Hz regardless of render frame rate; the accumulator
    carries leftover time to the next frame for natural interpolation.
    Returns a tuple of (events_ms, update_ms) covering ALL ticks this frame.
    """
    # Apply any queued display settings change at a safe point (outside event polling).
    pending = getattr(engine, "_pending_display_settings", None)
    if pending:
        try:
            dm, ws = pending
            engine._pending_display_settings = None
            engine.apply_display_settings(dm, ws)
        except Exception:
            # If anything goes wrong, clear the pending request and continue.
            engine._pending_display_settings = None

    # Store real frame dt for camera (presentation-rate, not sim-rate).
    engine._camera_dt = dt

    # Handle events ONCE per render frame (before sim ticks).
    t0 = time.perf_counter()
    engine.handle_events()
    if getattr(engine, "_ursina_viewer", False):
        try:
            from game.graphics.ursina_renderer import set_tax_gold_overlay_held

            g_held = False
            if getattr(engine, "input_manager", None) is not None:
                g_held = engine.input_manager.is_key_pressed("g")
            else:
                from ursina import held_keys

                g_held = bool(held_keys.get("g", 0))
            set_tax_gold_overlay_held(g_held)
        except Exception:
            pass
    t1 = time.perf_counter()

    # Accumulate scaled sim time.
    multiplier = get_time_multiplier()
    sim_time_to_advance = dt * multiplier
    engine._sim_accumulator += sim_time_to_advance

    # Mythos S5 (fast-dt-scaling, env-gated default OFF): above NORMAL speed,
    # drain the accumulator in proportionally larger steps instead of more
    # 50ms ticks. Published as an instance attr so the blend divisor
    # (engine.build_presentation_frame) and the clamps below stay consistent.
    if _FAST_DT_SCALING:
        base_dt = type(engine)._FIXED_SIM_DT
        if multiplier > _SPEED_NORMAL > 0.0:
            engine._FIXED_SIM_DT = min(
                _FAST_DT_MAX_STEP, base_dt * (multiplier / _SPEED_NORMAL)
            )
        else:
            engine._FIXED_SIM_DT = base_dt

    # Spiral-of-death guard: never bank more than one frame's worth of drainable sim
    # (MAX_TICKS * FIXED_DT). A single abnormal frame (one-time world build, alt-tab,
    # GC, prefab load) would otherwise inject a multi-second backlog that fast-forwards
    # over many catch-up frames (tick_simulation spikes -> FPS cascade). Normal frames
    # are far below this cap, so steady-state play is unchanged; only post-hitch recovery
    # is affected (the sim resumes from now instead of fast-forwarding the backlog).
    _max_backlog = engine._FIXED_SIM_DT * engine._MAX_TICKS_PER_FRAME
    if engine._sim_accumulator > _max_backlog:
        engine._sim_accumulator = _max_backlog

    # Run fixed-rate sim ticks until accumulator is drained (or safety cap hit).
    ticks_this_frame = 0
    t_update_start = time.perf_counter()

    while (engine._sim_accumulator >= engine._FIXED_SIM_DT
           and ticks_this_frame < engine._MAX_TICKS_PER_FRAME):
        engine.update(engine._FIXED_SIM_DT)
        engine._sim_accumulator -= engine._FIXED_SIM_DT
        ticks_this_frame += 1
        engine._sim_tick_counter += 1
        # After the first tick, zero camera_dt so update_camera (inside
        # _prepare_sim_and_camera) does not move the camera again this frame.
        engine._camera_dt = 0.0

    t2 = time.perf_counter()

    engine._last_frame_sim_ticks = ticks_this_frame

    evt_ms = (t1 - t0) * 1000.0
    upd_ms = (t2 - t_update_start) * 1000.0
    return evt_ms, upd_ms
