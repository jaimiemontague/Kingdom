"""WK139 boss memory record tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.entities.enemy import GoblinWarchief
from game.sim.contracts import BossMemorySummary
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str = "wk139_h3", name: str = "Cira", x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True


def _make_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def _make_context(hero: _Hero, boss, bus) -> SystemContext:
    return SystemContext(
        heroes=[hero],
        enemies=[boss],
        buildings=[],
        world=object(),
        economy=object(),
        event_bus=bus,
        castle=None,
    )


def _assert_primitive_record(record: dict[str, object]) -> None:
    assert isinstance(record, dict)
    assert set(record) >= {"event", "hero_id", "hero_name", "detail", "time_ms"}
    for value in record.values():
        assert isinstance(value, (str, int, float, bool, tuple, type(None)))


def test_boss_memory_facts_are_primitive_and_snapshot_ready():
    system = BossEncounterSystem()
    bus, events = _make_bus()
    hero = _Hero(hero_id="wk139_h3", name="Cira", x=160.0, y=160.0)
    boss = GoblinWarchief(160.0, 160.0)
    ctx = _make_context(hero, boss, bus)

    set_sim_now_ms(1000)
    system.register_boss(boss, event_bus=bus, now_ms=1000)

    killed = system.record_killed_hero(boss, hero, detail="crushed a scout", now_ms=1500)
    _assert_primitive_record(killed)
    assert killed["event"] == "killed_hero"
    assert boss.killed_hero[0]["detail"] == "crushed a scout"

    snapshot = system.get_active_boss_snapshots()[0]
    assert isinstance(snapshot.memory_summaries[0], BossMemorySummary)
    assert snapshot.memory_summaries[0].event == "killed_hero"
    assert snapshot.memory_summaries[0].hero_id == hero.hero_id
    assert snapshot.memory_summaries[0].at_ms == 1500

    defeated = system.record_defeated_by(
        boss,
        hero,
        detail="held the line",
        now_ms=2000,
        event_bus=bus,
        ctx=ctx,
    )
    _assert_primitive_record(defeated)
    assert defeated["event"] == "defeated_by"
    assert system.get_active_boss_snapshots() == ()
    assert boss.memory_facts[0]["event"] == "killed_hero"
    assert boss.memory_facts[1]["event"] == "defeated_by"
    assert boss.defeated_by[0]["hero_id"] == hero.hero_id
    assert boss.defeated_by[0]["hero_name"] == hero.name
    assert events[-1]["type"] == "boss_defeated"
    assert events[-1]["defeated_by_hero_id"] == hero.hero_id
