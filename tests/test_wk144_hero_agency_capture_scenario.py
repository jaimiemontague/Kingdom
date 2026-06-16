from __future__ import annotations

from math import hypot

import pygame
import pytest

from config import TILE_SIZE
from game.engine import GameEngine
from tools.screenshot_scenarios import Shot, get_scenario


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_hero_agency_showcase_registers_spread_scene_and_metadata():
    engine = GameEngine(headless=True, headless_ui=True)

    shots = get_scenario(engine, "hero_agency_showcase", seed=3)
    assert len(shots) == 2
    assert all(isinstance(shot, Shot) for shot in shots)
    assert [shot.filename for shot in shots] == [
        "hero_agency_showcase_world.png",
        "hero_agency_showcase_detail.png",
    ]

    world_shot = shots[0]
    detail_shot = shots[1]

    assert world_shot.meta is not None
    assert callable(world_shot.apply)
    assert world_shot.meta["scenario"] == "hero_agency_showcase"
    assert world_shot.meta["hero_count"] == 10
    assert world_shot.ticks == 1800
    assert sum(world_shot.meta["motive_counts"].values()) == 10
    assert len(world_shot.meta["motive_counts"]) >= 5
    assert len(world_shot.meta["cluster_keys"]) >= 5
    assert any(key in world_shot.meta["motive_counts"] for key in ("safe_rest", "home_or_guild_time", "social_linger"))
    assert any(
        key in world_shot.meta["motive_counts"]
        for key in ("poi_scout", "monster_patrol", "wilderness_explore", "opportunity_check", "kingdom_roam", "road_watch")
    )

    assert detail_shot.meta is not None
    assert callable(detail_shot.apply)
    assert detail_shot.ticks == 0
    assert detail_shot.meta["focus"] == "detail"
    assert detail_shot.meta["hero_count"] == 10
    assert detail_shot.meta["detail_target_key"]

    world_shot.apply(engine)
    castle = next(b for b in engine.buildings if getattr(b, "building_type", "") == "castle")

    assert len(engine.heroes) == 10
    assert len(engine.sim.pois) >= 2
    assert sum(1 for b in engine.buildings if getattr(b, "is_lair", False)) >= 1

    far_targets = []
    for hero in engine.heroes:
        target = getattr(hero, "target_position", None)
        if target is None:
            continue
        dx = float(target[0]) - float(castle.center_x)
        dy = float(target[1]) - float(castle.center_y)
        far_targets.append(hypot(dx, dy) / TILE_SIZE)

    assert far_targets
    assert max(far_targets) > 15.0
