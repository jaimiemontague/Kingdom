"""WK133 — Ursina capture patch: Herald's Post + Quest-Giver NPC + yellow "!" marker.

Places a CONSTRUCTED Herald's Post south of the castle, lets the sim spawn its
Quest-Giver NPC, arms a raid_lair quest via the real engine action (escrow) so the
giver's ``is_open`` flips True, and frames a fixed oblique camera on the post+NPC so
the PM can verify: post renders (blue 2x2 fallback sprite), NPC stands beside it,
and the yellow "!" floats above the NPC on top of everything.

Knobs: KINGDOM_WK133_CAM_SPAN (default 8.0), KINGDOM_WK133_CAM_ELEV (default 0.8),
KINGDOM_WK133_ARM_QUEST (default 1 — set 0 to capture the giver with NO open quest,
proving the "!" turns off).

Modeled on tools/wk132_poi_capture_patch.py.
"""
from __future__ import annotations

import os

from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _reveal_all(world) -> None:
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
    def _key(b) -> str:
        bt = getattr(b, "building_type", "")
        return str(getattr(bt, "value", bt) or "").strip().lower()

    return next((b for b in getattr(engine, "buildings", []) if _key(b) == "castle"), None)


def _clear_scene(engine) -> tuple[int, int]:
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    engine.heroes = []
    castle = _find_castle(engine)
    engine.buildings = [b for b in getattr(engine, "buildings", []) if b is castle]
    engine.pois = []
    for attr in ("selected_hero", "selected_peasant", "selected_building"):
        if hasattr(engine, attr):
            setattr(engine, attr, None)
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = True
    if castle is not None:
        return int(getattr(castle, "grid_x", MAP_WIDTH // 2)), int(
            getattr(castle, "grid_y", MAP_HEIGHT // 2)
        )
    return MAP_WIDTH // 2, MAP_HEIGHT // 2


def _disable_spawner(engine) -> None:
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
    try:
        from ursina import window

        if getattr(window, "fps_counter", None) is not None:
            window.fps_counter.enabled = False
    except Exception:
        pass


def _frame_camera(px: float, py: float, knobs) -> None:
    import math

    from ursina import Vec3, camera

    from game.graphics.ursina_renderer import sim_px_to_world_xz

    cx, cz = sim_px_to_world_xz(px, py)
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized

        look_at_y = (get_terrain_height(cx, cz) if is_initialized() else 0.0) + 0.4
    except Exception:
        look_at_y = 0.4

    span = float(knobs["span"])
    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    camera.position = Vec3(cx, look_at_y + d * float(knobs["elev"]), cz - d)
    camera.look_at(Vec3(cx, look_at_y, cz))


def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        engine = self.engine
        knobs = {
            "span": _env_float("KINGDOM_WK133_CAM_SPAN", 8.0),
            "elev": _env_float("KINGDOM_WK133_CAM_ELEV", 0.8),
        }
        arm_quest = str(os.environ.get("KINGDOM_WK133_ARM_QUEST", "1")).strip() != "0"

        cgx, cgy = _clear_scene(engine)
        _disable_fps_overlay()
        _reveal_all(engine.world)
        _disable_spawner(engine)

        # Place a CONSTRUCTED Herald's Post via the real factory.
        post = engine.building_factory.create("herald_post", cgx - 1, cgy + 5)
        post.hp = post.max_hp
        if hasattr(post, "is_constructed"):
            post.is_constructed = True
        for attr in ("construction_complete", "is_built", "built"):
            if hasattr(post, attr):
                try:
                    setattr(post, attr, True)
                except Exception:
                    pass
        engine.buildings.append(post)

        state = {"armed": False}
        px = (post.grid_x + 1.0) * TILE_SIZE
        py = (post.grid_y + 1.0) * TILE_SIZE

        orig_tick = engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            # Arm a quest once the sim has spawned the giver.
            sim = getattr(engine, "sim", engine)
            givers = getattr(sim, "quest_givers", None) or getattr(
                engine, "quest_givers", []
            )
            if arm_quest and not state["armed"] and givers:
                giver = givers[0]
                try:
                    q = sim.create_quest(
                        giver.giver_id, "explore_far",
                        f"{post.grid_x + 20},{post.grid_y}", 140,
                    )
                    state["armed"] = q is not None
                    print(f"[wk133-capture] quest armed={state['armed']} "
                          f"giver_open={getattr(giver, 'is_open', None)}", flush=True)
                except Exception as exc:  # report, don't crash the capture
                    print(f"[wk133-capture] create_quest failed: {exc!r}", flush=True)
                    state["armed"] = True
            _frame_camera(px, py, knobs)
            return result

        engine.tick_simulation = patched_tick
        _frame_camera(px, py, knobs)

        print(
            f"[wk133-quest-capture] post@({post.grid_x},{post.grid_y}) arm={arm_quest} "
            f"span={knobs['span']:.3g} elev={knobs['elev']:.3g}",
            flush=True,
        )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
