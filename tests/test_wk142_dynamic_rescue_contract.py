"""WK142 dynamic rescue/revenge contract pins.

These tests lock the new primitive capture/rescue/revenge read-model surfaces
without introducing any gameplay behavior. Fresh engines stay empty/default;
stubbed systems flow through the sim/view contracts as frozen primitive tuples.
"""

from __future__ import annotations

import dataclasses
import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.engine import GameEngine
from game.sim.ai_view import AiGameView
from game.sim.contracts import (
    BossKillMemory,
    HeroCaptureState,
    RescueOpportunitySnapshot,
    RevengeOpportunitySnapshot,
)
from game.sim.snapshot import RenderSnapshot


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _captured_state() -> HeroCaptureState:
    return HeroCaptureState(
        hero_id="wk142_captive",
        hero_name="Astra",
        captor_boss_id="boss_rusk_blackbanner",
        captor_boss_name="Rusk Blackbanner",
        captor_boss_type="bandit_lord",
        location_id="poi_blackbanner_fortress",
        location_name="Bandit Fortress",
        source_chain_id="chain_blackbanner_cells",
        source_chain_type="blackbanners_toll",
        captured_at_ms=1_000,
        status="captured",
    )


def _rescue_opportunity() -> RescueOpportunitySnapshot:
    return RescueOpportunitySnapshot(
        rescue_id="rescue_blackbanner_cells",
        captured_hero_id="wk142_captive",
        captured_hero_name="Astra",
        captor_boss_id="boss_rusk_blackbanner",
        captor_boss_name="Rusk Blackbanner",
        captor_boss_type="bandit_lord",
        target_location_id="poi_blackbanner_fortress",
        target_location_name="Bandit Fortress",
        current_phase_id="reach_fortress",
        current_phase_title="Reach the Bandit Fortress",
        source_chain_id="chain_blackbanner_cells",
        source_chain_type="blackbanners_toll",
        status="active",
        offered_at_ms=1_100,
    )


def _boss_kill_memory() -> BossKillMemory:
    return BossKillMemory(
        boss_id="boss_rusk_blackbanner",
        boss_name="Rusk Blackbanner",
        boss_type="bandit_lord",
        fallen_hero_id="wk142_fallen",
        fallen_hero_name="Mira",
        location_id="poi_blackbanner_fortress",
        location_name="Bandit Fortress",
        killed_at_ms=2_000,
        revenge_chain_id="revenge_rusk_mira",
        status="remembered",
    )


def _revenge_opportunity() -> RevengeOpportunitySnapshot:
    return RevengeOpportunitySnapshot(
        revenge_id="revenge_rusk_mira",
        boss_id="boss_rusk_blackbanner",
        boss_name="Rusk Blackbanner",
        boss_type="bandit_lord",
        fallen_hero_id="wk142_fallen",
        fallen_hero_name="Mira",
        target_location_id="poi_blackbanner_fortress",
        target_location_name="Bandit Fortress",
        current_phase_id="avenge_fallen_hero",
        current_phase_title="Avenge Mira",
        revenge_chain_id="revenge_rusk_mira",
        status="active",
        offered_at_ms=2_050,
    )


def _capture_stub(*, captured=(), rescue=()):
    return SimpleNamespace(
        get_active_captured_hero_snapshots=lambda: captured,
        get_active_captured_heroes=lambda: captured,
        get_active_capture_snapshots=lambda: captured,
        get_active_rescue_opportunity_snapshots=lambda: rescue,
        get_active_rescue_opportunities=lambda: rescue,
        get_active_rescue_views=lambda: rescue,
    )


def _boss_stub(*, memories=(), revenge=()):
    return SimpleNamespace(
        get_active_boss_kill_memory_snapshots=lambda: memories,
        get_active_boss_kill_memories=lambda: memories,
        get_active_boss_kill_memory_views=lambda: memories,
        get_active_revenge_opportunity_snapshots=lambda: revenge,
        get_active_revenge_opportunities=lambda: revenge,
        get_active_revenge_views=lambda: revenge,
    )


def test_wk142_contract_dataclasses_are_frozen_and_primitive_only():
    captured = _captured_state()
    rescue = _rescue_opportunity()
    memory = _boss_kill_memory()
    revenge = _revenge_opportunity()

    for obj in (captured, rescue, memory, revenge):
        assert dataclasses.is_dataclass(obj)
        with pytest.raises(dataclasses.FrozenInstanceError):
            obj.status = "mutated"  # type: ignore[misc]

    assert captured.to_dict()["hero_name"] == "Astra"
    assert captured.to_dict()["captor_boss_name"] == "Rusk Blackbanner"
    assert rescue.to_dict()["current_phase_title"] == "Reach the Bandit Fortress"
    assert rescue.to_dict()["captured_hero_id"] == "wk142_captive"
    assert memory.to_dict()["fallen_hero_name"] == "Mira"
    assert memory.to_dict()["revenge_chain_id"] == "revenge_rusk_mira"
    assert revenge.to_dict()["boss_name"] == "Rusk Blackbanner"
    assert revenge.to_dict()["current_phase_id"] == "avenge_fallen_hero"


def test_wk142_empty_default_views_stay_empty_on_fresh_engine():
    engine = GameEngine(headless=True)
    try:
        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert isinstance(view, AiGameView)
        assert isinstance(snapshot, RenderSnapshot)
        assert isinstance(view.captured_heroes, tuple)
        assert isinstance(view.rescue_opportunities, tuple)
        assert isinstance(view.boss_kill_memories, tuple)
        assert isinstance(view.revenge_opportunities, tuple)
        assert isinstance(snapshot.captured_heroes, tuple)
        assert isinstance(snapshot.rescue_opportunities, tuple)
        assert isinstance(snapshot.boss_kill_memories, tuple)
        assert isinstance(snapshot.revenge_opportunities, tuple)
        assert view.captured_heroes == ()
        assert view.rescue_opportunities == ()
        assert view.boss_kill_memories == ()
        assert view.revenge_opportunities == ()
        assert snapshot.captured_heroes == ()
        assert snapshot.rescue_opportunities == ()
        assert snapshot.boss_kill_memories == ()
        assert snapshot.revenge_opportunities == ()
    finally:
        pygame.quit()


def test_wk142_stubbed_capture_and_revenge_views_flow_through_engine_read_models():
    engine = GameEngine(headless=True)
    try:
        captured = _captured_state()
        rescue = _rescue_opportunity()
        memory = _boss_kill_memory()
        revenge = _revenge_opportunity()
        engine.sim.quest_chain_system = _capture_stub(captured=(captured,), rescue=(rescue,))
        engine.sim.boss_encounter_system = _boss_stub(memories=(memory,), revenge=(revenge,))

        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert view.captured_heroes == (captured,)
        assert view.rescue_opportunities == (rescue,)
        assert view.boss_kill_memories == (memory,)
        assert view.revenge_opportunities == (revenge,)
        assert snapshot.captured_heroes == (captured,)
        assert snapshot.rescue_opportunities == (rescue,)
        assert snapshot.boss_kill_memories == (memory,)
        assert snapshot.revenge_opportunities == (revenge,)
        assert view.captured_heroes[0].status == "captured"
        assert view.rescue_opportunities[0].captor_boss_name == "Rusk Blackbanner"
        assert snapshot.boss_kill_memories[0].fallen_hero_name == "Mira"
        assert snapshot.revenge_opportunities[0].current_phase_title == "Avenge Mira"
    finally:
        pygame.quit()
