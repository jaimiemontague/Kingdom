"""WK143 Ashwing's Hoard gameplay progression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import TILE_SIZE
from game.content.bosses import ASHWING_BOSS_DEF
from game.content.quest_chains import ASHWINGS_HOARD, CLAIM_HOARD, PREPARE_HUNT, SCOUT_DRAGON_CAVE, SLAY_ASHWING
from game.entities.enemy import Dragon
from game.entities.hero import Hero
from game.entities.poi import POI_DEFINITIONS, PointOfInterest
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def _recording_bus():
    events: list[dict] = []
    return SimpleNamespace(emit=events.append), events


def _make_context(hero: Hero, cave: PointOfInterest, shrine: PointOfInterest, bus) -> SystemContext:
    return SystemContext(
        heroes=[hero],
        enemies=[],
        buildings=[],
        world=object(),
        economy=object(),
        event_bus=bus,
        pois=[cave, shrine],
        castle=None,
    )


def test_ashwings_hoard_chain_unfolds_from_scout_to_claim_and_spawns_named_boss():
    quest_system = QuestChainSystem()
    boss_system = BossEncounterSystem()
    bus, events = _recording_bus()

    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="wk143_hero", name="Astra")
    hero.add_gold = lambda amount: setattr(hero, "gold", hero.gold + int(amount))
    cave = PointOfInterest(20, 12, POI_DEFINITIONS["poi_dragon_cave"])
    shrine = PointOfInterest(18, 12, POI_DEFINITIONS["poi_shrine"])
    ctx = _make_context(hero, cave, shrine, bus)

    set_sim_now_ms(1_000)
    chain = quest_system.start_ashwings_hoard(ctx=ctx, hero=hero, event_bus=bus, now_ms=1_000)

    assert chain.chain_type == ASHWINGS_HOARD.chain_type
    assert chain.status == "active"
    assert chain.current_phase_id == SCOUT_DRAGON_CAVE

    hero.x = float(cave.center_x)
    hero.y = float(cave.center_y)
    set_sim_now_ms(1_100)
    quest_system.update(ctx, 1 / 60)

    assert chain.current_phase_id == PREPARE_HUNT
    assert chain.facts["dragon_cave_scouted"] is True
    assert chain.facts["boss_target_revealed"] is True
    assert len(ctx.enemies) == 1

    boss = ctx.enemies[0]
    assert isinstance(boss, Dragon)
    assert boss.name == "Ashwing the Red"
    assert boss.boss_def is ASHWING_BOSS_DEF

    boss_system.update(ctx, 1 / 60)
    boss_snapshots = boss_system.get_active_boss_snapshots()
    assert len(boss_snapshots) == 1
    assert boss_snapshots[0].name == "Ashwing the Red"
    assert boss_snapshots[0].current_phase_title == "Sleeping Hoard"

    hero.x = float(shrine.center_x)
    hero.y = float(shrine.center_y)
    set_sim_now_ms(1_200)
    quest_system.update(ctx, 1 / 60)

    assert chain.current_phase_id == SLAY_ASHWING
    assert chain.facts["prep_target_prepared"] is True
    assert chain.facts["boss_target_weakness_known"] is True

    boss.take_damage(999)
    set_sim_now_ms(1_300)
    boss_system.update(ctx, 1 / 60)
    assert boss_system.get_active_boss_snapshots() == ()
    assert boss_system.defeated_bosses == [boss]

    quest_system.update(ctx, 1 / 60)
    assert chain.current_phase_id == CLAIM_HOARD
    assert chain.facts["boss_target_defeated"] is True

    hero.x = float(cave.center_x)
    hero.y = float(cave.center_y)
    set_sim_now_ms(1_400)
    quest_system.update(ctx, 1 / 60)

    assert chain.status == "completed"
    assert chain.completed_at_ms == 1_400
    assert hero.gold == ASHWINGS_HOARD.reward_profile.gold
    assert hero.taxed_gold == 0

