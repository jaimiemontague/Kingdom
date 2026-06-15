"""WK141 Blackbanner chain gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.quest_chains import (
    ASSAULT_GATE,
    BLACKBANNER_TOLL_TAKER_NAME,
    BLACKBANNERS_TOLL,
    CLAIM_REWARD,
    INTERCEPT_TOLL_TAKER,
    SCOUT_FORTRESS,
    SLAY_BLACKBANNER,
)
from game.sim.timebase import set_sim_now_ms
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str = "wk141_hero", name: str = "Astra", x: float = 0.0, y: float = 0.0):
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


def _recording_bus():
    events: list[dict] = []

    class _Bus:
        def __init__(self):
            self.subscriptions: list[tuple[object, object]] = []

        def emit(self, event: dict) -> None:
            events.append(event)

        def subscribe(self, topic, callback) -> None:
            self.subscriptions.append((topic, callback))

    return _Bus(), events


def _make_context(hero: _Hero, fortress: object, castle: object, bus) -> SystemContext:
    return SystemContext(
        heroes=[hero],
        enemies=[],
        buildings=[castle],
        world=None,
        economy=None,
        event_bus=bus,
        pois=[fortress],
        castle=castle,
    )


def test_blackbanner_chain_definition_matches_the_landed_content():
    assert BLACKBANNERS_TOLL.chain_type == "blackbanners_toll"
    assert BLACKBANNERS_TOLL.display_name == "Blackbanner's Toll"
    assert BLACKBANNERS_TOLL.reward_profile.gold == 260
    assert BLACKBANNERS_TOLL.tags == ("bandit", "siege", "blackbanner")

    assert [phase.phase_id for phase in BLACKBANNERS_TOLL.phases] == [
        SCOUT_FORTRESS,
        INTERCEPT_TOLL_TAKER,
        ASSAULT_GATE,
        SLAY_BLACKBANNER,
        CLAIM_REWARD,
    ]
    assert [phase.title for phase in BLACKBANNERS_TOLL.phases] == [
        "Scout the Bandit Fortress",
        "Intercept the Toll-Taker",
        "Assault the Gate",
        "Defeat Rusk Blackbanner",
        "Claim the Spoils",
    ]
    assert [phase.objective_type for phase in BLACKBANNERS_TOLL.phases] == [
        SCOUT_FORTRESS,
        INTERCEPT_TOLL_TAKER,
        ASSAULT_GATE,
        SLAY_BLACKBANNER,
        CLAIM_REWARD,
    ]
    assert [phase.target_ref for phase in BLACKBANNERS_TOLL.phases] == [
        "fortress_target",
        "elite_target",
        "gate_target",
        "boss_target",
        "reward_target",
    ]
    assert BLACKBANNERS_TOLL.phases[1].target_ref == "elite_target"
    assert BLACKBANNERS_TOLL.phases[3].target_ref == "boss_target"


def test_blackbanner_chain_progresses_and_cleans_up_after_reward():
    system = QuestChainSystem()
    hero = _Hero(x=160.0, y=160.0)
    fortress = SimpleNamespace(
        entity_id="poi_blackbanner_fortress",
        poi_type="poi_bandit_fortress",
        poi_def=SimpleNamespace(display_name="Bandit Fortress"),
        x=160.0,
        y=160.0,
        center_x=160.0,
        center_y=160.0,
    )
    castle = SimpleNamespace(
        entity_id="castle",
        name="Castle",
        x=480.0,
        y=320.0,
        center_x=480.0,
        center_y=320.0,
        building_type="castle",
        hp=100,
        is_targetable=True,
    )
    bus, events = _recording_bus()
    ctx = _make_context(hero, fortress, castle, bus)

    set_sim_now_ms(1000)
    chain = system.start_blackbanners_toll(ctx=ctx, hero=hero, event_bus=bus, now_ms=1000)

    assert chain.chain_type == BLACKBANNERS_TOLL.chain_type
    assert chain.status == "active"
    assert chain.current_phase_id == SCOUT_FORTRESS
    assert chain.facts["fortress_target_name"] == "Bandit Fortress"
    assert chain.facts["elite_target_name"] == BLACKBANNER_TOLL_TAKER_NAME
    assert chain.facts["elite_target_spawn_key"] == "blackbanner_toll:1:toll_taker"
    assert chain.facts["boss_target_name"] == ""
    assert chain.facts["boss_target_revealed"] is False

    snapshot = system.get_active_chain_snapshots()[0]
    assert snapshot.current_phase_id == SCOUT_FORTRESS
    assert [phase.status for phase in snapshot.phases] == ["active", "upcoming", "upcoming", "upcoming", "upcoming"]
    assert snapshot.phases[1].target_name == BLACKBANNER_TOLL_TAKER_NAME
    assert snapshot.phases[3].target_name == ""

    set_sim_now_ms(1100)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == INTERCEPT_TOLL_TAKER
    assert chain.facts["boss_target_revealed"] is True
    assert chain.facts["boss_target_name"] == "Rusk Blackbanner"
    assert len(ctx.enemies) == 2

    revealed_snapshot = system.get_active_chain_snapshots()[0]
    assert revealed_snapshot.phases[3].target_name == "Rusk Blackbanner"

    elite = next(enemy for enemy in ctx.enemies if getattr(enemy, "elite_story_name", "") == BLACKBANNER_TOLL_TAKER_NAME)
    elite.hp = 0
    set_sim_now_ms(1200)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == ASSAULT_GATE
    assert chain.facts["elite_target_defeated"] is True

    hero.x, hero.y = chain.facts["gate_target_position"]
    set_sim_now_ms(1300)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == SLAY_BLACKBANNER
    assert chain.facts["boss_target_revealed"] is True

    boss = next(enemy for enemy in ctx.enemies if getattr(enemy, "enemy_type", "") == "bandit_lord")
    boss.hp = 0
    set_sim_now_ms(1400)
    system.update(ctx, 1 / 60)
    assert chain.current_phase_id == CLAIM_REWARD
    assert chain.facts["boss_target_defeated"] is True

    hero.x, hero.y = castle.center_x, castle.center_y
    set_sim_now_ms(1500)
    system.update(ctx, 1 / 60)

    assert chain.status == "completed"
    assert chain.completed_at_ms == 1500
    assert hero.gold == BLACKBANNERS_TOLL.reward_profile.gold
    assert system.chains == []
    assert system.completed_chains == [chain]
    assert system.get_active_chain_snapshots() == ()
    assert chain.facts["elite_target_entity_id"] == ""
    assert chain.facts["elite_target_name"] == ""
    assert chain.facts["boss_target_entity_id"] == ""
    assert chain.facts["boss_target_name"] == ""
    assert [record["phase_id"] for record in chain.history if record["event"] == "phase_started"] == [
        SCOUT_FORTRESS,
        INTERCEPT_TOLL_TAKER,
        ASSAULT_GATE,
        SLAY_BLACKBANNER,
        CLAIM_REWARD,
    ]
    assert [record["phase_id"] for record in chain.history if record["event"] == "phase_completed"] == [
        SCOUT_FORTRESS,
        INTERCEPT_TOLL_TAKER,
        ASSAULT_GATE,
        SLAY_BLACKBANNER,
        CLAIM_REWARD,
    ]
    assert [event["type"] for event in events] == [
        "quest_chain_offered",
        "quest_chain_accepted",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_phase_started",
        "quest_chain_phase_completed",
        "quest_chain_completed",
    ]
    assert chain.history[-1]["event"] == "chain_completed"
