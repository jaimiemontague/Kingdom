"""WK132 — Ursina capture patch for the five new POI prefabs (import before main).

Places ONE of the five WK132 POIs (mysterious_well, ruined_outpost, windmill_ruin,
ancient_ruins, dragon_cave) a few tiles south of the castle, marks it discovered,
reveals fog, and frames a fixed oblique camera on its footprint so the PM can
screenshot-verify the prefab (ground contact, piece composition, cave-mouth facing).

Selected by ``KINGDOM_WK132_POI`` (default ``mysterious_well``). PM framing knobs:

  KINGDOM_WK132_POI        (str)   which POI id to place
  KINGDOM_WK132_CAM_SPAN   (float) world-unit span across the frame (default: footprint-scaled)
  KINGDOM_WK132_CAM_ELEV   (float) camera-elevation factor (default 0.8)

Modeled on ``tools/wk124_wizard_cleric_capture_patch.py`` (clear scene / reveal /
spawner-off / fixed camera). No import-time os.environ mutation.
"""
from __future__ import annotations

import os

from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE

_POI_IDS = (
    "mysterious_well",
    "ruined_outpost",
    "windmill_ruin",
    "ancient_ruins",
    "dragon_cave",
    # control captures (pre-WK132 known-good prefabs):
    "graveyard",
    "shrine",
)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _resolve_poi_id() -> str:
    raw = str(os.environ.get("KINGDOM_WK132_POI", "") or "").strip().lower()
    return raw if raw in _POI_IDS else "mysterious_well"


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


def _place_poi(engine, poi_id: str):
    from game.entities.poi import POI_DEFINITIONS, PointOfInterest

    definition = POI_DEFINITIONS.get(poi_id) or POI_DEFINITIONS[f"poi_{poi_id}"]
    size = tuple(getattr(definition, "size", (1, 1)) or (1, 1))
    cgx, cgy = _clear_scene(engine)
    # South of the castle, clear of its footprint; center the POI footprint.
    gx = cgx - size[0] // 2
    gy = cgy + 5
    poi = PointOfInterest(gx, gy, definition)
    poi.is_discovered = True
    engine.buildings.append(poi)
    engine.pois = [poi]
    return poi, size


def _frame_camera_on_poi(poi, size, knobs) -> None:
    import math

    from ursina import Vec3, camera

    from game.graphics.ursina_renderer import sim_px_to_world_xz

    px = (poi.grid_x + size[0] / 2.0) * TILE_SIZE
    py = (poi.grid_y + size[1] / 2.0) * TILE_SIZE
    cx, cz = sim_px_to_world_xz(px, py)
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized

        look_at_y = get_terrain_height(cx, cz) if is_initialized() else 0.0
    except Exception:
        look_at_y = 0.0

    span = float(knobs["span"])
    elev_factor = float(knobs["elev"])
    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    elev = d * elev_factor
    camera.position = Vec3(cx, look_at_y + elev, cz - d)
    camera.look_at(Vec3(cx, look_at_y, cz))


def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        poi_id = _resolve_poi_id()
        poi, size = _place_poi(self.engine, poi_id)
        # Footprint-scaled default span: ~1.7 world units per tile + margin.
        default_span = (max(size) + 3) * 1.7
        knobs = {
            "span": _env_float("KINGDOM_WK132_CAM_SPAN", default_span),
            "elev": _env_float("KINGDOM_WK132_CAM_ELEV", 0.8),
        }

        _disable_fps_overlay()
        _reveal_all(self.engine.world)
        _disable_spawner(self.engine)
        _frame_camera_on_poi(poi, size, knobs)

        orig_tick = self.engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            poi.is_discovered = True
            _frame_camera_on_poi(poi, size, knobs)
            return result

        self.engine.tick_simulation = patched_tick

        print(
            f"[wk132-poi-capture] poi={poi_id} grid=({poi.grid_x},{poi.grid_y}) "
            f"size={size} span={knobs['span']:.3g} elev={knobs['elev']:.3g}; "
            "discovered+revealed, spawner+fps overlay off",
            flush=True,
        )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
