"""WK139 boss read-model pins."""

from __future__ import annotations

import dataclasses
import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.engine import GameEngine
from game.entities.enemy import Goblin
from game.sim.ai_view import AiGameView
from game.sim.determinism import get_rng
from game.systems.boss_encounter import BossEncounterSystem


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_ai_view_and_snapshot_expose_empty_boss_tuples_on_fresh_engine():
    engine = GameEngine(headless=True)
    try:
        assert isinstance(engine.sim.boss_encounter_system, BossEncounterSystem)
        boss_rng = get_rng("boss_encounters")
        state_before = boss_rng.getstate()

        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert isinstance(view.boss_encounters, tuple)
        assert isinstance(view.elite_enemies, tuple)
        assert isinstance(view.elite_encounters, tuple)
        assert isinstance(snapshot.boss_encounters, tuple)
        assert isinstance(snapshot.elite_enemies, tuple)
        assert isinstance(snapshot.elite_encounters, tuple)
        assert view.boss_encounters == ()
        assert view.elite_enemies == ()
        assert view.elite_encounters == ()
        assert snapshot.boss_encounters == ()
        assert snapshot.elite_enemies == ()
        assert snapshot.elite_encounters == ()
        assert view.elite_encounters == view.elite_enemies
        assert snapshot.elite_encounters == snapshot.elite_enemies
        assert boss_rng.getstate() == state_before
    finally:
        pygame.quit()


def test_ai_view_is_constructible_without_boss_kwargs():
    view = AiGameView(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
        commands=None,
    )
    assert view.boss_encounters == ()
    assert view.elite_enemies == ()
    assert view.elite_encounters == ()
    assert isinstance(view.boss_encounters, tuple)
    assert isinstance(view.elite_enemies, tuple)
    assert isinstance(view.elite_encounters, tuple)


def test_active_boss_and_elite_snapshots_flow_through_read_models():
    engine = GameEngine(headless=True)
    try:
        system = engine.sim.boss_encounter_system
        assert isinstance(system, BossEncounterSystem)

        boss = SimpleNamespace(
            entity_id="boss-1",
            enemy_type="goblin_warchief",
            name="The Goblin Warchief",
            hp=45,
            max_hp=60,
            is_alive=True,
            x=128.0,
            y=96.0,
            target=None,
        )
        elite = Goblin(64.0, 64.0)

        system.register_boss(boss, event_bus=engine.sim.event_bus, now_ms=1234)
        system.register_elite(
            elite,
            affix_ids=("banner_bearer",),
            event_bus=engine.sim.event_bus,
            now_ms=1234,
        )

        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert len(view.boss_encounters) == 1
        assert len(snapshot.boss_encounters) == 1
        assert view.boss_encounters[0].boss_id == "boss-1"
        assert view.boss_encounters[0].boss_type == "goblin_warchief"
        assert view.boss_encounters[0].hp_pct == pytest.approx(0.75)
        assert snapshot.boss_encounters[0].current_phase_title == view.boss_encounters[0].current_phase_title

        assert len(view.elite_enemies) == 1
        assert len(snapshot.elite_enemies) == 1
        assert view.elite_enemies[0].base_type == "goblin"
        assert view.elite_enemies[0].affixes == ("banner_bearer",)
        assert snapshot.elite_enemies[0].affixes == ("banner_bearer",)
        assert view.elite_encounters == view.elite_enemies
        assert snapshot.elite_encounters == snapshot.elite_enemies
    finally:
        pygame.quit()


def test_boss_fields_are_read_only():
    engine = GameEngine(headless=True)
    try:
        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        with pytest.raises(dataclasses.FrozenInstanceError):
            view.boss_encounters = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            view.elite_enemies = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            view.elite_encounters = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.boss_encounters = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.elite_enemies = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.elite_encounters = ("mutated",)  # type: ignore[misc]
    finally:
        pygame.quit()
