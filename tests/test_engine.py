from __future__ import annotations

import pygame

from game.engine import GameEngine


REQUIRED_GAME_STATE_KEYS = frozenset({
    "screen_w", "screen_h", "display_mode", "window_size",
    "gold", "heroes", "peasants", "guards", "enemies",
    "buildings", "buildings_construction_progress",
    "bounties", "bounty_system", "wave",
    "selected_hero", "selected_building", "selected_peasant",
    "castle", "economy", "world",
    "placing_building_type", "debug_ui",
    "micro_view_mode", "micro_view_building",
    "micro_view_quest_hero", "micro_view_quest_data",
    "right_panel_rect", "llm_available", "ui_cursor_pos",
})


def _castle(engine: GameEngine):
    return next(
        b for b in engine.buildings
        if getattr(b, "building_type", None) == "castle"
    )


def test_engine_headless_init_creates_all_systems():
    engine = GameEngine(headless=True)
    try:
        assert engine.headless is True
        assert engine.world is not None
        assert engine.combat_system is not None
        assert engine.economy is not None
        assert engine.spawner is not None
        assert engine.lair_system is not None
        assert engine.bounty_system is not None
        assert engine.buff_system is not None
        assert engine.building_factory is not None
        assert engine.event_bus is not None
        assert engine.cleanup_manager is not None
        # Headless should NOT have UI/audio/VFX
        assert engine.audio_system is None
        assert engine.vfx_system is None
        assert engine.input_handler is None
        # But should have null stubs that don't crash
        engine.hud.add_message("test", (255, 255, 255))  # NullStub absorbs
    finally:
        pygame.quit()


def test_engine_headless_ui_init_creates_ui_and_systems():
    engine = GameEngine(headless=False, headless_ui=True)
    try:
        assert engine.headless_ui is True
        assert engine.world is not None
        assert engine.hud is not None
        assert engine.pause_menu is not None
        assert engine.input_handler is not None
        assert engine.audio_system is not None
        assert engine.vfx_system is not None
        assert engine.window_width == 1920
        assert engine.window_height == 1080
    finally:
        pygame.quit()


def test_engine_headless_tick_simulation_advances_sim_time():
    engine = GameEngine(headless=True)
    try:
        from config import DETERMINISTIC_SIM
        initial_sim_ms = engine._sim_now_ms
        # Run 60 ticks (1 second at 60 Hz)
        for _ in range(60):
            engine.update(1 / 60)
        if DETERMINISTIC_SIM:
            assert engine._sim_now_ms > initial_sim_ms
        else:
            assert engine._sim_now_ms == initial_sim_ms
    finally:
        pygame.quit()


def test_engine_get_game_state_has_all_required_keys():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        missing = REQUIRED_GAME_STATE_KEYS - set(gs.keys())
        assert not missing, f"Missing keys from get_game_state: {missing}"
    finally:
        pygame.quit()


def test_engine_full_tick_with_enemies_no_crash():
    engine = GameEngine(headless=True)
    try:
        from config import DETERMINISTIC_SIM
        from ai.basic_ai import BasicAI
        engine.ai_controller = BasicAI(llm_brain=None)
        for _ in range(300):
            engine.update(1 / 60)
        # Should have spawned some enemies and not crashed
        if DETERMINISTIC_SIM:
            assert engine._sim_now_ms > 0
    finally:
        pygame.quit()


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
