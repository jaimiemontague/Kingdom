"""WK138 quest-chain cleanup and empty-path tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.sim.timebase import set_sim_now_ms
from game.systems.quest_chain import QuestChainSystem
from game.systems.protocol import SystemContext


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _ExplosiveContext:
    def __getattr__(self, name: str):
        raise AssertionError(f"QuestChainSystem.update() should not touch context when no chains are live: {name}")


class _Hero:
    def __init__(self, *, hero_id: str = "wk138_h2", name: str = "Bryn", x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.gold = 0
        self.is_alive = True

    def distance_to(self, x: float, y: float) -> float:
        dx = self.x - float(x)
        dy = self.y - float(y)
        return (dx * dx + dy * dy) ** 0.5

    def add_gold(self, amount: int) -> None:
        self.gold += int(amount)


class _Target:
    def __init__(
        self,
        *,
        entity_id: str,
        name: str,
        x: float,
        y: float,
        poi_type: str = "",
        building_type: str = "",
    ):
        self.entity_id = entity_id
        self.poi_type = poi_type
        self.building_type = building_type
        self.poi_def = SimpleNamespace(display_name=name)
        self.center_x = float(x)
        self.center_y = float(y)
        self.x = float(x)
        self.y = float(y)


def _recording_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def _make_context(hero: _Hero, origin: _Target, castle: _Target, bus):
    return SystemContext(
        heroes=[hero],
        enemies=[],
        buildings=[castle],
        world=None,
        economy=None,
        event_bus=bus,
        pois=[origin],
        castle=castle,
    )


def test_empty_update_is_a_true_no_op():
    system = QuestChainSystem()
    system.update(_ExplosiveContext(), 1 / 60)

    assert system.chains == []
    assert system.completed_chains == []
    assert system.failed_chains == []
    assert system.get_active_chain_snapshots() == ()
    assert system.get_active_chain_views() == ()
    assert system.get_active_chains() == ()


def test_missing_target_fails_and_archives_the_chain():
    system = QuestChainSystem()
    hero = _Hero(x=128.0, y=96.0)
    origin = _Target(
        entity_id="poi_ancient_ruins",
        name="Ancient Ruins",
        x=128.0,
        y=96.0,
        poi_type="poi_ancient_ruins",
        building_type="poi_ancient_ruins",
    )
    castle = _Target(
        entity_id="castle",
        name="Castle",
        x=384.0,
        y=256.0,
        building_type="castle",
    )
    bus, events = _recording_bus()
    ctx = _make_context(hero, origin, castle, bus)

    set_sim_now_ms(1000)
    chain = system.start_relic_of_the_old_shrine(ctx=ctx, hero=hero, event_bus=bus, now_ms=1000)
    assert chain.status == "active"

    ctx.pois = []
    set_sim_now_ms(2000)
    system.update(ctx, 1 / 60)

    assert chain.status == "failed"
    assert chain.failed_at_ms == 2000
    assert system.chains == []
    assert system.completed_chains == []
    assert system.failed_chains == [chain]
    assert system.get_active_chain_snapshots() == ()
    assert events[-1]["type"] == "quest_chain_failed"
    assert events[-1]["reason"] == "target_missing"
    assert chain.history[-1]["event"] == "chain_failed"
    assert chain.history[-1]["reason"] == "target_missing"
