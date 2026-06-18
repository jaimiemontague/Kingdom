"""WK146 Ursina capture patch: Herald's Post story-chain launcher proof.

The capture runner imports this module before launching ``main.py --renderer ursina``.
It sets up a deterministic, quiet town slice with a constructed Herald's Post, a
real QuestGiver, a discovered Bandit Fortress, and a live Blackbanner quest chain
started through ``SimEngine.start_quest_chain_from_post`` / ``create_quest_chain``.

The patch also keeps the existing Pygame ``QuestCreatePanel`` open in the Ursina
HUD overlay so the screenshot can prove the Story Chains launcher path when that
overlay is available in the 3D renderer.
"""
from __future__ import annotations

import os

from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _building_type_key(building) -> str:
    value = getattr(building, "building_type", "")
    return str(getattr(value, "value", value) or "").strip().lower()


def _find_castle(engine):
    return next(
        (b for b in getattr(engine, "buildings", []) if _building_type_key(b) == "castle"),
        None,
    )


def _reveal_all(world) -> None:
    vis = getattr(world, "visibility", None)
    if not isinstance(vis, list):
        return
    try:
        for y, row in enumerate(vis):
            for x in range(len(row)):
                row[x] = 2
        if hasattr(world, "_currently_visible"):
            world._currently_visible = {
                (x, y) for y in range(len(vis)) for x in range(len(vis[y]))
            }
    except Exception:
        return


def _clear_scene(engine) -> tuple[int, int]:
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    engine.heroes = []
    sim = getattr(engine, "sim", engine)
    if hasattr(sim, "quest_givers"):
        sim.quest_givers = []
    castle = _find_castle(engine)
    engine.buildings = [b for b in getattr(engine, "buildings", []) if b is castle]
    engine.pois = []
    for attr in ("selected_hero", "selected_peasant", "selected_building", "selected_enemy"):
        if hasattr(engine, attr):
            setattr(engine, attr, None)
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = False
    if hasattr(engine, "show_perf"):
        engine.show_perf = False
    if hasattr(engine, "_perf_overlay_panel"):
        engine._perf_overlay_panel = None
    if castle is not None:
        return int(getattr(castle, "grid_x", MAP_WIDTH // 2)), int(
            getattr(castle, "grid_y", MAP_HEIGHT // 2)
        )
    return MAP_WIDTH // 2, MAP_HEIGHT // 2


def _disable_world_noise(engine) -> None:
    sim = getattr(engine, "sim", engine)
    spawner = getattr(sim, "spawner", None)
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
    wave = getattr(sim, "wave_event_system", None)
    if wave is not None:
        for attr in ("enabled", "active", "wave_active"):
            if hasattr(wave, attr):
                try:
                    setattr(wave, attr, False)
                except Exception:
                    pass


def _disable_fps_overlay() -> None:
    try:
        from ursina import window

        if getattr(window, "fps_counter", None) is not None:
            window.fps_counter.enabled = False
    except Exception:
        pass


def _mark_constructed(building) -> None:
    building.hp = getattr(building, "max_hp", getattr(building, "hp", 1))
    for attr, value in (
        ("is_constructed", True),
        ("construction_complete", True),
        ("construction_started", True),
        ("is_built", True),
        ("built", True),
        ("construction_progress", 1.0),
    ):
        if hasattr(building, attr):
            try:
                setattr(building, attr, value)
            except Exception:
                pass


def _place_post(engine, gx: int, gy: int):
    post = engine.building_factory.create("herald_post", int(gx), int(gy))
    _mark_constructed(post)
    engine.buildings.append(post)
    return post


def _place_bandit_fortress(engine, gx: int, gy: int):
    from game.entities.poi import POI_DEFINITIONS, PointOfInterest

    poi = PointOfInterest(int(gx), int(gy), POI_DEFINITIONS["poi_bandit_fortress"])
    poi.is_discovered = True
    poi.discoverer_hero_id = "wk146_ursina_hero_00"
    _mark_constructed(poi)
    engine.buildings.append(poi)
    engine.pois.append(poi)
    return poi


def _place_heroes(engine, post, fortress) -> list[object]:
    from game.entities.hero import Hero, HeroState

    heroes = []
    starts = [
        (post.center_x + TILE_SIZE * 2, post.center_y + TILE_SIZE * 0.5, "warrior", "Astra"),
        (post.center_x + TILE_SIZE * 2, post.center_y + TILE_SIZE * 1.5, "ranger", "Borin"),
        (fortress.center_x - TILE_SIZE * 1.5, fortress.center_y + TILE_SIZE * 3.2, "cleric", "Cora"),
    ]
    for i, (x, y, hero_class, name) in enumerate(starts):
        hero = Hero(
            float(x),
            float(y),
            hero_class=hero_class,
            hero_id=f"wk146_ursina_hero_{i:02d}",
            name=name,
        )
        hero.hp = hero.max_hp
        hero.gold = 150
        hero.state = HeroState.IDLE
        heroes.append(hero)
    engine.heroes.extend(heroes)
    return heroes


def _ensure_quest_giver(engine, post):
    from game.entities.quest_giver import QuestGiver

    sim = getattr(engine, "sim", engine)
    givers = getattr(sim, "quest_givers", None)
    if givers is None:
        return None
    post_id = str(getattr(post, "entity_id", "") or "")
    for giver in list(givers):
        if str(getattr(giver, "giver_id", "") or "") == post_id:
            return giver
    giver = QuestGiver(post)
    givers.append(giver)
    return giver


def _launch_blackbanner(engine, giver, hero) -> object | None:
    sim = getattr(engine, "sim", engine)
    launch = getattr(sim, "start_quest_chain_from_post", None)
    if not callable(launch):
        launch = getattr(sim, "create_quest_chain", None)
    if not callable(launch):
        return None
    try:
        return launch(
            getattr(giver, "giver_id", ""),
            "blackbanners_toll",
            hero_id=getattr(hero, "hero_id", None),
        )
    except TypeError:
        return launch(getattr(giver, "giver_id", ""), "blackbanners_toll")


def _keep_quest_modal_open(engine, post, message: str) -> None:
    panel = getattr(engine, "building_panel", None)
    if panel is None:
        return
    try:
        panel.select_building(post, getattr(engine, "heroes", []))
    except Exception:
        pass
    try:
        engine.selected_building = post
    except Exception:
        pass
    qcp = getattr(panel, "quest_create_panel", None)
    if qcp is None:
        return
    try:
        if not getattr(qcp, "visible", False) or getattr(qcp, "post", None) is not post:
            qcp.open(post, engine.get_game_state())
        else:
            qcp._sim = getattr(engine, "sim", engine)
            qcp._world = getattr(engine, "world", None)
        qcp.visible = True
        if message:
            qcp.feedback = message
    except Exception as exc:
        print(f"[wk146-ursina] modal open failed: {exc!r}", flush=True)
    if hasattr(engine, "_request_ursina_hud_upload"):
        try:
            engine._request_ursina_hud_upload()
        except Exception:
            pass
    if hasattr(engine, "_ursina_hud_force_upload"):
        try:
            engine._ursina_hud_force_upload = True
        except Exception:
            pass
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = False
    if hasattr(engine, "show_perf"):
        engine.show_perf = False


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
    distance = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    camera.position = Vec3(cx, look_at_y + distance * float(knobs["elev"]), cz - distance)
    camera.look_at(Vec3(cx, look_at_y, cz))


def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        engine = self.engine
        knobs = {
            "span": _env_float("KINGDOM_WK146_URSINA_CAM_SPAN", 14.0),
            "elev": _env_float("KINGDOM_WK146_URSINA_CAM_ELEV", 0.8),
        }

        cgx, cgy = _clear_scene(engine)
        _disable_fps_overlay()
        _disable_world_noise(engine)
        _reveal_all(engine.world)

        post = _place_post(engine, cgx - 2, cgy + 5)
        fortress = _place_bandit_fortress(engine, cgx + 7, cgy + 3)
        heroes = _place_heroes(engine, post, fortress)
        giver = _ensure_quest_giver(engine, post)
        chain = _launch_blackbanner(engine, giver, heroes[0]) if giver is not None else None
        if giver is not None:
            giver.is_open = True

        message = "Blackbanner Active" if chain is not None else "Story chain unavailable."
        focus_x = (float(post.center_x) + float(fortress.center_x)) * 0.5
        focus_y = (float(post.center_y) + float(fortress.center_y)) * 0.5

        _keep_quest_modal_open(engine, post, message)
        _frame_camera(focus_x, focus_y, knobs)

        orig_tick = engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            if giver is not None:
                giver.is_open = True
            for hero in heroes:
                if hasattr(hero, "hp"):
                    hero.hp = max(1, int(getattr(hero, "max_hp", 1) or 1))
                try:
                    from game.entities.hero import HeroState

                    if str(getattr(getattr(hero, "state", None), "name", "") or "") == "DEAD":
                        hero.state = HeroState.IDLE
                except Exception:
                    pass
            _keep_quest_modal_open(engine, post, message)
            _frame_camera(focus_x, focus_y, knobs)
            return result

        engine.tick_simulation = patched_tick

        chain_type = str(getattr(chain, "chain_type", "") or "")
        phase = str(getattr(getattr(chain, "current_phase", None), "phase_id", "") or "")
        print(
            "[wk146-ursina-quest-chain] "
            f"post=({post.grid_x},{post.grid_y}) fortress=({fortress.grid_x},{fortress.grid_y}) "
            f"chain={chain_type or 'none'} phase={phase or 'unknown'} span={knobs['span']:.3g}",
            flush=True,
        )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
