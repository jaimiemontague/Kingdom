"""WK122-T3 — Ursina guardhouse two-arrow capture patch (import before main).

Registered Ursina capture scenario ``ursina_guardhouse_arrows`` (see
``tools/screenshot_scenarios.py:URSINA_CAPTURE_SCENARIOS``). Jaimie asked for a test
that "starts the game with the guard tower firing at an enemy and screenshot to make
sure you see 2 distinct arrows". This patch sets up a deterministic scene — the REAL
``Guardhouse`` + ONE goblin a few tiles away (within ``GUARDHOUSE_ARROW_RANGE_TILES``)
— and HOLDS an in-flight two-arrow volley so the auto-screenshot always shows two
distinct arrow billboards between the guardhouse and the enemy.

Modeled on ``tools/wk67_combat_capture_patch.py`` (the registered melee-combat capture).

Robustness — why two mechanisms (belt + suspenders):

1. The sim path (FAITHFULNESS / live integration proof): we use the REAL
   ``game.entities.buildings.defensive.Guardhouse`` (not a generic ``Building``) and
   call its real ``update()`` via the engine each tick. We keep the goblin alive at full
   HP and in range, and reset the guardhouse ``_arrow_timer = 0.0`` so a fresh REAL volley
   fires every tick. With the shipped WK122-BUG-B1 ``sim_engine.py`` fix both
   ``_last_ranged_events`` are collected/emitted, so the VFX system spawns two real
   ``ProjectileVFX``.

2. The pin path (VISIBILITY guarantee): arrow VFX lifetimes are short (0.25-0.45 s), so a
   sim-driven volley may not coincide with the exact frame the screenshot grabs. To
   GUARANTEE two distinct billboards in the captured frame, we additionally re-pin EXACTLY
   two ``ProjectileVFX`` in ``engine.vfx_system._projectiles`` AFTER the real tick (and
   after the goblin/arrow_timer re-pin), at a fixed mid progress, using the same +/-X,
   +/-Y origin offsets the real building uses (factor 40 in X -> +/-20px; 8 in Y ->
   +/-4px) -> the same enemy target. This makes two visible arrows independent of
   sim/volley timing and wall-clock tick count.

Framing is tight (default span 4 world units; 1 tile = 1 world unit) so the small arrow
billboards (renderer ``PROJECTILE_BILLBOARD_SCALE`` = 0.075 world units) are large enough
to read. The camera aims at the MIDPOINT OF THE TWO PINNED ARROWS at the pin progress
(not the guardhouse->enemy midpoint) so the arrows sit dead-center.

PM iteration knobs (read at app-init, no code edits needed) — all parsed safely with a
fallback to the module default if unset/invalid:

  KINGDOM_WK122_SEP_TILES      (int,   default 3)   goblin distance east of the tower
  KINGDOM_WK122_CAM_SPAN       (float, default 4.0) world-unit span across the frame
  KINGDOM_WK122_CAM_ELEV       (float, default 0.8) camera-elevation factor (* back dist)
  KINGDOM_WK122_PROGRESS       (float, default 0.4) held mid-flight progress of the pins
  KINGDOM_WK122_ARROW_OFFSET_X (float, default 40.0) X origin-spread factor (-> +/-20px)
  KINGDOM_WK122_ARROW_OFFSET_Y (float, default 8.0)  Y origin-spread factor (-> +/-4px)

Determinism: the FPS/frame-time debug overlay (varying text in the grabbed framebuffer)
is disabled; the camera is a FIXED (non-EditorCamera) oblique camera re-aimed each tick
on the two-arrow midpoint. This module performs NO import-time ``os.environ`` mutation
(the scenario env is set by ``tools/run_ursina_capture_once.py``).
"""
from __future__ import annotations

import os

from config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    TILE_SIZE,
    GUARDHOUSE_ARROW_RANGE_TILES,
    GUARDHOUSE_ARROWS_PER_SHOT,
)

# Distinct origin offset factors matching the REAL Guardhouse.update() (defensive.py):
# the two arrows leave the building from +/-20px X (factor 40) and +/-4px Y (factor 8) so
# they read as two separate spots. offset_i = (i - (n - 1) / 2) * FACTOR.
_ARROW_OFFSET_X = 40.0  # (i-0.5)*40 -> +/-20px
_ARROW_OFFSET_Y = 8.0   # (i-0.5)*8  -> +/-4px

# Held mid-flight progress for the pinned billboards (nearer the tower = clearer gap).
_PINNED_PROGRESS = 0.4

# Goblin separation (tiles east of the guardhouse center). Kept < arrow range.
_SEP_TILES = 3

# Camera framing defaults (world units / factor).
# Span 5.0 fits BOTH pinned arrows + the tower base + goblin (span 2.4/4.0 was too tight
# and cut an arrow off); KINGDOM_WK122_CAM_SPAN still overrides.
_CAM_SPAN = 5.0
_CAM_ELEV_FACTOR = 0.8


# --- env helpers -------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    """Parse a float env knob; return ``default`` on missing/blank/invalid input."""
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _env_int(name: str, default: int) -> int:
    """Parse an int env knob; return ``default`` on missing/blank/invalid input."""
    raw = os.environ.get(name)
    if raw is None:
        return int(default)
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return int(default)


def _resolve_knobs() -> dict[str, float]:
    """Resolve every PM-overridable knob once (used for framing + the marker print)."""
    return {
        "sep_tiles": float(_env_int("KINGDOM_WK122_SEP_TILES", int(_SEP_TILES))),
        "span": _env_float("KINGDOM_WK122_CAM_SPAN", _CAM_SPAN),
        "elev": _env_float("KINGDOM_WK122_CAM_ELEV", _CAM_ELEV_FACTOR),
        "progress": _env_float("KINGDOM_WK122_PROGRESS", _PINNED_PROGRESS),
        "offset_x": _env_float("KINGDOM_WK122_ARROW_OFFSET_X", _ARROW_OFFSET_X),
        "offset_y": _env_float("KINGDOM_WK122_ARROW_OFFSET_Y", _ARROW_OFFSET_Y),
    }


def _building_type_key(building) -> str:
    bt = getattr(building, "building_type", "")
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _reveal_all(world) -> None:
    """Mark every tile VISIBLE (Visibility.VISIBLE == 2) so the scene is not fogged."""
    vis = getattr(world, "visibility", None)
    if not isinstance(vis, list):
        return
    try:
        for y in range(len(vis)):
            row = vis[y]
            for x in range(len(row)):
                row[x] = 2
        if hasattr(world, "_currently_visible"):
            world._currently_visible = {
                (x, y) for y in range(len(vis)) for x in range(len(vis[y]))
            }
    except Exception:
        return


def _find_castle(engine):
    return next(
        (b for b in getattr(engine, "buildings", []) if _building_type_key(b) == "castle"),
        None,
    )


def _tile_center(gx: int, gy: int) -> tuple[float, float]:
    return (gx * TILE_SIZE + TILE_SIZE / 2.0, gy * TILE_SIZE + TILE_SIZE / 2.0)


def _setup_arrows_scene(engine, knobs: dict[str, float]) -> tuple[object, object]:
    """Place the REAL Guardhouse + ONE goblin within arrow range near the castle.

    Returns ``(guardhouse, enemy)``. The goblin is ``sep_tiles`` east of the guardhouse
    center (kept inside ``GUARDHOUSE_ARROW_RANGE_TILES`` = 8) so the arrows have travel
    distance but always have a valid target. Uses
    ``game.entities.buildings.defensive.Guardhouse`` so the live sim genuinely fires.
    """
    from game.entities.enemy import Enemy
    from game.entities.buildings.defensive import Guardhouse

    # Clear all dynamic entities + bounties so only the guardhouse + goblin remain.
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    engine.heroes = []
    try:
        engine.bounty_system.bounties = []
    except Exception:
        pass

    # Keep only the castle as a backdrop anchor for placement; remove all other buildings.
    castle = _find_castle(engine)
    engine.buildings = [b for b in getattr(engine, "buildings", []) if b is castle]

    if castle is not None:
        cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
        cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))
    else:
        cgx, cgy = MAP_WIDTH // 2, MAP_HEIGHT // 2

    # Keep separation inside the arrow range (and at least 1 tile) regardless of env.
    sep = int(knobs["sep_tiles"])
    sep = max(1, min(sep, int(GUARDHOUSE_ARROW_RANGE_TILES) - 1))

    # Guardhouse a few tiles south-west of the castle; goblin `sep` tiles east of the
    # guardhouse center -> within the 8-tile arrow range with real travel distance.
    gh_gx, gh_gy = cgx - 6, cgy + 4
    guardhouse = Guardhouse(gh_gx, gh_gy)
    guardhouse.is_constructed = True
    if hasattr(guardhouse, "construction_started"):
        guardhouse.construction_started = True
    if hasattr(guardhouse, "max_hp") and hasattr(guardhouse, "hp"):
        guardhouse.hp = getattr(guardhouse, "max_hp", guardhouse.hp)
    engine.buildings.append(guardhouse)

    enemy_gx = gh_gx + sep
    enemy_gy = gh_gy
    ex, ey = _tile_center(enemy_gx, enemy_gy)
    enemy = Enemy(ex, ey, enemy_type="goblin")
    engine.enemies = [enemy]

    # Park selection / debug UI so they cannot perturb the frame.
    for attr in ("selected_hero", "selected_peasant", "selected_building"):
        if hasattr(engine, attr):
            setattr(engine, attr, None)
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = True

    return guardhouse, enemy


def _hold_arrows_pose(engine, guardhouse, enemy, *, enemy_pos, knobs) -> None:
    """Keep the goblin alive + in range and force the REAL guardhouse to re-fire each tick.

    Called after every sim tick so AI/combat mutation cannot move the goblin, kill it,
    or let the arrow cooldown idle the building. Resetting ``_arrow_timer = 0.0`` makes
    the real ``Guardhouse.update()`` fire a fresh two-arrow volley on the NEXT tick (the
    live integration proof). Then re-pins two mid-flight billboards (see
    ``_pin_two_projectiles``) so the captured frame always shows both arrows regardless
    of volley timing.
    """
    ex, ey = enemy_pos

    # Pin the goblin in place at full HP so it stays a valid target and never dies.
    enemy.x, enemy.y = ex, ey
    try:
        enemy.hp = getattr(enemy, "max_hp", enemy.hp)
    except Exception:
        pass

    # Reset the arrow cooldown so the REAL guardhouse fires a fresh volley every tick.
    if hasattr(guardhouse, "_arrow_timer"):
        guardhouse._arrow_timer = 0.0
    guardhouse.is_constructed = True
    guardhouse.target = enemy

    # Keep the scene free of strays.
    if list(engine.enemies) != [enemy]:
        engine.enemies = [enemy]

    # Pin AFTER the goblin/arrow_timer re-pin so the two billboards are deterministic
    # regardless of what the real sim spawned this tick.
    _pin_two_projectiles(engine, guardhouse, enemy, knobs)


def _arrow_world_positions(guardhouse, enemy, knobs) -> list[tuple[float, float]]:
    """Two pinned-arrow world-pixel (x, y) positions at the held progress.

    Mirrors ``_pin_two_projectiles`` (same origin offsets, target, progress) so the
    camera can frame on their average without re-instantiating the VFX.
    """
    to_x = float(getattr(enemy, "x", getattr(enemy, "center_x", 0.0)))
    to_y = float(getattr(enemy, "y", getattr(enemy, "center_y", 0.0)))
    cx = float(getattr(guardhouse, "center_x", 0.0))
    cy = float(getattr(guardhouse, "center_y", 0.0))

    progress = float(knobs["progress"])
    off_x = float(knobs["offset_x"])
    off_y = float(knobs["offset_y"])

    positions: list[tuple[float, float]] = []
    n = int(GUARDHOUSE_ARROWS_PER_SHOT)
    for i in range(n):
        from_x = cx + (i - (n - 1) / 2.0) * off_x
        from_y = cy + (i - (n - 1) / 2.0) * off_y
        px = from_x + (to_x - from_x) * progress
        py = from_y + (to_y - from_y) * progress
        positions.append((px, py))
    return positions


def _pin_two_projectiles(engine, guardhouse, enemy, knobs) -> None:
    """Force EXACTLY two mid-flight arrow ``ProjectileVFX`` into the VFX system.

    Guarantees two distinct billboards on screen regardless of the sim volley timing:
    rebuilds two projectiles each tick at the held progress, from the two distinct
    guardhouse origin spots to the goblin. Any sim-spawned arrows are cleared first so
    the frame contains exactly the two pinned billboards (no duplicate clutter).
    """
    from game.graphics.vfx import ProjectileVFX

    vfx = getattr(engine, "vfx_system", None)
    if vfx is None:
        return
    projectiles = getattr(vfx, "_projectiles", None)
    if not isinstance(projectiles, list):
        return

    to_x = float(getattr(enemy, "x", getattr(enemy, "center_x", 0.0)))
    to_y = float(getattr(enemy, "y", getattr(enemy, "center_y", 0.0)))
    cx = float(getattr(guardhouse, "center_x", 0.0))
    cy = float(getattr(guardhouse, "center_y", 0.0))

    progress = float(knobs["progress"])
    off_x = float(knobs["offset_x"])
    off_y = float(knobs["offset_y"])

    pinned: list[ProjectileVFX] = []
    n = int(GUARDHOUSE_ARROWS_PER_SHOT)
    for i in range(n):
        offset_x = (i - (n - 1) / 2.0) * off_x
        offset_y = (i - (n - 1) / 2.0) * off_y
        pinned.append(
            ProjectileVFX(
                from_x=cx + offset_x,
                from_y=cy + offset_y,
                to_x=to_x,
                to_y=to_y,
                progress=progress,
                # Lifetime/age chosen so progress holds and the projectile does not
                # expire before the next tick re-pins it.
                lifetime=10.0,
                age=progress * 10.0,
                color=(139, 69, 19),
                tip_color=(245, 245, 245),
                size_px=2,
            )
        )
    projectiles[:] = pinned


def _disable_spawner(engine) -> None:
    """Stop wave/neutral spawns so no stray enemies wander into the framed scene."""
    sim = getattr(engine, "sim", None)
    spawner = getattr(sim, "spawner", None) if sim is not None else None
    if spawner is not None:
        for attr in ("spawn_interval", "spawn_interval_sec", "spawn_timer"):
            if hasattr(spawner, attr):
                try:
                    setattr(spawner, attr, 1.0e9)
                except Exception:
                    pass
    neutral = getattr(engine, "neutral_building_system", None)
    if neutral is not None and hasattr(neutral, "spawn_interval_sec"):
        try:
            neutral.spawn_interval_sec = 1.0e9
        except Exception:
            pass


def _disable_fps_overlay() -> None:
    """Disable the wall-clock FPS / frame-time debug overlay so the PNG is deterministic."""
    try:
        from ursina import window

        if getattr(window, "fps_counter", None) is not None:
            window.fps_counter.enabled = False
    except Exception:
        pass


def _frame_camera_on_gap(guardhouse, enemy, knobs) -> None:
    """Point a FIXED (non-EditorCamera) oblique camera at the TWO-ARROW midpoint.

    The scenario env sets ``KINGDOM_URSINA_EDITORCAMERA=0`` so ``ursina_app`` already
    installed a static camera; we re-aim it precisely at the AVERAGE of the two pinned
    arrow world positions (at the held progress) so the arrows sit dead-center, large
    enough to read at the (tight) span. blend=0 removes orbit jitter. At span 4 with a
    3-tile separation both the tower base and the goblin stay roughly in frame.
    """
    import math

    from ursina import Vec3, camera

    from game.graphics.ursina_renderer import sim_px_to_world_xz

    arrows = _arrow_world_positions(guardhouse, enemy, knobs)
    if arrows:
        aim_x = sum(p[0] for p in arrows) / len(arrows)
        aim_y = sum(p[1] for p in arrows) / len(arrows)
    else:  # pragma: no cover - GUARDHOUSE_ARROWS_PER_SHOT is always >= 1
        aim_x = float(getattr(guardhouse, "center_x", 0.0))
        aim_y = float(getattr(guardhouse, "center_y", 0.0))

    cx, cz = sim_px_to_world_xz(aim_x, aim_y)

    # Vertically center the arrows: they sit at terrain_height + PROJECTILE_BILLBOARD_Y,
    # and this map has rolling terrain (terrain_y well above 0). Looking at world Y=0
    # (the old behavior) aimed far BELOW the arrows, pushing them to the top edge. Look at
    # the AVERAGE true 3D Y of the two pinned arrows instead. Wrapped in try/except so a
    # missing terrain module can't crash the capture (fallback 0.3).
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized
        from game.graphics.ursina_misc_props_sync import PROJECTILE_BILLBOARD_Y

        arrow_worlds = []
        for ax, ay in (arrows if arrows else [(aim_x, aim_y)]):
            wx, wz = sim_px_to_world_xz(ax, ay)
            wy = (get_terrain_height(wx, wz) if is_initialized() else 0.0) + PROJECTILE_BILLBOARD_Y
            arrow_worlds.append((wx, wy, wz))
        look_at_y = sum(w[1] for w in arrow_worlds) / len(arrow_worlds)
    except Exception:
        arrow_worlds = []
        look_at_y = 0.3

    # Span across the frame in world units (1 tile = 1 world unit). A small span keeps
    # the tiny arrow billboards large enough to read as two distinct arrows.
    span = float(knobs["span"])
    elev_factor = float(knobs["elev"])
    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    elev = d * elev_factor
    back = d
    # Elevation is relative to the ARROW height (not the terrain-0 plane), so the camera
    # sits above the arrow plane and the arrows stay vertically centered.
    camera.position = Vec3(cx, look_at_y + elev, cz - back)
    camera.look_at(Vec3(cx, look_at_y, cz))

    # Expose for the marker print so the PM can confirm centering from stdout.
    _frame_camera_on_gap.last_look_at_y = look_at_y
    _frame_camera_on_gap.last_arrow_worlds = arrow_worlds


def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        knobs = _resolve_knobs()

        _disable_fps_overlay()
        _reveal_all(self.engine.world)
        _disable_spawner(self.engine)
        guardhouse, enemy = _setup_arrows_scene(self.engine, knobs)
        enemy_pos = (enemy.x, enemy.y)

        # Aim the fixed camera straight at the two-arrow midpoint.
        _frame_camera_on_gap(guardhouse, enemy, knobs)

        # Hold the volley immediately so even a tick-0 grab shows two arrows.
        _hold_arrows_pose(self.engine, guardhouse, enemy, enemy_pos=enemy_pos, knobs=knobs)

        # Re-pin the held volley after every sim tick so the two arrows stay mid-flight
        # regardless of how many ticks run before the wall-clock auto-exit fires. The
        # pin runs AFTER orig_tick (the real sim/Guardhouse.update volley) so the two
        # visible billboards are deterministic regardless of sim timing.
        orig_tick = self.engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            _hold_arrows_pose(self.engine, guardhouse, enemy, enemy_pos=enemy_pos, knobs=knobs)
            # Re-aim the fixed camera (the update loop re-derives FOV from zoom each
            # frame; re-frame against the current FOV so the shot stays locked).
            _frame_camera_on_gap(guardhouse, enemy, knobs)
            return result

        self.engine.tick_simulation = patched_tick

        ghx = float(getattr(guardhouse, "center_x", 0.0))
        ghy = float(getattr(guardhouse, "center_y", 0.0))
        look_at_y = float(getattr(_frame_camera_on_gap, "last_look_at_y", 0.0))
        arrow_worlds = list(getattr(_frame_camera_on_gap, "last_arrow_worlds", []))
        arrows_str = " ".join(
            f"arrow{i}=({w[0]:.2f},{w[1]:.2f},{w[2]:.2f})"
            for i, w in enumerate(arrow_worlds)
        )
        print(
            "[wk122-arrows-capture] REAL Guardhouse@"
            f"({ghx:.0f},{ghy:.0f}) enemy=goblin@"
            f"({enemy_pos[0]:.0f},{enemy_pos[1]:.0f}) "
            f"range_tiles={GUARDHOUSE_ARROW_RANGE_TILES} "
            f"arrows={GUARDHOUSE_ARROWS_PER_SHOT} "
            f"sep_tiles={int(knobs['sep_tiles'])} "
            f"span={knobs['span']:.3g} elev={knobs['elev']:.3g} "
            f"progress={knobs['progress']:.3g} "
            f"offset_x={knobs['offset_x']:.3g} offset_y={knobs['offset_y']:.3g} "
            f"look_at_y={look_at_y:.3f} {arrows_str}; "
            "fps overlay disabled",
            flush=True,
        )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
