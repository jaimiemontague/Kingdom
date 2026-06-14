"""WK138 quest-chain AI/view pins.

This file locks the read-only view surface, the empty-default path, and the
live engine registration so a no-chain engine stays a no-op while active
snapshots flow through the read model.
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
from game.sim.timebase import set_sim_now_ms
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_ai_view_and_snapshot_expose_empty_chain_tuples_on_fresh_engine():
    engine = GameEngine(headless=True)
    try:
        assert isinstance(engine.sim.quest_chain_system, QuestChainSystem)
        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert hasattr(view, "quest_chains")
        assert isinstance(view.quest_chains, tuple)
        assert view.quest_chains == ()
        assert engine.sim.quest_chain_system.get_active_chain_snapshots() == ()

        assert hasattr(snapshot, "quest_chains")
        assert isinstance(snapshot.quest_chains, tuple)
        assert snapshot.quest_chains == ()
    finally:
        pygame.quit()


def test_live_chain_snapshots_flow_through_engine_read_models():
    engine = GameEngine(headless=True)
    try:
        chain_system = engine.sim.quest_chain_system
        assert isinstance(chain_system, QuestChainSystem)

        hero = SimpleNamespace(
            hero_id="wk138_h1",
            name="Astra",
            x=128.0,
            y=96.0,
            gold=0,
            is_alive=True,
        )
        origin = SimpleNamespace(
            entity_id="poi_ancient_ruins",
            name="Ancient Ruins",
            poi_type="poi_ancient_ruins",
            building_type="poi_ancient_ruins",
            poi_def=SimpleNamespace(display_name="Ancient Ruins"),
            center_x=128.0,
            center_y=96.0,
            x=128.0,
            y=96.0,
        )
        castle = SimpleNamespace(
            entity_id="castle",
            name="Castle",
            building_type="castle",
            poi_type="",
            poi_def=SimpleNamespace(display_name="Castle"),
            center_x=384.0,
            center_y=256.0,
            x=384.0,
            y=256.0,
        )
        events: list[dict] = []
        bus = SimpleNamespace(emit=events.append)
        ctx = SystemContext(
            heroes=[hero],
            enemies=[],
            buildings=[castle],
            world=None,
            economy=None,
            event_bus=bus,
            pois=[origin],
            castle=castle,
        )

        set_sim_now_ms(1000)
        chain_system.start_relic_of_the_old_shrine(ctx=ctx, hero=hero, event_bus=bus, now_ms=1000)

        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert len(view.quest_chains) == 1
        assert len(snapshot.quest_chains) == 1
        assert view.quest_chains[0].chain_type == "relic_of_the_old_shrine"
        assert snapshot.quest_chains[0].status == "active"
        assert view.quest_chains[0] == snapshot.quest_chains[0]
        assert events[0]["type"] == "quest_chain_offered"
        assert events[1]["type"] == "quest_chain_accepted"
    finally:
        set_sim_now_ms(0)
        pygame.quit()


def test_ai_view_is_constructible_without_chain_kwargs():
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
    )
    assert view.quest_chains == ()
    assert isinstance(view.quest_chains, tuple)


def test_chain_fields_are_read_only():
    engine = GameEngine(headless=True)
    try:
        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        with pytest.raises(dataclasses.FrozenInstanceError):
            view.quest_chains = ("mutated",)  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.quest_chains = ("mutated",)  # type: ignore[misc]
    finally:
        pygame.quit()
