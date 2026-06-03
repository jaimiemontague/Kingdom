"""WK124-T4a — ClericHealSystem unit tests.

Deterministic: sim time is pinned via ``set_sim_now_ms`` so the per-cleric
cooldown is exercised without wall-clock flakiness. No RNG. Real ``Hero`` +
real ``EventBus`` + real ``ClericHealSystem`` (mirrors tests/test_combat.py's
SystemContext construction pattern).
"""

from __future__ import annotations

import math

import pytest

from config import (
    TILE_SIZE,
    CLERIC_HEAL_AMOUNT,
    CLERIC_HEAL_COOLDOWN_MS,
    CLERIC_HEAL_RADIUS_TILES,
)
from game.entities.hero import Hero
from game.events import EventBus, GameEventType
from game.systems.cleric_heal import ClericHealSystem
from game.systems.protocol import SystemContext
from game.sim.timebase import set_sim_now_ms


@pytest.fixture(autouse=True)
def _pin_sim_clock():
    # Pin a deterministic sim clock for every test; reset afterward.
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(None)


def _make_context(heroes: list, event_bus: EventBus) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=[],
        buildings=[],
        world=object(),
        economy=object(),
        event_bus=event_bus,
    )


def _wounded(hero: Hero, hp: int) -> Hero:
    hero.hp = int(hp)
    return hero


def test_cleric_heals_wounded_warrior_in_range() -> None:
    set_sim_now_ms(1000)
    cleric = Hero(0.0, 0.0, hero_class="cleric", hero_id="c1")
    warrior = _wounded(
        Hero(float(TILE_SIZE), 0.0, hero_class="warrior", hero_id="w1"),
        hp=10,  # 10/60 = 16.7% << 85% threshold
    )
    bus = EventBus()
    sys = ClericHealSystem()

    sys.update(_make_context([cleric, warrior], bus), dt=0.016)

    assert warrior.hp == 10 + CLERIC_HEAL_AMOUNT


def test_cooldown_blocks_second_heal_within_window() -> None:
    set_sim_now_ms(1000)
    cleric = Hero(0.0, 0.0, hero_class="cleric", hero_id="c1")
    warrior = _wounded(
        Hero(float(TILE_SIZE), 0.0, hero_class="warrior", hero_id="w1"), hp=10
    )
    bus = EventBus()
    sys = ClericHealSystem()
    ctx = _make_context([cleric, warrior], bus)

    sys.update(ctx, dt=0.016)
    hp_after_first = warrior.hp
    assert hp_after_first == 10 + CLERIC_HEAL_AMOUNT

    # Still inside the cooldown window -> no second heal.
    set_sim_now_ms(1000 + CLERIC_HEAL_COOLDOWN_MS - 1)
    sys.update(ctx, dt=0.016)
    assert warrior.hp == hp_after_first

    # Cooldown elapsed -> heals again (still below the threshold).
    set_sim_now_ms(1000 + CLERIC_HEAL_COOLDOWN_MS)
    sys.update(ctx, dt=0.016)
    assert warrior.hp == hp_after_first + CLERIC_HEAL_AMOUNT


def test_hero_heal_event_is_emitted() -> None:
    set_sim_now_ms(1000)
    cleric = Hero(0.0, 0.0, hero_class="cleric", hero_id="c1")
    warrior = _wounded(
        Hero(float(TILE_SIZE), 0.0, hero_class="warrior", hero_id="w1"), hp=10
    )
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(GameEventType.HERO_HEAL.value, received.append)
    sys = ClericHealSystem()

    sys.update(_make_context([cleric, warrior], bus), dt=0.016)
    bus.flush()

    assert len(received) == 1
    evt = received[0]
    assert evt["type"] == GameEventType.HERO_HEAL.value
    assert evt["amount"] == CLERIC_HEAL_AMOUNT
    # Healed target position == warrior; source == cleric.
    assert evt["x"] == warrior.x and evt["y"] == warrior.y
    assert evt["from_x"] == cleric.x and evt["from_y"] == cleric.y


def test_out_of_range_ally_is_not_healed() -> None:
    set_sim_now_ms(1000)
    cleric = Hero(0.0, 0.0, hero_class="cleric", hero_id="c1")
    # Just outside the heal radius.
    far_x = float(TILE_SIZE) * (CLERIC_HEAL_RADIUS_TILES + 1)
    warrior = _wounded(
        Hero(far_x, 0.0, hero_class="warrior", hero_id="w1"), hp=10
    )
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(GameEventType.HERO_HEAL.value, received.append)
    sys = ClericHealSystem()

    sys.update(_make_context([cleric, warrior], bus), dt=0.016)
    bus.flush()

    assert warrior.hp == 10  # unchanged
    assert received == []  # no event
    # No cooldown was consumed either (no heal happened).
    assert int(cleric._heal_cooldown_until_ms) == 0


def test_full_hp_ally_is_not_healed() -> None:
    set_sim_now_ms(1000)
    cleric = Hero(0.0, 0.0, hero_class="cleric", hero_id="c1")
    warrior = Hero(float(TILE_SIZE), 0.0, hero_class="warrior", hero_id="w1")
    assert warrior.health_percent == 1.0  # full HP, above the 0.85 threshold
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(GameEventType.HERO_HEAL.value, received.append)
    sys = ClericHealSystem()

    sys.update(_make_context([cleric, warrior], bus), dt=0.016)
    bus.flush()

    assert warrior.hp == warrior.max_hp  # unchanged
    assert received == []
    assert int(cleric._heal_cooldown_until_ms) == 0
