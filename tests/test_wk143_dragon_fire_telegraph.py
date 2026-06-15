"""WK143 Ashwing fire telegraph gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.bosses import ASHWING_BOSS_DEF
from game.entities.enemy import Dragon
from game.entities.hero import Hero
from game.events import GameEventType
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def _recording_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def _make_context(hero_front: Hero, hero_side: Hero, boss: Dragon, bus) -> SystemContext:
    return SystemContext(
        heroes=[hero_front, hero_side],
        enemies=[boss],
        buildings=[],
        world=object(),
        economy=object(),
        event_bus=bus,
        castle=None,
    )


def test_ashwing_fire_telegraph_emits_warning_before_cone_damage():
    boss_system = BossEncounterSystem()
    bus, events = _recording_bus()

    boss = Dragon(320.0, 320.0)
    hero_front = Hero(384.0, 320.0, hero_class="warrior", hero_id="wk143_front", name="Front")
    hero_side = Hero(320.0, 384.0, hero_class="warrior", hero_id="wk143_side", name="Side")
    boss.target = hero_front
    ctx = _make_context(hero_front, hero_side, boss, bus)

    set_sim_now_ms(1_000)
    boss_system.register_boss(boss, boss_def=ASHWING_BOSS_DEF, event_bus=bus, now_ms=1_000)
    assert boss.current_boss_phase == "sleeping_hoard"
    assert boss.latest_telegraph == ""

    boss.hp = 450
    set_sim_now_ms(1_100)
    boss_system.update(ctx, 1 / 60)

    assert boss.current_boss_phase == "air_and_fire"
    assert boss.current_boss_ability_id == "ashwing_fire_breath"
    assert boss.latest_telegraph == ""
    assert events[-1]["type"] == GameEventType.BOSS_PHASE_CHANGED.value

    set_sim_now_ms(1_100)
    boss_system.update(ctx, 1 / 60)

    assert boss.latest_telegraph == "fire_breath"
    assert boss_system.get_active_boss_snapshots()[0].latest_telegraph == "fire_breath"
    assert events[-1]["type"] == GameEventType.BOSS_ABILITY_TELEGRAPHED.value

    telegraph_event = events[-1]
    assert telegraph_event["ability_id"] == "ashwing_fire_breath"
    assert telegraph_event["ability_name"] == "Fire Breath"
    assert telegraph_event["warning_event"] == "dragon_fire_telegraph"
    assert telegraph_event["shape"] == "cone"
    assert telegraph_event["range_tiles"] == 9.0
    assert telegraph_event["angle_degrees"] == 60.0
    assert telegraph_event["target_hero_id"] == hero_front.hero_id
    assert telegraph_event["target_hero_name"] == hero_front.name

    assert hero_front.hp == hero_front.max_hp
    assert hero_side.hp == hero_side.max_hp

    set_sim_now_ms(2_499)
    boss_system.update(ctx, 1 / 60)
    assert events[-1]["type"] == GameEventType.BOSS_ABILITY_TELEGRAPHED.value
    assert hero_front.hp == hero_front.max_hp
    assert hero_side.hp == hero_side.max_hp

    front_hp_before = hero_front.hp
    expected_damage = max(1, 24 - hero_front.defense)
    set_sim_now_ms(2_500)
    boss_system.update(ctx, 1 / 60)

    assert events[-1]["type"] == GameEventType.BOSS_ABILITY_RESOLVED.value
    resolve_event = events[-1]
    assert resolve_event["impact_event"] == "dragon_fire_impact"
    assert resolve_event["damage"] == 24
    assert resolve_event["hit_count"] == 1
    assert resolve_event["hit_hero_ids"] == (hero_front.hero_id,)
    assert resolve_event["killed_hero_ids"] == ()
    assert resolve_event["target_hero_id"] == hero_front.hero_id
    assert hero_front.hp == front_hp_before - expected_damage
    assert hero_front.scorched is True
    assert hero_front.scorched_at_ms == 2_500
    assert hero_side.hp == hero_side.max_hp
    assert not hasattr(hero_side, "scorched")
