from __future__ import annotations

import pygame
import pytest

from game.engine import GameEngine
from game.sim.timebase import set_sim_now_ms
from game.systems.quest_chain import QuestChainSystem
from tools.screenshot_scenarios import Shot, get_scenario


@pytest.fixture(autouse=True)
def _pygame_session():
    set_sim_now_ms(0)
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()
    set_sim_now_ms(0)


def _engine() -> GameEngine:
    return GameEngine(headless=True, headless_ui=True)


def _active_chain_types(engine: GameEngine) -> set[str]:
    return {
        str(getattr(snapshot, "chain_type", "") or "")
        for snapshot in engine.sim.quest_chain_system.get_active_chain_snapshots()
    }


def test_wk146_quest_chain_scenarios_are_registered_with_expected_filenames():
    expectations = {
        "quest_chain_launcher_ui": ["quest_chain_launcher_ui.png"],
        "quest_chain_live_blackbanner": [
            "quest_chain_live_blackbanner_world.png",
            "quest_chain_live_blackbanner_ledger.png",
        ],
        "quest_chain_live_ashwing": [
            "quest_chain_live_ashwing_world.png",
            "quest_chain_live_ashwing_ledger.png",
        ],
    }

    for scenario_name, filenames in expectations.items():
        engine = _engine()
        shots = get_scenario(engine, scenario_name, seed=3)

        assert all(isinstance(shot, Shot) for shot in shots)
        assert [shot.filename for shot in shots] == filenames
        assert all(callable(shot.apply) for shot in shots)
        assert all(shot.meta is not None for shot in shots)
        assert {shot.meta["scenario"] for shot in shots} == {scenario_name}


@pytest.mark.parametrize(
    ("scenario_name", "expected_chain_type"),
    (
        ("quest_chain_live_blackbanner", "blackbanners_toll"),
        ("quest_chain_live_ashwing", "ashwings_hoard"),
    ),
)
def test_wk146_live_scenarios_launch_real_active_quest_chains(
    scenario_name: str,
    expected_chain_type: str,
):
    engine = _engine()
    shots = get_scenario(engine, scenario_name, seed=3)

    assert isinstance(engine.sim.quest_chain_system, QuestChainSystem)
    assert expected_chain_type in _active_chain_types(engine)

    snapshots = engine.sim.quest_chain_system.get_active_chain_snapshots()
    snapshot = next(s for s in snapshots if s.chain_type == expected_chain_type)
    assert snapshot.status == "active"
    assert snapshot.current_phase_id
    assert snapshot.assigned_hero_id
    assert len(engine.heroes) == 10

    for shot in shots:
        meta = shot.meta or {}
        assert meta["chain_type"] == expected_chain_type
        assert meta["current_phase"] == snapshot.current_phase_id
        assert meta["current_phase_title"] == snapshot.current_phase_title
        assert meta["hero_count"] == 10
        assert meta["target_poi_id"]
        assert meta["target_poi_name"] in {"Bandit Fortress", "Dragon Cave"}
        assert meta["target_poi_type"] in {"poi_bandit_fortress", "poi_dragon_cave"}

    shots[-1].apply(engine)
    assert engine.building_panel.quest_create_panel.visible is True
    assert isinstance(engine.sim.quest_chain_system, QuestChainSystem)
    assert expected_chain_type in _active_chain_types(engine)


def test_wk146_launcher_ui_opens_existing_post_modal_and_board_area():
    engine = _engine()
    shots = get_scenario(engine, "quest_chain_launcher_ui", seed=3)

    assert len(shots) == 1
    shot = shots[0]
    assert shot.meta["hero_count"] == 10
    assert shot.meta["herald_post_id"]
    assert shot.meta["quest_board"] == "visible"
    assert isinstance(engine.sim.quest_chain_system, QuestChainSystem)

    shot.apply(engine)

    assert engine.selected_building is not None
    assert getattr(engine.selected_building, "building_type", "") == "herald_post"
    assert engine.building_panel.visible is True
    assert engine.building_panel.quest_create_panel.visible is True
