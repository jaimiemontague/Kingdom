"""WK142 Blackbanner revenge gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.bosses import RUSK_BLACKBANNER_BOSS_DEF
from game.content.quest_chains import AVENGE_FALLEN_HERO, BLACKBANNER_REVENGE
from game.entities.enemy import BanditLord
from game.entities.hero import HeroState
from game.sim.contracts import BossKillMemory, RevengeOpportunitySnapshot
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str, name: str, x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.gold = 0
        self.hp = 100
        self.max_hp = 100
        self.is_alive = True
        self.state = HeroState.IDLE
        self.can_attack = True
        self.attack_blocked_reason = ""
        self.is_captured = False

    def distance_to(self, x: float, y: float) -> float:
        dx = self.x - float(x)
        dy = self.y - float(y)
        return (dx * dx + dy * dy) ** 0.5

    def add_gold(self, amount: int) -> None:
        self.gold += int(amount)


def _recording_bus():
    events: list[dict] = []
    subscriptions: list[tuple[object, object]] = []

    class _Bus:
        def emit(self, event: dict) -> None:
            events.append(event)

        def subscribe(self, topic, callback) -> None:
            subscriptions.append((topic, callback))

    return _Bus(), events, subscriptions


def _make_context(fallen: _Hero, avenger: _Hero, boss, bus) -> SystemContext:
    return SystemContext(
        heroes=[fallen, avenger],
        enemies=[boss],
        buildings=[],
        world=None,
        economy=None,
        event_bus=bus,
        castle=None,
    )


def test_blackbanner_revenge_loop_records_memory_and_completes_when_rusk_falls():
    quest_system = QuestChainSystem()
    boss_system = BossEncounterSystem()
    fallen = _Hero(hero_id="wk142_fallen", name="Mira", x=192.0, y=192.0)
    avenger = _Hero(hero_id="wk142_avenger", name="Lyra", x=224.0, y=224.0)
    boss = BanditLord(384.0, 256.0)
    bus, events, _ = _recording_bus()
    ctx = _make_context(fallen, avenger, boss, bus)

    set_sim_now_ms(2000)
    boss_system.register_boss(boss, boss_def=RUSK_BLACKBANNER_BOSS_DEF, event_bus=bus, now_ms=2000)

    set_sim_now_ms(2050)
    revenge_chain = quest_system.record_blackbanner_revenge(
        boss=boss,
        hero=fallen,
        ctx=ctx,
        event_bus=bus,
        now_ms=2050,
    )
    assert revenge_chain is not None
    assert revenge_chain.chain_type == BLACKBANNER_REVENGE.chain_type
    assert revenge_chain.status == "offered"
    assert revenge_chain.current_phase_id == AVENGE_FALLEN_HERO
    assert revenge_chain.facts["boss_target_name"] == "Rusk Blackbanner"
    assert revenge_chain.facts["fallen_hero_id"] == fallen.hero_id
    assert len([chain for chain in quest_system.chains if chain.chain_type == BLACKBANNER_REVENGE.chain_type]) == 1

    memory_snapshots = boss_system.get_active_boss_kill_memory_snapshots()
    revenge_snapshots = boss_system.get_active_revenge_opportunity_snapshots()
    assert len(memory_snapshots) == 1
    assert len(revenge_snapshots) == 1
    assert isinstance(memory_snapshots[0], BossKillMemory)
    assert isinstance(revenge_snapshots[0], RevengeOpportunitySnapshot)
    assert memory_snapshots[0].boss_name == "Rusk Blackbanner"
    assert memory_snapshots[0].fallen_hero_id == fallen.hero_id
    assert revenge_snapshots[0].boss_id == boss.entity_id
    assert revenge_snapshots[0].current_phase_title == "Avenge the Fallen"

    duplicate = quest_system.record_blackbanner_revenge(
        boss=boss,
        hero=fallen,
        ctx=ctx,
        event_bus=bus,
        now_ms=2060,
    )
    assert duplicate is revenge_chain
    assert len([chain for chain in quest_system.chains if chain.chain_type == BLACKBANNER_REVENGE.chain_type]) == 1

    accepted = quest_system.accept_chain(revenge_chain.chain_id, ctx=ctx, hero=avenger, event_bus=bus, now_ms=2100)
    assert accepted is True
    assert revenge_chain.status == "active"
    assert revenge_chain.assigned_hero_id == avenger.hero_id

    boss.target = avenger
    boss.take_damage(999)
    set_sim_now_ms(2200)
    boss_system.update(ctx, 1 / 60)
    assert boss_system.get_active_boss_snapshots() == ()
    assert boss_system.get_active_boss_kill_memory_snapshots() == ()
    assert boss_system.get_active_revenge_opportunity_snapshots() == ()
    assert boss.memory_facts[-1]["event"] == "defeated_by"
    assert boss.defeated_by[-1]["hero_id"] == avenger.hero_id

    set_sim_now_ms(2300)
    quest_system.update(ctx, 1 / 60)

    assert revenge_chain.status == "completed"
    assert revenge_chain.completed_at_ms == 2300
    assert avenger.gold == BLACKBANNER_REVENGE.reward_profile.gold
    assert quest_system.get_active_revenge_opportunity_snapshots() == ()
    assert quest_system.get_active_chain_snapshots() == ()
    assert quest_system.completed_chains == [revenge_chain]
    assert [event["type"] for event in events if event["type"].startswith("boss")]  # smoke check
