from __future__ import annotations

import pygame

from game.engine import GameEngine


def _castle(engine: GameEngine):
    return next(
        b for b in engine.buildings
        if getattr(b, "building_type", None) == "castle"
    )


def test_engine_get_game_state_includes_live_context() -> None:
    engine = GameEngine(headless=True)
    try:
        game_state = engine.get_game_state()

        assert game_state["castle"] is not None
        assert game_state["castle"].building_type == "castle"
        assert game_state["economy"] is engine.economy
        assert game_state["world"] is engine.world
        assert game_state["bounty_system"] is engine.bounty_system
    finally:
        pygame.quit()


def test_engine_spawns_peasant_and_builds_new_structure(monkeypatch) -> None:
    engine = GameEngine(headless=True)
    try:
        # Keep the regression focused on the worker/build loop.
        monkeypatch.setattr(engine, "_maybe_apply_early_pacing_nudge", lambda dt, castle: None)
        monkeypatch.setattr(engine.spawner, "spawn", lambda dt: [])
        monkeypatch.setattr(engine.lair_system, "spawn_enemies", lambda dt, buildings: [])

        castle = _castle(engine)
        building = engine.building_factory.create("marketplace", castle.grid_x + 6, castle.grid_y)
        building.mark_unconstructed()
        engine.buildings.append(building)

        for _ in range(1200):
            engine.update(1 / 60)
            if building.is_constructed:
                break

        assert len(engine.peasants) >= 1
        assert building.construction_started is True
        assert building.is_constructed is True
        assert building.hp == building.max_hp
    finally:
        pygame.quit()
