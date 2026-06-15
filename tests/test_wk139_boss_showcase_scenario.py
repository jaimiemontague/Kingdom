from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.engine import GameEngine
from tools.screenshot_scenarios import get_scenario


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_boss_encounter_showcase_registers_boss_elite_and_telegraph():
    engine = GameEngine(headless=True, headless_ui=True)

    shots = get_scenario(engine, "boss_encounter_showcase", seed=3)
    assert len(shots) == 1

    shot = shots[0]
    assert shot.filename == "boss_encounter_showcase.png"
    assert callable(shot.apply)

    shot.apply(engine)

    boss_system = engine.sim.boss_encounter_system
    boss_snapshots = boss_system.get_active_boss_snapshots()
    elite_snapshots = boss_system.get_active_elite_snapshots()

    assert len(boss_snapshots) == 1
    assert boss_snapshots[0].name == "The Goblin Warchief"
    assert boss_snapshots[0].current_phase_title == "Rally"
    assert boss_snapshots[0].latest_telegraph == "rally"
    assert len(elite_snapshots) == 1
    assert elite_snapshots[0].name == "Skull-Banner Goblin"
    assert elite_snapshots[0].affixes == ("banner_bearer", "ironhide")

    game_state = engine.get_game_state()
    lines = engine.hud._top_bar._boss_status_lines(game_state)
    assert lines[0][0] == "The Goblin Warchief"
    assert "Tell: Rally" in lines[1][0]
    assert lines[2][0] == "Elites: 1 | banner/shield"

    telegraphs = getattr(engine.vfx_system, "_boss_telegraphs", {})
    assert boss_snapshots[0].boss_id in telegraphs
    assert telegraphs[boss_snapshots[0].boss_id].ability_id == "rally"

    assert engine.show_perf is False
    assert engine.screenshot_hide_ui is False
