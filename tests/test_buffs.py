from __future__ import annotations

from game.events import EventBus
from game.systems.buffs import BuffSystem
from game.systems.protocol import SystemContext


def _make_context(*, heroes: list, buildings: list) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=[],
        buildings=buildings,
        world=object(),
        economy=object(),
        event_bus=EventBus(),
    )


def test_buff_applied_when_hero_in_royal_gardens_range(make_hero, make_building, monkeypatch) -> None:
    now = {"value": 1000}
    monkeypatch.setattr("game.systems.buffs.sim_now_ms", lambda: now["value"])
    system = BuffSystem()
    hero = make_hero(name="AuraTarget")
    gardens = make_building(building_type="royal_gardens", hp=200)
    gardens.buff_attack_bonus = 3
    gardens.buff_defense_bonus = 2
    gardens.buff_duration = 1.25
    gardens.get_heroes_in_range = lambda heroes: list(heroes)
    ctx = _make_context(heroes=[hero], buildings=[gardens])

    system.update(ctx, dt=0.016)

    assert len(hero.buffs) == 1
    assert hero.buffs[0]["name"] == "royal_gardens_aura"
    assert hero.buffs[0]["atk_delta"] == 3
    assert hero.buffs[0]["def_delta"] == 2


def test_buff_expires_after_duration_when_out_of_range(make_hero, make_building, monkeypatch) -> None:
    now = {"value": 1000}
    monkeypatch.setattr("game.systems.buffs.sim_now_ms", lambda: now["value"])
    system = BuffSystem()
    hero = make_hero(name="Expires")
    gardens = make_building(building_type="royal_gardens", hp=200)
    gardens.buff_attack_bonus = 1
    gardens.buff_defense_bonus = 1
    gardens.buff_duration = 1.25
    gardens.get_heroes_in_range = lambda heroes: list(heroes)

    system.update(_make_context(heroes=[hero], buildings=[gardens]), dt=0.016)
    assert len(hero.buffs) == 1

    now["value"] = 2600
    system.update(_make_context(heroes=[hero], buildings=[]), dt=0.016)

    assert hero.buffs == []


def test_buff_refreshes_instead_of_stacking(make_hero, make_building, monkeypatch) -> None:
    now = {"value": 1000}
    monkeypatch.setattr("game.systems.buffs.sim_now_ms", lambda: now["value"])
    system = BuffSystem()
    hero = make_hero(name="Refresh")
    gardens = make_building(building_type="royal_gardens", hp=200)
    gardens.buff_attack_bonus = 2
    gardens.buff_defense_bonus = 1
    gardens.buff_duration = 1.25
    gardens.get_heroes_in_range = lambda heroes: list(heroes)
    ctx = _make_context(heroes=[hero], buildings=[gardens])

    system.update(ctx, dt=0.016)
    first_expiry = int(hero.buffs[0]["expires_at_ms"])
    now["value"] = 1400
    system.update(ctx, dt=0.016)
    second_expiry = int(hero.buffs[0]["expires_at_ms"])

    assert len(hero.buffs) == 1
    assert second_expiry > first_expiry
