"""WK139 boss encounter gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.entities.enemy import Goblin, GoblinWarchief
from game.events import GameEventType
from game.sim.determinism import get_rng
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str = "h-wk139", name: str = "Astra", x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

    def distance_to(self, x: float, y: float) -> float:
        dx = self.x - float(x)
        dy = self.y - float(y)
        return (dx * dx + dy * dy) ** 0.5


class _ExplosiveContext:
    def __getattr__(self, name: str):
        raise AssertionError(f"BossEncounterSystem.update() should not touch empty-path context: {name}")


def _make_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def _make_context(heroes: list, enemies: list, bus) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=enemies,
        buildings=[],
        world=object(),
        economy=object(),
        event_bus=bus,
        castle=None,
    )


def test_empty_update_is_a_true_no_op():
    system = BossEncounterSystem()
    boss_rng = get_rng("boss_encounters")
    state_before = boss_rng.getstate()

    system.update(_ExplosiveContext(), 1 / 60)

    assert system.get_active_boss_snapshots() == ()
    assert system.get_active_elite_snapshots() == ()
    assert boss_rng.getstate() == state_before


def test_warchief_banner_phase_transitions_to_rally_and_reinforces_when_thin():
    system = BossEncounterSystem()
    bus, events = _make_bus()
    hero = _Hero(hero_id="wk139_h1", name="Astra", x=160.0, y=160.0)
    boss = GoblinWarchief(160.0, 160.0)
    boss.target = hero
    nearby = Goblin(180.0, 160.0)
    far = Goblin(160.0 + 320.0, 160.0)
    enemies = [boss, nearby, far]
    ctx = _make_context([hero], enemies, bus)

    set_sim_now_ms(1000)
    system.register_boss(boss, event_bus=bus, now_ms=1000)

    snapshot = system.get_active_boss_snapshots()[0]
    assert snapshot.current_phase == "war_banner"
    assert snapshot.current_phase_title == "War Banner"
    assert snapshot.latest_telegraph == ""
    assert snapshot.target_hero_id == hero.hero_id

    system.update(ctx, 1 / 60)
    assert nearby.get_attack_bonus() == 2
    assert far.get_attack_bonus() == 0
    assert [event["type"] for event in events] == ["boss_encounter_started"]

    boss.take_damage(30)
    set_sim_now_ms(2000)
    system.update(ctx, 1 / 60)

    snapshot = system.get_active_boss_snapshots()[0]
    assert snapshot.current_phase == "rally"
    assert snapshot.current_phase_title == "Rally"
    assert snapshot.latest_telegraph == "rally"
    assert nearby.get_attack_bonus() == 0
    assert far.get_attack_bonus() == 0
    assert [event["type"] for event in events[:3]] == [
        "boss_encounter_started",
        "boss_phase_changed",
        "boss_ability_telegraphed",
    ]
    assert events[2]["ability_id"] == "rally"
    assert events[2]["telegraph_ms"] == 1200

    set_sim_now_ms(3200)
    before_enemy_count = len(enemies)
    system.update(ctx, 1 / 60)

    assert len(enemies) == before_enemy_count + 3
    assert sum(1 for enemy in enemies if getattr(enemy, "enemy_type", "") == "goblin") == 5
    assert events[-1]["type"] == "boss_ability_resolved"
    assert events[-1]["spawned_count"] == 3
    assert events[-1]["nearby_goblin_count"] == 1


def test_boss_defeat_records_memory_and_archives_the_snapshot():
    system = BossEncounterSystem()
    bus, events = _make_bus()
    hero = _Hero(hero_id="wk139_h2", name="Bryn", x=160.0, y=160.0)
    boss = GoblinWarchief(160.0, 160.0)
    boss.register_attacker(hero)
    enemies = [boss]
    ctx = _make_context([hero], enemies, bus)

    set_sim_now_ms(1000)
    system.register_boss(boss, event_bus=bus, now_ms=1000)
    boss.take_damage(999)

    set_sim_now_ms(2000)
    system.update(ctx, 1 / 60)

    assert system.get_active_boss_snapshots() == ()
    assert boss.boss_status == "defeated"
    assert boss.memory_facts[-1]["event"] == "defeated_by"
    assert boss.defeated_by[-1]["hero_id"] == hero.hero_id
    assert boss.defeated_by[-1]["hero_name"] == hero.name
    assert events[-1]["type"] == GameEventType.BOSS_DEFEATED.value
    assert events[-1]["defeated_by_hero_id"] == hero.hero_id
