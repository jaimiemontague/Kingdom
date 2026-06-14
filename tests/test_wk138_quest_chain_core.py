"""WK138 quest-chain gameplay state machine core tests."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from game.content.quest_chains import COLLECT_ITEM, DELIVER_ITEM, RELIC_OF_THE_OLD_SHRINE, SCOUT_LOCATION
from game.sim.contracts import QuestChainHistorySummary, QuestChainSnapshot
from game.sim.timebase import set_sim_now_ms
from game.systems.quest_chain import QuestChainSystem
from game.systems.protocol import SystemContext


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str = "wk138_h1", name: str = "Astra", x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.gold = 0
        self.is_alive = True

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))

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


def _assert_small_history_record(record: dict[str, object]) -> None:
    assert isinstance(record, dict)
    assert all(isinstance(value, (str, int, float, bool, tuple, type(None))) for value in record.values())
    for key, value in record.items():
        if key == "target_position" and value is not None:
            assert isinstance(value, tuple)
            assert len(value) == 2
            assert all(isinstance(coord, (int, float)) for coord in value)


def test_relic_chain_progresses_through_all_three_phases():
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
    chain = system.offer_relic_of_the_old_shrine(ctx=ctx, hero=hero, event_bus=bus)

    assert chain.chain_type == RELIC_OF_THE_OLD_SHRINE.chain_type
    assert chain.status == "offered"
    assert chain.current_phase_id == SCOUT_LOCATION
    assert chain.facts["origin_target_id"] == origin.entity_id
    assert chain.facts["delivery_target_id"] == castle.entity_id
    assert chain.facts["relic_collected"] is False
    assert [event["type"] for event in events] == ["quest_chain_offered"]

    set_sim_now_ms(2000)
    accepted = system.accept_chain(chain.chain_id, hero=hero, event_bus=bus, now_ms=2000)
    assert accepted is True
    assert chain.status == "active"
    assert chain.assigned_hero_id == hero.hero_id
    assert [event["type"] for event in events[:3]] == [
        "quest_chain_offered",
        "quest_chain_accepted",
        "quest_chain_phase_started",
    ]

    set_sim_now_ms(3000)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == COLLECT_ITEM
    assert chain.facts["relic_scouted"] is True
    assert chain.history[-1]["event"] == "phase_started"
    assert chain.history[-1]["phase_id"] == COLLECT_ITEM

    snap = system.get_active_chain_snapshots()[0]
    assert isinstance(snap, QuestChainSnapshot)
    assert snap.current_phase_id == COLLECT_ITEM
    assert snap.phases[0].status == "completed"
    assert snap.phases[1].status == "active"
    assert snap.phases[2].status == "upcoming"
    assert isinstance(snap.phases[0].history[0], QuestChainHistorySummary)
    assert snap.phases[0].history[0].event == "phase_started"
    assert snap.phases[0].history[1].event == "phase_completed"

    set_sim_now_ms(4000)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == DELIVER_ITEM
    assert chain.facts["relic_collected"] is True
    assert chain.facts["relic_carried"] is True
    assert chain.facts["relic_carried_by_hero_id"] == hero.hero_id
    assert chain.history[-2]["event"] == "phase_completed"
    assert chain.history[-2]["phase_id"] == COLLECT_ITEM
    assert chain.history[-1]["event"] == "phase_started"
    assert chain.history[-1]["phase_id"] == DELIVER_ITEM

    hero.x = castle.center_x
    hero.y = castle.center_y
    set_sim_now_ms(5000)
    system.update(ctx, 1 / 60)

    assert chain.status == "completed"
    assert chain.completed_at_ms == 5000
    assert hero.gold == RELIC_OF_THE_OLD_SHRINE.reward_profile.gold
    assert system.chains == []
    assert system.completed_chains == [chain]
    assert system.get_active_chain_snapshots() == ()
    assert [event["type"] for event in events] == [
        "quest_chain_offered",
        "quest_chain_accepted",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_completed",
    ]
    assert events[-1]["reward_gold"] == RELIC_OF_THE_OLD_SHRINE.reward_profile.gold

    for record in chain.history:
        _assert_small_history_record(record)

    assert all(
        isinstance(summary, QuestChainHistorySummary)
        for summary in snap.history
    )
