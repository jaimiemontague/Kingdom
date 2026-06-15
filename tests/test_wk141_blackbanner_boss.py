"""WK141 Blackbanner boss gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.bosses import RUSK_BLACKBANNER_BOSS_DEF
from game.entities.enemy import Bandit, BanditLord
from game.events import GameEventType
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext


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
        self.is_alive = True

    def distance_to(self, x: float, y: float) -> float:
        dx = self.x - float(x)
        dy = self.y - float(y)
        return (dx * dx + dy * dy) ** 0.5


def _recording_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def test_rusk_blackbanner_registers_and_transitions_through_boss_phases():
    system = BossEncounterSystem()
    bus, events = _recording_bus()
    hero = _Hero(x=480.0, y=320.0)
    boss = BanditLord(480.0, 320.0)
    boss.target = hero
    ally = Bandit(512.0, 320.0)
    ctx = SystemContext(
        heroes=[hero],
        enemies=[boss, ally],
        buildings=[],
        world=None,
        economy=None,
        event_bus=bus,
        castle=None,
    )

    set_sim_now_ms(1_000)
    system.register_enemy(boss, event_bus=bus, now_ms=1_000)

    assert boss.is_boss is True
    assert boss.boss_def is RUSK_BLACKBANNER_BOSS_DEF
    assert boss.name == "Rusk Blackbanner"
    assert boss.current_boss_phase == "toll_banner"
    assert boss.current_boss_phase_title == "Toll Banner"
    assert boss.current_boss_ability_id == "toll_banner"
    assert boss.current_boss_ability_name == "Toll Banner"
    assert boss.current_boss_ability_payload["buff_enemy_type"] == "bandit"
    assert boss.current_boss_ability_payload["announce_on_register"] is True

    snapshot = system.get_active_boss_snapshots()[0]
    assert snapshot.boss_id == boss.entity_id
    assert snapshot.name == "Rusk Blackbanner"
    assert snapshot.current_phase == "toll_banner"
    assert snapshot.current_phase_title == "Toll Banner"
    assert snapshot.target_hero_id == hero.hero_id
    assert snapshot.latest_telegraph == ""

    assert events[0]["type"] == GameEventType.BOSS_ENCOUNTER_STARTED.value
    assert events[0]["current_phase"] == "toll_banner"
    assert events[0]["name"] == "Rusk Blackbanner"

    boss.hp = 149
    set_sim_now_ms(2_000)
    system.update(ctx, 1 / 60)

    assert boss.current_boss_phase == "smoke_retreat"
    assert boss.current_boss_phase_title == "Smoke Retreat"
    assert boss.current_boss_ability_id == "smoke_retreat"
    assert boss.current_boss_ability_name == "Smoke Retreat"
    assert boss.current_boss_ability_payload["announce_on_phase_change"] is True
    assert boss.current_boss_ability_payload["speed_multiplier"] == 1.15

    snapshot = system.get_active_boss_snapshots()[0]
    assert snapshot.current_phase == "smoke_retreat"
    assert snapshot.current_phase_title == "Smoke Retreat"
    assert snapshot.latest_telegraph == ""
    assert any(event["type"] == GameEventType.BOSS_PHASE_CHANGED.value for event in events)

    boss.hp = 0
    set_sim_now_ms(3_000)
    system.update(ctx, 1 / 60)

    assert system.get_active_boss_snapshots() == ()
    assert system.bosses == []
    assert system.defeated_bosses == [boss]
    assert boss.boss_status == "defeated"
    assert boss.memory_facts[-1]["event"] == "defeated_by"
    assert boss.memory_facts[-1]["hero_id"] == hero.hero_id
    assert boss.defeated_by[-1]["hero_id"] == hero.hero_id
    assert events[-1]["type"] == GameEventType.BOSS_DEFEATED.value
    assert events[-1]["defeated_by_hero_id"] == hero.hero_id

